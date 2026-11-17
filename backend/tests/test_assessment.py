import hashlib
from io import BytesIO

import pytest

from app.evidence_files import path_of
from app.models import EvidenceFile, ScoreSnapshot

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def put(c, req, status, note=""):
    return c.put(f"/api/assessment/answers/{req}", json={"status": status, "note": note})


def test_overview_lists_all_areas_and_progress(as_role):
    data = as_role("auditor").get("/api/assessment").json()
    assert len(data["areas"]) == 11 and data["total"] == 52 and data["answered"] == 0
    req = data["areas"][0]["requirements"][0]
    assert req["question"]["en"] and req["question"]["ar"] and req["answer"] is None


def test_dpo_answers_and_score_moves(as_role, db):
    c = as_role("dpo")
    before = c.get("/api/posture").json()["overall"]
    r = put(c, "a01-01", "compliant", "Appointment letter signed.")
    assert r.status_code == 200
    assert r.json()["result"]["status"] == "compliant"
    after = c.get("/api/posture").json()["overall"]
    assert after > before
    assert db.query(ScoreSnapshot).filter_by(reason="assessment").count() == 1
    ov = c.get("/api/assessment").json()
    assert ov["answered"] == 1 and ov["areas"][0]["answered"] == 1
    # completing an area changes its score and the gap list
    for rid in ("a01-02", "a01-03", "a01-04", "a01-05"):
        put(c, rid, "compliant")
    area = c.get("/api/posture").json()["areas"][0]
    assert area["score"] == pytest.approx(1.0)
    gaps = c.get("/api/posture/dashboard").json()["gaps"]
    assert not any(g["area_id"] == "a01" for g in gaps)


def test_answer_is_audited_with_before_and_after(as_role):
    c = as_role("dpo")
    put(c, "a02-01", "partial")
    put(c, "a02-01", "compliant")
    items = as_role("admin").get("/api/audit").json()["items"]
    last = next(i for i in items if i["action"] == "assessment.answer")
    assert last["detail"]["from"]["status"] == "partial" and last["detail"]["to"]["status"] == "compliant"


@pytest.mark.parametrize("role", ["it", "auditor"])
def test_only_admin_and_dpo_answer(as_role, role):
    assert put(as_role(role), "a01-01", "compliant").status_code == 403


def test_answer_validation(as_role):
    c = as_role("dpo")
    assert put(c, "a01-01", "mostly").status_code == 422
    assert put(c, "nope-99", "compliant").status_code == 404
    assert c.put("/api/assessment/answers/a01-01", json={"status": "compliant", "note": "x" * 5000}).status_code == 422


def upload(c, req="a01-01", name="letter.pdf", data=PDF, ctype="application/pdf", desc="Signed"):
    return c.post("/api/evidence", data={"requirement_id": req, "description": desc}, files={"file": (name, data, ctype)})


def test_evidence_upload_hash_and_download(as_role, db):
    c = as_role("it")
    r = upload(c)
    assert r.status_code == 201
    body = r.json()
    assert body["sha256"] == hashlib.sha256(PDF).hexdigest() and body["size"] == len(PDF)
    d = c.get(f"/api/evidence/{body['id']}/download")
    assert d.status_code == 200 and d.content == PDF and d.headers["x-content-sha256"] == body["sha256"]
    listed = c.get("/api/evidence?requirement_id=a01-01").json()
    assert listed[0]["filename"] == "letter.pdf"


def test_tampered_evidence_is_refused(as_role, db):
    c = as_role("dpo")
    eid = upload(c).json()["id"]
    ev = db.get(EvidenceFile, eid)
    path_of(ev).write_bytes(PDF + b"tampered")
    assert c.get(f"/api/evidence/{eid}/download").status_code == 409


@pytest.mark.parametrize("name,data,ctype,status,code", [
    ("tool.exe", b"MZ\x90\x00", "application/octet-stream", 415, "bad_type"),
    ("fake.pdf", b"MZ not a pdf", "application/pdf", 415, "content_mismatch"),
    ("empty.pdf", b"", "application/pdf", 422, "empty_file"),
    ("macro.docm", b"PK\x03\x04", "application/octet-stream", 415, "bad_type"),
])
def test_bad_uploads_rejected(as_role, name, data, ctype, status, code):
    r = upload(as_role("dpo"), name=name, data=data, ctype=ctype)
    assert r.status_code == status and r.json()["detail"] == code


def test_oversized_upload_rejected(as_role, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    r = upload(as_role("dpo"))
    assert r.status_code == 413


def test_auditor_cannot_upload_and_unknown_requirement(as_role):
    assert upload(as_role("auditor")).status_code == 403
    assert upload(as_role("dpo"), req="zz-99").status_code == 404


def test_filename_is_sanitised(as_role):
    r = upload(as_role("dpo"), name="..\\..\\evil<script>.pdf")
    assert r.status_code == 201
    assert "/" not in r.json()["filename"] and "\\" not in r.json()["filename"] and "<" not in r.json()["filename"]


def test_evidence_counts_as_fresh_evidence_for_staleness(as_role, db):
    from datetime import timedelta
    from app.db import utcnow
    from app.models import Answer
    c = as_role("dpo")
    put(c, "a01-01", "compliant")
    a = db.query(Answer).filter_by(requirement_id="a01-01").one()
    a.updated_at = utcnow() - timedelta(days=90)
    db.commit()
    req = lambda: next(r for r in c.get("/api/posture").json()["requirements"] if r["id"] == "a01-01")  # noqa: E731
    assert req()["stale"] is True
    upload(c)
    assert req()["stale"] is False
