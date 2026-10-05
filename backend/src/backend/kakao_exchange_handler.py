"""Internet-facing Lambda used only for Kakao's token/profile exchange."""
from __future__ import annotations

import httpx


def handler(event: dict, _context: object) -> dict:
    token = httpx.post(
        "https://kauth.kakao.com/oauth/token",
        timeout=10,
        data={
            "grant_type": "authorization_code",
            "client_id": event["client_id"],
            "redirect_uri": event["redirect_uri"],
            "code": event["code"],
            **({"client_secret": event["client_secret"]} if event.get("client_secret") else {}),
        },
    ).raise_for_status().json()["access_token"]
    return httpx.get(
        "https://kapi.kakao.com/v2/user/me",
        timeout=10,
        headers={"Authorization": f"Bearer {token}"},
    ).raise_for_status().json()
