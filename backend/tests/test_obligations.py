from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Obligation, Reminder
from app.obligations_service import (
    _days, default_expiry, effective_status, evaluate_applicability, evaluate_licensing, generate_reminders,
    upcoming_deadlines,
)

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)


def test_licensing_results_say_likely_only():
    r = evaluate_licensing({"controls_processing": True, "processes_for_others": False, "cross_border": True,
                            "electronic_marketing": None, "surveillance": False, "sensitive_data": True})
    by = {x["key"]: x["likely_required"] for x in r["results"]}
    assert by == {"controller_licence": True, "processor_licence": False, "cross_border_permit": True,
                  "marketing_permit": None, "surveillance_permit": False}
    assert r["notes"] == ["sensitive_data_conditions"] and r["complete"] is False


@pytest.mark.parametrize("answers,result,reason", [
    ({}, "incomplete", None),
    ({"processes_personal_data": False, "cbe_supervised": False}, "likely_out_of_scope", "no_personal_data"),
    ({"processes_personal_data": True, "cbe_supervised": True, "money_transfer_or_exchange": False},
     "likely_out_of_scope", "cbe_supervised"),
    ({"processes_personal_data": True, "cbe_supervised": True, "money_transfer_or_exchange": True},
     "likely_in_scope", "cbe_exception"),
    ({"processes_personal_data": True, "cbe_supervised": True}, "incomplete", None),
    ({"processes_personal_data": True, "cbe_supervised": False}, "likely_in_scope", "processes_personal_data"),
])
def test_applicability_screener(answers, result, reason):
    assert evaluate_applicability(answers) == {"result": result, "reason": reason}


def test_default_licence_expiry_uses_configuration(monkeypatch):
    from app.config import get_settings
    issued = datetime(2024, 2, 29, 12, tzinfo=timezone.utc)
    assert default_expiry("licence", issued) == datetime(2027, 2, 28, 12, tzinfo=timezone.utc)  # leap day
    monkeypatch.setattr(get_settings(), "licence_validity_years", 5)
    assert default_expiry("licence", issued).year == 2029
    assert default_expiry("permit", issued) is None


def test_expired_status_is_computed_not_stored():
    o = Obligation(kind="permit", title="x", status="active", expires_on=NOW - timedelta(days=1))
    assert effective_status(o, NOW) == "expired" and o.status == "active"


def test_reminders_window_and_idempotence(db):
    db.add_all([
        Obligation(kind="permit", title="soon", status="active", expires_on=NOW + timedelta(days=30)),
        Obligation(kind="permit", title="far", status="active", expires_on=NOW + timedelta(days=200)),
        Obligation(kind="permit", title="missed", status="active", expires_on=NOW - timedelta(days=3)),
        Obligation(kind="permit", title="dropped", status="not_needed", expires_on=NOW + timedelta(days=5)),
        Obligation(kind="consent_mechanism", title="review", status="active", review_due=NOW + timedelta(days=2)),
    ])
    db.commit()
    assert generate_reminders(db, NOW) == 3
    assert generate_reminders(db, NOW) == 0  # no duplicates
    deadlines = upcoming_deadlines(db, NOW)
    assert [d["title"] for d in deadlines] == ["missed", "review", "soon"]
    assert deadlines[0]["days_left"] == -3


def test_deadline_days_across_midnight():
    # Deadlines are calendar dates; "today" is the calendar day in Africa/Cairo (UTC+2 in December).
    due = datetime(2026, 12, 2, 12, tzinfo=timezone.utc)
    assert _days(due, datetime(2026, 12, 1, 21, 30, tzinfo=timezone.utc)) == 1  # 23:30 Cairo, 1 Dec
    assert _days(due, datetime(2026, 12, 1, 23, 30, tzinfo=timezone.utc)) == 0  # 01:30 Cairo, 2 Dec
    assert _days(due, datetime(2026, 12, 2, 0, 5, tzinfo=timezone.utc)) == 0
    assert _days(due, datetime(2026, 12, 3, 0, 5, tzinfo=timezone.utc)) == -1


def test_api_questionnaires_and_tracking(as_role):
    c = as_role("dpo")
    q = c.get("/api/obligations/questionnaires").json()
    assert q["applicability"]["result"] == "incomplete" and q["licence_validity_years"] == 3
    r = c.put("/api/obligations/questionnaires/licensing",
              json={"answers": {"controls_processing": True, "surveillance": True}})
    likely = {x["key"] for x in r.json()["results"] if x["likely_required"]}
    assert likely == {"controller_licence", "surveillance_permit"}
    assert c.put("/api/obligations/questionnaires/licensing", json={"answers": {"invented": True}}).status_code == 422
    r = c.put("/api/obligations/questionnaires/applicability",
              json={"answers": {"processes_personal_data": True, "cbe_supervised": False}})
    assert r.json()["result"] == "likely_in_scope"
    # a licence without an expiry gets the configured default validity
    ob = c.post("/api/obligations", json={"kind": "licence", "title": "Controller licence", "status": "active",
                                          "issued_on": "2026-01-20"}).json()
    assert ob["expires_on"] == "2029-01-20" and ob["expiry_from_default"] is True
    from app.db import local_date, utcnow

    soon = (local_date(utcnow()) + timedelta(days=10)).isoformat()  # Cairo's date, as the app counts it
    p = c.post("/api/obligations", json={"kind": "permit", "title": "CCTV permit", "status": "active",
                                         "issued_on": "2025-12-01", "expires_on": soon}).json()
    assert p["expiry_from_default"] is False and 9 <= p["days_to_expiry"] <= 10
    rem = c.get("/api/obligations/reminders").json()
    assert any(x["obligation"]["title"] == "CCTV permit" for x in rem)
    assert c.post(f"/api/obligations/reminders/{rem[0]['id']}/dismiss").json() == {"ok": True}
    assert len(c.get("/api/obligations/reminders").json()) == len(rem) - 1
    dash = c.get("/api/posture/dashboard").json()
    assert dash["features"]["obligations"] is True and dash["deadlines"][0]["title"] == "CCTV permit"
    bad = c.post("/api/obligations", json={"kind": "permit", "title": "x", "issued_on": "2026-05-01",
                                           "expires_on": "2026-01-01"})
    assert bad.status_code == 422
    assert c.post("/api/obligations", json={"kind": "spaceship", "title": "x"}).status_code == 422


@pytest.mark.parametrize("role", ["it", "auditor"])
def test_only_admin_and_dpo_manage_obligations(as_role, role):
    c = as_role(role)
    assert c.get("/api/obligations").status_code == 200
    assert c.post("/api/obligations", json={"kind": "permit", "title": "x"}).status_code == 403
    assert c.put("/api/obligations/questionnaires/licensing", json={"answers": {}}).status_code == 403


def test_scheduler_generates_reminders(db, monkeypatch):
    from app import scheduler
    db.add(Obligation(kind="permit", title="soon", status="active",
                      expires_on=datetime.now(timezone.utc) + timedelta(days=3)))
    db.commit()
    monkeypatch.setattr("app.evidence.adapters.adapters", lambda: [])
    scheduler.collect_once()
    db.expire_all()
    assert db.query(Reminder).count() == 1
