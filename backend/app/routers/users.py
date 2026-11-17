from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import ROLES, Organisation, User
from ..security import MIN_PASSWORD_LEN, hash_password, require
from .auth import user_out

router = APIRouter(prefix="/api/users", tags=["users"])

ROLE_PATTERN = "^(" + "|".join(ROLES) + ")$"


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=256)
    role: str = Field(pattern=ROLE_PATTERN)
    # "all" or the ids of the organisations this user may open (ignored for admins)
    access: Literal["all"] | list[int] = "all"


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LEN, max_length=256)
    access: Literal["all"] | list[int] | None = None


def _access(db: Session, access) -> list[int] | None:
    if access == "all":
        return None
    known = set(db.execute(select(Organisation.id)).scalars())
    ids = sorted(set(access))
    if not ids or not set(ids) <= known:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_organisations")
    return ids


@router.get("")
def list_users(db: Session = Depends(get_db), _=Depends(require("users.manage"))):
    return [user_out(u) for u in db.execute(select(User).order_by(User.id)).scalars()]


@router.post("", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), actor: User = Depends(require("users.manage"))):
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
    u = User(username=body.username, display_name=body.display_name,
             password_hash=hash_password(body.password), role=body.role, org_ids=_access(db, body.access))
    db.add(u)
    db.flush()
    audit.record(db, actor, "user.create", "user", u.id,
                 {"username": u.username, "role": u.role, "org_ids": u.org_ids})
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
    if body.access is not None:
        ids = _access(db, body.access)
        if ids != u.org_ids:
            changes["org_ids"] = {"from": u.org_ids, "to": ids}
            u.org_ids = ids
    audit.record(db, actor, "user.update", "user", u.id, changes)
    db.commit()
    return user_out(u)
