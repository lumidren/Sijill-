"""Evidence pack: every evidence file and check run, with a manifest of SHA-256 hashes.

Layout of the ZIP:
  README.txt                        how to verify the pack
  manifest.json / manifest.csv      every item with hash, size, timestamps and requirement
  sha256sums.txt                    `sha256sum -c sha256sums.txt` checks every file in the pack
  assessment-results.oscal.json     the current OSCAL assessment results
  evidence/<requirement>/<file>     uploaded evidence files, byte-for-byte
  check-runs/run-<id>.json          every stored check run with all its results
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..evidence_files import path_of
from ..models import CheckRun, User
from .data import ReportData
from .oscal_export import assessment_results


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_pack(db: Session, d: ReportData) -> bytes:
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars()}
    files: dict[str, bytes] = {}
    items: list[dict] = []

    used: set[str] = set()
    for ev in d.evidence:
        data = path_of(ev).read_bytes() if path_of(ev).exists() else b""
        name = f"evidence/{ev.requirement_id or 'general'}/{ev.filename}"
        if name in used:
            stem, dot, ext = ev.filename.rpartition(".")
            name = f"evidence/{ev.requirement_id or 'general'}/{stem or ev.filename}-{ev.id}{dot}{ext if stem else ''}"
        used.add(name)
        files[name] = data
        items.append({
            "path": name, "kind": "evidence-file", "sha256": ev.sha256, "size": ev.size,
            "hash_matches": _sha(data) == ev.sha256, "requirement_id": ev.requirement_id,
            "uploaded_at": ev.uploaded_at.isoformat(), "uploaded_by": users.get(ev.uploaded_by_id, ""),
            "description": ev.description,
        })

    for run in db.execute(select(CheckRun).order_by(CheckRun.started_at, CheckRun.id)).scalars():
        doc = {
            "run_id": run.id, "source": run.source, "provider": run.provider, "target": run.target,
            "started_at": run.started_at.isoformat(), "imported_at": run.imported_at.isoformat(),
            "findings_file": run.filename, "findings_file_sha256": run.file_sha256,
            "results": [
                {"check_id": r.check_id, "status": r.status, "severity": r.severity, "resource": r.resource_uid,
                 "region": r.region, "message": r.message, "observed_at": r.observed_at.isoformat(),
                 "finding_sha256": r.sha256}
                for r in run.results
            ],
        }
        raw = json.dumps(doc, indent=1, ensure_ascii=False).encode("utf-8")
        name = f"check-runs/run-{run.id:05d}.json"
        files[name] = raw
        items.append({
            "path": name, "kind": "check-run", "sha256": _sha(raw), "size": len(raw), "hash_matches": True,
            "requirement_id": None, "uploaded_at": run.imported_at.isoformat(), "uploaded_by": "",
            "description": f"{run.provider} {run.target}: {run.passed} passed, {run.failed} failed "
                           f"(source file SHA-256 {run.file_sha256})",
        })

    ar = json.dumps(assessment_results(d), indent=1, ensure_ascii=False).encode("utf-8")
    files["assessment-results.oscal.json"] = ar
    items.append({"path": "assessment-results.oscal.json", "kind": "oscal-assessment-results", "sha256": _sha(ar),
                  "size": len(ar), "hash_matches": True, "requirement_id": None,
                  "uploaded_at": d.generated_at.isoformat(), "uploaded_by": "", "description": "OSCAL 1.1.3"})

    manifest = {
        "generated_at": d.generated_at.isoformat(),
        "organization": d.org.get("name", ""),
        "readiness_score": None if d.score.overall is None else round(d.score.overall * 100, 1),
        "disclaimer": "Evidence pack for readiness tracking. Not legal advice and not a legal compliance determination.",
        "items": items,
    }
    files["manifest.json"] = json.dumps(manifest, indent=1, ensure_ascii=False).encode("utf-8")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(items[0].keys()) if items else ["path"])
    w.writeheader()
    for i in items:
        w.writerow(i)
    files["manifest.csv"] = ("﻿" + buf.getvalue()).encode("utf-8")
    files["README.txt"] = (
        "Sijill evidence pack\n"
        f"Organisation: {d.org.get('name', '')}\nGenerated: {d.generated_at.isoformat()}\n\n"
        "Verify every file:   sha256sum -c sha256sums.txt\n"
        "manifest.json lists each item with the hash recorded when it was collected or uploaded.\n"
        "A hash_matches value of false means the stored file no longer matches its recorded hash.\n\n"
        "Not legal advice. This pack supports readiness tracking only.\n"
    ).encode("utf-8")
    sums = "".join(f"{_sha(data)}  {name}\n" for name, data in sorted(files.items()))
    files["sha256sums.txt"] = sums.encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr(name, data)
    return out.getvalue()
