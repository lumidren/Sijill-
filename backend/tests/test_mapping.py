"""The PDPL -> check mapping only uses check IDs that really exist.

- Always: AWS IDs are checked against the committed snapshot of Prowler 5.50.0's check metadata,
  and Linux IDs against the collector's own check list.
- When Prowler is installed (this interpreter, or the project's .vp venv), IDs are also checked
  against the live package, and the framework file is loaded with Prowler's own pydantic model.
- PDPL_REQUIRE_PROWLER=1 (CI) makes a missing Prowler a failure instead of a skip.
"""
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from app.catalog import get_catalog
from app.evidence.mapping import (
    AWS_FRAMEWORK, AWS_SNAPSHOT, LINUX_FRAMEWORK, aws_snapshot, get_mapping, linux_collector_checks, load_framework,
)
from app.config import REPO_DIR

REQUIRE = os.environ.get("PDPL_REQUIRE_PROWLER") == "1"


@pytest.fixture(scope="module", params=[AWS_FRAMEWORK, LINUX_FRAMEWORK], ids=["aws", "linux"])
def framework(request):
    return load_framework(request.param)


def test_framework_has_prowler_top_level_fields(framework):
    for key in ("Framework", "Name", "Provider", "Description", "Requirements"):
        assert framework.get(key) not in (None, ""), key


def test_every_catalog_requirement_appears_once(framework):
    cat_ids = [r.id for r in get_catalog().requirements]
    fw_ids = [r["Id"] for r in framework["Requirements"]]
    assert sorted(fw_ids) == sorted(cat_ids)


def test_requirement_fields_match_prowler_schema(framework):
    allowed_attr = {"ItemId", "Section", "SubSection", "SubGroup", "Service", "Type", "Comment"}
    for r in framework["Requirements"]:
        assert set(r) <= {"Id", "Name", "Description", "Attributes", "Checks", "ConfigRequirements"}
        assert isinstance(r["Checks"], list) and r["Description"]
        for a in r["Attributes"]:
            assert set(a) <= allowed_attr
            assert a["ItemId"] == r["Id"]
            assert a["Type"] == ("Automated" if r["Checks"] else "Manual")


def test_technical_requirements_have_aws_checks_and_others_have_none():
    fw = {r["Id"]: r for r in load_framework(AWS_FRAMEWORK)["Requirements"]}
    for req in get_catalog().requirements:
        if req.technical:
            assert fw[req.id]["Checks"], f"{req.id} is technical but has no automated checks"
        else:
            assert not fw[req.id]["Checks"], f"{req.id} is organisational but has checks"


def test_aws_check_ids_exist_in_prowler_snapshot():
    snapshot = aws_snapshot()
    used = {c for r in load_framework(AWS_FRAMEWORK)["Requirements"] for c in r["Checks"]}
    assert used and not (used - set(snapshot)), sorted(used - set(snapshot))


def test_linux_check_ids_exist_in_collector():
    used = {c for r in load_framework(LINUX_FRAMEWORK)["Requirements"] for c in r["Checks"]}
    assert used == set(linux_collector_checks())


def test_mapping_index_is_consistent():
    m = get_mapping()
    for req, checks in m.req_checks.items():
        for c in checks:
            assert req in m.check_reqs[c]
            assert m.checks[c].provider in {"aws", "linux"}
    assert m.checks["linux_firewall_enabled"].title
    assert m.checks["s3_bucket_public_access"].severity


# ----------------------------------------------------------- live Prowler (optional locally, required in CI)

def _live_site_packages() -> Path | None:
    spec = importlib.util.find_spec("prowler")
    if spec and spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0]).parent
    for cand in (REPO_DIR / ".vp" / "Lib" / "site-packages", *sorted((REPO_DIR / ".vp" / "lib").glob("python3*/site-packages"))):
        if (cand / "prowler" / "providers" / "aws").is_dir():
            return cand
    return None


def _live_python() -> str | None:
    for cand in (REPO_DIR / ".vp" / "Scripts" / "python.exe", REPO_DIR / ".vp" / "bin" / "python"):
        if cand.exists():
            return str(cand)
    return None


def test_aws_check_ids_exist_in_installed_prowler():
    site = _live_site_packages()
    if site is None:
        if REQUIRE:
            pytest.fail("PDPL_REQUIRE_PROWLER=1 but Prowler is not installed")
        pytest.skip("Prowler not installed here; snapshot test covers the IDs")
    live = set()
    for meta in (site / "prowler" / "providers" / "aws" / "services").glob("*/*/*.metadata.json"):
        live.add(meta.name[: -len(".metadata.json")])
    used = {c for r in load_framework(AWS_FRAMEWORK)["Requirements"] for c in r["Checks"]}
    assert live, "no checks found in installed Prowler"
    assert not (used - live), sorted(used - live)


def test_framework_loads_with_prowlers_own_model():
    code = (
        "import sys; from prowler.lib.check.compliance_models import load_compliance_framework as l; "
        "c = l(sys.argv[1], fatal=False); print('OK' if c and len(c.Requirements) > 0 else 'INVALID')"
    )
    if importlib.util.find_spec("prowler"):
        py = None
    else:
        py = _live_python()
        if py is None or _live_site_packages() is None:
            if REQUIRE:
                pytest.fail("PDPL_REQUIRE_PROWLER=1 but Prowler is not installed")
            pytest.skip("Prowler not installed here")
    import sys
    out = subprocess.run([py or sys.executable, "-c", code, str(AWS_FRAMEWORK)], capture_output=True, text=True, timeout=300)
    assert "OK" in out.stdout, out.stdout + out.stderr


def test_snapshot_file_records_its_source():
    data = json.loads(AWS_SNAPSHOT.read_text(encoding="utf-8"))
    assert data["prowler_version"] and re.match(r"\d+\.\d+\.\d+", data["prowler_version"])
    assert len(data["checks"]) > 500
