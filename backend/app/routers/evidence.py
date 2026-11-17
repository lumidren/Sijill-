from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..catalog import get_catalog
from ..config import get_settings
from ..db import get_db
from ..evidence_files import EvidenceError, path_of, store, verify
from ..models import EvidenceFile, User
from ..posture import take_snapshot
from ..security import require

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


def ev_out(f: EvidenceFile, db: Session) -> dict:
    who = db.get(User, f.uploaded_by_id) if f.uploaded_by_id else None
    return {"id": f.id, "requirement_id": f.requirement_id, "filename": f.filename, "content_type": f.content_type,
            "size": f.size, "sha256": f.sha256, "description": f.description,
            "uploaded_at": f.uploaded_at.isoformat(), "uploaded_by": who.display_name if who else None}


@router.get("")
def list_evidence(requirement_id: str | None = None, db: Session = Depends(get_db), _=Depends(require("read"))):
    q = select(EvidenceFile).order_by(EvidenceFile.uploaded_at.desc())
    if requirement_id:
        q = q.where(EvidenceFile.requirement_id == requirement_id)
    return [ev_out(f, db) for f in db.execute(q).scalars()]


@router.post("", status_code=201)
async def upload(file: UploadFile, requirement_id: str = Form(...), description: str = Form(""),
                 db: Session = Depends(get_db), actor: User = Depends(require("evidence.upload"))):
    if not get_catalog().requirement(requirement_id):
        raise HTTPException(404, "unknown_requirement")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    try:
        ev = store(db, data, file.filename or "evidence", requirement_id, actor, description)
    except EvidenceError as e:
        db.rollback()
        raise HTTPException(413 if e.code == "too_large" else 415 if e.code in ("bad_type", "content_mismatch") else 422, e.code)
    audit.record(db, actor, "evidence.upload", "evidence", ev.id,
                 {"requirement_id": requirement_id, "filename": ev.filename, "sha256": ev.sha256, "size": ev.size})
    take_snapshot(db, reason="evidence")
    db.commit()
    return ev_out(ev, db)


@router.get("/{ev_id}/download")
def download(ev_id: int, db: Session = Depends(get_db), _=Depends(require("read"))):
    ev = db.get(EvidenceFile, ev_id)
    if not ev:
        raise HTTPException(404, "not_found")
    if not verify(ev):
        raise HTTPException(409, "integrity_check_failed")
    return FileResponse(path_of(ev), media_type=ev.content_type, filename=ev.filename,
                        headers={"X-Content-SHA256": ev.sha256})
