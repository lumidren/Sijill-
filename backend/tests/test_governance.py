from datetime import date, datetime, timedelta, timezone

import pytest

from app.governance import dpia_screening, heat_map, risk_level
from app.models import Risk

TODAY = date.today()


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


# ------------------------------------------------------------------ pure rules

@pytest.mark.parametrize("score,level", [(1, "low"), (4, "low"), (5, "medium"), (9, "medium"), (10, "high"),
                                         (16, "high"), (20, "critical"), (25, "critical")])
def test_risk_bands(score, level):
    assert risk_level(score) == level


def test_heat_map_counts_open_risks_by_impact_and_likelihood():
    risks = [Risk(likelihood=5, impact=4, status="open"), Risk(likelihood=5, impact=4, status="treating"),
             Risk(likelihood=1, impact=1, status="closed"),
             Risk(likelihood=4, impact=4, residual_likelihood=2, residual_impact=2, status="open")]
    grid = heat_map(risks)
    assert grid[3][4] == 2 and grid[0][0] == 0 and grid[3][3] == 1
    assert heat_map(risks, residual=True)[1][1] == 1


def test_dpia_screening_rule_of_thumb():
    assert dpia_screening({"sensitive_data": True})["likely_needed"] is False
    r = dpia_screening({"sensitive_data": True, "cross_border": True, "large_scale": False})
    assert r["likely_needed"] is True and r["count"] == 2 and r["complete"] is False


# ------------------------------------------------------------------ tasks

def test_task_lifecycle_and_overdue(as_role):
    c = as_role("it")
    t = c.post("/api/tasks", json={"title": "Enable MFA for reception-kiosk", "requirement_id": "a06-05",
                                   "source": "gap", "due_on": d(-2), "priority": "high"}).json()
    assert t["overdue"] is True and t["requirement_label"] == "A06.05" and t["days_left"] == -2
    done = c.put(f"/api/tasks/{t['id']}", json={**{k: t[k] for k in ("title", "requirement_id", "source", "priority")},
                                               "status": "done", "due_on": d(-2)}).json()
    assert done["status"] == "done" and done["completed_at"] and done["overdue"] is False
    assert c.post("/api/tasks", json={"title": "x", "requirement_id": "zz-99"}).status_code == 422
    assert as_role("auditor").post("/api/tasks", json={"title": "x"}).status_code == 403


# ------------------------------------------------------------------ risks

RISK = {"title": "Patient scans exposed by misconfigured storage", "likelihood": 4, "impact": 5,
        "residual_likelihood": 2, "residual_impact": 5, "requirement_ids": ["a06-06"], "review_due": d(60)}


def test_risk_scoring_and_acceptance_rules(as_role):
    c = as_role("dpo")
    r = c.post("/api/risks", json=RISK).json()
    assert (r["score"], r["level"], r["residual_score"], r["residual_level"]) == (20, "critical", 10, "high")
    # only an Admin can accept, never in the past, never longer than the configured maximum
    assert c.post(f"/api/risks/{r['id']}/accept", json={"note": "Business decision", "expires_on": d(90)}).status_code == 403
    a = as_role("admin")
    assert a.post(f"/api/risks/{r['id']}/accept", json={"note": "Business decision", "expires_on": d(-1)}).status_code == 422
    assert a.post(f"/api/risks/{r['id']}/accept", json={"note": "Business decision", "expires_on": d(800)}).status_code == 422
    ok = a.post(f"/api/risks/{r['id']}/accept", json={"note": "Accepted until the migration ends", "expires_on": d(90)}).json()
    assert ok["status"] == "accepted" and ok["acceptance_expires_on"] == d(90)
    # editing the facts withdraws the acceptance
    edited = as_role("dpo").put(f"/api/risks/{r['id']}", json={**RISK, "likelihood": 5}).json()
    assert edited["status"] == "open" and edited["accepted_at"] is None
    assert c.post("/api/risks", json={**RISK, "likelihood": 6}).status_code == 422
    assert c.post("/api/risks", json={**RISK, "status": "accepted"}).status_code == 422


def test_expired_acceptance_is_flagged(as_role, db):
    from app.governance import risk_out
    r = Risk(title="x", likelihood=2, impact=2, status="accepted",
             acceptance_expires_on=datetime.now(timezone.utc) - timedelta(days=1))
    assert risk_out(r, datetime.now(timezone.utc))["acceptance_expired"] is True


# ------------------------------------------------------------------ data subject requests

def test_request_clock_uses_configured_days(as_role, monkeypatch):
    from app.config import get_settings
    c = as_role("dpo")
    received = (datetime.now(timezone.utc) - timedelta(days=25)).isoformat()
    r = c.post("/api/requests", json={"request_type": "access", "requester": "Patient #4471", "received_at": received}).json()
    assert r["ref"].startswith("DSR-") and r["state"] == "due_soon" and r["response_days"] == 30
    monkeypatch.setattr(get_settings(), "dsr_response_days", 20)
    again = c.get(f"/api/requests/{r['id']}").json()
    assert again["state"] == "overdue"
    done = c.put(f"/api/requests/{r['id']}", json={"request_type": "access", "requester": "Patient #4471",
                                                    "received_at": received, "status": "completed",
                                                    "identity_verified": True}).json()
    assert done["state"] == "late" and done["completed_at"]
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert c.post("/api/requests", json={"request_type": "access", "requester": "x", "received_at": future}).status_code == 422
    assert c.post("/api/requests", json={"request_type": "telepathy", "requester": "x", "received_at": received}).status_code == 422
    assert as_role("it").post("/api/requests", json={"request_type": "access", "requester": "x", "received_at": received}).status_code == 403


# ------------------------------------------------------------------ vendors

def test_vendor_issues(as_role):
    c = as_role("dpo")
    v = c.post("/api/vendors", json={"name": "SupportCo", "role": "processor", "countries": ["Egypt", " ", "India"],
                                     "next_review_on": d(-5)}).json()
    assert set(v["issues"]) == {"no_dpa", "no_due_diligence", "review_overdue", "cross_border"}
    assert v["countries"] == ["Egypt", "India"]
    fixed = c.put(f"/api/vendors/{v['id']}", json={"name": "SupportCo", "role": "processor", "countries": ["Egypt"],
                                                    "dpa_signed": True, "dpa_signed_on": d(-1), "due_diligence_on": d(-1),
                                                    "next_review_on": d(300)}).json()
    assert fixed["issues"] == []


# ------------------------------------------------------------------ DPIAs

def test_dpia_approval_flow(as_role, db):
    from app.models import ProcessingActivity
    db.add(ProcessingActivity(name="Patient records"))
    db.commit()
    act = db.query(ProcessingActivity).first().id
    c = as_role("dpo")
    body = {"title": "EHR in the cloud", "activity_id": act, "screening": {"sensitive_data": True, "cross_border": True},
            "status": "draft"}
    p = c.post("/api/dpias", json=body).json()
    assert p["screening_result"]["likely_needed"] is True and p["activity_name"] == "Patient records"
    a = as_role("admin")
    assert a.post(f"/api/dpias/{p['id']}/approve").status_code == 409  # still a draft
    c = as_role("dpo")
    c.put(f"/api/dpias/{p['id']}", json={**body, "status": "in_review"})
    a = as_role("admin")
    assert a.post(f"/api/dpias/{p['id']}/approve").status_code == 422  # no opinion or residual risk yet
    c = as_role("dpo")
    c.put(f"/api/dpias/{p['id']}", json={**body, "status": "in_review", "dpo_opinion": "Proceed with encryption.",
                                        "residual_risk": "medium"})
    assert as_role("dpo").post(f"/api/dpias/{p['id']}/approve").status_code == 403
    ok = as_role("admin").post(f"/api/dpias/{p['id']}/approve").json()
    assert ok["status"] == "approved" and ok["approved_at"]
    assert as_role("dpo").post("/api/dpias", json={**body, "screening": {"astrology": True}}).status_code == 422
    assert as_role("dpo").post("/api/dpias", json={**body, "activity_id": 999}).status_code == 422


# ------------------------------------------------------------------ policies

def test_policy_versions_and_approval(as_role):
    c = as_role("dpo")
    p = c.post("/api/policies", json={"title": "Data protection policy", "version": "1.2", "review_due": d(-3),
                                      "requirement_ids": ["a01-03"]}).json()
    assert p["status"] == "draft" and len(p["history"]) == 1
    ok = as_role("admin").post(f"/api/policies/{p['id']}/approve").json()
    assert ok["status"] == "approved" and ok["review_overdue"] is True and len(ok["history"]) == 2
    c = as_role("dpo")
    same = c.put(f"/api/policies/{p['id']}", json={"title": "Data protection policy (typo fixed)", "version": "1.2",
                                                     "review_due": d(-3), "requirement_ids": ["a01-03"]}).json()
    assert same["status"] == "approved" and same["approved_on"] is not None and len(same["history"]) == 2
    v2 = c.put(f"/api/policies/{p['id']}", json={"title": "Data protection policy", "version": "1.3",
                                                   "review_due": d(365), "requirement_ids": ["a01-03"]}).json()
    assert v2["status"] == "draft" and v2["approved_on"] is None and v2["history"][-1]["version"] == "1.3"
    assert c.post("/api/policies", json={"title": "x", "version": "1 2"}).status_code == 422
    assert c.post("/api/policies", json={"title": "x", "version": "1", "status": "approved"}).status_code == 422


def test_writes_are_audited_and_summary(as_role):
    c = as_role("dpo")
    c.post("/api/risks", json=RISK)
    c.post("/api/vendors", json={"name": "NoDpaCo", "role": "processor"})
    s = c.get("/api/governance/summary").json()
    assert s["risks"]["by_level"] == {"critical": 1} and s["vendors"]["without_dpa"] == 1
    actions = {i["action"] for i in as_role("admin").get("/api/audit").json()["items"]}
    assert {"risk.create", "vendor.create"} <= actions


@pytest.mark.parametrize("path", ["/api/tasks", "/api/risks", "/api/requests", "/api/vendors", "/api/dpias", "/api/policies"])
def test_auditor_reads_every_module(as_role, path):
    assert as_role("auditor").get(path).status_code == 200
