from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db, utcnow
from ..models import User
from ..reports.csv_export import gaps_csv
from ..reports.data import build
from ..reports.evidence_pack import build_pack
from ..reports.oscal_export import OscalImportError, assessment_results, import_assessment_results, poam
from ..reports.pdf import gaps_pdf, readiness_pdf
from ..security import require

router = APIRouter(prefix="/api/reports", tags=["reports"])
LANG = Query("en", pattern="^(en|ar)$")


def _name(kind: str, ext: str, lang: str | None = None) -> str:
    stamp = utcnow().strftime("%Y%m%d")
    return f"pdpl-{kind}{'-' + lang if lang else ''}-{stamp}.{ext}"


def _file(content: bytes, media: str, filename: str, inline: bool = False) -> Response:
    disposition = "inline" if inline else "attachment"
    return Response(content, media_type=media, headers={"Content-Disposition": f'{disposition}; filename="{filename}"'})


def _log(db: Session, actor: User, kind: str, **detail) -> None:
    audit.record(db, actor, "report.generate", "report", kind, detail)
    db.commit()


@router.get("/readiness.pdf")
def readiness(lang: str = LANG, inline: bool = False, db: Session = Depends(get_db), actor: User = Depends(require("reports.generate"))):
    pdf = readiness_pdf(build(db), lang)
    _log(db, actor, "readiness-pdf", lang=lang)
    return _file(pdf, "application/pdf", _name("readiness-report", "pdf", lang), inline)


@router.get("/gaps.pdf")
def gaps_report(lang: str = LANG, inline: bool = False, db: Session = Depends(get_db), actor: User = Depends(require("reports.generate"))):
    pdf = gaps_pdf(build(db), lang)
    _log(db, actor, "gaps-pdf", lang=lang)
    return _file(pdf, "application/pdf", _name("gap-list", "pdf", lang), inline)


@router.get("/gaps.csv")
def gaps_report_csv(db: Session = Depends(get_db), actor: User = Depends(require("reports.generate"))):
    data = gaps_csv(build(db))
    _log(db, actor, "gaps-csv")
    return _file(data, "text/csv; charset=utf-8", _name("gap-list", "csv"))


@router.get("/evidence-pack.zip")
def evidence_pack(db: Session = Depends(get_db), actor: User = Depends(require("reports.generate"))):
    data = build_pack(db, build(db))
    _log(db, actor, "evidence-pack")
    return _file(data, "application/zip", _name("evidence-pack", "zip"))


@router.get("/oscal/assessment-results")
def oscal_ar(db: Session = Depends(get_db), actor: User = Depends(require("reports.generate"))):
    doc = assessment_results(build(db))
    _log(db, actor, "oscal-assessment-results")
    return JSONResponse(doc, headers={"Content-Disposition": f'attachment; filename="{_name("assessment-results", "oscal.json")}"'})


@router.get("/oscal/poam")
def oscal_poam(db: Session = Depends(get_db), actor: User = Depends(require("reports.generate"))):
    doc = poam(build(db))
    _log(db, actor, "oscal-poam")
    return JSONResponse(doc, headers={"Content-Disposition": f'attachment; filename="{_name("poam", "oscal.json")}"'})


@router.post("/oscal/assessment-results/import")
async def oscal_ar_import(file: UploadFile, db: Session = Depends(get_db), actor: User = Depends(require("checks.write"))):
    raw = await file.read(50 * 1024 * 1024 + 1)
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "too_large")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "bad_json")
    try:
        runs = import_assessment_results(db, doc, actor)
    except OscalImportError as e:
        db.rollback()
        raise HTTPException(422, str(e)[:300])
    except Exception as e:  # DuplicateImport and friends
        db.rollback()
        if e.__class__.__name__ == "DuplicateImport":
            raise HTTPException(409, "duplicate_file")
        raise
    db.commit()
    return {"runs": len(runs), "results": sum(r.total for r in runs)}
