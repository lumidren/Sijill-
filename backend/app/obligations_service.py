"""Licensing questionnaire, applicability screener, obligations, renewal dates and reminders.

Every outcome is phrased as "likely": the rules encode the project brief's working context, not
verified legal text (see docs/LEGAL-REVIEW.md). Question and result wording lives in the UI's
string tables; this module deals in keys only.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import local_date, utcnow
from .models import AppSetting, Obligation, Reminder

LICENSING_QUESTIONS = ["controls_processing", "processes_for_others", "cross_border", "electronic_marketing",
                       "surveillance", "sensitive_data"]
# result key -> (question that triggers it, obligation kind it becomes)
LICENSING_RULES = {
    "controller_licence": ("controls_processing", "licence"),
    "processor_licence": ("processes_for_others", "licence"),
    "cross_border_permit": ("cross_border", "permit"),
    "marketing_permit": ("electronic_marketing", "permit"),
    "surveillance_permit": ("surveillance", "permit"),
}
SCREENER_QUESTIONS = ["processes_personal_data", "cbe_supervised", "money_transfer_or_exchange"]
ACTIVE_STATUSES = ("planned", "applied", "active")


def evaluate_licensing(answers: dict[str, bool | None]) -> dict:
    results = []
    for key, (question, kind) in LICENSING_RULES.items():
        a = answers.get(question)
        results.append({"key": key, "kind": kind, "question": question,
                        "likely_required": True if a is True else (False if a is False else None)})
    notes = ["sensitive_data_conditions"] if answers.get("sensitive_data") else []
    answered = sum(1 for q in LICENSING_QUESTIONS if answers.get(q) is not None)
    return {"results": results, "notes": notes, "complete": answered == len(LICENSING_QUESTIONS)}


def evaluate_applicability(answers: dict[str, bool | None]) -> dict:
    """Which side of the line is the organisation likely on?"""
    if answers.get("processes_personal_data") is None or answers.get("cbe_supervised") is None:
        return {"result": "incomplete", "reason": None}
    if answers["processes_personal_data"] is False:
        return {"result": "likely_out_of_scope", "reason": "no_personal_data"}
    if answers["cbe_supervised"] is True:
        exception = answers.get("money_transfer_or_exchange")
        if exception is None:
            return {"result": "incomplete", "reason": None}
        if exception:
            return {"result": "likely_in_scope", "reason": "cbe_exception"}
        return {"result": "likely_out_of_scope", "reason": "cbe_supervised"}
    return {"result": "likely_in_scope", "reason": "processes_personal_data"}


def get_answers(db: Session, key: str) -> dict:
    row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    return dict(row.value) if row else {}


def save_answers(db: Session, key: str, answers: dict) -> None:
    row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=key, value=answers))
    else:
        row.value = answers


def default_expiry(kind: str, issued_on: datetime | None) -> datetime | None:
    """Licences get the configured validity when no expiry date is entered."""
    if kind != "licence" or issued_on is None:
        return None
    years = get_settings().licence_validity_years
    try:
        return issued_on.replace(year=issued_on.year + years)
    except ValueError:  # 29 February
        return issued_on.replace(year=issued_on.year + years, day=28)


def effective_status(o: Obligation, now: datetime) -> str:
    if o.status == "active" and o.expires_on and o.expires_on < now:
        return "expired"
    return o.status


def _days(target: datetime | None, now: datetime) -> int | None:
    if target is None:
        return None
    # whole days, rounding toward the past so "due today" is 0 and yesterday is -1
    return (target.date() - local_date(now)).days


def upcoming_deadlines(db: Session, now: datetime | None = None, horizon_days: int = 90) -> list[dict]:
    now = now or utcnow()
    out = []
    for o in db.execute(select(Obligation).where(Obligation.status.in_(ACTIVE_STATUSES))).scalars():
        for kind, date in (("expiry", o.expires_on), ("review", o.review_due)):
            d = _days(date, now)
            if d is not None and d <= horizon_days:
                out.append({"id": o.id, "kind": kind, "obligation_kind": o.kind, "title": o.title,
                            "due": date.isoformat(), "days_left": d})
    return sorted(out, key=lambda x: x["days_left"])


def generate_reminders(db: Session, now: datetime | None = None) -> int:
    """Create one reminder per obligation date that falls inside the reminder window (or has passed)."""
    now = now or utcnow()
    window = get_settings().renewal_reminder_days
    created = 0
    for o in db.execute(select(Obligation).where(Obligation.status.in_(ACTIVE_STATUSES))).scalars():
        for kind, date in (("expiry", o.expires_on), ("review", o.review_due)):
            d = _days(date, now)
            if d is None or d > window:
                continue
            exists = db.execute(select(Reminder.id).where(Reminder.obligation_id == o.id, Reminder.kind == kind,
                                                          Reminder.due == date)).first()
            if exists:
                continue
            try:
                with db.begin_nested():
                    db.add(Reminder(obligation_id=o.id, kind=kind, due=date, created_at=now))
                created += 1
            except IntegrityError:
                pass
    return created


def obligation_out(o: Obligation, now: datetime | None = None) -> dict:
    now = now or utcnow()
    return {
        "id": o.id, "kind": o.kind, "title": o.title, "reference": o.reference, "status": o.status,
        "effective_status": effective_status(o, now),
        "issued_on": o.issued_on.date().isoformat() if o.issued_on else None,
        "expires_on": o.expires_on.date().isoformat() if o.expires_on else None,
        "review_due": o.review_due.date().isoformat() if o.review_due else None,
        "expiry_from_default": o.expiry_from_default,
        "days_to_expiry": _days(o.expires_on, now), "days_to_review": _days(o.review_due, now),
        "owner": o.owner, "notes": o.notes, "details": o.details or {},
        "updated_at": o.updated_at.isoformat(),
    }


def reminder_window() -> timedelta:
    return timedelta(days=get_settings().renewal_reminder_days)
