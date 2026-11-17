"""Evidence requests: ask client staff for answers and files through a private link.

The consultant picks requirements and gets a link once. The recipient opens it without an account,
answers each question, attaches files and submits. Nothing they send touches the assessment until
the consultant accepts an item; accepted files become ordinary evidence on that requirement.

Link safety: 256-bit random token, only its SHA-256 stored; expiry; revoke and replace; per-IP
throttle on unknown tokens; the custom CSRF header on every write; no-store and noindex headers.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..catalog import get_catalog
from ..config import get_settings
from ..db import get_db, utcnow
from ..evidence_files import EvidenceError, path_of, safe_name, verify, write_blob
from ..models import AppSetting, EvidenceFile, EvidenceRequest, EvidenceRequestFile, EvidenceRequestItem, Organisation, User
from ..posture import take_snapshot
from ..security import CSRF_HEADER, require

router = APIRouter(prefix="/api/evidence-requests", tags=["evidence requests"])
public = APIRouter(prefix="/api/public/r", tags=["evidence requests (public link)"])

MAX_DAYS = 60
_BAD: dict[str, deque] = defaultdict(deque)  # ip -> times of unknown-token lookups
_BAD_WINDOW, _BAD_MAX = 300, 20


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    t = secrets.token_urlsafe(32)
    return t, _hash(t)


def effective_status(r: EvidenceRequest, now=None) -> str:
    now = now or utcnow()
    if r.status == "open" and r.expires_at <= now:
        return "expired"
    return r.status


# ------------------------------------------------------------------------------------------ output

def _file_out(f: EvidenceRequestFile, public_view: bool = False) -> dict:
    out = {"id": f.id, "filename": f.filename, "size": f.size, "uploaded_at": f.uploaded_at.isoformat()}
    if not public_view:
        out.update({"sha256": f.sha256, "content_type": f.content_type, "evidence_file_id": f.evidence_file_id})
    return out


def _item_out(i: EvidenceRequestItem, public_view: bool = False) -> dict:
    req = get_catalog().requirement(i.requirement_id)
    out = {
        "id": i.id, "requirement_id": i.requirement_id, "label": req.label if req else i.requirement_id,
        "title": req.title.as_dict() if req else {"en": i.requirement_id},
        "question": req.question.as_dict() if req else {"en": ""},
        "ask": i.ask, "response": i.response, "status": i.status,
        "responded_at": i.responded_at.isoformat() if i.responded_at else None,
        "review_note": i.review_note if (i.status == "returned" or not public_view) else "",
        "files": [_file_out(f, public_view) for f in i.files],
    }
    if not public_view:
        out["reviewed_at"] = i.reviewed_at.isoformat() if i.reviewed_at else None
    return out


def request_out(r: EvidenceRequest, detail: bool = False) -> dict:
    counts = {s: 0 for s in ("open", "answered", "accepted", "returned")}
    for i in r.items:
        counts[i.status] = counts.get(i.status, 0) + 1
    out = {
        "id": r.id, "title": r.title, "recipient": r.recipient, "recipient_contact": r.recipient_contact,
        "message": r.message, "status": effective_status(r), "expires_at": r.expires_at.isoformat(),
        "created_at": r.created_at.isoformat(), "first_opened_at": r.first_opened_at.isoformat() if r.first_opened_at else None,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "total": len(r.items), "counts": counts, "files": sum(len(i.files) for i in r.items),
    }
    if detail:
        out["items"] = [_item_out(i) for i in r.items]
    return out


# ------------------------------------------------------------------------------------ consultant

class RequestIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    recipient: str = Field(min_length=1, max_length=128)
    recipient_contact: str = Field("", max_length=255)
    message: str = Field("", max_length=4000)
    requirement_ids: list[str] = Field(min_length=1, max_length=60)
    asks: dict[str, str] = Field(default_factory=dict)
    expires_days: int = Field(default_factory=lambda: get_settings().evidence_request_days, ge=1, le=MAX_DAYS)

    @field_validator("requirement_ids")
    @classmethod
    def known(cls, v: list[str]) -> list[str]:
        cat = get_catalog()
        out = list(dict.fromkeys(x.strip().lower() for x in v if x.strip()))
        bad = [x for x in out if not cat.requirement(x)]
        if bad or not out:
            raise ValueError(f"unknown requirement: {', '.join(bad) or '(none)'}")
        return out

    @field_validator("asks")
    @classmethod
    def short_asks(cls, v: dict[str, str]) -> dict[str, str]:
        if any(len(x) > 2000 for x in v.values()):
            raise ValueError("note too long")
        return {k.lower(): x.strip() for k, x in v.items()}


class LinkIn(BaseModel):
    expires_days: int = Field(default_factory=lambda: get_settings().evidence_request_days, ge=1, le=MAX_DAYS)


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(accept|return)$")
    note: str = Field("", max_length=2000)


def _get(db: Session, rid: int) -> EvidenceRequest:
    r = db.get(EvidenceRequest, rid)
    if not r:
        raise HTTPException(404, "not_found")
    return r


@router.get("")
def list_requests(db: Session = Depends(get_db), _=Depends(require("read"))):
    rows = db.execute(select(EvidenceRequest).order_by(EvidenceRequest.created_at.desc())).scalars()
    return [request_out(r) for r in rows]


@router.post("", status_code=201)
def create(body: RequestIn, db: Session = Depends(get_db), actor: User = Depends(require("evidence_requests.manage"))):
    token, h = new_token()
    r = EvidenceRequest(title=body.title.strip(), recipient=body.recipient.strip(), recipient_contact=body.recipient_contact.strip(),
                        message=body.message.strip(), token_hash=h, expires_at=utcnow() + timedelta(days=body.expires_days),
                        created_by_id=actor.id)
    r.items = [EvidenceRequestItem(requirement_id=x, ask=body.asks.get(x, "")) for x in body.requirement_ids]
    db.add(r)
    db.flush()
    audit.record(db, actor, "evidence_request.create", "evidence_request", r.id,
                 {"title": r.title, "recipient": r.recipient, "requirements": body.requirement_ids, "expires_at": r.expires_at.isoformat()})
    db.commit()
    # The token is shown this once; only its hash is kept.
    return {**request_out(r, detail=True), "token": token}


@router.get("/{rid}")
def get_request(rid: int, db: Session = Depends(get_db), _=Depends(require("read"))):
    return request_out(_get(db, rid), detail=True)


@router.post("/{rid}/link")
def new_link(rid: int, body: LinkIn, db: Session = Depends(get_db), actor: User = Depends(require("evidence_requests.manage"))):
    """Replace the link (the old one stops working) and reopen the request if it was revoked."""
    r = _get(db, rid)
    if r.status == "closed":
        raise HTTPException(409, "request_closed")
    token, r.token_hash = new_token()
    r.expires_at = utcnow() + timedelta(days=body.expires_days)
    if r.status == "revoked":
        r.status = "open"
    audit.record(db, actor, "evidence_request.new_link", "evidence_request", r.id, {"expires_at": r.expires_at.isoformat()})
    db.commit()
    return {**request_out(r, detail=True), "token": token}


@router.post("/{rid}/revoke")
def revoke(rid: int, db: Session = Depends(get_db), actor: User = Depends(require("evidence_requests.manage"))):
    r = _get(db, rid)
    if r.status in ("open", "submitted"):
        r.status = "revoked"
        audit.record(db, actor, "evidence_request.revoke", "evidence_request", r.id)
        db.commit()
    return request_out(r, detail=True)


@router.post("/{rid}/close")
def close(rid: int, db: Session = Depends(get_db), actor: User = Depends(require("evidence_requests.manage"))):
    r = _get(db, rid)
    if r.status != "closed":
        r.status = "closed"
        audit.record(db, actor, "evidence_request.close", "evidence_request", r.id)
        db.commit()
    return request_out(r, detail=True)


@router.post("/{rid}/items/{iid}/review")
def review(rid: int, iid: int, body: ReviewIn, db: Session = Depends(get_db),
           actor: User = Depends(require("evidence_requests.manage"))):
    r = _get(db, rid)
    item = next((i for i in r.items if i.id == iid), None)
    if item is None:
        raise HTTPException(404, "not_found")
    if item.status not in ("answered", "returned") and not (item.status == "open" and body.decision == "return"):
        raise HTTPException(409, "nothing_to_review" if item.status == "open" else "already_accepted")
    now = utcnow()
    item.reviewed_at, item.reviewed_by_id, item.review_note = now, actor.id, body.note.strip()
    linked = []
    if body.decision == "accept":
        item.status = "accepted"
        for f in item.files:
            if f.evidence_file_id is None:
                ev = EvidenceFile(requirement_id=item.requirement_id, filename=f.filename, stored_name=f.stored_name,
                                  content_type=f.content_type, size=f.size, sha256=f.sha256,
                                  description=f"From {r.recipient} via evidence request \"{r.title}\""[:2000],
                                  uploaded_by_id=actor.id, uploaded_at=f.uploaded_at)
                db.add(ev)
                db.flush()
                f.evidence_file_id = ev.id
                linked.append(ev.id)
    else:
        item.status = "returned"
        if r.status == "submitted":  # let the recipient answer again on the same link
            r.status = "open"
    audit.record(db, actor, f"evidence_request.item_{'accepted' if body.decision == 'accept' else 'returned'}",
                 "evidence_request", r.id, {"item": item.id, "requirement_id": item.requirement_id,
                                             "evidence_files": linked, "note": item.review_note})
    if linked:
        take_snapshot(db, reason="evidence")
    db.commit()
    return request_out(r, detail=True)


@router.get("/{rid}/files/{fid}/download")
def download(rid: int, fid: int, db: Session = Depends(get_db), _=Depends(require("read"))):
    f = db.get(EvidenceRequestFile, fid)
    if not f or f.item.request_id != rid:
        raise HTTPException(404, "not_found")
    if not verify(f):  # same check as evidence: the stored bytes still hash to the recorded value
        raise HTTPException(409, "integrity_check_failed")
    return FileResponse(path_of(f), media_type=f.content_type, filename=f.filename, headers={"X-Content-SHA256": f.sha256})


# ----------------------------------------------------------------------------------- public link

def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _throttled(ip: str) -> bool:
    q, now = _BAD[ip], time.monotonic()
    while q and now - q[0] > _BAD_WINDOW:
        q.popleft()
    return len(q) >= _BAD_MAX


def _open(token: str, request: Request, response: Response, db: Session, write: bool = False) -> EvidenceRequest:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    ip = _ip(request)
    if _throttled(ip):
        raise HTTPException(429, "too_many_attempts")
    if write and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(403, "missing_csrf_header")
    r = None
    if 20 <= len(token) <= 100:
        r = db.execute(select(EvidenceRequest).where(EvidenceRequest.token_hash == _hash(token))
                       .execution_options(all_orgs=True)).scalar_one_or_none()
    if r is None:
        _BAD[ip].append(time.monotonic())
        raise HTTPException(404, "link_not_found")
    db.info["org_id"] = r.org_id  # everything below works inside the request's organisation
    state = effective_status(r)
    if state in ("revoked", "closed"):
        raise HTTPException(410, "link_closed")
    if state == "expired":
        raise HTTPException(410, "link_expired")
    if write and state == "submitted":
        raise HTTPException(409, "already_submitted")
    return r


def _who(r: EvidenceRequest) -> str:
    return f"link: {r.recipient}"[:64]


def _org_name(db: Session, r: EvidenceRequest) -> dict:
    row = db.execute(select(AppSetting).where(AppSetting.key == "organization")).scalar_one_or_none()
    org = db.get(Organisation, r.org_id)
    v = row.value if row else {}
    return {"name": v.get("name") or (org.name if org else ""), "name_ar": v.get("name_ar") or ""}


def _public_item(r: EvidenceRequest, iid: int) -> EvidenceRequestItem:
    item = next((i for i in r.items if i.id == iid), None)
    if item is None:
        raise HTTPException(404, "not_found")
    if item.status == "accepted":
        raise HTTPException(409, "already_accepted")
    return item


@public.get("/{token}")
def public_view(token: str, request: Request, response: Response, db: Session = Depends(get_db)):
    r = _open(token, request, response, db)
    if r.first_opened_at is None:
        r.first_opened_at = utcnow()
        audit.record(db, None, "evidence_request.opened", "evidence_request", r.id, actor_name=_who(r))
        db.commit()
    s = get_settings()
    return {
        "organization": _org_name(db, r), "title": r.title, "recipient": r.recipient, "message": r.message,
        "status": effective_status(r), "expires_at": r.expires_at.isoformat(),
        "max_upload_mb": s.max_upload_mb, "files_per_item": s.evidence_request_files_per_item,
        "items": [_item_out(i, public_view=True) for i in r.items],
    }


class AnswerIn(BaseModel):
    response: str = Field(max_length=5000)


@public.put("/{token}/items/{iid}")
def public_answer(token: str, iid: int, body: AnswerIn, request: Request, response: Response, db: Session = Depends(get_db)):
    r = _open(token, request, response, db, write=True)
    item = _public_item(r, iid)
    item.response = body.response.strip()
    item.responded_at = utcnow()
    item.status = "answered" if (item.response or item.files) else "open"
    audit.record(db, None, "evidence_request.answer", "evidence_request", r.id,
                 {"item": item.id, "requirement_id": item.requirement_id, "chars": len(item.response)}, actor_name=_who(r))
    db.commit()
    return _item_out(item, public_view=True)


@public.post("/{token}/items/{iid}/files", status_code=201)
async def public_upload(token: str, iid: int, file: UploadFile, request: Request, response: Response,
                        db: Session = Depends(get_db)):
    r = _open(token, request, response, db, write=True)
    item = _public_item(r, iid)
    s = get_settings()
    if len(item.files) >= s.evidence_request_files_per_item:
        raise HTTPException(409, "too_many_files")
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    try:
        stored, ctype, sha = write_blob(data, file.filename or "evidence")
    except EvidenceError as e:
        raise HTTPException(413 if e.code == "too_large" else 415 if e.code in ("bad_type", "content_mismatch") else 422, e.code)
    f = EvidenceRequestFile(filename=safe_name(file.filename or "evidence"), stored_name=stored, content_type=ctype,
                            size=len(data), sha256=sha)
    item.files.append(f)
    item.status = "answered"
    item.responded_at = utcnow()
    db.flush()
    audit.record(db, None, "evidence_request.file", "evidence_request", r.id,
                 {"item": item.id, "requirement_id": item.requirement_id, "filename": f.filename, "sha256": sha,
                  "size": f.size}, actor_name=_who(r))
    db.commit()
    return _item_out(item, public_view=True)


@public.delete("/{token}/items/{iid}/files/{fid}")
def public_remove_file(token: str, iid: int, fid: int, request: Request, response: Response, db: Session = Depends(get_db)):
    r = _open(token, request, response, db, write=True)
    item = _public_item(r, iid)
    f = next((x for x in item.files if x.id == fid), None)
    if f is None:
        raise HTTPException(404, "not_found")
    item.files.remove(f)  # the blob stays: it is content-addressed and may back other evidence
    if not item.files and not item.response:
        item.status = "open"
    audit.record(db, None, "evidence_request.file_removed", "evidence_request", r.id,
                 {"item": item.id, "filename": f.filename, "sha256": f.sha256}, actor_name=_who(r))
    db.commit()
    return _item_out(item, public_view=True)


@public.post("/{token}/submit")
def public_submit(token: str, request: Request, response: Response, db: Session = Depends(get_db)):
    r = _open(token, request, response, db, write=True)
    if not any(i.status == "answered" for i in r.items):
        raise HTTPException(422, "nothing_answered")
    r.status, r.submitted_at = "submitted", utcnow()
    audit.record(db, None, "evidence_request.submit", "evidence_request", r.id,
                 {"answered": sum(1 for i in r.items if i.status == "answered")}, actor_name=_who(r))
    db.commit()
    return {"status": "submitted"}
