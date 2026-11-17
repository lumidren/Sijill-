"""Readiness scoring. Pure functions: no database, no clock, fully unit-tested.

Rules (see README "How scoring works"):
- Each requirement ends up compliant, partial, non_compliant, not_applicable or not_assessed.
- A self-attested answer is used as given, except that a requirement backed by automated
  checks can never score above `partial` while any mapped check is failing.
- With no answer, a requirement with automated results takes its status from them:
  all passing -> compliant, mixed -> partial, all failing -> non_compliant.
- "Not applicable" is ignored while a mapped check is failing (the systems clearly exist);
  the requirement then takes the automated status, capped at partial.
- Evidence older than `stale_days` is flagged stale. Staleness is shown, not scored.
- Values: compliant 1, partial 0.5, non_compliant 0, not_assessed 0; not_applicable is
  excluded. Area and overall scores are weight-averaged over requirements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

STATUS_VALUE = {"compliant": 1.0, "partial": 0.5, "non_compliant": 0.0, "not_assessed": 0.0}
RANK = {"non_compliant": 0, "partial": 1, "compliant": 2}


@dataclass(frozen=True)
class ReqInput:
    id: str
    area_id: str
    weight: int
    technical: bool = False


@dataclass(frozen=True)
class AnswerInput:
    status: str
    updated_at: datetime


@dataclass(frozen=True)
class Observation:
    """One automated result for one resource, from the latest run of its target."""
    check_id: str
    status: str  # PASS | FAIL | MANUAL
    resource: str
    observed_at: datetime
    target: str = ""


@dataclass
class CheckSummary:
    check_id: str
    status: str | None  # PASS | FAIL | None (no result yet)
    passing: int = 0
    failing: int = 0
    failing_resources: list[str] = field(default_factory=list)
    last_observed: datetime | None = None

    def as_dict(self) -> dict:
        return {"check_id": self.check_id, "status": self.status, "passing": self.passing,
                "failing": self.failing, "failing_resources": self.failing_resources[:25],
                "last_observed": self.last_observed.isoformat() if self.last_observed else None}


@dataclass
class ReqResult:
    id: str
    area_id: str
    weight: int
    technical: bool
    status: str
    basis: str  # automated | attested | not_assessed
    value: float | None  # None when not applicable
    attested_status: str | None
    automated_status: str | None
    reason: str
    capped: bool
    stale: bool
    evidence_at: datetime | None
    checks: list[CheckSummary]

    @property
    def failing_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def passing_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == "PASS")

    def as_dict(self) -> dict:
        return {
            "id": self.id, "area_id": self.area_id, "weight": self.weight, "technical": self.technical,
            "status": self.status, "basis": self.basis, "value": self.value,
            "attested_status": self.attested_status, "automated_status": self.automated_status,
            "reason": self.reason, "capped": self.capped, "stale": self.stale,
            "evidence_at": self.evidence_at.isoformat() if self.evidence_at else None,
            "failing_checks": self.failing_checks, "passing_checks": self.passing_checks,
            "checks": [c.as_dict() for c in self.checks],
        }


@dataclass
class AreaResult:
    id: str
    score: float | None
    weight: int  # weight of scored (non-N/A) requirements
    by_status: dict[str, int]
    by_basis: dict[str, int]

    def as_dict(self) -> dict:
        return {"id": self.id, "score": self.score, "weight": self.weight,
                "by_status": self.by_status, "by_basis": self.by_basis}


@dataclass
class ScoreResult:
    overall: float | None
    areas: list[AreaResult]
    requirements: list[ReqResult]

    def counts(self) -> dict:
        by_status = _count(r.status for r in self.requirements)
        by_basis = _count(r.basis for r in self.requirements)
        tech = [r for r in self.requirements if r.technical]
        return {
            "total": len(self.requirements),
            "by_status": by_status,
            "by_basis": by_basis,
            "stale": sum(1 for r in self.requirements if r.stale),
            "capped": sum(1 for r in self.requirements if r.capped),
            "technical_total": len(tech),
            "technical_automated": sum(1 for r in tech if r.basis == "automated"),
            "failing_checks": len({c.check_id for r in self.requirements for c in r.checks if c.status == "FAIL"}),
        }

    def as_dict(self) -> dict:
        return {"overall": self.overall, "counts": self.counts(),
                "areas": [a.as_dict() for a in self.areas],
                "requirements": [r.as_dict() for r in self.requirements]}


def _count(items: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def summarize_checks(check_ids: list[str], observations: dict[str, list[Observation]]) -> list[CheckSummary]:
    out = []
    for cid in check_ids:
        obs = [o for o in observations.get(cid, []) if o.status in ("PASS", "FAIL")]
        if not obs:
            out.append(CheckSummary(cid, None))
            continue
        failing = [o for o in obs if o.status == "FAIL"]
        out.append(CheckSummary(
            check_id=cid,
            status="FAIL" if failing else "PASS",
            passing=len(obs) - len(failing),
            failing=len(failing),
            failing_resources=sorted({o.resource or o.target for o in failing}),
            last_observed=max(o.observed_at for o in obs),
        ))
    return out


def automated_status(checks: list[CheckSummary]) -> str | None:
    seen = [c for c in checks if c.status is not None]
    if not seen:
        return None
    fails = sum(1 for c in seen if c.status == "FAIL")
    if fails == 0:
        return "compliant"
    if fails == len(seen):
        return "non_compliant"
    return "partial"


def _cap(status: str, ceiling: str) -> str:
    return status if RANK[status] <= RANK[ceiling] else ceiling


def score_requirement(req: ReqInput, answer: AnswerInput | None, check_ids: list[str],
                      observations: dict[str, list[Observation]], evidence_files: list[datetime],
                      now: datetime, stale_days: int) -> ReqResult:
    checks = summarize_checks(check_ids, observations)
    auto = automated_status(checks)
    failing = any(c.status == "FAIL" for c in checks)
    attested = answer.status if answer and answer.status != "not_assessed" else None

    capped = False
    if attested == "not_applicable" and failing:
        status = _cap(auto or "non_compliant", "partial")
        reason = "na_overridden_by_failing_checks"
        capped = True
    elif attested == "not_applicable":
        status, reason = "not_applicable", "from_answer"
    elif attested:
        status, reason = attested, "from_answer"
        if failing and RANK[attested] > RANK["partial"]:
            status, reason, capped = "partial", "capped_by_failing_checks", True
    elif auto:
        status, reason = auto, "derived_from_checks"
    else:
        status, reason = "not_assessed", "not_assessed"

    basis = "automated" if auto is not None else ("attested" if attested else "not_assessed")

    # Evidence age: automated -> the oldest "latest observation" among mapped checks with results;
    # attested -> the newer of the answer and the newest attached evidence file.
    if basis == "automated":
        evidence_at = min(c.last_observed for c in checks if c.last_observed)
    elif basis == "attested":
        candidates = [answer.updated_at] + list(evidence_files)
        evidence_at = max(candidates)
    else:
        evidence_at = None
    stale = bool(evidence_at and now - evidence_at > timedelta(days=stale_days))

    value = None if status == "not_applicable" else STATUS_VALUE[status]
    return ReqResult(
        id=req.id, area_id=req.area_id, weight=req.weight, technical=req.technical, status=status,
        basis=basis, value=value, attested_status=attested, automated_status=auto, reason=reason,
        capped=capped, stale=stale, evidence_at=evidence_at, checks=checks,
    )


def _weighted(results: list[ReqResult]) -> tuple[float | None, int]:
    scored = [r for r in results if r.value is not None]
    total_w = sum(r.weight for r in scored)
    if total_w == 0:
        return None, 0
    return sum(r.value * r.weight for r in scored) / total_w, total_w


def score(requirements: list[ReqInput], answers: dict[str, AnswerInput], check_map: dict[str, list[str]],
          observations: dict[str, list[Observation]], evidence_files: dict[str, list[datetime]],
          now: datetime, stale_days: int) -> ScoreResult:
    results = [
        score_requirement(r, answers.get(r.id), check_map.get(r.id, []), observations,
                          evidence_files.get(r.id, []), now, stale_days)
        for r in requirements
    ]
    areas: list[AreaResult] = []
    for area_id in dict.fromkeys(r.area_id for r in requirements):
        rs = [r for r in results if r.area_id == area_id]
        s, w = _weighted(rs)
        areas.append(AreaResult(area_id, s, w, _count(r.status for r in rs), _count(r.basis for r in rs)))
    overall, _ = _weighted(results)
    return ScoreResult(overall=overall, areas=areas, requirements=results)
