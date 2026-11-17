"""The demo organisation: Nour Family Clinic, a fictional private clinic in Giza.

The story the seed tells, oldest first:
  ~40 days ago  The DPO starts the self-assessment and answers the governance questions.
  weeks 1-5     Weekly automated scans of the clinic's AWS account (Frankfurt region) and its two
                Linux servers. IT fixes findings every week and the readiness score climbs.
  ~20 days ago  The DPO answers more areas (transparency, records, transfers, licences).
  ~10 days ago  The DPO self-attests several technical safeguards as met; failing checks cap them.
  ~34 hours ago The latest scan finds a regression: the patient-scans bucket was made public and its
                access logging was switched off (to share images with an outside radiologist).
                The score dips and the dashboard flags the regression.
Later phases add the processing register, licences nearing renewal and an open breach clock.
Every name, number and document here is fictional.
"""
from __future__ import annotations

import io
import json
from argparse import Namespace
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location

from sqlalchemy.orm import Session

from . import demo_aws
from .config import REPO_DIR
from .db import utcnow
from .evidence.service import import_findings
from .evidence_files import store
from .models import Answer, AppSetting, User
from .posture import take_snapshot

ORG = {
    "name": "Nour Family Clinic",
    "name_ar": "عيادة نور للأسرة",
    "sector": "Private clinic (healthcare)",
    "city": "Giza",
    "employees": 38,
    "dpo": "Dr. Mona Hassan",
    "demo": True,
}

# (requirement, status, note) answered at each stage
STAGE_1 = [  # governance, ~40 days ago
    ("a01-01", "compliant", "Dr. Mona Hassan appointed as DPO by the medical director; appointment letter attached."),
    ("a01-02", "partial", "Registration form prepared; submission to the regulator not yet confirmed."),
    ("a01-03", "compliant", "Data protection policy v1.2 approved by management; copy attached."),
    ("a01-04", "non_compliant", "No data protection training has been run yet. Planned for reception and nursing staff."),
    ("a01-05", "partial", "Policies exist; decisions and reviews are not yet recorded consistently."),
    ("a02-01", "partial", "Lawful basis recorded for patient care; not yet for marketing and research uses."),
    ("a02-02", "partial", "Paper consent forms at reception; no record of withdrawals."),
    ("a02-03", "compliant", "Patient data is used for care and billing only."),
    ("a02-04", "non_compliant", "Health records are sensitive data but have no extra documented controls yet."),
    ("a02-05", "partial", "Parents sign for children at registration; the form does not explain processing."),
    ("a05-02", "compliant", "Patients confirm their details at every visit."),
]
STAGE_2 = [  # more areas, ~20 days ago
    ("a03-01", "partial", "Privacy notice displayed at reception; not yet on the website or booking app."),
    ("a03-02", "non_compliant", "No written process for access or deletion requests."),
    ("a04-01", "partial", "Processing register started for patient care and billing; HR and CCTV still missing."),
    ("a04-02", "not_applicable", "The clinic does not process personal data on behalf of other organisations."),
    ("a04-04", "partial", "Systems listed; laptops and paper archives not yet mapped."),
    ("a05-03", "partial", "Retention periods agreed for medical records; not applied to scan images."),
    ("a08-01", "partial", "Draft breach response plan; roles not yet confirmed."),
    ("a09-01", "partial", "Contracts with the lab and the cloud provider; none yet with the IT support vendor."),
    ("a10-01", "partial", "Clinic systems are hosted in AWS Frankfurt (eu-central-1); remote IT support flows not mapped."),
    ("a10-02", "non_compliant", "No cross-border transfer permit has been requested."),
    ("a10-03", "partial", "Encryption is used; transfer contract terms not reviewed."),
    ("a11-01", "compliant", "Controller licence held; see the obligations tracker."),
    ("a11-02", "not_applicable", "The clinic sends appointment reminders only, no electronic marketing."),
    ("a11-03", "partial", "CCTV in the waiting area with signs; permit held but expiring soon."),
    ("a11-04", "partial", "Dates now tracked in PDPL-Ready; the CCTV permit renewal is due soon."),
]
STAGE_3 = [  # technical self-attestation, ~10 days ago
    ("a05-04", "compliant", "Nightly backups via AWS Backup; restore tested in October."),
    ("a06-01", "compliant", "All storage encrypted according to IT."),
    ("a06-05", "compliant", "MFA required for all staff accounts according to IT."),
    ("a06-06", "compliant", "No public buckets or databases."),
]


def _collector():
    spec = spec_from_file_location("pdpl_linux_collector", REPO_DIR / "collectors/linux/pdpl_linux_collector.py")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Linux web server improvements by week: check -> PASS message
WEB_FIXES = {
    3: {"linux_firewall_enabled": "ufw is active.", "linux_auditd_running": "auditd is active."},
    5: {"linux_pending_security_updates": "No pending security updates (apt).",
        "linux_automatic_security_updates_enabled": "unattended-upgrades is enabled.",
        "linux_ssh_root_login_disabled": "PermitRootLogin is 'no' (sshd -T)."},
}


def _linux_findings(col, week: int, when: datetime) -> bytes:
    """Both servers' collector output for one week, bundled in one file (one run per host)."""
    opts = Namespace(hostname=None, min_log_retention_days=90)
    bundle = []
    for host in ("clinic-db-01", "clinic-web-01"):
        out = col.collect(col.FixtureProbe(str(REPO_DIR / "fixtures/linux" / host)), opts, now=when.timestamp())
        if host == "clinic-web-01":
            fixed = {}
            for w in range(2, week + 1):
                fixed.update(WEB_FIXES.get(w, {}))
            for f in out:
                msg = fixed.get(f["metadata"]["event_code"])
                if msg:
                    f["status_code"] = "PASS"
                    f["message"] = f["status_detail"] = msg
        bundle += out
    return json.dumps(bundle).encode("utf-8")


def _answer(db: Session, req: str, status: str, note: str, user: User, at: datetime) -> None:
    a = db.query(Answer).filter_by(requirement_id=req).one_or_none() or Answer(requirement_id=req)
    a.status, a.note, a.updated_by_id, a.updated_at = status, note, user.id, at
    db.add(a)


def _pdf(title: str, lines: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    c.setTitle(title)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(60, 780, title)
    c.setFont("Helvetica", 10)
    y = 750
    for line in ["FICTIONAL DEMO DOCUMENT - Nour Family Clinic does not exist.", ""] + lines:
        c.drawString(60, y, line)
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


def seed_all(db: Session, users: dict[str, User]) -> str:
    now = utcnow().replace(microsecond=0)
    dpo, it = users["dpo"], users["it"]
    db.add(AppSetting(key="organization", value=ORG))

    # Evidence documents (one deliberately old, so it shows as stale)
    store(db, _pdf("DPO appointment letter", [
        "The medical director appoints Dr. Mona Hassan as Data Protection Officer,",
        "reporting to the board, with responsibility for personal data protection.",
    ]), "DPO appointment letter.pdf", "a01-01", dpo, "Signed appointment letter", now - timedelta(days=41))
    store(db, _pdf("Data protection policy v1.2", [
        "1. Scope   2. Roles   3. Lawful processing   4. Security   5. Breaches   6. Review",
    ]), "Data protection policy v1.2.pdf", "a01-03", dpo, "Approved policy", now - timedelta(days=75))
    store(db, _pdf("Backup restore test - October", [
        "Restore of nour-ehr-db snapshot to an isolated instance completed in 42 minutes.",
    ]), "Backup restore test.pdf", "a05-04", it, "Restore test record", now - timedelta(days=11))

    events: list[tuple[datetime, str, object]] = []
    events.append((now - timedelta(days=40), "answers", STAGE_1))
    events.append((now - timedelta(days=20), "answers", STAGE_2))
    events.append((now - timedelta(days=10), "answers", STAGE_3))
    for week in range(1, demo_aws.WEEKS + 1):
        when = now - timedelta(hours=34) if week == demo_aws.WEEKS else now - timedelta(days=36 - 7 * (week - 1))
        events.append((when, "aws", week))
        events.append((when + timedelta(minutes=50), "linux", week))
    events.sort(key=lambda e: e[0])

    col = _collector()
    for at, kind, payload in events:
        if kind == "answers":
            for req, status, note in payload:
                _answer(db, req, status, note, dpo, at)
            db.flush()
            take_snapshot(db, reason="assessment", at=at)
        elif kind == "aws":
            import_findings(db, demo_aws.findings_bytes(payload, at), f"nour-clinic-week{payload}.ocsf.json",
                            it, source="prowler-import", imported_at=at + timedelta(minutes=20))
        else:
            import_findings(db, _linux_findings(col, payload, at), f"linux-servers-week{payload}.ocsf.json",
                            it, source="linux-collector", imported_at=at + timedelta(minutes=5))

    extras = []
    for name in ("seed_register", "seed_obligations", "seed_incidents", "seed_governance"):
        try:
            mod = __import__(f"app.demo_{name.split('_', 1)[1]}", fromlist=[name])
        except ModuleNotFoundError:
            continue
        extras.append(getattr(mod, name)(db, users, now))
    return "Nour Family Clinic (fictional)" + (f"; {', '.join(e for e in extras if e)}" if extras else "")
