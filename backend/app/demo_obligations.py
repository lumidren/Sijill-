"""Demo licences, permits and duties for the fictional Nour Family Clinic.

Dates come from the clinic's own (fictional) documents, except the controller licence, whose
expiry uses the configured default validity. Nothing here states a legal deadline.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from .models import AppSetting, Obligation
from .obligations_service import default_expiry, generate_reminders


def _day(dt: datetime) -> datetime:
    return datetime.combine(dt.date(), time(12, 0), tzinfo=timezone.utc)


def seed_obligations(db, users, now: datetime) -> str:
    dpo = users["dpo"]
    db.add(AppSetting(key="licensing", value={
        "controls_processing": True, "processes_for_others": False, "cross_border": True,
        "electronic_marketing": False, "surveillance": True, "sensitive_data": True,
    }))
    db.add(AppSetting(key="applicability", value={
        "processes_personal_data": True, "cbe_supervised": False, "money_transfer_or_exchange": None,
    }))
    issued = _day(now - timedelta(days=300))
    items = [
        dict(kind="licence", title="Controller licence", reference="CL-2026-0412", status="active", issued_on=issued,
             expires_on=default_expiry("licence", issued), expiry_from_default=True, owner="Dr. Mona Hassan",
             notes="Expiry uses the default licence validity from Settings; replace it with the date on the licence."),
        dict(kind="permit", title="Surveillance permit (CCTV, waiting area)", reference="SV-2025-1180", status="active",
             issued_on=_day(now - timedelta(days=340)), expires_on=_day(now + timedelta(days=25)),
             owner="Omar Adel", notes="Expiry date taken from the permit document. Start the renewal now."),
        dict(kind="permit", title="Cross-border transfer permit (EHR hosted in Germany)", status="planned",
             review_due=_day(now + timedelta(days=14)), owner="Dr. Mona Hassan",
             notes="Application not yet submitted. Target date set by management."),
        dict(kind="dpo_registration", title="DPO registration: Dr. Mona Hassan", status="applied",
             issued_on=_day(now - timedelta(days=28)), review_due=_day(now + timedelta(days=5)),
             owner="Karim Fathy", notes="Submitted; follow up if no confirmation arrives."),
        dict(kind="consent_mechanism", title="Patient consent form (paper, reception)", status="active",
             review_due=_day(now + timedelta(days=13)), owner="Reception supervisor",
             notes="Version 2. Add a withdrawal option and record consent in the EHR.",
             details={"channel": "Paper form at reception"}),
        dict(kind="cross_border_flow", title="EHR hosting on AWS eu-central-1 (Frankfurt)", status="active",
             review_due=_day(now + timedelta(days=60)), owner="Omar Adel",
             notes="Patient records stored outside Egypt. Contract terms under review.",
             details={"destination": "Germany", "data": "Patient medical records", "safeguards": "Encryption at rest and in transit"}),
        dict(kind="permit", title="Electronic marketing permit", status="not_needed", owner="Dr. Mona Hassan",
             notes="The clinic sends appointment reminders only, no marketing."),
    ]
    for it in items:
        db.add(Obligation(updated_by_id=dpo.id, created_at=now - timedelta(days=20), updated_at=now - timedelta(days=20), **it))
    db.flush()
    reminders = generate_reminders(db, now)
    return f"{len(items)} obligations, {reminders} reminders"
