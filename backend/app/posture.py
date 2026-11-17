"""Database-facing side of scoring: current posture, snapshots, run-to-run drift."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import get_catalog
from .config import get_settings
from .db import utcnow
from .evidence.mapping import get_mapping
from .models import Answer, CheckResult, CheckRun, EvidenceFile, ScoreSnapshot
from .scoring import AnswerInput, Observation, ReqInput, ScoreResult, score


def latest_runs(db: Session, as_of: datetime | None = None) -> list[CheckRun]:
    """The most recent completed run for each (provider, target)."""
    q = select(CheckRun).where(CheckRun.status == "completed")
    if as_of is not None:
        q = q.where(CheckRun.started_at <= as_of)
    latest: dict[tuple[str, str], CheckRun] = {}
    for run in db.execute(q.order_by(CheckRun.started_at, CheckRun.id)).scalars():
        latest[(run.provider, run.target)] = run
    return sorted(latest.values(), key=lambda r: r.started_at, reverse=True)


def latest_observations(db: Session, as_of: datetime | None = None) -> dict[str, list[Observation]]:
    out: dict[str, list[Observation]] = defaultdict(list)
    for run in latest_runs(db, as_of):
        for r in run.results:
            out[r.check_id].append(Observation(r.check_id, r.status, r.resource_uid, r.observed_at, run.target))
    return out


def current_score(db: Session, now: datetime | None = None) -> ScoreResult:
    now = now or utcnow()
    cat = get_catalog()
    mapping = get_mapping()
    reqs = [ReqInput(r.id, r.area_id, r.weight, r.technical) for r in cat.requirements]
    answers = {
        a.requirement_id: AnswerInput(a.status, a.updated_at)
        for a in db.execute(select(Answer)).scalars()
    }
    files: dict[str, list[datetime]] = defaultdict(list)
    for f in db.execute(select(EvidenceFile).where(EvidenceFile.requirement_id.is_not(None))).scalars():
        files[f.requirement_id].append(f.uploaded_at)
    check_map = {r.id: mapping.checks_for(r.id) for r in cat.requirements}
    return score(reqs, answers, check_map, latest_observations(db, as_of=now), files, now,
                 get_settings().evidence_stale_days)


def take_snapshot(db: Session, reason: str, run_id: int | None = None, at: datetime | None = None) -> ScoreSnapshot:
    at = at or utcnow()
    result = current_score(db, now=at)
    snap = ScoreSnapshot(
        at=at, overall=round(result.overall or 0.0, 4),
        by_area={a.id: (None if a.score is None else round(a.score, 4)) for a in result.areas},
        counts=result.counts(), reason=reason, run_id=run_id,
    )
    db.add(snap)
    db.flush()
    return snap


def previous_run(db: Session, run: CheckRun) -> CheckRun | None:
    return db.execute(
        select(CheckRun)
        .where(CheckRun.provider == run.provider, CheckRun.target == run.target,
               CheckRun.status == "completed", CheckRun.id != run.id,
               CheckRun.started_at <= run.started_at)
        .order_by(CheckRun.started_at.desc(), CheckRun.id.desc()).limit(1)
    ).scalar_one_or_none()


def _key(r: CheckResult) -> tuple[str, str]:
    return r.check_id, r.resource_uid


def run_diff(db: Session, run: CheckRun) -> dict:
    """Compare a run with the previous run of the same target, resource by resource."""
    prev = previous_run(db, run)
    mapping = get_mapping()
    out = {"run_id": run.id, "previous_run_id": prev.id if prev else None,
           "regressions": [], "fixed": [], "new_failures": []}
    if prev is None:
        return out
    before = {_key(r): r.status for r in prev.results}
    for r in run.results:
        was = before.get(_key(r))
        item = {"check_id": r.check_id, "resource": r.resource_uid, "region": r.region, "title": r.title,
                "message": r.message, "severity": r.severity,
                "requirements": mapping.requirements_for(r.check_id)}
        if r.status == "FAIL" and was == "PASS":
            out["regressions"].append(item)
        elif r.status == "PASS" and was == "FAIL":
            out["fixed"].append(item)
        elif r.status == "FAIL" and was is None:
            out["new_failures"].append(item)
    return out


def open_regressions(db: Session) -> list[dict]:
    """Regressions in the latest run of each target (a check that passed before and fails now)."""
    out = []
    for run in latest_runs(db):
        d = run_diff(db, run)
        for item in d["regressions"]:
            out.append({**item, "run_id": run.id, "previous_run_id": d["previous_run_id"],
                        "target": run.target, "provider": run.provider,
                        "detected_at": run.started_at.isoformat()})
    return out


def snapshots(db: Session, limit: int = 500) -> list[ScoreSnapshot]:
    rows = db.execute(select(ScoreSnapshot).order_by(ScoreSnapshot.at.desc(), ScoreSnapshot.id.desc()).limit(limit)).scalars()
    return list(reversed(list(rows)))
