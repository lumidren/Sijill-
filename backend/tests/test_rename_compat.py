"""Sijill was called PDPL-Ready until 2026-11-18. Files made under the old name still load."""
import json

from app.catalog import CATALOG_PATH, parse
from app.evidence.ocsf import _provider_and_target


def test_catalog_with_the_old_namespace_loads_the_same():
    text = CATALOG_PATH.read_text(encoding="utf-8")
    assert "urn:sijill:oscal" in text
    old = json.loads(text.replace("urn:sijill:oscal", "urn:pdpl-ready:oscal"))
    a, b = parse(json.loads(text)), parse(old)
    assert [(r.id, r.title.ar, r.weight, r.technical, r.verified) for r in a.requirements] == \
           [(r.id, r.title.ar, r.weight, r.technical, r.verified) for r in b.requirements]


def test_findings_from_the_old_linux_collector_are_still_linux():
    item = {"metadata": {"product": {"uid": "pdpl-ready-linux"}}, "resources": [{"uid": "old-host"}]}
    assert _provider_and_target(item) == ("linux", "old-host")
