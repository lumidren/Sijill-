"""HTTP API for tasks, risks, data subject requests, vendors, DPIAs and policies.

Every write is role-checked and audited; list and get are open to every signed-in role.
"""
from datetime import date, timedelta
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..catalog import get_catalog
from ..config import get_settings
from ..db import Base, get_db, utcnow
from ..governance import (
    DPIA_CRITERIA, day, dpia_out, policy_out, request_out, risk_out, summary, task_out, vendor_out,
)
from ..incidents_service import parse_when
from ..models import DataRequest, Dpia, Policy, ProcessingActivity, Risk, Task, User, Vendor
from ..security import require

router = APIRouter(tags=["governance"])


def _clean_list(v: list[str]) -> list[str]:
    return [s.strip()[:200] for s in v if s and s.strip()][:50]


def _check_requirements(ids: list[str]) -> list[str]:
    cat = get_catalog()
    bad = [i for i in ids if not cat.requirement(i)]
    if bad:
        raise HTTPException(422, f"unknown_requirement: {bad[0]}")
    return ids


# ------------------------------------------------------------------ schemas

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field("", max_length=4000)
    requirement_id: str | None = None
    source: str = Field("manual", pattern="^(gap|risk|incident|dpia|vendor|manual)$")
    source_id: str = Field("", max_length=64)
    owner: str = Field("", max_length=128)
    priority: str = Field("medium", pattern="^(low|medium|high)$")
    status: str = Field("todo", pattern="^(todo|in_progress|blocked|done)$")
    due_on: date | None = None
    notes: str = Field("", max_length=4000)


class RiskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field("", max_length=4000)
    category: str = Field("", max_length=64)
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    residual_likelihood: int | None = Field(None, ge=1, le=5)
    residual_impact: int | None = Field(None, ge=1, le=5)
    treatment: str = Field("mitigate", pattern="^(mitigate|accept|transfer|avoid)$")
    status: str = Field("open", pattern="^(open|treating|closed)$")  # "accepted" only via /accept
    owner: str = Field("", max_length=128)
    requirement_ids: list[str] = []
    controls: str = Field("", max_length=4000)
    review_due: date | None = None


class AcceptIn(BaseModel):
    note: str = Field(min_length=5, max_length=2000)
    expires_on: date


class RequestIn(BaseModel):
    request_type: str = Field(pattern="^(access|correction|deletion|objection|withdraw_consent|portability|other)$")
    requester: str = Field(min_length=1, max_length=128)
    channel: str = Field("", max_length=64)
    received_at: str
    identity_verified: bool = False
    status: str = Field("received", pattern="^(received|in_progress|completed|refused)$")
    details: str = Field("", max_length=4000)
    outcome: str = Field("", max_length=4000)
    owner: str = Field("", max_length=128)

    @field_validator("received_at")
    @classmethod
    def _when(cls, v: str) -> str:
        parse_when(v)
        return v


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    service: str = Field("", max_length=255)
    role: str = Field("processor", pattern="^(processor|sub_processor|recipient)$")
    data_categories: list[str] = []
    countries: list[str] = []
    dpa_signed: bool = False
    dpa_signed_on: date | None = None
    due_diligence_on: date | None = None
    next_review_on: date | None = None
    risk_level: str = Field("medium", pattern="^(low|medium|high)$")
    security_notes: str = Field("", max_length=4000)
    status: str = Field("active", pattern="^(active|offboarded)$")
    owner: str = Field("", max_length=128)

    @field_validator("data_categories", "countries")
    @classmethod
    def _lists(cls, v: list[str]) -> list[str]:
        return _clean_list(v)


class DpiaIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    activity_id: int | None = None
    screening: dict[str, bool | None] = {}
    description: str = Field("", max_length=8000)
    necessity: str = Field("", max_length=8000)
    risks: str = Field("", max_length=8000)
    measures: str = Field("", max_length=8000)
    residual_risk: str = Field("", pattern="^(|low|medium|high)$")
    dpo_opinion: str = Field("", max_length=4000)
    status: str = Field("draft", pattern="^(draft|in_review)$")  # approval only via /approve
    review_due: date | None = None
    owner: str = Field("", max_length=128)

    @field_validator("screening")
    @classmethod
    def _criteria(cls, v: dict) -> dict:
        unknown = set(v) - set(DPIA_CRITERIA)
        if unknown:
            raise ValueError(f"unknown criteria {sorted(unknown)}")
        return v


class PolicyIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z.\-]+$")
    owner: str = Field("", max_length=128)
    summary: str = Field("", max_length=4000)
    requirement_ids: list[str] = []
    evidence_file_id: int | None = None
    review_due: date | None = None
    status: str = Field("draft", pattern="^(draft|retired)$")  # approval only via /approve


# ------------------------------------------------------------------ generic CRUD

def _crud(prefix: str, model: type[Base], schema: type[BaseModel], write_cap: str, entity: str,
          out: Callable[[Session, object], dict], apply: Callable[[Session, object, BaseModel, User], None],
          order: Callable[[list], list] = lambda rows: rows) -> None:
    @router.get(prefix, name=f"list_{entity}")
    def list_rows(db: Session = Depends(get_db), _=Depends(require("read"))):
        return [out(db, r) for r in order(list(db.execute(select(model)).scalars()))]

    @router.get(prefix + "/{rid}", name=f"get_{entity}")
    def get_row(rid: int, db: Session = Depends(get_db), _=Depends(require("read"))):
        row = db.get(model, rid)
        if not row:
            raise HTTPException(404, "not_found")
        return out(db, row)

    @router.post(prefix, status_code=201, name=f"create_{entity}")
    def create_row(body: schema, db: Session = Depends(get_db), actor: User = Depends(require(write_cap))):  # type: ignore[valid-type]
        row = model(updated_by_id=actor.id)
        apply(db, row, body, actor)
        db.add(row)
        db.flush()
        audit.record(db, actor, f"{entity}.create", entity, row.id, {"title": getattr(row, "title", None) or getattr(row, "name", None) or getattr(row, "requester", "")})
        db.commit()
        return out(db, row)

    @router.put(prefix + "/{rid}", name=f"update_{entity}")
    def update_row(rid: int, body: schema, db: Session = Depends(get_db), actor: User = Depends(require(write_cap))):  # type: ignore[valid-type]
        row = db.get(model, rid)
        if not row:
            raise HTTPException(404, "not_found")
        before = out(db, row)
        apply(db, row, body, actor)
        row.updated_at, row.updated_by_id = utcnow(), actor.id
        after = out(db, row)
        changed = sorted(k for k in after if k not in ("updated_at", "days_left", "days_to_review") and before.get(k) != after.get(k))
        audit.record(db, actor, f"{entity}.update", entity, row.id, {"changed": changed})
        db.commit()
        return out(db, row)


# ------------------------------------------------------------------ tasks

def _apply_task(db, t: Task, b: TaskIn, actor):
    if b.requirement_id:
        _check_requirements([b.requirement_id])
    data = b.model_dump()
    due = data.pop("due_on")
    was_done = t.status == "done"
    for k, v in data.items():
        setattr(t, k, v)
    t.due_on = day(due)
    if b.status == "done" and not was_done:
        t.completed_at = utcnow()
    elif b.status != "done":
        t.completed_at = None


_crud("/api/tasks", Task, TaskIn, "tasks.write", "task", lambda db, t: task_out(t, utcnow()), _apply_task,
      order=lambda rows: sorted(rows, key=lambda t: (t.status == "done", t.due_on is None, t.due_on or utcnow(), t.id)))


# ------------------------------------------------------------------ risks

def _apply_risk(db, r: Risk, b: RiskIn, actor):
    _check_requirements(b.requirement_ids)
    data = b.model_dump()
    review = data.pop("review_due")
    for k, v in data.items():
        setattr(r, k, v)
    r.review_due = day(review)
    # editing an accepted risk re-opens it: acceptance must be given again for the new facts
    r.accepted_by_id = r.accepted_at = r.acceptance_expires_on = None
    r.acceptance_note = ""


_crud("/api/risks", Risk, RiskIn, "governance.write", "risk", lambda db, r: risk_out(r, utcnow()), _apply_risk,
      order=lambda rows: sorted(rows, key=lambda r: (r.status == "closed", -(r.likelihood * r.impact), r.id)))


@router.post("/api/risks/{rid}/accept")
def accept_risk(rid: int, body: AcceptIn, db: Session = Depends(get_db), actor: User = Depends(require("risks.accept"))):
    r = db.get(Risk, rid)
    if not r:
        raise HTTPException(404, "not_found")
    today = utcnow().date()
    if body.expires_on <= today:
        raise HTTPException(422, "expiry_in_past")
    if body.expires_on > today + timedelta(days=get_settings().risk_acceptance_max_days):
        raise HTTPException(422, "expiry_too_far")
    r.status, r.treatment = "accepted", "accept"
    r.accepted_by_id, r.accepted_at = actor.id, utcnow()
    r.acceptance_expires_on, r.acceptance_note = day(body.expires_on), body.note.strip()
    r.updated_at, r.updated_by_id = utcnow(), actor.id
    audit.record(db, actor, "risk.accept", "risk", r.id, {"expires_on": body.expires_on.isoformat(), "note": body.note[:300]})
    db.commit()
    return risk_out(r, utcnow())


# ------------------------------------------------------------------ data subject requests

def _apply_request(db, r: DataRequest, b: RequestIn, actor):
    data = b.model_dump()
    received = parse_when(data.pop("received_at"))
    if received > utcnow():
        raise HTTPException(422, "received_in_future")
    was_closed = r.status in ("completed", "refused")
    for k, v in data.items():
        setattr(r, k, v)
    r.received_at = received
    if b.status in ("completed", "refused") and not was_closed:
        r.completed_at = utcnow()
    elif b.status not in ("completed", "refused"):
        r.completed_at = None


_crud("/api/requests", DataRequest, RequestIn, "governance.write", "data_request",
      lambda db, r: request_out(r, utcnow()), _apply_request,
      order=lambda rows: sorted(rows, key=lambda r: (r.status in ("completed", "refused"), r.received_at)))


# ------------------------------------------------------------------ vendors

def _apply_vendor(db, v: Vendor, b: VendorIn, actor):
    data = b.model_dump()
    for k in ("dpa_signed_on", "due_diligence_on", "next_review_on"):
        data[k] = day(data[k])
    for k, val in data.items():
        setattr(v, k, val)


_crud("/api/vendors", Vendor, VendorIn, "governance.write", "vendor", lambda db, v: vendor_out(v, utcnow()), _apply_vendor,
      order=lambda rows: sorted(rows, key=lambda v: (v.status != "active", v.name.lower())))


# ------------------------------------------------------------------ DPIAs

def _activity_names(db: Session) -> dict[int, str]:
    return {a.id: a.name for a in db.execute(select(ProcessingActivity)).scalars()}


def _apply_dpia(db, d: Dpia, b: DpiaIn, actor):
    if b.activity_id is not None and not db.get(ProcessingActivity, b.activity_id):
        raise HTTPException(422, "unknown_activity")
    data = b.model_dump()
    review = data.pop("review_due")
    for k, v in data.items():
        setattr(d, k, v)
    d.review_due = day(review)
    d.approved_by_id = d.approved_at = None  # any edit needs a fresh approval


_crud("/api/dpias", Dpia, DpiaIn, "governance.write", "dpia", lambda db, d: dpia_out(d, utcnow(), _activity_names(db)), _apply_dpia)


@router.post("/api/dpias/{did}/approve")
def approve_dpia(did: int, db: Session = Depends(get_db), actor: User = Depends(require("approve"))):
    d = db.get(Dpia, did)
    if not d:
        raise HTTPException(404, "not_found")
    if d.status != "in_review":
        raise HTTPException(409, "not_in_review")
    if not d.dpo_opinion.strip() or not d.residual_risk:
        raise HTTPException(422, "opinion_and_residual_risk_required")
    d.status, d.approved_by_id, d.approved_at = "approved", actor.id, utcnow()
    audit.record(db, actor, "dpia.approve", "dpia", d.id, {"residual_risk": d.residual_risk})
    db.commit()
    return dpia_out(d, utcnow(), _activity_names(db))


# ------------------------------------------------------------------ policies

def _apply_policy(db, p: Policy, b: PolicyIn, actor):
    _check_requirements(b.requirement_ids)
    data = b.model_dump()
    review = data.pop("review_due")
    new_version = data["version"] != p.version and p.id is not None
    for k, v in data.items():
        setattr(p, k, v)
    p.review_due = day(review)
    if new_version or p.id is None:
        p.approved_by_id = p.approved_on = None
        p.history = (p.history or []) + [{"version": p.version, "status": p.status, "at": utcnow().isoformat(),
                                          "by": actor.display_name}]


_crud("/api/policies", Policy, PolicyIn, "governance.write", "policy", lambda db, p: policy_out(p, utcnow()), _apply_policy,
      order=lambda rows: sorted(rows, key=lambda p: (p.status == "retired", p.title.lower())))


@router.post("/api/policies/{pid}/approve")
def approve_policy(pid: int, db: Session = Depends(get_db), actor: User = Depends(require("approve"))):
    p = db.get(Policy, pid)
    if not p:
        raise HTTPException(404, "not_found")
    if p.status == "retired":
        raise HTTPException(409, "retired")
    p.status, p.approved_by_id, p.approved_on = "approved", actor.id, utcnow()
    p.history = (p.history or []) + [{"version": p.version, "status": "approved", "at": utcnow().isoformat(),
                                      "by": actor.display_name}]
    audit.record(db, actor, "policy.approve", "policy", p.id, {"version": p.version})
    db.commit()
    return policy_out(p, utcnow())


# ------------------------------------------------------------------ summary

@router.get("/api/governance/summary")
def governance_summary(db: Session = Depends(get_db), _=Depends(require("read"))):
    return summary(db)
