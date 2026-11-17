import copy
import json

import pytest

from app import catalog as catmod
from app.catalog import CATALOG_PATH, CatalogError, parse, to_oscal
from app.oscal.validate import errors


@pytest.fixture(scope="module")
def raw():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_catalog_validates_against_official_oscal_schema(raw):
    assert errors(raw, "catalog") == []


def test_eleven_areas_and_every_requirement_complete(raw):
    cat = parse(raw)
    assert len(cat.areas) == 11
    assert len(cat.requirements) >= 44
    for r in cat.requirements:
        assert r.title.en and r.title.ar, r.id
        assert r.statement.en and r.statement.ar, r.id
        assert r.question.en and r.question.ar, r.id
        assert 1 <= r.weight <= 5
    for a in cat.areas:
        assert a.title.ar and a.overview.en and a.overview.ar
        assert len(a.requirements) >= 3


def test_no_requirement_claims_verification_without_a_source(raw):
    for r in parse(raw).requirements:
        if r.verified:
            assert r.source, f"{r.id} is verified but cites no source"
        else:
            assert r.source_status == "needed"


def test_round_trip_through_oscal_is_lossless(raw):
    cat = parse(raw)
    out = to_oscal(cat)
    assert errors(out, "catalog") == []
    assert parse(out) == cat


def test_no_hardcoded_deadlines_or_article_numbers_in_catalog_text(raw):
    text = json.dumps(raw, ensure_ascii=False).lower()
    for banned in ("72 hours", "article ", "art. ", "egp", "fine of", "penalty of"):
        assert banned not in text, banned


def test_invalid_catalog_is_rejected(raw):
    broken = copy.deepcopy(raw)
    del broken["catalog"]["metadata"]["title"]
    with pytest.raises(CatalogError):
        parse(broken)
    dup = copy.deepcopy(raw)
    g = dup["catalog"]["groups"][0]
    g["controls"].append(copy.deepcopy(g["controls"][0]))
    with pytest.raises(CatalogError):
        parse(dup)


def test_schema_validator_catches_bad_tokens(raw):
    bad = copy.deepcopy(raw)
    bad["catalog"]["groups"][0]["id"] = "has space"
    assert errors(bad, "catalog")


def test_catalog_api(as_role):
    c = as_role("auditor")
    data = c.get("/api/catalog").json()
    assert len(data["areas"]) == 11
    one = data["areas"][0]["requirements"][0]
    assert one["verified"] is False and one["title"]["ar"]
    exported = c.get("/api/catalog/oscal").json()
    assert errors(exported, "catalog") == []


def test_catalog_import_requires_admin_and_valid_oscal(as_role, raw):
    c = as_role("dpo")
    files = {"file": ("catalog.json", json.dumps(raw).encode(), "application/json")}
    assert c.post("/api/catalog/import", files=files).status_code == 403
    c = as_role("admin")
    bad = {"file": ("catalog.json", b"{not json", "application/json")}
    assert c.post("/api/catalog/import", files=bad).status_code == 422
    reviewed = copy.deepcopy(raw)
    ctrl = reviewed["catalog"]["groups"][0]["controls"][0]
    for p in ctrl["props"]:
        if p["name"] == "verified":
            p["value"] = "true"
    ctrl["props"].append({"name": "source", "value": "Reviewed text, page 1", "ns": "urn:pdpl-ready:oscal"})
    ok = {"file": ("catalog.json", json.dumps(reviewed).encode(), "application/json")}
    r = c.post("/api/catalog/import", files=ok)
    assert r.status_code == 200, r.text
    first = c.get("/api/catalog").json()["areas"][0]["requirements"][0]
    assert first["verified"] is True and first["source"] == "Reviewed text, page 1"
    # back to the shipped catalog
    assert c.delete("/api/catalog/import").status_code == 200
    catmod.reload_catalog()


def test_legal_review_document_is_current():
    import importlib.util
    from app.config import REPO_DIR
    spec = importlib.util.spec_from_file_location("legal_review", REPO_DIR / "scripts" / "legal_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    on_disk = (REPO_DIR / "docs" / "LEGAL-REVIEW.md").read_text(encoding="utf-8")
    assert on_disk == mod.render(), "run: python scripts/legal_review.py"
    for r in parse(json.loads(CATALOG_PATH.read_text(encoding="utf-8"))).requirements:
        if not r.verified:
            assert f"`{r.id}`" in on_disk
