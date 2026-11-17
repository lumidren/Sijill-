"""Run Alembic migrations programmatically (used by the CLI, start script and tests)."""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from .config import BACKEND_DIR


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    if url:
        cfg.attributes["url"] = url
    return cfg


def upgrade(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")
