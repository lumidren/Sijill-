import pytest
from sqlalchemy import text

from app.audit import AuditImmutableError, verify_chain
from app.models import AuditLog
from tests.conftest import PASSWORD, ROLES


def test_first_run_setup_then_locked(app_client, db):
    assert app_client.get("/api/auth/status").json() == {"needs_setup": True}
    r = app_client.post("/api/auth/setup", json={"username": "owner", "display_name": "Owner",
                                                 "password": "long-enough-pw"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert app_client.get("/api/auth/status").json() == {"needs_setup": False}
    r = app_client.post("/api/auth/setup", json={"username": "xx2", "display_name": "X",
                                                 "password": "long-enough-pw"})
    assert r.status_code == 409


@pytest.mark.parametrize("role", ROLES)
def test_each_role_can_log_in(as_role, role):
    c = as_role(role)
    me = c.get("/api/auth/me").json()
    assert me["role"] == role
    assert "read" in me["capabilities"]


def test_bad_password_rejected_and_throttled(app_client, users):
    for _ in range(5):
        r = app_client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401
    r = app_client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 429


def test_unauthenticated_is_401(app_client, users):
    assert app_client.get("/api/auth/me").status_code == 401
    assert app_client.get("/api/users").status_code == 401


def test_mutation_requires_csrf_header(as_role):
    c = as_role("admin")
    del c.headers["X-PDPL-Request"]
    r = c.put("/api/auth/me/locale", json={"locale": "ar"})
    assert r.status_code == 403


def test_locale_switch(as_role):
    c = as_role("dpo")
    assert c.put("/api/auth/me/locale", json={"locale": "ar"}).json()["locale"] == "ar"
    assert c.put("/api/auth/me/locale", json={"locale": "fr"}).status_code == 422


@pytest.mark.parametrize("role", ["dpo", "it", "auditor"])
def test_only_admin_manages_users(as_role, role):
    c = as_role(role)
    assert c.get("/api/users").status_code == 403
    r = c.post("/api/users", json={"username": "new1", "display_name": "N", "password": "x" * 12,
                                   "role": "auditor"})
    assert r.status_code == 403


def test_admin_creates_and_deactivates_user(as_role):
    c = as_role("admin")
    r = c.post("/api/users", json={"username": "newbie", "display_name": "N", "password": "x" * 12,
                                   "role": "auditor"})
    assert r.status_code == 201
    uid = r.json()["id"]
    assert c.post("/api/users", json={"username": "newbie", "display_name": "N", "password": "x" * 12,
                                      "role": "auditor"}).status_code == 409
    assert c.patch(f"/api/users/{uid}", json={"is_active": False}).json()["is_active"] is False
    me = c.get("/api/auth/me").json()
    assert c.patch(f"/api/users/{me['id']}", json={"role": "auditor"}).status_code == 400


def test_password_change_invalidates_old_session(app_client, users, db):
    from tests.conftest import login
    login(app_client, "dpo")
    assert app_client.get("/api/auth/me").status_code == 200
    from app.security import hash_password
    u = users["dpo"]
    u.password_hash = hash_password("another-password-1")
    db.commit()
    assert app_client.get("/api/auth/me").status_code == 401


def test_audit_log_records_and_chain_verifies(as_role, db):
    c = as_role("admin")
    c.post("/api/users", json={"username": "aud2", "display_name": "A", "password": "x" * 12, "role": "auditor"})
    items = c.get("/api/audit").json()["items"]
    actions = [i["action"] for i in items]
    assert "user.create" in actions and "auth.login" in actions
    assert c.get("/api/audit/verify").json() == {"ok": True, "first_bad_id": None}
    # passwords never appear in the audit trail
    assert "x" * 12 not in str(items)


def test_audit_log_is_append_only(as_role, db):
    as_role("admin")
    entry = db.query(AuditLog).first()
    entry.action = "tampered"
    with pytest.raises(AuditImmutableError):
        db.commit()
    db.rollback()
    with pytest.raises(Exception):
        db.execute(text("UPDATE audit_log SET action='x'"))
        db.commit()
    db.rollback()
    with pytest.raises(Exception):
        db.execute(text("DELETE FROM audit_log"))
        db.commit()
    db.rollback()
    assert verify_chain(db) == (True, None)


def test_auditor_reads_audit_log_but_it_cannot(as_role):
    assert as_role("auditor").get("/api/audit").status_code == 200
    assert as_role("it").get("/api/audit").status_code == 403
