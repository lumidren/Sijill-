"""Parse OCSF Detection Findings (Prowler JSON-OCSF output and the PDPL-Ready Linux collector).

Only the fields the engine needs are kept. Anything that looks like a credential is
redacted before it can reach the database, logs or exports.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

VALID_STATUS = {"PASS", "FAIL", "MANUAL"}

# AWS access key ids, secret-access-key-like values, bearer tokens, private key blocks.
_REDACTIONS = [
    (re.compile(r"\b(AKIA|ASIA|AROA|AIDA)[A-Z0-9]{16}\b"), "[redacted-key-id]"),
    (re.compile(r"(?i)(aws_secret_access_key|secret_access_key|secretaccesskey)(\W{1,4})[A-Za-z0-9/+=]{40}"), r"\1\2[redacted]"),
    (re.compile(r"(?i)(aws_session_token|x-amz-security-token)(\W{1,4})[A-Za-z0-9/+=]{40,}"), r"\1\2[redacted]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"), "Bearer [redacted]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[redacted-private-key]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class FindingsError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass
class Finding:
    check_id: str
    status: str
    severity: str
    resource_uid: str
    region: str
    title: str
    message: str
    observed_at: datetime
    sha256: str


@dataclass
class Batch:
    provider: str  # aws | linux | <other provider name>
    target: str  # account id or hostname
    findings: list[Finding] = field(default_factory=list)

    @property
    def started_at(self) -> datetime:
        return min(f.observed_at for f in self.findings)


def _s(v, limit: int) -> str:
    if v is None:
        return ""
    return redact(str(v))[:limit]


def _time(item: dict) -> datetime:
    for key in ("time", ("finding_info", "created_time")):
        v = item.get(key) if isinstance(key, str) else (item.get(key[0]) or {}).get(key[1])
        if isinstance(v, (int, float)) and v > 0:
            if v > 1e12:  # milliseconds
                v = v / 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
    for key in ("time_dt", ("finding_info", "created_time_dt")):
        v = item.get(key) if isinstance(key, str) else (item.get(key[0]) or {}).get(key[1])
        if isinstance(v, str) and v:
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    raise FindingsError("not_findings", "finding has no usable time")


def _provider_and_target(item: dict) -> tuple[str, str]:
    cloud = item.get("cloud") or {}
    if isinstance(cloud, dict) and cloud.get("provider"):
        provider = str(cloud["provider"]).lower()
        account = (cloud.get("account") or {}).get("uid") or ""
        return provider, str(account) or "unknown-account"
    unmapped = item.get("unmapped") or {}
    device = item.get("device") or {}
    product_uid = ((item.get("metadata") or {}).get("product") or {}).get("uid", "")
    if device or unmapped.get("provider") == "linux" or product_uid == "pdpl-ready-linux":
        host = device.get("hostname") or ((item.get("resources") or [{}])[0] or {}).get("uid") or "unknown-host"
        return "linux", str(host)
    return "unknown", "unknown"


def parse(raw: bytes, max_bytes: int) -> list[Batch]:
    """Parse a findings file into one batch per (provider, target)."""
    if len(raw) > max_bytes:
        raise FindingsError("too_large")
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise FindingsError("bad_json")
    if isinstance(doc, dict) and isinstance(doc.get("findings"), list):
        doc = doc["findings"]
    if not isinstance(doc, list):
        raise FindingsError("not_findings", "expected a JSON array of OCSF findings")
    if not doc:
        raise FindingsError("empty_findings")

    batches: dict[tuple[str, str], Batch] = {}
    for i, item in enumerate(doc):
        if not isinstance(item, dict):
            raise FindingsError("not_findings", f"item {i} is not an object")
        meta = item.get("metadata") or {}
        check_id = meta.get("event_code")
        status = str(item.get("status_code") or "").upper()
        if not isinstance(check_id, str) or not check_id or status not in VALID_STATUS:
            raise FindingsError("not_findings", f"item {i} lacks metadata.event_code or a PASS/FAIL/MANUAL status_code")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", check_id):
            raise FindingsError("not_findings", f"item {i} has an invalid check id")
        cls = item.get("class_uid")
        if cls is not None and cls != 2004:
            raise FindingsError("not_findings", f"item {i} is OCSF class {cls}, expected 2004 (Detection Finding)")
        provider, target = _provider_and_target(item)
        res = (item.get("resources") or [{}])[0] or {}
        info = item.get("finding_info") or {}
        canonical = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        f = Finding(
            check_id=check_id,
            status=status,
            severity=_s(item.get("severity"), 16),
            resource_uid=_s(res.get("uid") or res.get("name") or target, 512),
            region=_s(res.get("region") or (item.get("cloud") or {}).get("region"), 64),
            title=_s(info.get("title"), 512),
            message=_s(item.get("status_detail") or item.get("message"), 4000),
            observed_at=_time(item),
            sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
        batches.setdefault((provider, target), Batch(provider, _s(target, 255))).findings.append(f)
    return list(batches.values())
