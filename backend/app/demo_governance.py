"""Demo governance records for the fictional Nour Family Clinic, consistent with the rest of the story:
the public patient-scans bucket, the IT support vendor without a contract, the missing request process."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select

from .models import DataRequest, Dpia, EvidenceFile, Incident, Policy, ProcessingActivity, Risk, Task, Vendor


def _day(dt: datetime) -> datetime:
    return datetime.combine(dt.date(), time(12, 0), tzinfo=timezone.utc)


def seed_governance(db, users, now: datetime) -> str:
    dpo, it, admin = users["dpo"], users["it"], users["admin"]
    acts = {a.name: a.id for a in db.execute(select(ProcessingActivity)).scalars()}
    incident = db.execute(select(Incident).limit(1)).scalar_one_or_none()
    policy_file = db.execute(select(EvidenceFile).where(EvidenceFile.requirement_id == "a01-03")).scalar_one_or_none()
    stamp = dict(created_at=now - timedelta(days=12), updated_at=now - timedelta(days=2))

    tasks = [
        dict(title="Re-enable Block Public Access on the patient-scans bucket and confirm in the next scan",
             requirement_id="a06-06", source="incident", source_id=str(incident.id) if incident else "", owner="Omar Adel",
             priority="high", status="in_progress", due_on=_day(now + timedelta(days=1))),
        dict(title="Require MFA for the reception-kiosk account", requirement_id="a06-05", source="gap",
             owner="Omar Adel", priority="high", status="todo", due_on=_day(now - timedelta(days=3))),
        dict(title="Run data protection training for reception and nursing staff", requirement_id="a01-04", source="gap",
             owner="Dr. Mona Hassan", priority="medium", status="todo", due_on=_day(now + timedelta(days=21))),
        dict(title="Write the procedure for access, correction and deletion requests", requirement_id="a03-02",
             source="gap", owner="Dr. Mona Hassan", priority="high", status="in_progress",
             due_on=_day(now + timedelta(days=7))),
        dict(title="Sign a data processing agreement with the IT support vendor", requirement_id="a09-01",
             source="vendor", owner="Karim Fathy", priority="medium", status="blocked",
             due_on=_day(now - timedelta(days=1)), notes="Vendor legal team has not replied."),
        dict(title="Add lifecycle rules to delete scan images after the retention period", requirement_id="a05-03",
             source="gap", owner="Omar Adel", priority="medium", status="todo", due_on=_day(now + timedelta(days=30))),
        dict(title="Turn on CloudTrail data events for the patient-scans bucket", requirement_id="a07-05", source="gap",
             owner="Omar Adel", priority="low", status="done", due_on=_day(now - timedelta(days=10)),
             completed_at=now - timedelta(days=12)),
    ]
    for t in tasks:
        db.add(Task(updated_by_id=dpo.id, **stamp, **t))

    risks = [
        dict(title="Patient images exposed through misconfigured cloud storage", category="Security",
             likelihood=4, impact=5, residual_likelihood=2, residual_impact=5, treatment="mitigate", status="treating",
             owner="Omar Adel", requirement_ids=["a06-06", "a07-05"], review_due=_day(now + timedelta(days=30)),
             controls="Account-level public access block, weekly automated scans, sharing through expiring links."),
        dict(title="Processor without a contract (IT support vendor) handles patient data", category="Third parties",
             likelihood=3, impact=4, treatment="mitigate", status="open", owner="Karim Fathy",
             requirement_ids=["a09-01", "a09-02"], review_due=_day(now + timedelta(days=14))),
        dict(title="Requests from patients answered late or not at all", category="Individuals' rights",
             likelihood=3, impact=3, treatment="mitigate", status="open", owner="Dr. Mona Hassan",
             requirement_ids=["a03-02", "a03-04"]),
        dict(title="Patient records hosted outside Egypt without a transfer permit", category="Cross-border",
             likelihood=4, impact=3, treatment="mitigate", status="open", owner="Dr. Mona Hassan",
             requirement_ids=["a10-02", "a10-03"]),
        dict(title="Unencrypted disk on the web server", category="Security", likelihood=2, impact=4,
             residual_likelihood=2, residual_impact=4, treatment="accept", status="accepted", owner="Omar Adel",
             requirement_ids=["a06-01"], accepted_by_id=admin.id, accepted_at=now - timedelta(days=9),
             acceptance_expires_on=_day(now + timedelta(days=81)),
             acceptance_note="The web server holds no patient data; re-image with encryption during the Q1 migration."),
        dict(title="Staff unaware of data protection duties", category="People", likelihood=3, impact=2,
             treatment="mitigate", status="open", owner="Dr. Mona Hassan", requirement_ids=["a01-04"]),
    ]
    for r in risks:
        db.add(Risk(updated_by_id=dpo.id, **stamp, **r))

    for days_ago, kind, who, channel, status, verified, outcome in [
        (26, "access", "Patient #4471", "Email", "in_progress", True, ""),
        (9, "correction", "Patient #5120", "Reception desk", "received", False, ""),
        (40, "deletion", "Former patient #1288", "Letter", "completed", True,
         "Marketing contact details deleted; medical record kept under the retention rule (to be confirmed with legal adviser)."),
    ]:
        received = now - timedelta(days=days_ago)
        db.add(DataRequest(request_type=kind, requester=who, channel=channel, received_at=received, status=status,
                           identity_verified=verified, outcome=outcome, owner="Dr. Mona Hassan",
                           completed_at=received + timedelta(days=18) if status == "completed" else None,
                           created_at=received, updated_at=received, updated_by_id=dpo.id))

    vendors = [
        dict(name="Amazon Web Services (EU)", service="Cloud hosting for the EHR and scan images", role="processor",
             data_categories=["Patient records", "Medical images"], countries=["Germany"], dpa_signed=True,
             dpa_signed_on=_day(now - timedelta(days=400)), due_diligence_on=_day(now - timedelta(days=400)),
             next_review_on=_day(now + timedelta(days=60)), risk_level="medium", owner="Omar Adel",
             security_notes="Provider's standard data processing terms accepted online; certifications reviewed."),
        dict(name="CairoTech IT Support", service="Remote IT support for clinic workstations", role="processor",
             data_categories=["Any data on workstations"], countries=["Egypt"], dpa_signed=False,
             risk_level="high", owner="Karim Fathy", security_notes="Remote access tool installed on reception PCs."),
        dict(name="SMS Gateway Co.", service="Appointment reminder messages", role="processor",
             data_categories=["Name", "Mobile number", "Appointment time"], countries=["Egypt"], dpa_signed=True,
             dpa_signed_on=_day(now - timedelta(days=200)), due_diligence_on=_day(now - timedelta(days=210)),
             next_review_on=_day(now - timedelta(days=5)), risk_level="low", owner="Reception supervisor"),
        dict(name="Delta Medical Laboratory", service="Laboratory tests", role="recipient",
             data_categories=["Identity details", "Test orders"], countries=["Egypt"],
             due_diligence_on=_day(now - timedelta(days=90)), next_review_on=_day(now + timedelta(days=275)),
             risk_level="medium", owner="Dr. Mona Hassan"),
    ]
    for v in vendors:
        db.add(Vendor(updated_by_id=dpo.id, **stamp, **v))

    db.add(Dpia(
        title="Hosting patient records and scans in the cloud (Frankfurt)", activity_id=acts.get("Patient medical records"),
        screening={"sensitive_data": True, "large_scale": False, "systematic_monitoring": False, "new_technology": True,
                   "vulnerable_people": True, "cross_border": True, "automated_decisions": False, "data_matching": False},
        description="EHR database and scan images stored in AWS eu-central-1; staff access through the clinic network.",
        necessity="Needed for continuity of care and backups; no Egyptian region offered by the current provider.",
        risks="Exposure through misconfiguration; access by the provider; transfer outside Egypt without a permit.",
        measures="Encryption at rest and in transit, account-level public access block, weekly automated checks, "
                 "transfer permit application.",
        residual_risk="medium", dpo_opinion="Proceed once the transfer permit application is filed.",
        status="approved", approved_by_id=admin.id, approved_at=now - timedelta(days=30),
        review_due=_day(now + timedelta(days=150)), owner="Dr. Mona Hassan", updated_by_id=dpo.id,
        created_at=now - timedelta(days=45), updated_at=now - timedelta(days=30)))
    db.add(Dpia(
        title="Sharing scan images with outside radiologists", activity_id=acts.get("Patient medical records"),
        screening={"sensitive_data": True, "large_scale": False, "systematic_monitoring": False, "new_technology": False,
                   "vulnerable_people": True, "cross_border": None, "automated_decisions": False, "data_matching": False},
        description="Raised after the public-bucket breach: how to share images with outside specialists safely.",
        risks="Links forwarded or left public; images re-identified from file names.", status="draft",
        owner="Dr. Mona Hassan", updated_by_id=dpo.id, created_at=now - timedelta(days=1), updated_at=now - timedelta(days=1)))

    db.add(Policy(title="Data protection policy", version="1.2", status="approved", owner="Dr. Mona Hassan",
                  summary="Roles, lawful processing, security, breaches and review.", requirement_ids=["a01-03", "a01-05"],
                  evidence_file_id=policy_file.id if policy_file else None, approved_by_id=admin.id,
                  approved_on=now - timedelta(days=75), review_due=_day(now - timedelta(days=10)),
                  history=[{"version": "1.2", "status": "draft", "at": (now - timedelta(days=80)).isoformat(), "by": "Dr. Mona Hassan"},
                           {"version": "1.2", "status": "approved", "at": (now - timedelta(days=75)).isoformat(), "by": "Karim Fathy"}],
                  updated_by_id=dpo.id, created_at=now - timedelta(days=80), updated_at=now - timedelta(days=75)))
    db.add(Policy(title="Breach response plan", version="0.3", status="draft", owner="Dr. Mona Hassan",
                  summary="Who decides, who investigates, who notifies; contacts and templates.", requirement_ids=["a08-01"],
                  review_due=_day(now + timedelta(days=30)),
                  history=[{"version": "0.3", "status": "draft", "at": (now - timedelta(days=5)).isoformat(), "by": "Dr. Mona Hassan"}],
                  updated_by_id=dpo.id, created_at=now - timedelta(days=5), updated_at=now - timedelta(days=5)))
    db.add(Policy(title="Retention schedule", version="0.1", status="draft", owner="Dr. Mona Hassan",
                  summary="Retention period per record type, and how deletion happens.", requirement_ids=["a05-03"],
                  history=[{"version": "0.1", "status": "draft", "at": (now - timedelta(days=3)).isoformat(), "by": "Dr. Mona Hassan"}],
                  updated_by_id=dpo.id, created_at=now - timedelta(days=3), updated_at=now - timedelta(days=3)))
    db.flush()
    return f"{len(tasks)} tasks, {len(risks)} risks, 3 requests, {len(vendors)} vendors, 2 DPIAs, 3 policies"
