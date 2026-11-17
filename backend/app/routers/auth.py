from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db, utcnow
from ..models import User
from ..security import (
    COOKIE_NAME, MIN_PASSWORD_LEN, capabilities_for, current_user, hash_password,
    make_session_token, verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_FAILS: dict[str, deque] = defaultdict(deque)
_WINDOW = 300
_MAX_FAILS = 5


def _throttled(key: str) -> bool:
    q = _FAILS[key]
    now = time.monotonic()
    while q and now - q[0] > _WINDOW:
        q.popleft()
    return len(q) >= _MAX_FAILS


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SetupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=256)


class LocaleIn(BaseModel):
    locale: str = Field(pattern=r"^(en|ar)$")


def user_out(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
        "locale": u.locale, "is_active": u.is_active, "capabilities": capabilities_for(u.role),
        "mfa_enabled": bool(u.totp_enabled),
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


def _set_cookie(resp: Response, user: User) -> None:
    s = get_settings()
    resp.set_cookie(
        COOKIE_NAME, make_session_token(user), httponly=True, samesite="strict",
        secure=s.cookie_secure, max_age=s.session_hours * 3600, path="/",
    )


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(User))
    return {"needs_setup": count == 0}


@router.post("/setup")
def first_admin(body: SetupIn, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(status.HTTP_409_CONFLICT, "already_set_up")
    u = User(username=body.username, display_name=body.display_name,
             password_hash=hash_password(body.password), role="admin")
    db.add(u)
    db.flush()
    audit.record(db, u, "user.setup_first_admin", "user", u.id, {"username": u.username})
    db.commit()
    _set_cookie(response, u)
    return user_out(u)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{body.username.lower()}"
    if _throttled(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts")
    u = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    if not u or not u.is_active or not verify_password(u.password_hash, body.password):
        _FAILS[key].append(time.monotonic())
        audit.record(db, None, "auth.login_failed", "user", None, {"username": body.username[:64]},
                     actor_name="anonymous")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    _FAILS.pop(key, None)
    if u.totp_enabled:
        # password was right; the session cookie is only issued after the second factor
        from .mfa import make_mfa_token
        audit.record(db, u, "auth.password_ok_mfa_pending", "user", u.id)
        db.commit()
        return {"mfa_required": True, "mfa_token": make_mfa_token(u)}
    u.last_login_at = utcnow()
    audit.record(db, u, "auth.login", "user", u.id)
    db.commit()
    _set_cookie(response, u)
    return user_out(u)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.put("/me/locale")
def set_locale(body: LocaleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    u.locale = body.locale
    db.commit()
    return user_out(u)
