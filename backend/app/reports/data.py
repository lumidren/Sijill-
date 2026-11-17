"""One snapshot of everything a report needs, built once and rendered many ways."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import Catalog, Requirement, get_catalog
from ..config import get_settings
from ..db import utcnow
from ..evidence.mapping import Mapping, get_mapping
from ..models import Answer, AppSetting, CheckRun, EvidenceFile, User
from ..posture import current_score, latest_runs, open_regressions, snapshots
from ..scoring import ReqResult, ScoreResult

GAP_ORDER = {"non_compliant": 0, "partial": 1, "not_assessed": 2}


@dataclass
class ReportData:
    generated_at: datetime
    org: dict
    catalog: Catalog
    mapping: Mapping
    score: ScoreResult
    answers: dict[str, Answer]
    answer_by: dict[str, str]
    evidence: list[EvidenceFile]
    runs: list[CheckRun]
    regressions: list[dict]
    trend: list[tuple[datetime, float]]
    stale_days: int
    results: dict[str, ReqResult] = field(default_factory=dict)
    tasks: list = field(default_factory=list)
    risks: list = field(default_factory=list)

    def req(self, rid: str) -> Requirement:
        return self.catalog.requirement(rid)

    @property
    def gaps(self) -> list[ReqResult]:
        gaps = [r for r in self.score.requirements if r.status in GAP_ORDER]
        return sorted(gaps, key=lambda r: (GAP_ORDER[r.status], -r.weight, r.id))

    @property
    def unverified(self) -> int:
        return sum(1 for r in self.catalog.requirements if not r.verified)


def build(db: Session, now: datetime | None = None) -> ReportData:
    now = now or utcnow()
    score = current_score(db, now)
    answers = {a.requirement_id: a for a in db.execute(select(Answer)).scalars()}
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars()}
    org_row = db.execute(select(AppSetting).where(AppSetting.key == "organization")).scalar_one_or_none()
    return ReportData(
        generated_at=now,
        org=org_row.value if org_row else {"name": "Organisation"},
        catalog=get_catalog(),
        mapping=get_mapping(),
        score=score,
        answers=answers,
        answer_by={rid: users.get(a.updated_by_id, "") for rid, a in answers.items()},
        evidence=list(db.execute(select(EvidenceFile).order_by(EvidenceFile.uploaded_at)).scalars()),
        runs=latest_runs(db, as_of=now),
        regressions=open_regressions(db),
        trend=[(s.at, s.overall) for s in snapshots(db)],
        stale_days=get_settings().evidence_stale_days,
        results={r.id: r for r in score.requirements},
        tasks=_tasks(db, now),
        risks=_risks(db, now),
    )


def _tasks(db: Session, now: datetime) -> list[dict]:
    from ..governance import task_out
    from ..models import Task

    rows = [task_out(t, now) for t in db.execute(select(Task)).scalars()]
    return sorted((t for t in rows if t["status"] != "done"),
                  key=lambda t: (t["days_left"] is None, t["days_left"] if t["days_left"] is not None else 0))


def _risks(db: Session, now: datetime) -> list[dict]:
    from ..governance import risk_out
    from ..models import Risk

    rows = [risk_out(r, now) for r in db.execute(select(Risk)).scalars()]
    return sorted((r for r in rows if r["status"] != "closed"), key=lambda r: -r["score"])
