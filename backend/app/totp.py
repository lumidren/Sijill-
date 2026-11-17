"""Time-based one-time passwords (RFC 6238 / RFC 4226), standard library only.

Codes are 6 digits, 30-second steps, HMAC-SHA1 (what common authenticator apps expect). A code is
accepted for the current step or one step either side, and never twice (the last accepted step is
stored per user). The shared secret lives in the users table alongside the password hash; the
database file must be protected accordingly (see DECISIONS #28).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP = 30
DIGITS = 6
WINDOW = 1


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret_b32: str) -> bytes:
    padded = secret_b32.upper() + "=" * (-len(secret_b32) % 8)
    return base64.b32decode(padded)


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def code_at(secret_b32: str, at: float | None = None) -> str:
    return hotp(_key(secret_b32), int((time.time() if at is None else at) // STEP))


def verify(secret_b32: str, code: str, last_counter: int | None = None, at: float | None = None) -> int | None:
    """Return the matched time step, or None. Rejects reuse of a step at or before `last_counter`."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return None
    key = _key(secret_b32)
    now = int((time.time() if at is None else at) // STEP)
    for counter in range(now - WINDOW, now + WINDOW + 1):
        if last_counter is not None and counter <= last_counter:
            continue
        if hmac.compare_digest(hotp(key, counter), code):
            return counter
    return None


def otpauth_uri(secret_b32: str, account: str, issuer: str = "Sijill") -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?" + urlencode({"secret": secret_b32, "issuer": issuer, "digits": DIGITS, "period": STEP})
