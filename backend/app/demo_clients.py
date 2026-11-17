"""Two more fictional clients, so the demo shows a consultant's portfolio.

Nour Family Clinic (organisation 1) is the detailed demo. These two are lighter and differ on
purpose: Delta Pharmacies is fully self-assessed but has no automated evidence; Sphinx Dental
Centre has barely started. Neither organisation exists.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from .db import org_session, utcnow
from .models import Answer, AppSetting, DataRequest, Organisation, Risk, Task, User, Vendor
from .posture import take_snapshot

CLIENTS = [
    {
        "name": "Delta Pharmacies", "name_ar": "صيدليات الدلتا", "sector": "Retail pharmacy chain (4 branches)",
        "city": "Tanta", "employees": 61, "dpo": "External consultant", "demo": True,
    },
    {
        "name": "Sphinx Dental Centre", "name_ar": "مركز سفنكس لطب الأسنان", "sector": "Dental practice",
        "city": "6th of October City", "employees": 14, "dpo": "External consultant", "demo": True,
    },
]

# Delta: every requirement answered from interviews, none backed by automated checks.
_DELTA_GOOD = {"a01-01", "a01-02", "a02-01", "a02-02", "a03-01", "a05-01", "a05-04", "a06-01", "a06-02", "a08-01", "a10-01"}
_DELTA_BAD = {"a04-03", "a06-05", "a06-06", "a07-01", "a07-02", "a09-02", "a11-02"}
# Sphinx: only the first interview has happened.
_SPHINX = [("a01-01", "non_compliant", "No DPO appointed yet; the owner handles patient data questions."),
           ("a01-03", "partial", "A one-page privacy notice exists at reception, no written policy."),
           ("a02-01", "partial", "Paper consent forms for treatment; no consent for SMS reminders."),
           ("a05-04", "non_compliant", "Backups are copied to a USB drive kept at the receptionist's desk."),
           ("a06-05", "non_compliant", "Shared login on the X-ray workstation.")]


def _delta(db: Session, req_ids: list[str], now) -> None:
    for rid in req_ids:
        status = "compliant" if rid in _DELTA_GOOD else "non_compliant" if rid in _DELTA_BAD else "partial"
        db.add(Answer(requirement_id=rid, status=status, note="Interview with the operations manager, branch 1.",
                      updated_at=now - timedelta(days=9)))
    db.flush()
    take_snapshot(db, "answers", at=now - timedelta(days=9))
    for title, req, owner, prio, days in [
        ("Turn on multi-factor sign-in for the dispensing system", "a06-05", "IT vendor", "high", -4),
        ("Write the breach response plan", "a07-01", "Consultant", "high", 10),
        ("Sign data processing agreement with the delivery app", "a09-02", "Operations manager", "medium", 21),
    ]:
        db.add(Task(title=title, requirement_id=req, owner=owner, priority=prio, source="gap", source_id=req,
                    due_on=now + timedelta(days=days)))
    db.add(Risk(title="Prescriptions visible on unattended counter screens", category="Physical", likelihood=4, impact=4,
                owner="Branch managers", requirement_ids=["a06-01"], controls="Screen lock after 2 minutes (planned)"))
    db.add(Risk(title="Delivery app shares customer addresses without a contract", category="Third party", likelihood=3,
                impact=4, owner="Operations manager", requirement_ids=["a09-02"]))
    db.add(Vendor(name="Fast Delivery (fictional)", service="Home delivery of orders", role="processor",
                  data_categories=["Name", "Address", "Phone"], countries=["Egypt"], dpa_signed=False, risk_level="high",
                  owner="Operations manager"))
    db.add(DataRequest(request_type="access", requester="Customer ref C-2231", channel="Branch 2 counter",
                       received_at=now - timedelta(days=12), status="in_progress", owner="Consultant"))


def _sphinx(db: Session, now) -> None:
    for rid, status, note in _SPHINX:
        db.add(Answer(requirement_id=rid, status=status, note=note, updated_at=now - timedelta(days=2)))
    db.flush()
    take_snapshot(db, "answers", at=now - timedelta(days=2))
    db.add(Task(title="Move backups off the USB drive to encrypted cloud storage", requirement_id="a05-04",
                owner="Clinic owner", priority="high", source="gap", source_id="a05-04", due_on=now + timedelta(days=14)))
    db.add(Risk(title="Unencrypted backup drive could be lost or stolen", category="Security", likelihood=4, impact=5,
                owner="Clinic owner", requirement_ids=["a05-04"]))


def seed_clients(db: Session, users: dict[str, User]) -> str:
    """Create the two extra organisations. db is the caller's session (organisation 1)."""
    from .catalog import get_catalog

    now = utcnow().replace(microsecond=0)
    req_ids = [r.id for r in get_catalog().requirements]
    ids = []
    for profile in CLIENTS:
        o = Organisation(name=profile["name"])
        db.add(o)
        db.flush()
        ids.append(o.id)
    db.commit()  # the per-organisation sessions below must see the new rows
    for org_id, profile in zip(ids, CLIENTS):
        with org_session(org_id) as s:
            s.add(AppSetting(key="organization", value=profile))
            (_delta(s, req_ids, now) if profile["name"].startswith("Delta") else _sphinx(s, now))
            s.commit()
    return "2 more fictional clients"
