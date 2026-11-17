from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import verify_chain
from ..db import get_db
from ..models import AuditLog
from ..security import require

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), _=Depends(require("audit.read"))):
    total = db.scalar(select(func.count()).select_from(AuditLog))
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)).scalars()
    return {
        "total": total,
        "items": [
            {"id": e.id, "at": e.at.isoformat(), "actor": e.actor_name, "action": e.action,
             "entity_type": e.entity_type, "entity_id": e.entity_id, "detail": e.detail, "hash": e.hash}
            for e in rows
        ],
    }


@router.get("/verify")
def verify(db: Session = Depends(get_db), _=Depends(require("audit.read"))):
    ok, bad = verify_chain(db)
    return {"ok": ok, "first_bad_id": bad}
