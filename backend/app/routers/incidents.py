from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db, utcnow
from ..incidents_service import clocks, notice, notice_pdf, parse_when
from ..models import INCIDENT_STATUSES, Incident, IncidentEvent, User
from ..security import require

router = APIRouter(prefix="/api/incidents", tags=["incidents"])
STATUS = "^(" + "|".join(INCIDENT_STATUSES) + ")$"


def _when(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    try:
        parse_when(v)
    except ValueError:
        raise ValueError("invalid date-time")
    return v


class IncidentIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field("", max_length=8000)
    severity: str = Field("medium", pattern="^(low|medium|high)$")
    discovered_at: str
    occurred_at: str | None = None
    data_categories: list[str] = []
    affected_count: int | None = Field(None, ge=0, le=1_000_000_000)
    systems: list[str] = []
    likely_consequences: str = Field("", max_length=4000)
    measures_taken: str = Field("", max_length=4000)
    contact: str = Field("", max_length=255)
    individuals_notice_needed: bool | None = None

    _d = field_validator("discovered_at")(lambda cls, v: _when(v))
    _o = field_validator("occurred_at")(lambda cls, v: _when(v))

    @field_validator("data_categories", "systems")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [s.strip()[:200] for s in v if s and s.strip()][:50]


class EventIn(BaseModel):
    kind: str = Field(pattern="^(note|status)$")
    text: str = Field("", max_length=4000)
    status: str | None = Field(None, pattern=STATUS)


class NotifiedIn(BaseModel):
    target: str = Field(pattern="^(regulator|individuals)$")
    at: str | None = None


def out(i: Incident, with_events: bool = False) -> dict:
    d = {c: getattr(i, c) for c in ("id", "title", "description", "status", "severity", "data_categories",
                                     "affected_count", "systems", "likely_consequences", "measures_taken", "contact",
                                     "individuals_notice_needed", "source")}
    d |= {"ref": f"INC-{i.id:04d}", "discovered_at": i.discovered_at.isoformat(),
          "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
          "regulator_notified_at": i.regulator_notified_at.isoformat() if i.regulator_notified_at else None,
          "individuals_notified_at": i.individuals_notified_at.isoformat() if i.individuals_notified_at else None,
          "clocks": clocks(i)}
    if with_events:
        d["events"] = [{"id": e.id, "at": e.at.isoformat(), "kind": e.kind, "text": e.text, "actor": e.actor_name}
                       for e in i.events]
    return d


def _event(i: Incident, actor: User, kind: str, text: str = "", at=None) -> None:
    i.events.append(IncidentEvent(kind=kind, text=text, actor_name=actor.display_name, at=at or utcnow()))


def _get(db: Session, iid: int) -> Incident:
    i = db.get(Incident, iid)
    if not i:
        raise HTTPException(404, "not_found")
    return i


@router.get("")
def list_incidents(db: Session = Depends(get_db), _=Depends(require("read"))):
    rows = db.execute(select(Incident).order_by(Incident.discovered_at.desc())).scalars()
    return [out(i) for i in rows]


@router.post("", status_code=201)
def create(body: IncidentIn, db: Session = Depends(get_db), actor: User = Depends(require("incidents.write"))):
    data = body.model_dump()
    discovered = parse_when(data.pop("discovered_at"))
    if discovered > utcnow():
        raise HTTPException(422, "discovered_in_future")
    occurred = data.pop("occurred_at")
    i = Incident(**data, discovered_at=discovered, occurred_at=parse_when(occurred) if occurred else None,
                 created_by_id=actor.id)
    db.add(i)
    db.flush()
    _event(i, actor, "created", body.title)
    audit.record(db, actor, "incident.create", "incident", i.id, {"title": i.title, "discovered_at": discovered.isoformat()})
    db.commit()
    return out(i, True)


@router.get("/{iid}")
def get(iid: int, db: Session = Depends(get_db), _=Depends(require("read"))):
    return out(_get(db, iid), True)


@router.put("/{iid}")
def update(iid: int, body: IncidentIn, db: Session = Depends(get_db), actor: User = Depends(require("incidents.write"))):
    i = _get(db, iid)
    data = body.model_dump()
    discovered = parse_when(data.pop("discovered_at"))
    occurred = data.pop("occurred_at")
    changed = [k for k, v in data.items() if getattr(i, k) != v]
    if discovered != i.discovered_at:
        changed.append("discovered_at")
    for k, v in data.items():
        setattr(i, k, v)
    i.discovered_at, i.occurred_at = discovered, parse_when(occurred) if occurred else None
    i.updated_at = utcnow()
    if changed:
        _event(i, actor, "edited", ", ".join(sorted(changed)))
    audit.record(db, actor, "incident.update", "incident", i.id, {"changed": sorted(changed)})
    db.commit()
    return out(i, True)


@router.post("/{iid}/events", status_code=201)
def add_event(iid: int, body: EventIn, db: Session = Depends(get_db), actor: User = Depends(require("incidents.write"))):
    i = _get(db, iid)
    if body.kind == "status":
        if not body.status:
            raise HTTPException(422, "status_required")
        _event(i, actor, "status", f"{i.status} → {body.status}" + (f": {body.text}" if body.text else ""))
        i.status = body.status
    else:
        if not body.text.strip():
            raise HTTPException(422, "text_required")
        _event(i, actor, "note", body.text.strip())
    i.updated_at = utcnow()
    audit.record(db, actor, f"incident.{body.kind}", "incident", i.id, {"status": i.status})
    db.commit()
    return out(i, True)


@router.post("/{iid}/notified")
def notified(iid: int, body: NotifiedIn, db: Session = Depends(get_db), actor: User = Depends(require("incidents.write"))):
    i = _get(db, iid)
    at = parse_when(body.at) if body.at else utcnow()
    if at < i.discovered_at:
        raise HTTPException(422, "notified_before_discovery")
    if body.target == "regulator":
        i.regulator_notified_at = at
        if i.status in ("open", "contained"):
            i.status = "notified"
    else:
        i.individuals_notified_at = at
    _event(i, actor, f"notified_{body.target}", at.isoformat(), at=at)
    audit.record(db, actor, f"incident.notified_{body.target}", "incident", i.id, {"at": at.isoformat()})
    db.commit()
    return out(i, True)


@router.get("/{iid}/notice")
def get_notice(iid: int, target: str = Query(pattern="^(regulator|individuals)$"),
               lang: str = Query("en", pattern="^(en|ar)$"), fmt: str = Query("json", pattern="^(json|pdf)$"),
               db: Session = Depends(get_db), actor: User = Depends(require("read"))):
    i = _get(db, iid)
    n = notice(db, i, target, lang)
    if fmt == "json":
        return n
    audit.record(db, actor, "report.generate", "report", f"incident-notice-{target}", {"incident": i.id, "lang": lang})
    db.commit()
    return Response(notice_pdf(n), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="INC-{i.id:04d}-{target}-{lang}.pdf"'})
