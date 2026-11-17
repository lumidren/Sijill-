from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import audit
from ..catalog import CatalogError, get_catalog, parse, reload_catalog, to_oscal
from ..config import get_settings
from ..db import get_db
from ..models import User
from ..security import require

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

MAX_CATALOG_BYTES = 5 * 1024 * 1024


@router.get("")
def get(_=Depends(require("read"))):
    cat = get_catalog()
    return {
        "uuid": cat.uuid, "title": cat.title, "version": cat.version, "last_modified": cat.last_modified,
        "unverified_count": sum(1 for r in cat.requirements if not r.verified),
        "requirement_count": len(cat.requirements),
        "areas": [a.as_dict() for a in cat.areas],
    }


@router.get("/oscal")
def export_oscal(_=Depends(require("read"))):
    return to_oscal(get_catalog())


@router.post("/import")
async def import_catalog(file: UploadFile, db: Session = Depends(get_db),
                         actor: User = Depends(require("settings.manage"))):
    """Replace the catalog with a reviewed OSCAL catalog (e.g. after legal review)."""
    raw = await file.read(MAX_CATALOG_BYTES + 1)
    if len(raw) > MAX_CATALOG_BYTES:
        raise HTTPException(413, "too_large")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "bad_json")
    try:
        cat = parse(doc)
    except CatalogError as e:
        raise HTTPException(422, f"invalid_catalog: {e}"[:500])
    override = get_settings().data_dir / "catalog-override.json"
    override.write_text(json.dumps(to_oscal(cat), ensure_ascii=False, indent=2), encoding="utf-8")
    reload_catalog()
    audit.record(db, actor, "catalog.import", "catalog", cat.uuid,
                 {"version": cat.version, "requirements": len(cat.requirements),
                  "verified": sum(1 for r in cat.requirements if r.verified)})
    db.commit()
    return {"ok": True, "requirements": len(cat.requirements)}


@router.delete("/import")
def reset_catalog(db: Session = Depends(get_db), actor: User = Depends(require("settings.manage"))):
    override = get_settings().data_dir / "catalog-override.json"
    if override.exists():
        override.unlink()
    reload_catalog()
    audit.record(db, actor, "catalog.reset", "catalog", None)
    db.commit()
    return {"ok": True}
