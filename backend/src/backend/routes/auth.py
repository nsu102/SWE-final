"""Email/password accounts: register, login, JWT refresh, logout, password reset."""
from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation

from src.backend.auth import (
    FailureLimiter, create_reset_token, hash_password, raise_if_limited, require_user,
    send_reset_mail, token_hash, verify_password,
)
from src.backend.db import connect_db
from src.backend.schemas import Credentials, PasswordReset, ResetRequest, User
from src.backend.tokens import (
    REFRESH_COOKIE, TokenError, clear_auth_cookies, decode, revoke_family, revoke_user,
    rotate_refresh, set_auth_cookies, start_session,
)

router = APIRouter(prefix="/api/auth")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Per email+IP: 5 wrong passwords / 10 min. Per IP: 30 failures (spraying many emails) / 10 min.
login_failures = FailureLimiter(limit=5, window=600)
ip_failures = FailureLimiter(limit=30, window=600)
reset_requests = FailureLimiter(limit=5, window=3600)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def valid_password(password: str) -> str:
    if not 8 <= len(password) <= 128:
        raise HTTPException(status_code=422, detail="비밀번호는 8~128자여야 해요.")
    return password


def valid_credentials(body: Credentials) -> tuple[str, str]:
    email = body.email.strip().lower()
    if not EMAIL_PATTERN.match(email) or len(email) > 254:
        raise HTTPException(status_code=422, detail="이메일 형식이 올바르지 않아요.")
    return email, valid_password(body.password)


def load_user(user_id: int) -> User:
    with connect_db() as connection:
        row = connection.execute(
            "SELECT id, email, display_name, avatar_url FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요해요.")
    return User(id=str(row["id"]), email=row["email"] or "", display_name=row["display_name"], avatar_url=row["avatar_url"])


def sign_in(response: Response, user_id: int) -> User:
    start_session(response, user_id)
    return load_user(user_id)


@router.post("/register", response_model=User, status_code=201)
def register(body: Credentials, response: Response) -> User:
    email, password = valid_credentials(body)
    try:
        with connect_db() as connection:
            user = connection.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (email, hash_password(password)),
            ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일이에요.") from exc
    return sign_in(response, user["id"])


@router.post("/login", response_model=User)
def login(body: Credentials, request: Request, response: Response) -> User:
    email = body.email.strip().lower()
    ip = client_ip(request)
    key = f"{ip}|{email}"
    raise_if_limited(login_failures, key)
    raise_if_limited(ip_failures, ip)
    with connect_db() as connection:
        user = connection.execute(
            "SELECT id, password_hash FROM users WHERE email = %s", (email,)
        ).fetchone()
    # Kakao-only accounts have no password_hash and can't log in with a password.
    if not user or not user["password_hash"] or not verify_password(body.password, user["password_hash"]):
        login_failures.hit(key)
        ip_failures.hit(ip)
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 맞지 않아요.")
    login_failures.reset(key)
    return sign_in(response, user["id"])


@router.post("/refresh", status_code=204)
def refresh(token: str | None = Cookie(None, alias=REFRESH_COOKIE)) -> Response:
    """Rotate the refresh token and issue a new access token. 401 (+ cleared cookies) = log in again."""
    try:
        if not token:
            raise TokenError("no refresh token")
        user_id, new_refresh = rotate_refresh(token)
    except TokenError:
        failed = JSONResponse({"detail": "로그인이 만료됐어요. 다시 로그인해 주세요."}, status_code=401)
        clear_auth_cookies(failed)
        return failed
    response = Response(status_code=204)
    set_auth_cookies(response, user_id, new_refresh)
    return response


@router.post("/logout", status_code=204)
def logout(token: str | None = Cookie(None, alias=REFRESH_COOKIE)) -> Response:
    """End this login everywhere it was refreshed (the token's family); other devices stay logged in."""
    if token:
        try:
            family = decode(token, "refresh", verify_exp=False)["fam"]
        except TokenError:
            family = None
        if family:
            with connect_db() as connection:
                revoke_family(connection, family)
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=User)
def me(user_id: int = Depends(require_user)) -> User:
    return load_user(user_id)


@router.post("/reset-request", status_code=204)
def reset_request(body: ResetRequest, request: Request, background: BackgroundTasks) -> Response:
    # Always 204 and mail in the background, so the response never reveals whether the email exists.
    ip = client_ip(request)
    raise_if_limited(reset_requests, ip)
    reset_requests.hit(ip)
    email = body.email.strip().lower()
    with connect_db() as connection:
        user = connection.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
    if user:
        background.add_task(send_reset_mail, email, create_reset_token(user["id"]))
    return Response(status_code=204)


@router.post("/reset", response_model=User)
def reset_password(body: PasswordReset, request: Request, response: Response) -> User:
    password_hash = hash_password(valid_password(body.password))
    with connect_db() as connection:
        row = connection.execute(
            "UPDATE password_resets SET used_at = now() "
            "WHERE token_hash = %s AND used_at IS NULL AND expires_at > now() RETURNING user_id",
            (token_hash(body.token),),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="재설정 링크가 만료됐거나 이미 사용됐어요.")
        user = connection.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s RETURNING id, email",
            (password_hash, row["user_id"]),
        ).fetchone()
        # A reset ends every existing login (refresh tokens); access tokens lapse within 15 minutes.
        revoke_user(connection, user["id"])
    # The owner proved access to the mailbox, so lift any wrong-password lockout from this IP.
    login_failures.reset(f"{client_ip(request)}|{user['email']}")
    return sign_in(response, user["id"])
