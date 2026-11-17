from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Isolate every test session in its own data dir before the app is imported.
_TMP = Path(tempfile.mkdtemp(prefix="pdpl-test-"))
os.environ["PDPL_DATA_DIR"] = str(_TMP)
os.environ["PDPL_SCHEDULER_ENABLED"] = "false"
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import migrate  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_engine, session_factory  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "correct-horse-battery"
ROLES = ("admin", "dpo", "it", "auditor")


def _fresh_db() -> None:
    url = os.environ.get("PDPL_TEST_DATABASE_URL")
    if url:  # CI Postgres
        from sqlalchemy import text

        eng = init_engine(url)
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        migrate.upgrade(url)
        init_engine(url)
        s = get_settings()
        shutil.rmtree(s.evidence_dir, ignore_errors=True)  # same clean slate as the SQLite path
        s.ensure_dirs()
        return
    from app import db as dbmod

    if dbmod._engine is not None:
        dbmod._engine.dispose()
    s = get_settings()
    for p in s.data_dir.glob("pdpl.db*"):
        p.unlink()
    shutil.rmtree(s.evidence_dir, ignore_errors=True)
    s.ensure_dirs()
    init_engine()
    migrate.upgrade()
    init_engine()


@pytest.fixture()
def db():
    _fresh_db()
    with session_factory()() as s:
        yield s


@pytest.fixture()
def app_client(db):
    from app.main import create_app
    from app.routers import auth

    auth._FAILS.clear()
    app = create_app(start_scheduler=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def users(db):
    out = {}
    for r in ROLES:
        u = User(username=r, display_name=r.title(), password_hash=hash_password(PASSWORD), role=r)
        db.add(u)
        out[r] = u
    db.commit()
    return out


def login(client: TestClient, username: str) -> TestClient:
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.headers["X-PDPL-Request"] = "1"
    return client


@pytest.fixture()
def as_role(app_client, users):
    def _as(role: str) -> TestClient:
        app_client.cookies.clear()
        return login(app_client, role)

    return _as
