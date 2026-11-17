"""PDPL requirement <-> automated check mapping.

Both mapping files use Prowler's compliance framework schema (Framework, Name, Provider,
Requirements[Id, Name, Description, Attributes, Checks]):

- compliance/prowler/pdpl_egypt_aws.json   - a real Prowler framework file (upstream candidate)
- compliance/linux/pdpl_egypt_linux.json   - same schema, for the Sijill Linux collector
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import REPO_DIR

COMPLIANCE_DIR = REPO_DIR / "compliance"
AWS_FRAMEWORK = COMPLIANCE_DIR / "prowler" / "pdpl_egypt_aws.json"
LINUX_FRAMEWORK = COMPLIANCE_DIR / "linux" / "pdpl_egypt_linux.json"
AWS_SNAPSHOT = COMPLIANCE_DIR / "prowler" / "prowler-5.50.0-aws-checks.json"
LINUX_COLLECTOR = REPO_DIR / "collectors" / "linux" / "pdpl_linux_collector.py"


@dataclass(frozen=True)
class CheckInfo:
    id: str
    provider: str  # aws | linux
    title: str
    severity: str
    service: str


@dataclass(frozen=True)
class Mapping:
    req_checks: dict[str, tuple[str, ...]]
    check_reqs: dict[str, tuple[str, ...]]
    checks: dict[str, CheckInfo]

    def checks_for(self, req_id: str) -> list[str]:
        return list(self.req_checks.get(req_id, ()))

    def requirements_for(self, check_id: str) -> list[str]:
        return list(self.check_reqs.get(check_id, ()))

    def is_mapped(self, check_id: str) -> bool:
        return check_id in self.check_reqs


def load_framework(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def linux_collector_checks() -> dict[str, tuple]:
    spec = importlib.util.spec_from_file_location("pdpl_linux_collector", LINUX_COLLECTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.CHECKS)


@lru_cache
def aws_snapshot() -> dict[str, dict]:
    data = json.loads(AWS_SNAPSHOT.read_text(encoding="utf-8"))
    return {c["CheckID"]: c for c in data["checks"]}


@lru_cache
def get_mapping() -> Mapping:
    req_checks: dict[str, list[str]] = {}
    check_reqs: dict[str, list[str]] = {}
    checks: dict[str, CheckInfo] = {}
    snap = aws_snapshot()
    linux = linux_collector_checks()
    for path, provider in ((AWS_FRAMEWORK, "aws"), (LINUX_FRAMEWORK, "linux")):
        fw = load_framework(path)
        for req in fw["Requirements"]:
            for cid in req.get("Checks", []):
                req_checks.setdefault(req["Id"], [])
                if cid not in req_checks[req["Id"]]:
                    req_checks[req["Id"]].append(cid)
                check_reqs.setdefault(cid, [])
                if req["Id"] not in check_reqs[cid]:
                    check_reqs[cid].append(req["Id"])
                if cid not in checks:
                    if provider == "aws":
                        meta = snap.get(cid, {})
                        checks[cid] = CheckInfo(cid, "aws", meta.get("Title") or cid,
                                                (meta.get("Severity") or "").lower(), meta.get("Service") or "")
                    else:
                        title, severity = (linux.get(cid) or (cid, ""))[:2]
                        checks[cid] = CheckInfo(cid, "linux", title, severity, "linux")
    return Mapping(
        req_checks={k: tuple(v) for k, v in req_checks.items()},
        check_reqs={k: tuple(v) for k, v in check_reqs.items()},
        checks=checks,
    )
