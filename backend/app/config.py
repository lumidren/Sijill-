"""Runtime configuration.

Every legal deadline or duration is configuration with a default, never a
constant in code. Defaults reflect the project owner's working context and are
NOT verified legal citations (see docs/LEGAL-REVIEW.md).
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PDPL_", env_file=".env", extra="ignore")

    data_dir: Path = REPO_DIR / "data"
    # DATABASE_URL (no prefix) is honoured too, see database_url_resolved.
    database_url: str | None = None
    secret_key: str | None = None
    frontend_dist: Path = REPO_DIR / "frontend" / "dist"
    cookie_secure: bool = False
    session_hours: int = 12

    # Legal durations (defaults, unverified - see LEGAL-REVIEW.md)
    breach_regulator_hours: int = 72
    breach_individuals_hours: int = 72 + 72  # follow-up notice; placeholder default
    licence_validity_years: int = 3
    renewal_reminder_days: int = 90

    # Evidence
    evidence_stale_days: int = 30
    max_upload_mb: int = 20

    # Scheduler
    scheduler_enabled: bool = True
    collect_interval_hours: int = 24
    # Optional: AWS profile name or role ARN taken from the environment. Never stored in the DB.
    aws_profile: str | None = None
    aws_role_arn: str | None = None
    prowler_bin: str | None = None

    timezone_display: str = "Africa/Cairo"

    @property
    def database_url_resolved(self) -> str:
        import os

        url = self.database_url or os.environ.get("DATABASE_URL")
        if url:
            return url
        return f"sqlite:///{(self.data_dir / 'pdpl.db').as_posix()}"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.evidence_dir, self.inbox_dir):
            d.mkdir(parents=True, exist_ok=True)

    def resolved_secret(self) -> str:
        if self.secret_key:
            return self.secret_key
        self.ensure_dirs()
        f = self.data_dir / "secret.key"
        if not f.exists():
            f.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        return f.read_text(encoding="utf-8").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
