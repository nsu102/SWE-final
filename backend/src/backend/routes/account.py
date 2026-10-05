"""MY PAGE profile editing: display name and avatar."""
from __future__ import annotations

import unicodedata

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from src.backend.auth import require_user
from src.backend.db import connect_db
from src.backend.images import avatar_data_url
from src.backend.routes.auth import load_user
from src.backend.schemas import ProfileUpdate, User

router = APIRouter(prefix="/api/auth/me")

NAME_MAX = 30
AVATAR_MAX_BYTES = 5 * 1024 * 1024  # the frontend downscales to 512px before upload


def valid_display_name(raw: str) -> str:
    name = " ".join(raw.split())  # trim and collapse whitespace
    if not name:
        raise HTTPException(status_code=422, detail="이름을 입력해 주세요.")
    if len(name) > NAME_MAX:
        raise HTTPException(status_code=422, detail=f"이름은 {NAME_MAX}자 이하로 입력해 주세요.")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in name):
        raise HTTPException(status_code=422, detail="이름에 사용할 수 없는 문자가 있어요.")
    return name


def set_profile(user_id: int, column: str, value: str | None) -> User:
    assert column in {"display_name", "avatar_url"}
    with connect_db() as connection:
        connection.execute(f"UPDATE users SET {column} = %s WHERE id = %s", (value, user_id))
    return load_user(user_id)


@router.patch("", response_model=User)
def update_profile(body: ProfileUpdate, user_id: int = Depends(require_user)) -> User:
    return set_profile(user_id, "display_name", valid_display_name(body.display_name))


@router.put("/avatar", response_model=User)
async def upload_avatar(image: UploadFile = File(...), user_id: int = Depends(require_user)) -> User:
    body = await image.read(AVATAR_MAX_BYTES + 1)
    if len(body) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="5MB 이하의 이미지를 선택해 주세요.")
    try:
        avatar = await run_in_threadpool(avatar_data_url, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="이미지 파일을 읽을 수 없어요.") from exc
    return set_profile(user_id, "avatar_url", avatar)


@router.delete("/avatar", response_model=User)
def remove_avatar(user_id: int = Depends(require_user)) -> User:
    return set_profile(user_id, "avatar_url", None)
