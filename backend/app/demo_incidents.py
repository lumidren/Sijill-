"""Demo breach: the public patient-scans bucket the latest scan flagged. The clock is running."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from .models import CheckRun, Incident, IncidentEvent


def seed_incidents(db, users, now: datetime) -> str:
    it, dpo = users["it"], users["dpo"]
    run = db.execute(select(CheckRun).where(CheckRun.provider == "aws").order_by(CheckRun.started_at.desc()).limit(1)).scalar_one_or_none()
    discovered = now - timedelta(hours=31)
    i = Incident(
        title="Patient scan images exposed through a public storage bucket",
        description=("The storage bucket holding patient scan images (nour-patient-scans) was made publicly readable so "
                     "that an outside radiologist could open a shared link. The weekly automated scan flagged the bucket "
                     "as public and its access logging as switched off."),
        severity="high", status="contained", discovered_at=discovered, occurred_at=now - timedelta(hours=40),
        data_categories=["Medical images (scans)", "Patient names in file names"], affected_count=1240,
        systems=["AWS S3 bucket nour-patient-scans"],
        likely_consequences="Health information could have been viewed or copied by anyone holding the bucket address.",
        measures_taken=("Public access removed and the bucket-level block re-enabled; access logs under review to see "
                        "whether files were downloaded; outside sharing now goes through expiring links only."),
        contact="dpo@nour-clinic.example", individuals_notice_needed=None,
        source={"run_id": run.id if run else None, "check_id": "s3_bucket_public_access"},
        created_at=discovered, updated_at=now - timedelta(hours=6), created_by_id=it.id,
    )
    db.add(i)
    db.flush()
    for at, kind, text, who in [
        (discovered, "created", "Raised from the automated-check regression on the patient-scans bucket.", it),
        (now - timedelta(hours=30), "note", "Public access removed and bucket policy restored. Waiting for the next scan to confirm.", it),
        (now - timedelta(hours=29), "status", "open → contained", it),
        (now - timedelta(hours=6), "note", "Regulator notification drafted from the template; reviewing access logs before sending.", dpo),
    ]:
        db.add(IncidentEvent(incident_id=i.id, at=at, kind=kind, text=text, actor_name=who.display_name))
    db.flush()
    return "1 open breach"
