import base64
import time

from app import totp
from app.models import User
from tests.conftest import PASSWORD

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


def test_rfc6238_test_vectors():
    # RFC 6238 appendix B (SHA1), truncated to the 6 digits authenticator apps use
    assert totp.hotp(b"12345678901234567890", 59 // 30, digits=8) == "94287082"
    assert totp.code_at(RFC_SECRET, 59) == "287082"
    assert totp.code_at(RFC_SECRET, 1111111109) == "081804"


def test_window_and_replay():
    t = 1_800_000_000
    code = totp.code_at(RFC_SECRET, t)
    step = t // 30
    assert totp.verify(RFC_SECRET, code, at=t) == step
    assert totp.verify(RFC_SECRET, code, at=t + 30) == step  # one step late is fine
    assert totp.verify(RFC_SECRET, code, at=t + 90) is None  # too late
    assert totp.verify(RFC_SECRET, code, last_counter=step, at=t) is None  # replay
    assert totp.verify(RFC_SECRET, "12345", at=t) is None and totp.verify(RFC_SECRET, "abcdef", at=t) is None


def test_otpauth_uri():
    uri = totp.otpauth_uri("ABCDEF", "dpo")
    assert uri.startswith("otpauth://totp/PDPL-Ready%3Adpo?") and "secret=ABCDEF" in uri and "issuer=PDPL-Ready" in uri


def _enable(c, db) -> str:
    secret = c.post("/api/auth/mfa/setup").json()["secret"]
    assert c.post("/api/auth/mfa/enable", json={"code": "000000"}).status_code == 422
    r = c.post("/api/auth/mfa/enable", json={"code": totp.code_at(secret)})
    assert r.status_code == 200 and r.json()["mfa_enabled"] is True
    return secret


def test_login_requires_second_factor_once_enabled(as_role, app_client, db):
    c = as_role("dpo")
    secret = _enable(c, db)
    c.post("/api/auth/logout")
    c.cookies.clear()
    r = c.post("/api/auth/login", json={"username": "dpo", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["mfa_required"] is True
    assert c.get("/api/auth/me").status_code == 401  # no session yet
    token = r.json()["mfa_token"]
    assert c.post("/api/auth/mfa/verify", json={"mfa_token": token, "code": "123456"}).status_code == 401
    # the code used to enable is a replay; wait for it not to matter by asking for the next step's code
    code = totp.code_at(secret, time.time() + 30)
    ok = c.post("/api/auth/mfa/verify", json={"mfa_token": token, "code": code})
    assert ok.status_code == 200 and ok.json()["username"] == "dpo"
    assert c.get("/api/auth/me").status_code == 200
    # the same code cannot be used twice
    assert c.post("/api/auth/mfa/verify", json={"mfa_token": token, "code": code}).status_code == 401
    assert c.post("/api/auth/mfa/verify", json={"mfa_token": "forged-token-value", "code": code}).status_code == 401


def test_mfa_failures_are_throttled(as_role, db):
    c = as_role("it")
    _enable(c, db)
    c.cookies.clear()
    token = c.post("/api/auth/login", json={"username": "it", "password": PASSWORD}).json()["mfa_token"]
    for _ in range(5):
        assert c.post("/api/auth/mfa/verify", json={"mfa_token": token, "code": "000000"}).status_code == 401
    assert c.post("/api/auth/mfa/verify", json={"mfa_token": token, "code": "000000"}).status_code == 429


def test_admin_can_reset_a_lost_device(as_role, db):
    c = as_role("auditor")
    _enable(c, db)
    uid = c.get("/api/auth/me").json()["id"]
    assert as_role("dpo").post(f"/api/users/{uid}/mfa/reset").status_code == 403
    r = as_role("admin").post(f"/api/users/{uid}/mfa/reset")
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False
    db.expire_all()
    assert db.get(User, uid).totp_secret is None
    actions = [i["action"] for i in as_role("admin").get("/api/audit").json()["items"]]
    assert "auth.mfa_reset" in actions and "auth.mfa_enabled" in actions
