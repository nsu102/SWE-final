"""Accounts: scrypt passwords, login rate limits, reset mails, Kakao profiles and the JWT auth dependencies."""
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

from fastapi import Cookie, HTTPException

from src.backend.config import get_settings
from src.backend.db import connect_db
from src.backend.tokens import ACCESS_COOKIE, TokenError, user_from_access

logger = logging.getLogger("uvicorn.error")

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


def optional_user(access: str | None = Cookie(None, alias=ACCESS_COOKIE)) -> int | None:
    """User id from the access-token cookie; None when anonymous.

    An expired or invalid token is a 401 (not anonymous), so the client refreshes and retries
    instead of silently running e.g. a search that is not saved to the user's ARCHIVE.
    """
    if not access:
        return None
    try:
        return user_from_access(access)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="access token expired") from exc


def require_user(access: str | None = Cookie(None, alias=ACCESS_COOKIE)) -> int:
    user_id = optional_user(access)
    if user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요해요.")
    return user_id


def kakao_profile(profile: dict) -> tuple[str, str | None, str | None, str | None]:
    """(kakao_id, verified email or None, nickname, avatar) from Kakao /v2/user/me."""
    account = profile.get("kakao_account") or {}
    info = account.get("profile") or {}
    verified = account.get("is_email_valid") and account.get("is_email_verified")
    email = (account.get("email") or "").strip().lower() if verified else ""
    return str(profile["id"]), email or None, info.get("nickname"), info.get("profile_image_url")


def kakao_user(profile: dict) -> int:
    """Find or create the account for a Kakao profile. A verified Kakao email links to the same email account."""
    kakao_id, email, name, avatar = kakao_profile(profile)
    with connect_db() as connection:
        row = connection.execute(
            "UPDATE users SET display_name = %s, avatar_url = %s WHERE kakao_id = %s RETURNING id",
            (name, avatar, kakao_id),
        ).fetchone()
        if not row and email:
            row = connection.execute(
                "UPDATE users SET kakao_id = %s, display_name = COALESCE(display_name, %s), "
                "avatar_url = COALESCE(avatar_url, %s) WHERE email = %s AND kakao_id IS NULL RETURNING id",
                (kakao_id, name, avatar, email),
            ).fetchone()
        if not row:
            # The email can already belong to an account linked to another Kakao id; then store none.
            taken = email and connection.execute("SELECT 1 FROM users WHERE email = %s", (email,)).fetchone()
            row = connection.execute(
                "INSERT INTO users (email, kakao_id, display_name, avatar_url) VALUES (%s, %s, %s, %s) RETURNING id",
                (None if taken else email, kakao_id, name, avatar),
            ).fetchone()
    return int(row["id"])


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
