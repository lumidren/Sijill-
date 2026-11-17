from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import DateTime, Integer, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker, with_loader_criteria
from sqlalchemy.types import TypeDecorator

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local_date(now: datetime):
    """Today's calendar date where the users are (PDPL_TIMEZONE_DISPLAY), not in UTC.

    Due dates are calendar dates; between midnight and 02:00 in Cairo the UTC date is still
    yesterday, which used to make "due today" read as "due tomorrow".
    """
    from zoneinfo import ZoneInfo

    return now.astimezone(ZoneInfo(get_settings().timezone_display)).date()


class UTCDateTime(TypeDecorator):
    """Stores datetimes as UTC and always returns timezone-aware UTC values.

    SQLite drops tzinfo, Postgres keeps it; this makes both behave the same.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime given; store UTC-aware datetimes only")
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


# --- Organisations (multi-tenancy) -------------------------------------------------------------
# One install can hold several client organisations. Every table that holds an organisation's
# data mixes in OrgScoped. A session carries the organisation it works for in
# session.info["org_id"]; ORM reads, updates and deletes are then filtered to that organisation
# automatically, and new rows are stamped with it. Users and the audit log are install-wide.
# See docs/DECISIONS.md #34.

DEFAULT_ORG_ID = 1
ORG_COOKIE = "pdpl_org"


class OrgScoped:
    org_id: Mapped[int] = mapped_column(Integer, index=True)


@event.listens_for(Session, "do_orm_execute")
def _org_filter(state) -> None:
    # A session that names no organisation works on the default one, never on all of them.
    org = state.session.info.get("org_id") or DEFAULT_ORG_ID
    if state.execution_options.get("all_orgs"):
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(OrgScoped, lambda cls: cls.org_id == org, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _org_stamp(session: Session, _ctx, _instances) -> None:
    org = session.info.get("org_id") or DEFAULT_ORG_ID
    for obj in session.new:
        if isinstance(obj, OrgScoped) and obj.org_id is None:
            obj.org_id = org


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


def make_engine(url: str) -> Engine:
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def init_engine(url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    settings = get_settings()
    settings.ensure_dirs()
    if _engine is not None:
        _engine.dispose()
    _engine = make_engine(url or settings.database_url_resolved)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def org_session(org_id: int) -> Session:
    """A session that only sees (and writes to) one organisation. Caller closes it."""
    db = session_factory()()
    db.info["org_id"] = org_id
    return db


def get_db(request: Request) -> Iterator[Session]:
    # The organisation the cookie asks for; security.current_user checks the user may see it (and
    # falls back to one they may) before any endpoint reads data.
    raw = request.cookies.get(ORG_COOKIE, "")
    db = session_factory()()
    db.info["org_id"] = int(raw) if raw.isdigit() else DEFAULT_ORG_ID
    try:
        yield db
    finally:
        db.close()
