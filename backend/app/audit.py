"""Append-only, hash-chained audit log."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import AuditLog, User

GENESIS = "0" * 64


def _digest(prev_hash: str, at_iso: str, actor: str, action: str, entity_type: str,
            entity_id: str | None, detail: dict) -> str:
    payload = json.dumps(
        [prev_hash, at_iso, actor, action, entity_type, entity_id, detail],
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record(db: Session, actor: User | None, action: str, entity_type: str,
           entity_id: Any = None, detail: dict | None = None, actor_name: str | None = None) -> AuditLog:
    """Append one audit entry. Caller commits."""
    last = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    prev = last.hash if last else GENESIS
    at = utcnow().replace(microsecond=0)
    name = actor.username if actor else (actor_name or "system")
    eid = None if entity_id is None else str(entity_id)
    d = _scrub(detail or {})
    entry = AuditLog(
        at=at, actor_id=actor.id if actor else None, actor_name=name, action=action,
        entity_type=entity_type, entity_id=eid, detail=d, prev_hash=prev,
        hash=_digest(prev, at.isoformat(), name, action, entity_type, eid, d),
    )
    db.add(entry)
    db.flush()
    return entry


_SECRET_KEYS = {"password", "password_hash", "secret", "token", "access_key", "secret_access_key", "session_token"}


def _scrub(detail: dict) -> dict:
    """Never let a credential reach the audit log."""
    out = {}
    for k, v in detail.items():
        if k.lower() in _SECRET_KEYS:
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = _scrub(v)
        else:
            out[k] = v
    return out


def verify_chain(db: Session) -> tuple[bool, int | None]:
    """Recompute every hash. Returns (ok, first_bad_id)."""
    prev = GENESIS
    for e in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
        at = e.at.replace(microsecond=0).isoformat()
        expected = _digest(prev, at, e.actor_name, e.action, e.entity_type, e.entity_id, e.detail or {})
        if e.prev_hash != prev or e.hash != expected:
            return False, e.id
        prev = e.hash
    return True, None


class AuditImmutableError(RuntimeError):
    pass


@event.listens_for(AuditLog, "before_update")
def _block_update(*_a):
    raise AuditImmutableError("audit log entries cannot be modified")


@event.listens_for(AuditLog, "before_delete")
def _block_delete(*_a):
    raise AuditImmutableError("audit log entries cannot be deleted")
