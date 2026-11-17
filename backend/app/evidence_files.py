"""Evidence file storage: type and size checks, SHA-256 content addressing, timestamps."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .models import EvidenceFile, User

# extension -> (content type, magic-byte check)
ALLOWED = {
    ".pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    ".png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", lambda b: b.startswith(b"PK\x03\x04")),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", lambda b: b.startswith(b"PK\x03\x04")),
    ".txt": ("text/plain", lambda b: _is_text(b)),
    ".csv": ("text/csv", lambda b: _is_text(b)),
    ".json": ("application/json", lambda b: _is_text(b)),
}


def _is_text(b: bytes) -> bool:
    try:
        b[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return False
    return b"\x00" not in b[:4096]


class EvidenceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()؀-ۿ]", "_", name).strip(" .")
    return (name or "evidence")[:200]


def validate(data: bytes, filename: str) -> tuple[str, str]:
    ext = Path(filename.lower()).suffix
    if ext not in ALLOWED:
        raise EvidenceError("bad_type")
    if len(data) == 0:
        raise EvidenceError("empty_file")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise EvidenceError("too_large")
    ctype, check = ALLOWED[ext]
    if not check(data):
        raise EvidenceError("content_mismatch")
    return ext, ctype


def write_blob(data: bytes, filename: str) -> tuple[str, str, str]:
    """Validate and store content-addressed. Returns (stored_name, content_type, sha256)."""
    ext, ctype = validate(data, filename)
    sha = hashlib.sha256(data).hexdigest()
    settings = get_settings()
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{sha}{ext}"
    path = settings.evidence_dir / stored
    # Content-addressed: an existing file with this name must hold these exact bytes. If it was
    # damaged or tampered with, the fresh upload repairs it rather than silently keeping the bad copy.
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        path.write_bytes(data)
    return stored, ctype, sha


def store(db: Session, data: bytes, filename: str, requirement_id: str | None, actor: User | None,
          description: str = "", uploaded_at: datetime | None = None) -> EvidenceFile:
    stored, ctype, sha = write_blob(data, filename)
    ev = EvidenceFile(
        requirement_id=requirement_id, filename=safe_name(filename), stored_name=stored, content_type=ctype,
        size=len(data), sha256=sha, description=description[:2000], uploaded_by_id=actor.id if actor else None,
        uploaded_at=uploaded_at or utcnow(),
    )
    db.add(ev)
    db.flush()
    return ev


def path_of(ev: EvidenceFile) -> Path:
    return get_settings().evidence_dir / ev.stored_name


def verify(ev: EvidenceFile) -> bool:
    p = path_of(ev)
    return p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == ev.sha256
