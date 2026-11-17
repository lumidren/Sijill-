"""Gap list as CSV (UTF-8 with BOM so Excel shows Arabic correctly)."""
from __future__ import annotations

import csv
import io

from .data import ReportData

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(v) -> str:
    s = "" if v is None else str(v)
    # neutralise spreadsheet formula injection
    return "'" + s if s.startswith(FORMULA_PREFIXES) else s


def gaps_csv(d: ReportData) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["label", "requirement_id", "requirement", "requirement_ar", "area", "status", "basis", "reason",
                "weight", "failing_checks", "failing_resources", "capped", "stale", "verified", "answer_note"])
    for r in d.gaps:
        req = d.req(r.id)
        area = d.catalog.area(r.area_id)
        failing = [c for c in r.checks if c.status == "FAIL"]
        answer = d.answers.get(r.id)
        w.writerow([_cell(x) for x in [
            req.label, r.id, req.title.en, req.title.ar, f"{area.label} {area.title.en}", r.status, r.basis, r.reason,
            r.weight, " ".join(c.check_id for c in failing),
            " ".join(sorted({res for c in failing for res in c.failing_resources})),
            str(r.capped).lower(), str(r.stale).lower(), str(req.verified).lower(), answer.note if answer else "",
        ]])
    return ("﻿" + buf.getvalue()).encode("utf-8")
