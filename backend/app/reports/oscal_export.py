"""OSCAL assessment results and plan of action & milestones (POA&M), plus AR import.

- Each automated check, per monitored target, becomes an observation (method TEST) whose
  relevant-evidence entries are the individual resource results with their SHA-256 hashes.
- Each self-attested answer becomes an observation (method INTERVIEW, or EXAMINE when evidence
  files are attached).
- Each assessed requirement becomes a finding targeting its assessment objective
  (`<control-id>_obj` in the catalog), with the PDPL-Ready status kept in a namespaced prop.
- Gaps become POA&M items.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import __version__
from ..catalog import CATALOG_PATH
from ..evidence.service import import_findings
from ..models import CheckRun, User
from ..oscal import NS, OSCAL_VERSION
from ..oscal.validate import errors as oscal_errors
from .data import ReportData

UUID_NS = uuid.UUID("5d1c4b8e-7a1f-4f0e-9c3b-2e6a9d8f1c07")
STATE = {
    "compliant": ("satisfied", "pass"),
    "partial": ("not-satisfied", "other"),
    "non_compliant": ("not-satisfied", "fail"),
    "not_applicable": ("satisfied", "other"),
}


def _u(*parts) -> str:
    return str(uuid.uuid5(UUID_NS, "|".join(str(p) for p in parts)))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prop(name: str, value) -> dict:
    v = " ".join(str(value).split()) or "-"
    return {"name": name, "ns": NS, "value": v}


def _metadata(d: ReportData, title: str) -> dict:
    org = d.org.get("name", "Organisation")
    return {
        "title": f"{title}: {org}",
        "last-modified": _iso(d.generated_at),
        "version": f"{d.generated_at:%Y%m%d%H%M%S}",
        "oscal-version": OSCAL_VERSION,
        "props": [
            _prop("generator", f"PDPL-Ready {__version__}"),
            _prop("disclaimer", "Readiness tracking aid. Not legal advice and not a legal compliance determination."),
            _prop("catalog-verified", "false" if d.unverified else "true"),
        ],
        "parties": [{"uuid": _u("party", org), "type": "organization", "name": org}],
    }


def _back_matter(d: ReportData) -> dict:
    catalog_sha = hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
    return {"resources": [
        {"uuid": _u("catalog", d.catalog.uuid), "title": d.catalog.title,
         "props": [_prop("catalog-version", d.catalog.version or "draft")],
         "rlinks": [{"href": "pdpl-catalog.json", "media-type": "application/json",
                     "hashes": [{"algorithm": "SHA-256", "value": catalog_sha}]}]},
        {"uuid": _u("implicit-ap"), "title": "Continuous self-assessment (no separate assessment plan document)",
         "description": "PDPL-Ready assesses every catalog requirement continuously from questionnaire answers and automated checks."},
    ]}


def _observations(d: ReportData) -> tuple[list[dict], dict[str, list[str]]]:
    """Returns observations and, per requirement, the observation uuids that back it."""
    obs: list[dict] = []
    by_req: dict[str, list[str]] = defaultdict(list)
    for run in d.runs:
        per_check: dict[str, list] = defaultdict(list)
        for r in run.results:
            per_check[r.check_id].append(r)
        for check_id, rows in sorted(per_check.items()):
            if not d.mapping.is_mapped(check_id):
                continue
            ou = _u("obs", run.provider, run.target, check_id, run.id)
            failing = [r for r in rows if r.status == "FAIL"]
            graded = [r for r in rows if r.status in ("PASS", "FAIL")]
            result = "FAIL" if failing else ("PASS" if graded else "MANUAL")
            info = d.mapping.checks.get(check_id)
            obs.append({
                "uuid": ou,
                "title": (info.title if info else check_id)[:300],
                "description": f"{len(failing)} of {len(rows)} resource result(s) failing on {run.target}.",
                "props": [_prop("check-id", check_id), _prop("result", result), _prop("provider", run.provider),
                          _prop("target", run.target), _prop("source", run.source),
                          _prop("findings-file-sha256", run.file_sha256 or "-")],
                "methods": ["TEST"],
                "collected": _iso(max(r.observed_at for r in rows)),
                "relevant-evidence": [
                    {"description": (r.message or r.title or r.check_id)[:2000] or "-",
                     "props": [_prop("resource", r.resource_uid or run.target), _prop("status", r.status),
                               _prop("region", r.region or "-"), _prop("observed-at", _iso(r.observed_at)),
                               _prop("severity", r.severity or "-"), _prop("sha256", r.sha256 or "-")]}
                    for r in rows
                ],
            })
            for rid in d.mapping.requirements_for(check_id):
                by_req[rid].append(ou)
    files_by_req = defaultdict(list)
    for f in d.evidence:
        if f.requirement_id:
            files_by_req[f.requirement_id].append(f)
    for rid, a in sorted(d.answers.items()):
        if a.status == "not_assessed" or not d.req(rid):
            continue
        ou = _u("attest", rid)
        files = files_by_req.get(rid, [])
        o = {
            "uuid": ou,
            "title": f"Self-attestation: {d.req(rid).label}",
            "description": a.note or "Self-attested answer.",
            "props": [_prop("answer", a.status), _prop("requirement-id", rid),
                      _prop("answered-by", d.answer_by.get(rid) or "unknown")],
            "methods": ["EXAMINE" if files else "INTERVIEW"],
            "collected": _iso(a.updated_at),
        }
        if files:
            o["relevant-evidence"] = [
                {"href": f"evidence/{f.stored_name}", "description": f.filename,
                 "props": [_prop("sha256", f.sha256), _prop("uploaded-at", _iso(f.uploaded_at)),
                           _prop("size-bytes", f.size)]}
                for f in files
            ]
        obs.append(o)
        by_req[rid].append(ou)
    return obs, by_req


def _findings(d: ReportData, by_req: dict[str, list[str]], only: set[str] | None = None) -> list[dict]:
    out = []
    for r in d.score.requirements:
        if r.status == "not_assessed" or (only is not None and r.id not in only):
            continue
        req = d.req(r.id)
        state, reason = STATE[r.status]
        f = {
            "uuid": _u("finding", r.id),
            "title": f"{req.label} {req.title.en}",
            "description": req.statement.en,
            "props": [_prop("requirement-id", r.id), _prop("pdpl-status", r.status), _prop("basis", r.basis),
                      _prop("reason", r.reason), _prop("capped", str(r.capped).lower()),
                      _prop("stale", str(r.stale).lower()), _prop("weight", r.weight)],
            "target": {"type": "objective-id", "target-id": f"{r.id}_obj",
                       "status": {"state": state, "reason": reason}},
        }
        if by_req.get(r.id):
            f["related-observations"] = [{"observation-uuid": u} for u in by_req[r.id]]
        out.append(f)
    return out


def assessment_results(d: ReportData) -> dict:
    obs, by_req = _observations(d)
    findings = _findings(d, by_req)
    starts = [datetime.fromisoformat(o["collected"].replace("Z", "+00:00")) for o in obs] or [d.generated_at]
    result = {
        "uuid": _u("result", d.generated_at.isoformat()),
        "title": "PDPL readiness self-assessment",
        "description": ("Readiness against the PDPL-Ready catalog for Law No. 151 of 2020, combining self-attested "
                        "answers and automated technical checks. Not a legal compliance determination."),
        "start": _iso(min(starts)),
        "end": _iso(d.generated_at),
        "props": [_prop("readiness-score", f"{(d.score.overall or 0) * 100:.1f}")],
        "reviewed-controls": {"control-selections": [{"include-all": {}}]},
    }
    if obs:
        result["observations"] = obs
    if findings:
        result["findings"] = findings
    return {"assessment-results": {
        "uuid": str(uuid.uuid4()),
        "metadata": _metadata(d, "PDPL readiness assessment results"),
        "import-ap": {"href": f"#{_u('implicit-ap')}",
                      "remarks": "There is no separate assessment plan; see the referenced back-matter resource."},
        "results": [result],
        "back-matter": _back_matter(d),
    }}


def poam(d: ReportData) -> dict:
    obs, by_req = _observations(d)
    gap_ids = {g.id for g in d.gaps}
    findings = _findings(d, by_req, only=gap_ids)
    finding_ids = {f["uuid"] for f in findings}
    used_obs = {o for rid in gap_ids for o in by_req.get(rid, [])}
    items = []
    for g in d.gaps:
        req = d.req(g.id)
        failing = [c.check_id for c in g.checks if c.status == "FAIL"]
        what = {
            "non_compliant": "Requirement not met.",
            "partial": "Requirement only partly met.",
            "not_assessed": "Requirement not assessed yet.",
        }[g.status]
        if failing:
            what += f" Failing automated checks: {', '.join(failing)}."
        item = {
            "uuid": _u("poam", g.id),
            "title": f"{req.label} {req.title.en}",
            "description": f"{what} {req.question.en}",
            "props": [_prop("requirement-id", g.id), _prop("pdpl-status", g.status), _prop("basis", g.basis),
                      _prop("priority-weight", g.weight)],
        }
        fu = _u("finding", g.id)
        if fu in finding_ids:
            item["related-findings"] = [{"finding-uuid": fu}]
        items.append(item)
    if not items:
        items = [{"uuid": _u("poam", "none"), "title": "No open gaps",
                  "description": "Every assessed requirement is met or not applicable."}]
    doc = {"plan-of-action-and-milestones": {
        "uuid": str(uuid.uuid4()),
        "metadata": _metadata(d, "PDPL readiness plan of action"),
        "poam-items": items,
        "back-matter": _back_matter(d),
    }}
    body = doc["plan-of-action-and-milestones"]
    kept_obs = [o for o in obs if o["uuid"] in used_obs]
    if kept_obs:
        body["observations"] = kept_obs
    if findings:
        body["findings"] = findings
    return doc


# ----------------------------------------------------------------- import (round trip)

class OscalImportError(ValueError):
    pass


def _props(o: dict) -> dict:
    return {p["name"]: p["value"] for p in o.get("props", []) if p.get("ns") == NS}


def import_assessment_results(db: Session, doc: dict, actor: User | None) -> list[CheckRun]:
    """Restore automated check results from an OSCAL assessment-results document.

    Observations made by automated checks (method TEST with a check-id prop) are turned back into
    OCSF findings and imported through the normal pipeline, so drift and scoring stay consistent.
    """
    errs = oscal_errors(doc, "assessment-results")
    if errs:
        raise OscalImportError("invalid OSCAL assessment results: " + "; ".join(errs[:3]))
    items = []
    for result in doc["assessment-results"]["results"]:
        for o in result.get("observations", []):
            p = _props(o)
            if "check-id" not in p or "TEST" not in o.get("methods", []):
                continue
            provider, target = p.get("provider", "unknown"), p.get("target", "unknown")
            for ev in o.get("relevant-evidence", []):
                ep = _props(ev)
                status = ep.get("status", "MANUAL")
                observed = ep.get("observed-at") or o["collected"]
                ts = int(datetime.fromisoformat(observed.replace("Z", "+00:00")).timestamp())
                item = {
                    "metadata": {"event_code": p["check-id"], "product": {"name": "PDPL-Ready OSCAL import", "uid": "pdpl-ready-oscal"}},
                    "status_code": status, "status_detail": ev.get("description", ""), "time": ts,
                    "severity": ep.get("severity", "") if ep.get("severity") != "-" else "",
                    "finding_info": {"title": o.get("title", ""), "uid": f"{p['check-id']}-{ep.get('resource')}"},
                    "resources": [{"uid": ep.get("resource", target), "region": "" if ep.get("region") == "-" else ep.get("region", "")}],
                    "class_uid": 2004,
                }
                if provider == "linux":
                    item["device"] = {"hostname": target}
                    item["unmapped"] = {"provider": "linux"}
                else:
                    item["cloud"] = {"provider": provider, "account": {"uid": target}}
                items.append(item)
    if not items:
        raise OscalImportError("the document contains no automated check observations")
    raw = json.dumps(items, sort_keys=True).encode("utf-8")
    return import_findings(db, raw, "assessment-results.oscal.json", actor, source="oscal-import")
