from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.incidents_service import clock, clocks, parse_when
from app.models import Incident

UTC = timezone.utc
CAIRO = ZoneInfo("Africa/Cairo")


def inc(hours_ago: float, **kw) -> Incident:
    now = datetime.now(UTC)
    return Incident(title="t", discovered_at=now - timedelta(hours=hours_ago), **kw)


def test_incident_70_hours_old_has_two_hours_left_and_is_urgent():
    c = clocks(inc(70))["regulator"]
    assert c["state"] == "urgent"
    assert 2 * 3600 - 60 <= c["seconds_left"] <= 2 * 3600


@pytest.mark.parametrize("hours_ago,state", [(1, "running"), (50, "warning"), (61, "urgent"), (72.1, "overdue"), (100, "overdue")])
def test_escalation_states(hours_ago, state):
    assert clocks(inc(hours_ago))["regulator"]["state"] == state


def test_notified_on_time_late_and_not_needed():
    now = datetime.now(UTC)
    i = inc(80, regulator_notified_at=now - timedelta(hours=20), individuals_notice_needed=False)
    c = clocks(i)
    assert c["regulator"]["state"] == "met"  # notified at 60h, before the 72h deadline
    assert c["individuals"]["state"] == "not_needed"
    late = clocks(inc(80, regulator_notified_at=now - timedelta(hours=1)))
    assert late["regulator"]["state"] == "met_late"


def test_deadline_hours_are_configuration(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "breach_regulator_hours", 24)
    assert clocks(inc(23))["regulator"]["state"] == "urgent"
    assert clocks(inc(25))["regulator"]["state"] == "overdue"


def test_naive_input_is_cairo_time_and_deadline_crosses_midnight():
    d = parse_when("2026-11-15T23:30")  # Cairo is UTC+2 in November
    assert d == datetime(2026, 11, 15, 21, 30, tzinfo=UTC)
    due = datetime.fromisoformat(clock(d + timedelta(hours=72), None, d)["due"])
    assert due.astimezone(CAIRO).strftime("%Y-%m-%d %H:%M") == "2026-11-18 23:30"
    assert parse_when("2026-11-15T23:30:00+00:00") == datetime(2026, 11, 15, 23, 30, tzinfo=UTC)


def test_deadline_across_the_daylight_saving_change():
    # Egypt leaves summer time at the end of October 2026: 72 real hours, not 72 wall-clock hours.
    d = parse_when("2026-10-29T12:00")  # UTC+3 (summer time)
    assert d == datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    due = d + timedelta(hours=72)
    assert due.astimezone(CAIRO).strftime("%m-%d %H:%M") == "11-01 11:00"  # UTC+2 after the change


def _new(c, **kw):
    body = {"title": "Lost laptop", "discovered_at": (datetime.now(UTC) - timedelta(hours=70)).isoformat(),
            "data_categories": ["Contact details"], "affected_count": 50, **kw}
    return c.post("/api/incidents", json=body)


def test_api_lifecycle_and_timeline(as_role):
    c = as_role("it")
    r = _new(c)
    assert r.status_code == 201
    i = r.json()
    assert i["ref"].startswith("INC-") and i["clocks"]["regulator"]["state"] == "urgent"
    assert i["events"][0]["kind"] == "created"
    r = c.post(f"/api/incidents/{i['id']}/events", json={"kind": "status", "status": "contained", "text": "Laptop wiped remotely"})
    assert r.json()["status"] == "contained"
    r = c.post(f"/api/incidents/{i['id']}/notified", json={"target": "regulator"})
    body = r.json()
    assert body["status"] == "notified" and body["clocks"]["regulator"]["state"] == "met"
    assert [e["kind"] for e in body["events"]] == ["created", "status", "notified_regulator"]
    dash = c.get("/api/posture/dashboard").json()
    assert dash["features"]["incidents"] is True
    assert dash["breaches"][0]["regulator_done"] is True and dash["breaches"][0]["individuals_state"] == "running"  # 144 h default


def test_overdue_incident_shows_on_dashboard(as_role):
    c = as_role("dpo")
    _new(c, discovered_at=(datetime.now(UTC) - timedelta(hours=80)).isoformat())
    b = c.get("/api/posture/dashboard").json()["breaches"][0]
    assert b["regulator_state"] == "overdue"


def test_validation(as_role):
    c = as_role("dpo")
    assert _new(c, discovered_at=(datetime.now(UTC) + timedelta(hours=2)).isoformat()).status_code == 422
    assert _new(c, discovered_at="yesterday-ish").status_code == 422
    assert _new(c, affected_count=-5).status_code == 422
    i = _new(c).json()
    early = (datetime.now(UTC) - timedelta(hours=100)).isoformat()
    assert c.post(f"/api/incidents/{i['id']}/notified", json={"target": "regulator", "at": early}).status_code == 422
    assert c.post(f"/api/incidents/{i['id']}/events", json={"kind": "note", "text": " "}).status_code == 422
    assert c.get("/api/incidents/999").status_code == 404


def test_auditor_reads_but_cannot_write(as_role):
    i = _new(as_role("dpo")).json()
    c = as_role("auditor")
    assert c.get(f"/api/incidents/{i['id']}").status_code == 200
    assert _new(c).status_code == 403
    assert c.post(f"/api/incidents/{i['id']}/notified", json={"target": "regulator"}).status_code == 403


@pytest.mark.parametrize("target", ["regulator", "individuals"])
@pytest.mark.parametrize("lang", ["en", "ar"])
def test_notice_templates_fill_from_the_incident(as_role, target, lang):
    c = as_role("dpo")
    i = _new(c, description="A laptop with client files was stolen.", measures_taken="Remote wipe.").json()
    n = c.get(f"/api/incidents/{i['id']}/notice?target={target}&lang={lang}").json()
    assert n["subject"] and n["note"]
    assert "A laptop with client files was stolen." in n["body"]
    assert ("Contact details" in n["body"])
    assert n["missing_fields"] > 0  # blanks are marked, never invented
    if target == "regulator":
        assert "50" in n["body"] or "٥٠" in n["body"]
    pdf = c.get(f"/api/incidents/{i['id']}/notice?target={target}&lang={lang}&fmt=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")


def test_demo_has_an_open_breach_with_running_clock(app_client, db):
    from app.demo import DEMO_PASSWORD, seed_demo
    seed_demo(reset=True)
    app_client.post("/api/auth/login", json={"username": "auditor", "password": DEMO_PASSWORD})
    incidents = app_client.get("/api/incidents").json()
    assert len(incidents) == 1
    clk = incidents[0]["clocks"]["regulator"]
    assert clk["state"] == "running" and 40 * 3600 < clk["seconds_left"] < 42 * 3600
    assert incidents[0]["source"]["check_id"] == "s3_bucket_public_access"
