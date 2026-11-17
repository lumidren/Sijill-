from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..catalog import get_catalog
from ..db import get_db, utcnow
from ..models import ANSWER_STATUSES, Answer, EvidenceFile, User
from ..posture import current_score, take_snapshot
from ..security import require

router = APIRouter(prefix="/api/assessment", tags=["assessment"])

STATUS_PATTERN = "^(" + "|".join(ANSWER_STATUSES) + ")$"


class AnswerIn(BaseModel):
    status: str = Field(pattern=STATUS_PATTERN)
    note: str = Field(default="", max_length=4000)


def _answer_out(a: Answer | None, users: dict[int, str]) -> dict | None:
    if not a:
        return None
    return {"status": a.status, "note": a.note, "updated_at": a.updated_at.isoformat(),
            "updated_by": users.get(a.updated_by_id)}


@router.get("")
def overview(db: Session = Depends(get_db), _=Depends(require("read"))):
    """Every area with its requirements, the current answer, evidence count and live status."""
    cat = get_catalog()
    score = current_score(db)
    results = {r.id: r for r in score.requirements}
    area_scores = {a.id: a for a in score.areas}
    answers = {a.requirement_id: a for a in db.execute(select(Answer)).scalars()}
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars()}
    ev_counts = dict(db.execute(select(EvidenceFile.requirement_id, func.count()).group_by(EvidenceFile.requirement_id)).all())
    areas = []
    answered_total = 0
    for a in cat.areas:
        reqs = []
        answered = 0
        for r in a.requirements:
            ans = answers.get(r.id)
            if ans and ans.status != "not_assessed":
                answered += 1
            res = results[r.id]
            reqs.append({
                **r.as_dict(),
                "answer": _answer_out(ans, users),
                "evidence_count": ev_counts.get(r.id, 0),
                "result": {"status": res.status, "basis": res.basis, "capped": res.capped, "stale": res.stale,
                           "reason": res.reason, "failing_checks": res.failing_checks,
                           "passing_checks": res.passing_checks, "automated_status": res.automated_status},
            })
        answered_total += answered
        areas.append({**a.as_dict(with_requirements=False), "score": area_scores[a.id].score,
                      "answered": answered, "requirements": reqs})
    return {"answered": answered_total, "total": len(cat.requirements), "areas": areas}


@router.put("/answers/{req_id}")
def answer(req_id: str, body: AnswerIn, db: Session = Depends(get_db), actor: User = Depends(require("assessment.write"))):
    req = get_catalog().requirement(req_id)
    if not req:
        raise HTTPException(404, "unknown_requirement")
    a = db.execute(select(Answer).where(Answer.requirement_id == req_id)).scalar_one_or_none()
    before = {"status": a.status, "note": a.note} if a else None
    if a is None:
        a = Answer(requirement_id=req_id)
        db.add(a)
    a.status, a.note, a.updated_by_id, a.updated_at = body.status, body.note.strip(), actor.id, utcnow()
    db.flush()
    audit.record(db, actor, "assessment.answer", "requirement", req_id,
                 {"from": before, "to": {"status": body.status, "note": body.note.strip()[:500]}})
    take_snapshot(db, reason="assessment")
    db.commit()
    res = next(r for r in current_score(db).requirements if r.id == req_id)
    return {"requirement_id": req_id, "answer": _answer_out(a, {actor.id: actor.display_name}),
            "result": {"status": res.status, "basis": res.basis, "capped": res.capped, "stale": res.stale,
                       "reason": res.reason, "failing_checks": res.failing_checks,
                       "passing_checks": res.passing_checks, "automated_status": res.automated_status}}
