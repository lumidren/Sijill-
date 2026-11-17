import csv
import io
import json

import pytest

from app.demo import seed_demo
from app.models import CheckResult, CheckRun
from app.oscal.validate import errors
from app.posture import current_score
from app.reports.data import build
from app.reports.oscal_export import assessment_results, import_assessment_results, poam
from app.reports.pdf import Para, gaps_pdf, readiness_pdf, visual


@pytest.fixture()
def demo(db):
    seed_demo(reset=True)
    return db


def test_assessment_results_validate_and_reflect_scores(demo):
    d = build(demo)
    doc = assessment_results(d)
    assert errors(doc, "assessment-results") == []
    result = doc["assessment-results"]["results"][0]
    findings = {next(p["value"] for p in f["props"] if p["name"] == "requirement-id"): f for f in result["findings"]}
    # every assessed requirement has a finding; status is kept exactly
    for r in d.score.requirements:
        if r.status == "not_assessed":
            assert r.id not in findings
        else:
            props = {p["name"]: p["value"] for p in findings[r.id]["props"]}
            assert props["pdpl-status"] == r.status
    capped = findings["a06-06"]
    assert capped["target"]["status"] == {"state": "not-satisfied", "reason": "other"}
    # observations carry per-resource hashes
    obs = [o for o in result["observations"] if "TEST" in o["methods"]]
    ev = obs[0]["relevant-evidence"][0]
    assert any(p["name"] == "sha256" and len(p["value"]) == 64 for p in ev["props"])


def test_poam_validates_and_lists_every_gap(demo):
    d = build(demo)
    doc = poam(d)
    assert errors(doc, "plan-of-action-and-milestones") == []
    items = doc["plan-of-action-and-milestones"]["poam-items"]
    assert len(items) == len(d.gaps)
    regressed = next(i for i in items if "A06.06" in i["title"])
    assert "s3_bucket_public_access" in regressed["description"]


def test_assessment_results_round_trip(demo):
    doc = assessment_results(build(demo))
    before = {(r.check_id, r.resource_uid, r.status) for run in demo.query(CheckRun).all() for r in run.results}
    latest_before = current_score(demo)
    # fresh install: wipe check data, then import the OSCAL document
    for run in demo.query(CheckRun).all():
        demo.delete(run)
    demo.commit()
    runs = import_assessment_results(demo, doc, None)
    demo.commit()
    assert {r.provider for r in runs} == {"aws", "linux"}
    after = {(r.check_id, r.resource_uid, r.status) for r in demo.query(CheckResult).all()}
    assert after and after <= before
    latest_after = current_score(demo)
    auto_before = {r.id: r.automated_status for r in latest_before.requirements}
    auto_after = {r.id: r.automated_status for r in latest_after.requirements}
    assert auto_before == auto_after
    # exporting again gives the same findings
    again = assessment_results(build(demo))["assessment-results"]["results"][0]["findings"]
    first = doc["assessment-results"]["results"][0]["findings"]
    strip = lambda fs: sorted((f["title"], f["target"]["status"]["state"]) for f in fs)  # noqa: E731
    assert strip(again) == strip(first)


def test_import_rejects_invalid_oscal(demo):
    from app.reports.oscal_export import OscalImportError
    with pytest.raises(OscalImportError):
        import_assessment_results(demo, {"assessment-results": {"uuid": "x"}}, None)


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_pdfs_render(demo, lang):
    d = build(demo)
    pdf = readiness_pdf(d, lang)
    assert pdf.startswith(b"%PDF-") and len(pdf) > 10_000
    assert b"PDPLSans" in pdf  # embedded font, so Arabic renders without system fonts
    assert gaps_pdf(d, lang).startswith(b"%PDF-")


def test_arabic_is_shaped_and_reordered():
    out = visual("مرحبا")
    assert out != "مرحبا"  # presentation forms, visual order
    assert all(0xFE70 <= ord(ch) <= 0xFEFF for ch in out)
    mixed = visual("المتطلب A06.06 مستوفى")
    assert "A06.06" in mixed  # Latin run keeps its own order


def test_rtl_paragraph_wraps_on_logical_text():
    p = Para("كلمة " * 60, rtl=True, size=10)
    w, h = p.wrap(200, 1000)
    assert len(p.lines) > 3 and h == pytest.approx(len(p.lines) * p.leading)


def test_csv_gap_list(demo):
    from app.reports.csv_export import gaps_csv
    raw = gaps_csv(build(demo))
    assert raw.startswith("﻿".encode())
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows and {"label", "status", "failing_checks"} <= set(rows[0])
    a0606 = next(r for r in rows if r["requirement_id"] == "a06-06")
    assert "s3_bucket_public_access" in a0606["failing_checks"]
    assert any(r["requirement_ar"] for r in rows)


def test_csv_neutralises_formulas():
    from app.reports.csv_export import _cell
    assert _cell("=HYPERLINK(1)").startswith("'")
    assert _cell("plain") == "plain"


@pytest.mark.parametrize("role", ["admin", "dpo", "it", "auditor"])
def test_every_role_can_download_reports(as_role, role):
    c = as_role(role)
    r = c.get("/api/reports/readiness.pdf?lang=ar")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert c.get("/api/reports/gaps.csv").status_code == 200
    ar = c.get("/api/reports/oscal/assessment-results").json()
    assert errors(ar, "assessment-results") == []
    assert errors(c.get("/api/reports/oscal/poam").json(), "plan-of-action-and-milestones") == []


def test_report_language_is_validated(as_role):
    assert as_role("dpo").get("/api/reports/readiness.pdf?lang=fr").status_code == 422


def test_oscal_import_endpoint_roles_and_round_trip(as_role):
    c = as_role("it")
    c.post("/api/checks/import", files={"file": ("f.json", open(__file__.replace("test_reports.py", "../../fixtures/linux-output/clinic-web-01.ocsf.json"), "rb").read(), "application/json")})
    doc = c.get("/api/reports/oscal/assessment-results").content
    assert as_role("auditor").post("/api/reports/oscal/assessment-results/import", files={"file": ("ar.json", doc, "application/json")}).status_code == 403
    c = as_role("admin")
    r = c.post("/api/reports/oscal/assessment-results/import", files={"file": ("ar.json", doc, "application/json")})
    assert r.status_code == 200 and r.json()["runs"] == 1
    bad = c.post("/api/reports/oscal/assessment-results/import", files={"file": ("ar.json", b'{"x": 1}', "application/json")})
    assert bad.status_code == 422


def test_report_generation_is_audited(as_role):
    c = as_role("auditor")
    c.get("/api/reports/gaps.csv")
    items = c.get("/api/audit").json()["items"]
    assert items[0]["action"] == "report.generate"


def test_evidence_pack_manifest_and_hashes(demo, app_client):
    import hashlib
    import zipfile
    from app.demo import DEMO_PASSWORD
    c = app_client
    assert c.post("/api/auth/login", json={"username": "auditor", "password": DEMO_PASSWORD}).status_code == 200
    r = c.get("/api/reports/evidence-pack.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"manifest.json", "manifest.csv", "sha256sums.txt", "README.txt", "assessment-results.oscal.json"} <= names
    # every line of sha256sums.txt verifies
    for line in z.read("sha256sums.txt").decode().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256(z.read(name)).hexdigest() == digest, name
    manifest = json.loads(z.read("manifest.json"))
    evidence = [i for i in manifest["items"] if i["kind"] == "evidence-file"]
    assert len(evidence) >= 3 and all(i["hash_matches"] for i in evidence)
    assert any(n.startswith("evidence/a01-01/") for n in names)
    assert len([i for i in manifest["items"] if i["kind"] == "check-run"]) >= 12
    assert errors(json.loads(z.read("assessment-results.oscal.json")), "assessment-results") == []


def test_poam_items_carry_remediation_owner_and_due_date(demo):
    doc = poam(build(demo))
    assert errors(doc, "plan-of-action-and-milestones") == []
    items = {next(p["value"] for p in i["props"] if p["name"] == "requirement-id"): i
             for i in doc["plan-of-action-and-milestones"]["poam-items"] if i.get("props")}
    props = {p["name"]: p["value"] for p in items["a06-05"]["props"]}
    assert props["remediation-owner"] == "Omar Adel" and props["remediation-due"] and "Remediation tasks" in items["a06-05"]["remarks"]


def test_readiness_report_includes_remediation_and_risks(demo):
    d = build(demo)
    assert d.tasks and d.risks and d.risks[0]["level"] == "critical"
    assert readiness_pdf(d, "en").startswith(b"%PDF-") and readiness_pdf(d, "ar").startswith(b"%PDF-")
