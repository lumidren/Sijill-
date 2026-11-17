"""Two-factor sign-in: enrol, confirm, disable, complete a login, and admin reset."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit, totp
from ..config import get_settings
from ..db import get_db, utcnow
from ..models import User
from ..security import current_user, require
from .auth import _FAILS, _MAX_FAILS, _set_cookie, _throttled, user_out

router = APIRouter(tags=["mfa"])
MFA_TOKEN_SECONDS = 300


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class VerifyIn(BaseModel):
    mfa_token: str = Field(min_length=10, max_length=512)
    code: str = Field(min_length=6, max_length=8)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().resolved_secret(), salt="pdpl-mfa")


def make_mfa_token(user: User) -> str:
    return _serializer().dumps({"uid": user.id, "pv": user.password_hash[-12:]})


def _check(db: Session, u: User, code: str) -> bool:
    if not u.totp_secret:
        return False
    counter = totp.verify(u.totp_secret, code, u.totp_last_counter)
    if counter is None:
        return False
    u.totp_last_counter = counter
    return True


@router.post("/api/auth/mfa/setup")
def setup(db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(User, user.id)
    if u.totp_enabled:
        raise HTTPException(409, "already_enabled")
    u.totp_secret, u.totp_last_counter = totp.new_secret(), None
    db.commit()
    return {"secret": u.totp_secret, "otpauth_uri": totp.otpauth_uri(u.totp_secret, u.username)}


@router.post("/api/auth/mfa/enable")
def enable(body: CodeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(User, user.id)
    if u.totp_enabled:
        raise HTTPException(409, "already_enabled")
    if not _check(db, u, body.code):
        raise HTTPException(422, "invalid_code")
    u.totp_enabled = True
    audit.record(db, u, "auth.mfa_enabled", "user", u.id)
    db.commit()
    return user_out(u)


@router.post("/api/auth/mfa/disable")
def disable(body: CodeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(User, user.id)
    if not u.totp_enabled:
        raise HTTPException(409, "not_enabled")
    if not _check(db, u, body.code):
        raise HTTPException(422, "invalid_code")
    u.totp_enabled, u.totp_secret, u.totp_last_counter = False, None, None
    audit.record(db, u, "auth.mfa_disabled", "user", u.id)
    db.commit()
    return user_out(u)


@router.post("/api/auth/mfa/verify")
def verify_login(body: VerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        data = _serializer().loads(body.mfa_token, max_age=MFA_TOKEN_SECONDS)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "mfa_token_expired")
    u = db.get(User, data.get("uid"))
    if not u or not u.is_active or not u.totp_enabled or u.password_hash[-12:] != data.get("pv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    key = f"mfa:{u.id}"
    if _throttled(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts")
    if not _check(db, u, body.code):
        import time
        _FAILS[key].append(time.monotonic())
        audit.record(db, u, "auth.mfa_failed", "user", u.id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_code")
    _FAILS.pop(key, None)
    u.last_login_at = utcnow()
    audit.record(db, u, "auth.login", "user", u.id, {"mfa": True})
    db.commit()
    _set_cookie(response, u)
    return user_out(u)


@router.post("/api/users/{user_id}/mfa/reset")
def admin_reset(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "not_found")
    u.totp_enabled, u.totp_secret, u.totp_last_counter = False, None, None
    audit.record(db, actor, "auth.mfa_reset", "user", u.id, {"username": u.username})
    db.commit()
    return user_out(u)


__all__ = ["router", "make_mfa_token", "_MAX_FAILS"]
