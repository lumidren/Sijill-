from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__, audit
from ..catalog import get_catalog
from ..config import get_settings
from ..db import get_db
from ..models import AppSetting, User
from ..security import require

router = APIRouter(prefix="/api/settings", tags=["settings"])


class OrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    name_ar: str = Field("", max_length=200)
    sector: str = Field("", max_length=200)
    city: str = Field("", max_length=100)
    dpo: str = Field("", max_length=128)


@router.get("")
def read_settings(db: Session = Depends(get_db), _=Depends(require("read"))):
    s = get_settings()
    org = db.execute(select(AppSetting).where(AppSetting.key == "organization")).scalar_one_or_none()
    cat = get_catalog()
    return {
        "version": __version__,
        "organization": org.value if org else None,
        "legal_defaults": [
            {"key": "breach_regulator_hours", "value": s.breach_regulator_hours, "unit": "hours", "env": "PDPL_BREACH_REGULATOR_HOURS", "verified": False},
            {"key": "breach_individuals_hours", "value": s.breach_individuals_hours, "unit": "hours", "env": "PDPL_BREACH_INDIVIDUALS_HOURS", "verified": False},
            {"key": "licence_validity_years", "value": s.licence_validity_years, "unit": "years", "env": "PDPL_LICENCE_VALIDITY_YEARS", "verified": False},
            {"key": "dsr_response_days", "value": s.dsr_response_days, "unit": "days", "env": "PDPL_DSR_RESPONSE_DAYS", "verified": False},
        ],
        "policy": [
            {"key": "evidence_stale_days", "value": s.evidence_stale_days, "unit": "days", "env": "PDPL_EVIDENCE_STALE_DAYS"},
            {"key": "renewal_reminder_days", "value": s.renewal_reminder_days, "unit": "days", "env": "PDPL_RENEWAL_REMINDER_DAYS"},
            {"key": "collect_interval_hours", "value": s.collect_interval_hours, "unit": "hours", "env": "PDPL_COLLECT_INTERVAL_HOURS"},
            {"key": "max_upload_mb", "value": s.max_upload_mb, "unit": "MB", "env": "PDPL_MAX_UPLOAD_MB"},
            {"key": "risk_acceptance_max_days", "value": s.risk_acceptance_max_days, "unit": "days", "env": "PDPL_RISK_ACCEPTANCE_MAX_DAYS"},
        ],
        "timezone": s.timezone_display,
        "catalog": {"version": cat.version, "requirements": len(cat.requirements),
                    "unverified": sum(1 for r in cat.requirements if not r.verified)},
        "aws": {"profile_configured": bool(s.aws_profile), "role_configured": bool(s.aws_role_arn)},
    }


@router.put("/organization")
def update_org(body: OrgIn, db: Session = Depends(get_db), actor: User = Depends(require("settings.manage"))):
    row = db.execute(select(AppSetting).where(AppSetting.key == "organization")).scalar_one_or_none()
    value = {**(row.value if row else {}), **body.model_dump()}
    if row is None:
        db.add(AppSetting(key="organization", value=value))
    else:
        row.value = value
    audit.record(db, actor, "settings.organization", "settings", "organization", body.model_dump())
    db.commit()
    return value
