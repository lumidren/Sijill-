"""Import findings into check runs. Every adapter ends here."""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import utcnow
from ..models import CheckResult, CheckRun, User
from ..posture import take_snapshot
from . import ocsf
from .mapping import get_mapping


class DuplicateImport(ValueError):
    pass


def import_findings(db: Session, raw: bytes, filename: str, actor: User | None, source: str,
                    allow_duplicate: bool = False, actor_name: str | None = None,
                    imported_at: datetime | None = None) -> list[CheckRun]:
    """Parse, store and score a findings file. One CheckRun per (provider, target) in the file.

    The caller commits. Raises ocsf.FindingsError for bad input and DuplicateImport when the
    exact same file was imported before (by SHA-256). `imported_at` is only set by the demo seed
    to replay history; normal imports use the current time.
    """
    settings = get_settings()
    imported_at = imported_at or utcnow()
    file_sha = hashlib.sha256(raw).hexdigest()
    if not allow_duplicate and db.execute(
        select(CheckRun.id).where(CheckRun.file_sha256 == file_sha).limit(1)
    ).first():
        raise DuplicateImport(file_sha)
    batches = ocsf.parse(raw, settings.max_upload_mb * 1024 * 1024)
    mapping = get_mapping()
    runs = []
    for b in sorted(batches, key=lambda b: b.started_at):
        run = CheckRun(
            source=source, provider=b.provider, target=b.target, started_at=b.started_at,
            imported_at=imported_at, filename=filename[:255], file_sha256=file_sha,
            created_by_id=actor.id if actor else None,
        )
        for f in b.findings:
            run.results.append(CheckResult(
                check_id=f.check_id, status=f.status, severity=f.severity, resource_uid=f.resource_uid,
                region=f.region, title=f.title, message=f.message, observed_at=f.observed_at, sha256=f.sha256,
            ))
        run.total = len(b.findings)
        run.passed = sum(1 for f in b.findings if f.status == "PASS")
        run.failed = sum(1 for f in b.findings if f.status == "FAIL")
        run.manual = sum(1 for f in b.findings if f.status == "MANUAL")
        run.unmapped = sum(1 for f in b.findings if not mapping.is_mapped(f.check_id))
        db.add(run)
        db.flush()
        audit.record(db, actor, "checks.import", "check_run", run.id,
                     {"source": source, "provider": run.provider, "target": run.target, "filename": run.filename,
                      "sha256": file_sha, "total": run.total, "failed": run.failed},
                     actor_name=actor_name)
        runs.append(run)
    if runs:
        take_snapshot(db, reason="check_run", run_id=runs[-1].id, at=imported_at)
    return runs


def import_findings_file(db: Session, raw: bytes, filename: str, actor: User | None, source: str) -> CheckRun:
    """CLI helper: import and return the first run."""
    return import_findings(db, raw, filename, actor, source)[0]
