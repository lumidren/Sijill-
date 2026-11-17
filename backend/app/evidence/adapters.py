"""Evidence adapters. Each one produces OCSF findings and hands them to service.import_findings.

- InboxAdapter:      imports findings files dropped into <data>/inbox (Prowler output from another
                     machine, Linux collector output copied off a host, CI artefacts, ...).
- ProwlerCliAdapter: runs Prowler as a subprocess when it is installed AND AWS credentials are
                     available from the environment. The platform never stores credentials: it
                     only passes a profile name or role ARN through to Prowler.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from .mapping import get_mapping
from .ocsf import FindingsError
from .service import DuplicateImport, import_findings


@dataclass
class AdapterResult:
    adapter: str
    status: str  # ok | skipped | error
    detail: str = ""
    runs: int = 0

    def as_dict(self) -> dict:
        return {"adapter": self.adapter, "status": self.status, "detail": self.detail, "runs": self.runs}


class InboxAdapter:
    name = "inbox"

    def __init__(self, inbox: Path | None = None):
        self.inbox = inbox or get_settings().inbox_dir

    def available(self) -> tuple[bool, str]:
        return True, str(self.inbox)

    def collect(self, db: Session) -> AdapterResult:
        self.inbox.mkdir(parents=True, exist_ok=True)
        done, failed = self.inbox / "processed", self.inbox / "failed"
        done.mkdir(exist_ok=True)
        failed.mkdir(exist_ok=True)
        files = sorted(p for p in self.inbox.iterdir() if p.is_file() and p.suffix.lower() == ".json")
        runs, errors = 0, []
        for p in files:
            try:
                runs += len(import_findings(db, p.read_bytes(), p.name, actor=None, source="inbox",
                                            actor_name="scheduler"))
                db.commit()
                shutil.move(str(p), done / p.name)
            except (FindingsError, DuplicateImport) as e:
                db.rollback()
                code = e.code if isinstance(e, FindingsError) else "duplicate_file"
                errors.append(f"{p.name}: {code}")
                shutil.move(str(p), failed / p.name)
        status = "ok" if not errors else "error"
        detail = f"{len(files)} file(s), {runs} run(s)" + (f"; failed: {', '.join(errors)}" if errors else "")
        return AdapterResult(self.name, status if files else "ok", detail if files else "inbox empty", runs)


CREDENTIAL_ENV = ("AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")


class ProwlerCliAdapter:
    name = "prowler"

    def __init__(self, runner=subprocess.run):
        self.runner = runner
        self.settings = get_settings()

    def binary(self) -> str | None:
        return self.settings.prowler_bin or shutil.which("prowler")

    def credentials_hint(self) -> str | None:
        """Where credentials would come from - a name, never a secret."""
        if self.settings.aws_role_arn:
            return "role"
        if self.settings.aws_profile:
            return "profile"
        for var in CREDENTIAL_ENV:
            if os.environ.get(var):
                return "environment"
        return None

    def available(self) -> tuple[bool, str]:
        if not self.binary():
            return False, "prowler_not_installed"
        if not self.credentials_hint():
            return False, "no_aws_credentials_in_environment"
        return True, "ready"

    def command(self, outdir: str) -> list[str]:
        checks = sorted(c for c, info in get_mapping().checks.items() if info.provider == "aws")
        cmd = [self.binary(), "aws", "--checks", *checks, "--output-formats", "json-ocsf",
               "--output-directory", outdir, "--output-filename", "sijill", "--no-banner"]
        if self.settings.aws_profile:
            cmd += ["--profile", self.settings.aws_profile]
        if self.settings.aws_role_arn:
            cmd += ["--role", self.settings.aws_role_arn]
        return cmd

    def collect(self, db: Session) -> AdapterResult:
        ok, why = self.available()
        if not ok:
            return AdapterResult(self.name, "skipped", why)
        with tempfile.TemporaryDirectory(prefix="pdpl-prowler-") as tmp:
            cmd = self.command(tmp)
            proc = self.runner(cmd, capture_output=True, text=True, timeout=3 * 3600)
            # Prowler exits 3 when findings fail; that is a successful scan.
            if proc.returncode not in (0, 3):
                return AdapterResult(self.name, "error", f"prowler exited with {proc.returncode}")
            outputs = sorted(Path(tmp).glob("*.ocsf.json"))
            if not outputs:
                return AdapterResult(self.name, "error", "prowler produced no json-ocsf output")
            runs = 0
            for out in outputs:
                runs += len(import_findings(db, out.read_bytes(), out.name, actor=None, source="prowler-run",
                                            actor_name="scheduler"))
            db.commit()
            return AdapterResult(self.name, "ok", f"{runs} run(s) imported", runs)


def adapters() -> list:
    return [InboxAdapter(), ProwlerCliAdapter()]
