"""Passwords (Argon2), signed session cookies and role permissions."""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

COOKIE_NAME = "pdpl_session"
CSRF_HEADER = "x-pdpl-request"

_hasher = PasswordHasher()

# capability -> roles allowed. Enforced server-side on every endpoint.
PERMISSIONS: dict[str, set[str]] = {
    "read": {"admin", "dpo", "it", "auditor"},
    "audit.read": {"admin", "dpo", "auditor"},
    "users.manage": {"admin"},
    "settings.manage": {"admin"},
    "assessment.write": {"admin", "dpo"},
    "evidence.upload": {"admin", "dpo", "it"},
    "checks.write": {"admin", "it"},
    "register.write": {"admin", "dpo"},
    "obligations.write": {"admin", "dpo"},
    "incidents.write": {"admin", "dpo", "it"},
    "reports.generate": {"admin", "dpo", "it", "auditor"},
    "tasks.write": {"admin", "dpo", "it"},
    "governance.write": {"admin", "dpo"},
    "risks.accept": {"admin"},
    "approve": {"admin"},
}

MIN_PASSWORD_LEN = 10


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().resolved_secret(), salt="pdpl-session")


def make_session_token(user: User) -> str:
    # Binding to a fragment of the password hash means a password change logs out other sessions.
    return _serializer().dumps({"uid": user.id, "pv": user.password_hash[-12:]})


def read_session_token(token: str) -> dict | None:
    try:
        return _serializer().loads(token, max_age=get_settings().session_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    data = read_session_token(token) if token else None
    if not data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    user = db.get(User, data.get("uid"))
    if not user or not user.is_active or user.password_hash[-12:] != data.get("pv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing_csrf_header")
    return user


def require(capability: str):
    allowed = PERMISSIONS[capability]

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden_for_role")
        return user

    return dep


def capabilities_for(role: str) -> list[str]:
    return sorted(c for c, roles in PERMISSIONS.items() if role in roles)
