from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..catalog import get_catalog
from ..config import get_settings
from ..db import get_db
from ..evidence.adapters import adapters
from ..evidence.mapping import get_mapping
from ..evidence.ocsf import FindingsError
from ..evidence.service import DuplicateImport, import_findings
from ..models import CheckResult, CheckRun, User
from ..posture import latest_observations, open_regressions, run_diff
from ..scheduler import collect_once, last_collection, next_run_time
from ..security import require

router = APIRouter(prefix="/api/checks", tags=["checks"])

FINDINGS_TYPES = {"application/json", "application/octet-stream", "text/json", "text/plain", ""}


def run_out(r: CheckRun) -> dict:
    return {
        "id": r.id, "source": r.source, "provider": r.provider, "target": r.target,
        "started_at": r.started_at.isoformat(), "imported_at": r.imported_at.isoformat(),
        "filename": r.filename, "file_sha256": r.file_sha256, "total": r.total, "passed": r.passed,
        "failed": r.failed, "manual": r.manual, "unmapped": r.unmapped, "status": r.status,
    }


@router.get("/runs")
def list_runs(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db), _=Depends(require("read"))):
    rows = db.execute(select(CheckRun).order_by(CheckRun.started_at.desc(), CheckRun.id.desc()).limit(limit)).scalars()
    out = []
    for r in rows:
        d = run_out(r)
        diff = run_diff(db, r)
        d["regressions"] = len(diff["regressions"])
        d["fixed"] = len(diff["fixed"])
        d["previous_run_id"] = diff["previous_run_id"]
        out.append(d)
    return out


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _=Depends(require("read"))):
    run = db.get(CheckRun, run_id)
    if not run:
        raise HTTPException(404, "not_found")
    mapping = get_mapping()
    results = sorted(run.results, key=lambda r: (r.status != "FAIL", r.check_id, r.resource_uid))
    return {
        **run_out(run),
        "diff": run_diff(db, run),
        "results": [
            {"check_id": r.check_id, "status": r.status, "severity": r.severity, "resource": r.resource_uid,
             "region": r.region, "title": r.title, "message": r.message, "observed_at": r.observed_at.isoformat(),
             "sha256": r.sha256, "requirements": mapping.requirements_for(r.check_id)}
            for r in results
        ],
    }


@router.post("/import")
async def import_file(file: UploadFile, db: Session = Depends(get_db), actor: User = Depends(require("checks.write"))):
    settings = get_settings()
    name = file.filename or "findings.json"
    if not name.lower().endswith(".json") or (file.content_type or "") not in FINDINGS_TYPES:
        raise HTTPException(415, "bad_type")
    limit = settings.max_upload_mb * 1024 * 1024
    raw = await file.read(limit + 1)
    try:
        runs = import_findings(db, raw, name, actor, source="upload")
    except FindingsError as e:
        db.rollback()
        status = 413 if e.code == "too_large" else 422
        raise HTTPException(status, e.code)
    except DuplicateImport:
        db.rollback()
        raise HTTPException(409, "duplicate_file")
    db.commit()
    return {"runs": [run_out(r) for r in runs],
            "total": sum(r.total for r in runs), "failed": sum(r.failed for r in runs)}


@router.get("/regressions")
def regressions(db: Session = Depends(get_db), _=Depends(require("read"))):
    return open_regressions(db)


@router.get("/mapping")
def mapping(db: Session = Depends(get_db), _=Depends(require("read"))):
    """Every technical requirement with its checks and each check's latest result."""
    m = get_mapping()
    obs = latest_observations(db)
    cat = get_catalog()
    out = []
    for req in cat.requirements:
        cids = m.checks_for(req.id)
        if not cids:
            continue
        checks = []
        for cid in cids:
            info = m.checks[cid]
            o = [x for x in obs.get(cid, []) if x.status in ("PASS", "FAIL")]
            status = None if not o else ("FAIL" if any(x.status == "FAIL" for x in o) else "PASS")
            checks.append({"check_id": cid, "provider": info.provider, "title": info.title, "severity": info.severity,
                           "status": status, "resources": len(o),
                           "failing": sorted({x.resource for x in o if x.status == "FAIL"})[:10]})
        out.append({"requirement": {"id": req.id, "label": req.label, "title": req.title.as_dict(), "area_id": req.area_id},
                    "checks": checks})
    return out


@router.get("/collectors")
def collectors(db: Session = Depends(get_db), _=Depends(require("read"))):
    out = []
    for a in adapters():
        ok, detail = a.available()
        out.append({"adapter": a.name, "available": ok, "detail": detail})
    nxt = next_run_time()
    total_results = db.scalar(select(func.count()).select_from(CheckResult))
    from ..scheduler import collect_org_id

    return {"adapters": out, "interval_hours": get_settings().collect_interval_hours,
            "collect_org_id": collect_org_id(), "active_here": db.info.get("org_id") == collect_org_id(),
            "next_run": nxt.isoformat() if nxt else None, "last": last_collection(),
            "inbox": str(get_settings().inbox_dir), "stored_results": total_results}


@router.post("/collect")
def collect_now(db: Session = Depends(get_db), _=Depends(require("checks.write"))):
    from ..scheduler import collect_org_id

    if db.info.get("org_id") != collect_org_id():
        raise HTTPException(409, "collectors_bound_to_other_org")
    return collect_once()
