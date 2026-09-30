"""Email/password accounts with opaque bearer tokens (stdlib scrypt, no extra deps)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import threading
import time
from collections import defaultdict, deque
from email.message import EmailMessage

from fastapi import Header, HTTPException

from src.backend.config import get_settings
from src.backend.db import connect_db

logger = logging.getLogger("uvicorn.error")

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


class FailureLimiter:
    """Blocks a key after `limit` failures inside `window` seconds.

    ponytail: in-process memory, correct for the single uvicorn worker we deploy;
    move the counters to a DB table or Redis if you add workers/instances.
    """

    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again (0 = allowed)."""
        now = time.monotonic()
        with self._lock:
            hits = self._recent(key, now)
            return 0 if len(hits) < self.limit else int(hits[0] + self.window - now) + 1

    def hit(self, key: str) -> None:
        with self._lock:
            self._recent(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


def raise_if_limited(limiter: FailureLimiter, *keys: str) -> None:
    wait = max(limiter.retry_after(key) for key in keys)
    if wait:
        raise HTTPException(
            status_code=429, headers={"Retry-After": str(wait)},
            detail=f"시도가 너무 많아요. {max(1, round(wait / 60))}분 후 다시 시도해 주세요.",
        )


RESET_MINUTES = 30


def create_reset_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect_db() as connection:
        connection.execute(
            "INSERT INTO password_resets (token_hash, user_id, expires_at) "
            "VALUES (%s, %s, now() + make_interval(mins => %s))",
            (token_hash(token), user_id, RESET_MINUTES),
        )
    return token


def send_reset_mail(email: str, token: str) -> None:
    settings = get_settings()
    link = f"{settings.frontend_url}/?reset={token}"
    if not settings.smtp_host:
        # Local development: no mail server, so hand the link to whoever runs the backend.
        logger.warning("SMTP_HOST is not set. Password reset link for %s: %s", email, link)
        return
    message = EmailMessage()
    message["Subject"] = "[LookFind] 비밀번호 재설정"
    message["From"] = settings.mail_from
    message["To"] = email
    message.set_content(
        f"아래 링크에서 {RESET_MINUTES}분 안에 새 비밀번호를 설정해 주세요.\n\n{link}\n\n"
        "요청하지 않았다면 이 메일을 무시하면 됩니다."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send password reset mail to %s", email)
