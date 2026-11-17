from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db, utcnow
from ..models import AppSetting, ProcessingActivity, User
from ..register_export import to_csv, to_pdf
from ..security import require

router = APIRouter(prefix="/api/register", tags=["register"])

ShortList = list[str]


class ActivityIn(BaseModel):
    role: str = Field("controller", pattern="^(controller|processor)$")
    name: str = Field(min_length=1, max_length=255)
    purpose: str = Field("", max_length=4000)
    lawful_basis: str = Field("", max_length=255)
    data_subjects: ShortList = []
    data_categories: ShortList = []
    sensitive_categories: ShortList = []
    source: str = Field("", max_length=255)
    recipients: ShortList = []
    cross_border: bool = False
    transfer_countries: ShortList = []
    transfer_safeguards: str = Field("", max_length=4000)
    retention: str = Field("", max_length=255)
    security_measures: str = Field("", max_length=4000)
    systems: ShortList = []
    client_name: str = Field("", max_length=255)
    owner: str = Field("", max_length=128)

    @field_validator("data_subjects", "data_categories", "sensitive_categories", "recipients",
                     "transfer_countries", "systems")
    @classmethod
    def _clean_list(cls, v: list[str]) -> list[str]:
        out = [s.strip()[:200] for s in v if s and s.strip()]
        if len(out) > 50:
            raise ValueError("too many items")
        return out


def out(a: ProcessingActivity) -> dict:
    return {c: getattr(a, c) for c in (
        "id", "role", "name", "purpose", "lawful_basis", "data_subjects", "data_categories", "sensitive_categories",
        "source", "recipients", "cross_border", "transfer_countries", "transfer_safeguards", "retention",
        "security_measures", "systems", "client_name", "owner", "status")} | {
        "updated_at": a.updated_at.isoformat(), "created_at": a.created_at.isoformat(),
        "ref": f"{'C' if a.role == 'controller' else 'P'}-{a.id:03d}",
        "issues": issues(a),
    }


def issues(a: ProcessingActivity) -> list[str]:
    """Plain-language completeness checks the UI turns into hints."""
    found = []
    if not a.purpose:
        found.append("missing_purpose")
    if a.role == "controller" and not a.lawful_basis:
        found.append("missing_lawful_basis")
    if not a.retention:
        found.append("missing_retention")
    if a.cross_border and not a.transfer_countries:
        found.append("missing_transfer_countries")
    if a.cross_border and not a.transfer_safeguards:
        found.append("missing_transfer_safeguards")
    if a.sensitive_categories and not a.security_measures:
        found.append("sensitive_without_measures")
    if a.role == "processor" and not a.client_name:
        found.append("missing_client")
    return found


@router.get("")
def list_activities(include_archived: bool = False, db: Session = Depends(get_db), _=Depends(require("read"))):
    q = select(ProcessingActivity).order_by(ProcessingActivity.role, ProcessingActivity.id)
    if not include_archived:
        q = q.where(ProcessingActivity.status == "active")
    return [out(a) for a in db.execute(q).scalars()]


@router.post("", status_code=201)
def create(body: ActivityIn, db: Session = Depends(get_db), actor: User = Depends(require("register.write"))):
    a = ProcessingActivity(**body.model_dump(), updated_by_id=actor.id)
    db.add(a)
    db.flush()
    audit.record(db, actor, "register.create", "processing_activity", a.id, {"name": a.name, "role": a.role})
    db.commit()
    return out(a)


@router.put("/{aid}")
def update(aid: int, body: ActivityIn, db: Session = Depends(get_db), actor: User = Depends(require("register.write"))):
    a = db.get(ProcessingActivity, aid)
    if not a:
        raise HTTPException(404, "not_found")
    before = out(a)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    a.updated_at, a.updated_by_id = utcnow(), actor.id
    changed = sorted(k for k, v in body.model_dump().items() if before.get(k) != v)
    audit.record(db, actor, "register.update", "processing_activity", a.id, {"changed": changed})
    db.commit()
    return out(a)


@router.post("/{aid}/archive")
def archive(aid: int, db: Session = Depends(get_db), actor: User = Depends(require("register.write"))):
    a = db.get(ProcessingActivity, aid)
    if not a:
        raise HTTPException(404, "not_found")
    a.status = "archived" if a.status == "active" else "active"
    a.updated_at, a.updated_by_id = utcnow(), actor.id
    audit.record(db, actor, "register.archive" if a.status == "archived" else "register.restore",
                 "processing_activity", a.id, {"name": a.name})
    db.commit()
    return out(a)


@router.get("/export")
def export(role: str = Query("controller", pattern="^(controller|processor)$"),
           fmt: str = Query("csv", pattern="^(csv|pdf)$"), lang: str = Query("en", pattern="^(en|ar)$"),
           db: Session = Depends(get_db), actor: User = Depends(require("reports.generate"))):
    rows = list(db.execute(select(ProcessingActivity).where(ProcessingActivity.role == role,
                                                            ProcessingActivity.status == "active")
                           .order_by(ProcessingActivity.id)).scalars())
    org_row = db.execute(select(AppSetting).where(AppSetting.key == "organization")).scalar_one_or_none()
    org = org_row.value if org_row else {}
    stamp = utcnow().strftime("%Y%m%d")
    audit.record(db, actor, "report.generate", "report", f"register-{role}-{fmt}", {"lang": lang})
    db.commit()
    if fmt == "csv":
        return Response(to_csv(rows, role), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="pdpl-{role}-register-{stamp}.csv"'})
    return Response(to_pdf(rows, role, lang, org), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="pdpl-{role}-register-{lang}-{stamp}.pdf"'})
