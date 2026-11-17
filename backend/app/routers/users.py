from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import ROLES, User
from ..security import MIN_PASSWORD_LEN, hash_password, require
from .auth import user_out

router = APIRouter(prefix="/api/users", tags=["users"])

ROLE_PATTERN = "^(" + "|".join(ROLES) + ")$"


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=256)
    role: str = Field(pattern=ROLE_PATTERN)


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LEN, max_length=256)


@router.get("")
def list_users(db: Session = Depends(get_db), _=Depends(require("users.manage"))):
    return [user_out(u) for u in db.execute(select(User).order_by(User.id)).scalars()]


@router.post("", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
    u = User(username=body.username, display_name=body.display_name,
             password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.flush()
    audit.record(db, actor, "user.create", "user", u.id, {"username": u.username, "role": u.role})
    db.commit()
    return user_out(u)


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db),
                actor: User = Depends(require("users.manage"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    changes: dict = {}
    if body.display_name is not None:
        u.display_name = body.display_name
        changes["display_name"] = body.display_name
    if body.role is not None and body.role != u.role:
        if u.id == actor.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_change_own_role")
        changes["role"] = {"from": u.role, "to": body.role}
        u.role = body.role
    if body.is_active is not None and body.is_active != u.is_active:
        if u.id == actor.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_deactivate_self")
        u.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
        changes["password"] = "changed"
    audit.record(db, actor, "user.update", "user", u.id, changes)
    db.commit()
    return user_out(u)
