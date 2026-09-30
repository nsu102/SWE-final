"""Email/password accounts with opaque bearer tokens (stdlib scrypt, no extra deps)."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Header, HTTPException

from src.backend.db import connect_db

SESSION_DAYS = 30
SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
    return hmac.compare_digest(candidate.hex(), digest)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect_db() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) "
            "VALUES (%s, %s, now() + make_interval(days => %s))",
            (token_hash(token), user_id, SESSION_DAYS),
        )
    return token


def bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def optional_user(authorization: str | None = Header(None)) -> int | None:
    token = bearer(authorization)
    if not token:
        return None
    with connect_db() as connection:
        row = connection.execute(
            "SELECT user_id FROM sessions WHERE token_hash = %s AND expires_at > now()",
            (token_hash(token),),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="session expired")
    return int(row["user_id"])


def require_user(authorization: str | None = Header(None)) -> int:
    user_id = optional_user(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="login required")
    return user_id
