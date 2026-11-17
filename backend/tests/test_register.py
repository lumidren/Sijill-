import csv
import io

import pytest

from app.demo import DEMO_PASSWORD, seed_demo

ACT = {
    "role": "controller", "name": "Patient records", "purpose": "Care", "lawful_basis": "Consent",
    "data_subjects": ["Patients", " ", "Guardians"], "data_categories": ["Contact", "Medical history"],
    "sensitive_categories": ["Health data"], "recipients": ["Lab"], "cross_border": True,
    "transfer_countries": ["Germany"], "transfer_safeguards": "", "retention": "10 years",
    "security_measures": "", "systems": ["EHR"], "owner": "DPO",
}


def test_create_update_archive_and_audit(as_role):
    c = as_role("dpo")
    r = c.post("/api/register", json=ACT)
    assert r.status_code == 201
    a = r.json()
    assert a["ref"].startswith("C-") and a["data_subjects"] == ["Patients", "Guardians"]
    assert set(a["issues"]) == {"missing_transfer_safeguards", "sensitive_without_measures"}
    upd = c.put(f"/api/register/{a['id']}", json={**ACT, "transfer_safeguards": "Contract + encryption",
                                                  "security_measures": "Encrypted, RBAC"}).json()
    assert upd["issues"] == []
    assert c.post(f"/api/register/{a['id']}/archive").json()["status"] == "archived"
    assert c.get("/api/register").json() == []
    assert len(c.get("/api/register?include_archived=true").json()) == 1
    actions = [i["action"] for i in as_role("admin").get("/api/audit").json()["items"]]
    assert {"register.create", "register.update", "register.archive"} <= set(actions)


@pytest.mark.parametrize("role", ["it", "auditor"])
def test_only_admin_and_dpo_edit(as_role, role):
    c = as_role(role)
    assert c.get("/api/register").status_code == 200
    assert c.post("/api/register", json=ACT).status_code == 403


def test_validation(as_role):
    c = as_role("dpo")
    assert c.post("/api/register", json={**ACT, "role": "joint"}).status_code == 422
    assert c.post("/api/register", json={**ACT, "name": ""}).status_code == 422
    assert c.post("/api/register", json={**ACT, "systems": [f"s{i}" for i in range(60)]}).status_code == 422
    assert c.put("/api/register/999", json=ACT).status_code == 404


def test_processor_activity_needs_client(as_role):
    c = as_role("dpo")
    a = c.post("/api/register", json={**ACT, "role": "processor", "lawful_basis": ""}).json()
    assert "missing_client" in a["issues"] and "missing_lawful_basis" not in a["issues"]


def test_exports_in_both_layouts(app_client, db):
    seed_demo(reset=True)
    c = app_client
    c.post("/api/auth/login", json={"username": "auditor", "password": DEMO_PASSWORD})
    r = c.get("/api/register/export?role=controller&fmt=csv")
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Ref / المرجع" and "Retention period / مدة الاحتفاظ" in rows[0]
    assert any("Patient medical records" in row for row in rows)
    assert any("Yes (Germany" in cell for row in rows for cell in row)
    assert "not verified against the official templates" in r.content.decode("utf-8-sig")
    p = c.get("/api/register/export?role=processor&fmt=csv")
    header = list(csv.reader(io.StringIO(p.content.decode("utf-8-sig"))))[0]
    assert header[1].startswith("Controller (client)")
    for lang in ("en", "ar"):
        pdf = c.get(f"/api/register/export?role=controller&fmt=pdf&lang={lang}")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert c.get("/api/register/export?role=joint").status_code == 422
