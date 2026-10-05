"""Kakao OAuth login (authorization code flow with a state cookie)."""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie
from fastapi.responses import RedirectResponse

from src.backend.auth import kakao_user
from src.backend.config import get_settings
from src.backend.tokens import start_session

router = APIRouter()
settings = get_settings()
logger = logging.getLogger("uvicorn.error")


KAKAO_STATE_COOKIE = "lookfind_kakao_state"
KAKAO_COOKIE_PATH = "/api/auth/kakao"


def exchange_kakao_profile(code: str) -> dict:
    payload = {
        "client_id": settings.kakao_rest_api_key,
        "client_secret": settings.kakao_client_secret,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": code,
    }
    function_name = os.getenv("KAKAO_EXCHANGE_FUNCTION")
    if function_name:
        import boto3

        response = boto3.client("lambda", region_name=settings.aws_region).invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        body = json.loads(response["Payload"].read())
        if response.get("FunctionError"):
            raise RuntimeError(body.get("errorMessage", "Kakao exchange Lambda failed"))
        return body
    token = httpx.post("https://kauth.kakao.com/oauth/token", timeout=10, data={
        "grant_type": "authorization_code", "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri, "code": code,
        **({"client_secret": settings.kakao_client_secret} if settings.kakao_client_secret else {}),
    }).raise_for_status().json()["access_token"]
    return httpx.get("https://kapi.kakao.com/v2/user/me", timeout=10,
                     headers={"Authorization": f"Bearer {token}"}).raise_for_status().json()


def kakao_failed() -> RedirectResponse:
    response = RedirectResponse(f"{settings.frontend_url}/?login_error=kakao", status_code=302)
    response.delete_cookie(KAKAO_STATE_COOKIE, path=KAKAO_COOKIE_PATH)
    return response


@router.get("/api/auth/kakao")
def kakao_start() -> RedirectResponse:
    if not settings.kakao_rest_api_key:
        logger.warning("KAKAO_REST_API_KEY is not set; Kakao login is disabled.")
        return kakao_failed()
    state = secrets.token_urlsafe(24)
    query = urlencode({
        "client_id": settings.kakao_rest_api_key, "redirect_uri": settings.kakao_redirect_uri,
        "response_type": "code", "state": state,
    })
    response = RedirectResponse(f"https://kauth.kakao.com/oauth/authorize?{query}", status_code=302)
    # Lax still reaches the callback: Kakao sends the browser back with a top-level GET.
    response.set_cookie(KAKAO_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, path=KAKAO_COOKIE_PATH)
    return response


@router.get("/api/auth/kakao/callback")
def kakao_callback(
    code: str = "", state: str = "", error: str = "",
    expected_state: str | None = Cookie(None, alias=KAKAO_STATE_COOKIE),
) -> RedirectResponse:
    if error or not code or not expected_state or not hmac.compare_digest(state, expected_state):
        return kakao_failed()
    try:
        profile = exchange_kakao_profile(code)
        user_id = kakao_user(profile)
    except (httpx.HTTPError, KeyError, ValueError, RuntimeError):
        logger.exception("Kakao login failed")
        return kakao_failed()
    response = RedirectResponse(f"{settings.frontend_url}/", status_code=302)
    response.delete_cookie(KAKAO_STATE_COOKIE, path=KAKAO_COOKIE_PATH)
    start_session(response, user_id)
    return response
