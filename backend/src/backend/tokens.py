"""JWT access/refresh tokens, carried in HttpOnly cookies.

- Access token: short-lived and stateless (signature + expiry), sent with every /api request.
- Refresh token: long-lived JWT whose `jti` is stored in `refresh_tokens`, so it can be revoked.
  Every refresh rotates it (old jti revoked, new one issued in the same `family`); a rotated token
  presented again after the grace window is treated as stolen and the whole family is revoked.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Response
from psycopg import Connection

from src.backend.config import get_settings
from src.backend.db import connect_db

ACCESS_COOKIE = "lookfind_access"
REFRESH_COOKIE = "lookfind_refresh"
ACCESS_COOKIE_PATH = "/api"
REFRESH_COOKIE_PATH = "/api/auth"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
# Two tabs refreshing with the same cookie at once is not theft; only reuse after this window is.
REUSE_GRACE = timedelta(seconds=30)
ALGORITHM = "HS256"
ISSUER = "lookfind"


class TokenError(Exception):
    """Missing, malformed, expired, revoked or wrong-type token."""


def _encode(claims: dict, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({**claims, "iss": ISSUER, "iat": now, "exp": now + ttl}, get_settings().jwt_secret, algorithm=ALGORITHM)


def decode(token: str, kind: str, *, verify_exp: bool = True) -> dict:
    try:
        claims = jwt.decode(
            token, get_settings().jwt_secret, algorithms=[ALGORITHM], issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "typ"], "verify_exp": verify_exp},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if claims["typ"] != kind:  # a refresh token must never work as an access token (and vice versa)
        raise TokenError("wrong token type")
    return claims


def access_token(user_id: int) -> str:
    return _encode({"sub": str(user_id), "typ": "access"}, ACCESS_TTL)


def user_from_access(token: str) -> int:
    return int(decode(token, "access")["sub"])


def issue_refresh(connection: Connection, user_id: int, family: uuid.UUID | None = None) -> str:
    jti, family = uuid.uuid4(), family or uuid.uuid4()
    connection.execute("DELETE FROM refresh_tokens WHERE user_id = %s AND expires_at < now()", (user_id,))
    connection.execute(
        "INSERT INTO refresh_tokens (jti, user_id, family, expires_at) VALUES (%s, %s, %s, now() + %s)",
        (jti, user_id, family, REFRESH_TTL),
    )
    return _encode({"sub": str(user_id), "typ": "refresh", "jti": str(jti), "fam": str(family)}, REFRESH_TTL)


def rotate_refresh(token: str) -> tuple[int, str]:
    """Revoke `token` and return (user_id, new refresh token in the same family)."""
    claims = decode(token, "refresh")
    with connect_db() as connection:
        row = connection.execute(
            "UPDATE refresh_tokens SET revoked_at = now() "
            "WHERE jti = %s AND revoked_at IS NULL AND expires_at > now() RETURNING user_id, family",
            (claims["jti"],),
        ).fetchone()
        if row:
            return int(row["user_id"]), issue_refresh(connection, int(row["user_id"]), row["family"])
        reused = connection.execute(
            "SELECT 1 FROM refresh_tokens WHERE jti = %s AND revoked_at < now() - %s", (claims["jti"], REUSE_GRACE)
        ).fetchone()
        if reused:
            revoke_family(connection, claims["fam"])
    # Raised outside the `with` so the family revocation above is committed, not rolled back.
    raise TokenError("refresh token revoked")


def revoke_family(connection: Connection, family: str | uuid.UUID) -> None:
    connection.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE family = %s AND revoked_at IS NULL", (family,))


def revoke_user(connection: Connection, user_id: int) -> None:
    connection.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (user_id,))


def set_auth_cookies(response: Response, user_id: int, refresh: str) -> None:
    secure = get_settings().cookie_secure
    response.set_cookie(ACCESS_COOKIE, access_token(user_id), max_age=int(ACCESS_TTL.total_seconds()),
                        httponly=True, secure=secure, samesite="strict", path=ACCESS_COOKIE_PATH)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=int(REFRESH_TTL.total_seconds()),
                        httponly=True, secure=secure, samesite="strict", path=REFRESH_COOKIE_PATH)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path=ACCESS_COOKIE_PATH)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def start_session(response: Response, user_id: int) -> None:
    """Log `user_id` in: new refresh family + access token, both as cookies."""
    with connect_db() as connection:
        refresh = issue_refresh(connection, user_id)
    set_auth_cookies(response, user_id, refresh)
