"""Organisations: switch between clients, manage them, and see all of them at a glance.

A consultant or DPO serving several small organisations keeps each one fully separate (its own
assessment, evidence, registers and reports) and still sees where every client stands on one page.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import ORG_COOKIE, get_db, org_session
from ..models import AppSetting, Organisation, User
from ..security import allowed_orgs, current_user, require

router = APIRouter(prefix="/api/orgs", tags=["organisations"])


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sector: str = Field("", max_length=200)


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class Select(BaseModel):
    id: int


def org_out(o: Organisation) -> dict:
    return {"id": o.id, "name": o.name, "archived": o.archived, "created_at": o.created_at.isoformat()}


def set_org_cookie(resp: Response, org_id: int) -> None:
    s = get_settings()
    resp.set_cookie(ORG_COOKIE, str(org_id), httponly=True, samesite="strict", secure=s.cookie_secure,
                    max_age=s.session_hours * 3600, path="/")


@router.get("")
def list_orgs(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"current": request.state.org_id, "items": [org_out(o) for o in allowed_orgs(db, user)]}


@router.post("/select")
def select_org(body: Select, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.id not in {o.id for o in allowed_orgs(db, user)}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no_access_to_organisation")
    set_org_cookie(response, body.id)
    return {"current": body.id}


@router.get("/all")
def all_orgs(db: Session = Depends(get_db), _=Depends(require("orgs.manage"))):
    """Every organisation, archived ones included (for the admin's management view)."""
    return [org_out(o) for o in db.execute(select(Organisation).order_by(Organisation.id)).scalars()]


@router.post("", status_code=201)
def create_org(body: OrgCreate, db: Session = Depends(get_db), actor: User = Depends(require("orgs.manage"))):
    o = Organisation(name=body.name.strip())
    db.add(o)
    db.flush()
    # The new organisation's profile lives in its own settings, like every other organisation's.
    db.add(AppSetting(org_id=o.id, key="organization", value={"name": o.name, "sector": body.sector}))
    audit.record(db, actor, "organisation.create", "organisation", o.id, {"name": o.name})
    db.commit()
    return org_out(o)


@router.patch("/{org_id}")
def update_org(org_id: int, body: OrgPatch, db: Session = Depends(get_db), actor: User = Depends(require("orgs.manage"))):
    o = db.get(Organisation, org_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    changes: dict = {}
    if body.name is not None and body.name.strip() != o.name:
        changes["name"] = {"from": o.name, "to": body.name.strip()}
        o.name = body.name.strip()
        with org_session(o.id) as s:
            row = s.execute(select(AppSetting).where(AppSetting.key == "organization")).scalar_one_or_none()
            if row:
                row.value = {**row.value, "name": o.name}
                s.commit()
    if body.archived is not None and body.archived != o.archived:
        if body.archived:
            active = db.execute(select(Organisation).where(Organisation.archived.is_(False))).scalars().all()
            if len(active) <= 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "last_active_organisation")
        o.archived = body.archived
        changes["archived"] = body.archived
    audit.record(db, actor, "organisation.update", "organisation", o.id, changes)
    db.commit()
    return org_out(o)


def client_summary(org: Organisation) -> dict:
    """One row of the client overview, computed in a session that only sees that organisation."""
    from ..governance import summary as governance_summary
    from ..posture import current_score, latest_runs

    with org_session(org.id) as s:
        res = current_score(s)
        counts = res.counts()
        gov = governance_summary(s)
        runs = latest_runs(s)
        try:
            from ..incidents_service import active_clocks
            breaches = active_clocks(s)
        except ModuleNotFoundError:
            breaches = []
        gaps = sum(1 for r in res.requirements if r.status in ("non_compliant", "partial"))
    return {
        **org_out(org),
        "overall": res.overall,
        "counts": counts,
        "gaps": gaps,
        "risks_high": gov["risks"]["by_level"].get("critical", 0) + gov["risks"]["by_level"].get("high", 0),
        "tasks_overdue": gov["tasks"]["overdue"],
        "requests_overdue": gov["requests"]["overdue"],
        "vendors_without_dpa": gov["vendors"]["without_dpa"],
        "open_breaches": len(breaches),
        "last_run": runs[0].started_at.isoformat() if runs else None,
    }


@router.get("/overview")
def overview(request: Request, db: Session = Depends(get_db), user: User = Depends(require("read"))):
    return {"current": request.state.org_id, "items": [client_summary(o) for o in allowed_orgs(db, user)]}
