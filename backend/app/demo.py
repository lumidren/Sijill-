"""Demo seed: a fictional private clinic. Extended phase by phase."""
from __future__ import annotations

from sqlalchemy import func, select

from . import audit
from .db import get_engine, session_factory
from .models import User
from .security import hash_password

DEMO_PASSWORD = "pdpl-demo-2026"
DEMO_USERS = [
    ("admin", "Karim Fathy", "admin"),
    ("dpo", "Dr. Mona Hassan", "dpo"),
    ("it", "Omar Adel", "it"),
    ("auditor", "Salma Nabil", "auditor"),
]


def _reset_db() -> None:
    from . import migrate
    from .db import Base

    eng = get_engine()
    with eng.begin() as conn:
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for t in reversed(Base.metadata.sorted_tables):
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{t.name}"')
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrate.upgrade()


def seed_demo(reset: bool = False, only_if_empty: bool = False) -> str:
    if reset:
        _reset_db()
    with session_factory()() as db:
        if db.scalar(select(func.count()).select_from(User)):
            if only_if_empty:
                return "database already has users; demo seed skipped"
            if not reset:
                return "database is not empty; use --reset to replace it with the demo"
        users = {}
        for username, name, role in DEMO_USERS:
            u = User(username=username, display_name=name, password_hash=hash_password(DEMO_PASSWORD), role=role)
            db.add(u)
            users[role] = u
        db.flush()
        audit.record(db, None, "demo.seed", "system", None, {"users": [u[0] for u in DEMO_USERS]},
                     actor_name="seed")
        extra = _seed_extras(db, users)
        db.commit()
    return "demo seeded" + (f": {extra}" if extra else "")


def _seed_extras(db, users) -> str:
    """Hook for later phases (catalog answers, check history, register, incidents)."""
    try:
        from .demo_data import seed_all
    except ModuleNotFoundError:
        return ""
    return seed_all(db, users)
