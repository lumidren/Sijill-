from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db, utcnow
from ..models import OBLIGATION_KINDS, OBLIGATION_STATUSES, Obligation, Reminder, User
from ..obligations_service import (
    LICENSING_QUESTIONS, SCREENER_QUESTIONS, default_expiry, evaluate_applicability, evaluate_licensing,
    generate_reminders, get_answers, obligation_out, save_answers, upcoming_deadlines,
)
from ..security import require

router = APIRouter(prefix="/api/obligations", tags=["obligations"])
KIND = "^(" + "|".join(OBLIGATION_KINDS) + ")$"
STATUS = "^(" + "|".join(OBLIGATION_STATUSES) + ")$"


def _dt(d: date | None) -> datetime | None:
    # Dates are stored as midday UTC so they stay on the same calendar day in Africa/Cairo (UTC+2/+3).
    return datetime.combine(d, time(12, 0), tzinfo=timezone.utc) if d else None


class AnswersIn(BaseModel):
    answers: dict[str, bool | None]


class ObligationIn(BaseModel):
    kind: str = Field(pattern=KIND)
    title: str = Field(min_length=1, max_length=255)
    reference: str = Field("", max_length=128)
    status: str = Field("planned", pattern=STATUS)
    issued_on: date | None = None
    expires_on: date | None = None
    review_due: date | None = None
    owner: str = Field("", max_length=128)
    notes: str = Field("", max_length=4000)
    details: dict[str, str] = {}


@router.get("/questionnaires")
def questionnaires(db: Session = Depends(get_db), _=Depends(require("read"))):
    lic = get_answers(db, "licensing")
    app = get_answers(db, "applicability")
    return {
        "licensing": {"questions": LICENSING_QUESTIONS, "answers": lic, **evaluate_licensing(lic)},
        "applicability": {"questions": SCREENER_QUESTIONS, "answers": app, **evaluate_applicability(app)},
        "licence_validity_years": get_settings().licence_validity_years,
    }


def _save(db: Session, actor: User, key: str, allowed: list[str], body: AnswersIn) -> dict:
    unknown = set(body.answers) - set(allowed)
    if unknown:
        raise HTTPException(422, f"unknown_questions: {sorted(unknown)}")
    save_answers(db, key, body.answers)
    audit.record(db, actor, f"questionnaire.{key}", "questionnaire", key, {"answers": body.answers})
    db.commit()
    return body.answers


@router.put("/questionnaires/licensing")
def save_licensing(body: AnswersIn, db: Session = Depends(get_db), actor: User = Depends(require("obligations.write"))):
    answers = _save(db, actor, "licensing", LICENSING_QUESTIONS, body)
    return {"answers": answers, **evaluate_licensing(answers)}


@router.put("/questionnaires/applicability")
def save_applicability(body: AnswersIn, db: Session = Depends(get_db), actor: User = Depends(require("obligations.write"))):
    answers = _save(db, actor, "applicability", SCREENER_QUESTIONS, body)
    return {"answers": answers, **evaluate_applicability(answers)}


@router.get("")
def list_obligations(db: Session = Depends(get_db), _=Depends(require("read"))):
    now = utcnow()
    rows = db.execute(select(Obligation).order_by(Obligation.kind, Obligation.id)).scalars()
    return [obligation_out(o, now) for o in rows]


def _apply(o: Obligation, body: ObligationIn) -> None:
    o.kind, o.title, o.reference, o.status = body.kind, body.title.strip(), body.reference.strip(), body.status
    o.issued_on, o.review_due = _dt(body.issued_on), _dt(body.review_due)
    o.owner, o.notes, o.details = body.owner, body.notes, body.details
    if body.expires_on:
        o.expires_on, o.expiry_from_default = _dt(body.expires_on), False
    else:
        o.expires_on = default_expiry(body.kind, o.issued_on)
        o.expiry_from_default = o.expires_on is not None
    if o.issued_on and o.expires_on and o.expires_on < o.issued_on:
        raise HTTPException(422, "expiry_before_issue")


@router.post("", status_code=201)
def create(body: ObligationIn, db: Session = Depends(get_db), actor: User = Depends(require("obligations.write"))):
    o = Obligation(updated_by_id=actor.id)
    _apply(o, body)
    db.add(o)
    db.flush()
    generate_reminders(db)
    audit.record(db, actor, "obligation.create", "obligation", o.id, {"kind": o.kind, "title": o.title})
    db.commit()
    return obligation_out(o)


@router.put("/{oid}")
def update(oid: int, body: ObligationIn, db: Session = Depends(get_db), actor: User = Depends(require("obligations.write"))):
    o = db.get(Obligation, oid)
    if not o:
        raise HTTPException(404, "not_found")
    _apply(o, body)
    o.updated_at, o.updated_by_id = utcnow(), actor.id
    generate_reminders(db)
    audit.record(db, actor, "obligation.update", "obligation", o.id,
                 {"status": o.status, "expires_on": o.expires_on.isoformat() if o.expires_on else None})
    db.commit()
    return obligation_out(o)


@router.get("/deadlines")
def deadlines(db: Session = Depends(get_db), _=Depends(require("read"))):
    return upcoming_deadlines(db)


@router.get("/reminders")
def reminders(db: Session = Depends(get_db), _=Depends(require("read"))):
    now = utcnow()
    rows = db.execute(select(Reminder, Obligation).join(Obligation, Obligation.id == Reminder.obligation_id)
                      .where(Reminder.dismissed_at.is_(None)).order_by(Reminder.due)).all()
    return [{"id": r.id, "kind": r.kind, "due": r.due.isoformat(), "days_left": (r.due.date() - now.date()).days,
             "obligation": {"id": o.id, "title": o.title, "kind": o.kind}} for r, o in rows]


@router.post("/reminders/{rid}/dismiss")
def dismiss(rid: int, db: Session = Depends(get_db), actor: User = Depends(require("obligations.write"))):
    r = db.get(Reminder, rid)
    if not r:
        raise HTTPException(404, "not_found")
    r.dismissed_at, r.dismissed_by_id = utcnow(), actor.id
    audit.record(db, actor, "reminder.dismiss", "reminder", r.id, {"obligation_id": r.obligation_id})
    db.commit()
    return {"ok": True}
