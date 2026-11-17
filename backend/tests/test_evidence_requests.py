"""Evidence requests: private links for client staff."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import org_session, utcnow
from app.models import AuditLog, EvidenceFile, EvidenceRequest
from app.routers import evidence_requests as er

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
BODY = {"title": "Security evidence for Q4", "recipient": "Omar (IT vendor)", "recipient_contact": "omar@example.test",
        "message": "Please answer by Thursday.", "requirement_ids": ["a06-05", "A05-04", "a06-05"],
        "asks": {"a06-05": "A screenshot of the MFA setting is enough."}}


@pytest.fixture(autouse=True)
def _clear_throttle():
    er._BAD.clear()


def _make(c, **over):
    r = c.post("/api/evidence-requests", json={**BODY, **over})
    assert r.status_code == 201, r.text
    return r.json()


def _anon(app_client):
    app_client.cookies.clear()
    app_client.headers.pop("X-PDPL-Request", None)
    return app_client


def test_create_shows_the_link_once_and_stores_only_its_hash(as_role, db):
    req = _make(as_role("dpo"))
    token = req["token"]
    assert len(token) >= 40 and [i["requirement_id"] for i in req["items"]] == ["a06-05", "a05-04"]
    assert req["items"][0]["ask"].startswith("A screenshot")
    row = db.execute(select(EvidenceRequest)).scalar_one()
    assert row.token_hash == er._hash(token) and token not in row.token_hash
    again = as_role("dpo").get(f"/api/evidence-requests/{req['id']}").json()
    assert "token" not in again
    assert as_role("it").post("/api/evidence-requests", json=BODY).status_code == 403
    assert as_role("auditor").get("/api/evidence-requests").status_code == 200
    assert as_role("dpo").post("/api/evidence-requests", json={**BODY, "requirement_ids": ["zz-99"]}).status_code == 422
    assert as_role("dpo").post("/api/evidence-requests", json={**BODY, "expires_days": 90}).status_code == 422


def test_recipient_answers_uploads_and_submits_without_an_account(as_role, app_client):
    req = _make(as_role("dpo"))
    token, item = req["token"], req["items"][0]["id"]
    c = _anon(app_client)
    view = c.get(f"/api/public/r/{token}")
    assert view.status_code == 200 and view.headers["cache-control"] == "no-store"
    v = view.json()
    assert v["organization"]["name"] == "My organisation" and v["recipient"] == "Omar (IT vendor)"
    assert v["items"][0]["question"]["en"] and v["items"][0]["question"]["ar"]
    assert "sha256" not in str(v) and "recipient_contact" not in v
    # Writes need the CSRF header, like everything else
    assert c.put(f"/api/public/r/{token}/items/{item}", json={"response": "x"}).status_code == 403
    c.headers["X-PDPL-Request"] = "1"
    assert c.post(f"/api/public/r/{token}/submit").status_code == 422  # nothing answered yet
    a = c.put(f"/api/public/r/{token}/items/{item}", json={"response": "MFA is on for all staff since October."}).json()
    assert a["status"] == "answered"
    up = c.post(f"/api/public/r/{token}/items/{item}/files", files={"file": ("mfa.pdf", PDF, "application/pdf")})
    assert up.status_code == 201 and up.json()["files"][0]["filename"] == "mfa.pdf"
    bad = c.post(f"/api/public/r/{token}/items/{item}/files", files={"file": ("x.exe", b"MZ..", "application/octet-stream")})
    assert bad.status_code == 415
    fake = c.post(f"/api/public/r/{token}/items/{item}/files", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert fake.status_code == 415
    assert c.post(f"/api/public/r/{token}/submit").json() == {"status": "submitted"}
    assert c.put(f"/api/public/r/{token}/items/{item}", json={"response": "changed"}).status_code == 409

    # Nothing reaches the assessment before review
    dpo = as_role("dpo")
    assert dpo.get("/api/evidence?requirement_id=a06-05").json() == []
    detail = dpo.get(f"/api/evidence-requests/{req['id']}").json()
    assert detail["status"] == "submitted" and detail["counts"]["answered"] == 1
    f = detail["items"][0]["files"][0]
    dl = dpo.get(f"/api/evidence-requests/{req['id']}/files/{f['id']}/download")
    assert dl.status_code == 200 and dl.content == PDF and dl.headers["x-content-sha256"] == f["sha256"]

    accepted = dpo.post(f"/api/evidence-requests/{req['id']}/items/{item}/review", json={"decision": "accept"}).json()
    assert accepted["items"][0]["status"] == "accepted" and accepted["items"][0]["files"][0]["evidence_file_id"]
    ev = dpo.get("/api/evidence?requirement_id=a06-05").json()
    assert len(ev) == 1 and ev[0]["sha256"] == f["sha256"] and "Omar (IT vendor)" in ev[0]["description"]
    assert dpo.post(f"/api/evidence-requests/{req['id']}/items/{item}/review", json={"decision": "accept"}).status_code == 409

    actions = [e["action"] for e in as_role("admin").get("/api/audit?limit=50").json()["items"]]
    for a in ("evidence_request.create", "evidence_request.opened", "evidence_request.answer", "evidence_request.file",
              "evidence_request.submit", "evidence_request.item_accepted"):
        assert a in actions
    assert as_role("admin").get("/api/audit/verify").json()["ok"] is True


def test_returning_an_item_reopens_the_link(as_role, app_client):
    req = _make(as_role("dpo"))
    token, item = req["token"], req["items"][1]["id"]
    c = _anon(app_client)
    c.headers["X-PDPL-Request"] = "1"
    c.put(f"/api/public/r/{token}/items/{item}", json={"response": "Backups go to a USB drive."})
    c.post(f"/api/public/r/{token}/submit")
    dpo = as_role("dpo")
    back = dpo.post(f"/api/evidence-requests/{req['id']}/items/{item}/review",
                    json={"decision": "return", "note": "Please attach the last restore test."}).json()
    assert back["status"] == "open" and back["items"][1]["status"] == "returned"
    c = _anon(app_client)
    v = c.get(f"/api/public/r/{token}").json()
    assert v["items"][1]["review_note"] == "Please attach the last restore test."
    assert v["items"][0]["review_note"] == ""
    c.headers["X-PDPL-Request"] = "1"
    assert c.post(f"/api/public/r/{token}/items/{item}/files", files={"file": ("restore.pdf", PDF, "application/pdf")}).status_code == 201


def test_link_states_revoke_replace_expire(as_role, app_client, db):
    dpo = as_role("dpo")
    req = _make(dpo)
    old = req["token"]
    new = dpo.post(f"/api/evidence-requests/{req['id']}/link", json={"expires_days": 3}).json()["token"]
    c = _anon(app_client)
    assert c.get(f"/api/public/r/{old}").status_code == 404
    assert c.get(f"/api/public/r/{new}").status_code == 200
    dpo = as_role("dpo")
    dpo.post(f"/api/evidence-requests/{req['id']}/revoke")
    assert _anon(app_client).get(f"/api/public/r/{new}").status_code == 410
    dpo = as_role("dpo")
    newer = dpo.post(f"/api/evidence-requests/{req['id']}/link", json={}).json()
    assert newer["status"] == "open"
    row = db.execute(select(EvidenceRequest)).scalar_one()
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    c = _anon(app_client)
    r = c.get(f"/api/public/r/{newer['token']}")
    assert r.status_code == 410 and r.json()["detail"] == "link_expired"
    assert as_role("dpo").get("/api/evidence-requests").json()[0]["status"] == "expired"
    as_role("dpo").post(f"/api/evidence-requests/{req['id']}/close")
    assert as_role("dpo").post(f"/api/evidence-requests/{req['id']}/link", json={}).status_code == 409


def test_unknown_tokens_are_throttled(app_client):
    c = _anon(app_client)
    for _ in range(er._BAD_MAX):
        assert c.get("/api/public/r/" + "x" * 43).status_code == 404
    assert c.get("/api/public/r/" + "y" * 43).status_code == 429


def test_files_per_item_limit(as_role, app_client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "evidence_request_files_per_item", 2)
    req = _make(as_role("dpo"))
    c = _anon(app_client)
    c.headers["X-PDPL-Request"] = "1"
    url = f"/api/public/r/{req['token']}/items/{req['items'][0]['id']}/files"
    for n in range(2):
        assert c.post(url, files={"file": (f"{n}.txt", f"note {n}".encode(), "text/plain")}).status_code == 201
    assert c.post(url, files={"file": ("3.txt", b"note 3", "text/plain")}).status_code == 409


def test_a_link_works_inside_its_own_organisation_only(as_role, app_client):
    admin = as_role("admin")
    second = admin.post("/api/orgs", json={"name": "Delta Pharmacies"}).json()["id"]
    admin.post("/api/orgs/select", json={"id": second})
    req = _make(admin)
    c = _anon(app_client)
    c.cookies.set("pdpl_org", "1")  # whatever the browser says, the link decides
    v = c.get(f"/api/public/r/{req['token']}").json()
    assert v["organization"]["name"] == "Delta Pharmacies"
    c.headers["X-PDPL-Request"] = "1"
    item = req["items"][0]["id"]
    c.put(f"/api/public/r/{req['token']}/items/{item}", json={"response": "yes"})
    c.post(f"/api/public/r/{req['token']}/items/{item}/files", files={"file": ("p.pdf", PDF, "application/pdf")})
    admin = as_role("admin")
    admin.post("/api/orgs/select", json={"id": second})
    admin.post(f"/api/evidence-requests/{req['id']}/items/{item}/review", json={"decision": "accept"})
    with org_session(1) as s:
        assert s.execute(select(EvidenceFile)).scalars().all() == []
        assert s.execute(select(EvidenceRequest)).scalars().all() == []
    with org_session(second) as s:
        assert len(s.execute(select(EvidenceFile)).scalars().all()) == 1
        assert {e.org_id for e in s.execute(select(AuditLog).where(AuditLog.action.like("evidence_request.%"))).scalars()} == {second}
    admin.post("/api/orgs/select", json={"id": 1})
    assert admin.get(f"/api/evidence-requests/{req['id']}").status_code == 404
    assert admin.get("/api/orgs/overview").json()["items"][1]["evidence_to_review"] == 0
