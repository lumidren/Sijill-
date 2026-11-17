from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import get_catalog
from ..config import get_settings
from ..db import get_db
from ..evidence.mapping import get_mapping
from ..models import Answer, CheckRun, EvidenceFile, User
from ..posture import current_score, latest_runs, open_regressions, snapshots
from ..security import require

router = APIRouter(prefix="/api/posture", tags=["posture"])


def _area_titles() -> dict:
    return {a.id: {"label": a.label, "title": a.title.as_dict(), "overview": a.overview.as_dict(), "weight": a.weight}
            for a in get_catalog().areas}


@router.get("")
def posture(db: Session = Depends(get_db), _=Depends(require("read"))):
    res = current_score(db)
    cat = get_catalog()
    titles = _area_titles()
    reqs = []
    for r in res.requirements:
        req = cat.requirement(r.id)
        reqs.append({**r.as_dict(), "label": req.label, "title": req.title.as_dict(), "verified": req.verified,
                     "checks": [c.as_dict() for c in r.checks]})
    return {
        "overall": res.overall,
        "counts": res.counts(),
        "stale_days": get_settings().evidence_stale_days,
        "areas": [{**a.as_dict(), **titles[a.id]} for a in res.areas],
        "requirements": reqs,
    }


@router.get("/requirements/{req_id}")
def explain(req_id: str, db: Session = Depends(get_db), _=Depends(require("read"))):
    """Everything behind one requirement's status: the answer, each check and each resource."""
    cat = get_catalog()
    req = cat.requirement(req_id)
    if not req:
        raise HTTPException(404, "not_found")
    res = current_score(db)
    r = next(x for x in res.requirements if x.id == req_id)
    area = next(a for a in res.areas if a.id == req.area_id)
    mapping = get_mapping()
    answer = db.execute(select(Answer).where(Answer.requirement_id == req_id)).scalar_one_or_none()
    who = db.get(User, answer.updated_by_id) if answer and answer.updated_by_id else None
    files = db.execute(select(EvidenceFile).where(EvidenceFile.requirement_id == req_id)
                       .order_by(EvidenceFile.uploaded_at.desc())).scalars()
    scored = [x for x in res.requirements if x.area_id == req.area_id and x.value is not None]
    area_weight = sum(x.weight for x in scored) or 1
    return {
        "requirement": req.as_dict(),
        "area": {"id": area.id, "score": area.score, **_area_titles()[area.id]},
        "result": r.as_dict(),
        "contribution": None if r.value is None else {"points": r.value * r.weight, "of": r.weight,
                                                       "area_weight": area_weight},
        "answer": None if not answer else {
            "status": answer.status, "note": answer.note, "updated_at": answer.updated_at.isoformat(),
            "updated_by": who.display_name if who else None,
        },
        "checks": [
            {**c.as_dict(), "title": mapping.checks[c.check_id].title, "provider": mapping.checks[c.check_id].provider,
             "severity": mapping.checks[c.check_id].severity}
            for c in r.checks
        ],
        "evidence": [
            {"id": f.id, "filename": f.filename, "size": f.size, "sha256": f.sha256, "content_type": f.content_type,
             "uploaded_at": f.uploaded_at.isoformat(), "description": f.description}
            for f in files
        ],
    }


@router.get("/history")
def history(limit: int = Query(500, ge=1, le=2000), db: Session = Depends(get_db), _=Depends(require("read"))):
    return [
        {"at": s.at.isoformat(), "overall": s.overall, "by_area": s.by_area, "reason": s.reason, "run_id": s.run_id,
         "counts": s.counts}
        for s in snapshots(db, limit)
    ]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(require("read"))):
    res = current_score(db)
    cat = get_catalog()
    titles = _area_titles()
    hist = history(db=db, limit=500, _=None)
    gaps = sorted(
        (r for r in res.requirements if r.status in ("non_compliant", "partial", "not_assessed")),
        key=lambda r: ({"non_compliant": 0, "partial": 1, "not_assessed": 2}[r.status], -r.weight, r.id),
    )
    runs = latest_runs(db)
    out = {
        "overall": res.overall,
        "counts": res.counts(),
        "areas": [{**a.as_dict(), **titles[a.id]} for a in res.areas],
        "trend": [{"at": h["at"], "overall": h["overall"], "reason": h["reason"]} for h in hist],
        "gaps": [
            {"id": r.id, "label": cat.requirement(r.id).label, "title": cat.requirement(r.id).title.as_dict(),
             "status": r.status, "basis": r.basis, "weight": r.weight, "area_id": r.area_id,
             "failing_checks": r.failing_checks, "capped": r.capped, "stale": r.stale}
            for r in gaps[:8]
        ],
        "gap_total": len(gaps),
        "regressions": open_regressions(db),
        "targets": [
            {"provider": r.provider, "target": r.target, "run_id": r.id, "started_at": r.started_at.isoformat(),
             "passed": r.passed, "failed": r.failed}
            for r in runs
        ],
        "last_run": runs[0].started_at.isoformat() if runs else None,
        "runs_total": db.query(CheckRun).count(),
        "deadlines": [],
        "breaches": [],
    }
    try:
        from ..obligations_service import upcoming_deadlines
        out["deadlines"] = upcoming_deadlines(db)
    except ModuleNotFoundError:
        pass
    try:
        from ..incidents_service import active_clocks
        out["breaches"] = active_clocks(db)
    except ModuleNotFoundError:
        pass
    return out
