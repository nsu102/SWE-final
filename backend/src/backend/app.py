from __future__ import annotations

import base64
import hmac
import io
import logging
import re
import secrets
import time
import uuid
from functools import lru_cache
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

import httpx

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel

from src.backend.auth import (
    SESSION_COOKIE, FailureLimiter, create_reset_token, hash_password, kakao_user, optional_user,
    raise_if_limited, require_user, send_reset_mail, set_session_cookie, token_hash, verify_password,
)
from src.backend.config import get_settings
from src.backend.db import connect_db, count_products, initialize_database, search_similar
from src.backend.ml import get_models
from src.backend.storage import image_url, s3_client


class SearchResult(BaseModel):
    platform: str
    goods_no: str
    goods_name: str
    brand_name: str
    price: int | None
    product_url: str
    image_url: str
    similarity: float


class SearchResponse(BaseModel):
    query_id: uuid.UUID
    used_top_mask: bool
    top_ratio: float
    box_preview: str
    masked_preview: str | None
    elapsed_ms: int
    results: list[SearchResult]


class Credentials(BaseModel):
    email: str
    password: str


class User(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


class ResetRequest(BaseModel):
    email: str


class PasswordReset(BaseModel):
    token: str
    password: str


class HistoryItem(BaseModel):
    id: str
    label: str
    searched_at: str
    count: int
    image_url: str | None


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_cursor: int | None


class HistoryDetail(HistoryItem):
    results: list[SearchResult]


class HistoryIds(BaseModel):
    ids: list[str]


class DeletedHistory(BaseModel):
    deleted_ids: list[str]


class RestoredHistory(BaseModel):
    restored: int


PRODUCT_COLUMNS = (
    "p.platform, p.goods_no, p.goods_name, p.brand_name, p.price, p.product_url, "
    "p.image_path, p.s3_bucket, p.s3_key"
)


logger = logging.getLogger("uvicorn.error")


def to_result(row: dict) -> SearchResult:
    return SearchResult(
        platform=row["platform"], goods_no=row["goods_no"], goods_name=row["goods_name"],
        brand_name=row["brand_name"], price=row["price"], product_url=row["product_url"],
        image_url=image_url(row), similarity=float(row["similarity"]),
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    if settings.auto_migrate:
        initialize_database()
    yield


app = FastAPI(title="Fashion Similarity Search API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "products": count_products()}


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


def infer(source: Image.Image):
    models = get_models()
    prepared = models.prepare_query(source)
    embedding = models.embed([prepared.search_image])[0].tolist()
    return prepared, embedding


def preview_data_url(image: Image.Image) -> str:
    preview = image.copy()
    preview.thumbnail((480, 480))
    output = io.BytesIO()
    preview.convert("RGB").save(output, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


@app.post("/api/search", response_model=SearchResponse)
async def search(
    image: UploadFile = File(...),
    limit: int = Query(20, ge=1, le=50),
    platform: str | None = Query(None, pattern="^(musinsa|ably)$"),
    label: str = Form(""),
    user_id: int | None = Depends(optional_user),
) -> SearchResponse:
    started = time.perf_counter()
    body = await image.read(settings.max_upload_bytes + 1)
    if len(body) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="image is too large")
    try:
        source = Image.open(io.BytesIO(body))
        if source.width * source.height > 20_000_000:
            raise HTTPException(status_code=413, detail="image resolution is too large")
        source.thumbnail((1024, 1024))
        source = source.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="invalid image") from exc

    prepared, embedding = await run_in_threadpool(infer, source)
    rows = await run_in_threadpool(
        search_similar, embedding, limit, platform, prepared.color_lab, settings.color_weight
    )
    query_id = uuid.uuid4()
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    box_preview = preview_data_url(prepared.box_image)

    with connect_db() as connection:
        event = connection.execute(
            "INSERT INTO search_events (query_id, platform_filter, result_count, elapsed_ms, user_id, label, thumb) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (query_id, platform, len(rows), elapsed_ms, user_id,
             (label or image.filename or "업로드 사진")[:100], box_preview if user_id else None),
        ).fetchone()
        if user_id:
            connection.cursor().executemany(
                "INSERT INTO search_results (event_id, rank, platform, goods_no, similarity) VALUES (%s, %s, %s, %s, %s)",
                [(event["id"], rank, row["platform"], row["goods_no"], float(row["similarity"]))
                 for rank, row in enumerate(rows)],
            )

    return SearchResponse(
        query_id=query_id, used_top_mask=prepared.used_top_mask,
        top_ratio=prepared.top_ratio,
        box_preview=box_preview,
        masked_preview=(
            preview_data_url(prepared.masked_image) if prepared.masked_image else None
        ),
        elapsed_ms=elapsed_ms, results=[to_result(row) for row in rows],
    )


@lru_cache(maxsize=2048)  # ponytail: per-process cache (~50KB each); a CDN if traffic grows
def cropped_catalog_image(bucket: str, key: str, crop_box: tuple[float, ...]) -> bytes:
    if bucket != settings.s3_bucket:
        raise HTTPException(status_code=404, detail="image not found")
    body = s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    with Image.open(io.BytesIO(body)) as image:
        image = image.convert("RGB")
        x0, y0, x1, y1 = crop_box
        crop = image.crop((
            round(x0 * image.width), round(y0 * image.height),
            round(x1 * image.width), round(y1 * image.height),
        ))
    output = io.BytesIO()
    crop.save(output, format="JPEG", quality=88)
    return output.getvalue()


@app.get("/media/{platform}/{goods_no}")
def product_image(platform: str, goods_no: str, full: bool = False):
    """Catalog photo cropped to the garment (hides most of the model); ?full=1 for the original."""
    if platform not in {"musinsa", "ably"} or not goods_no.isdigit():
        raise HTTPException(status_code=404, detail="image not found")
    with connect_db() as connection:
        row = connection.execute(
            "SELECT platform, goods_no, image_path, s3_bucket, s3_key, crop_box FROM products WHERE platform = %s AND goods_no = %s",
            (platform, goods_no),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="image not found")
    if row.get("s3_key") and row.get("crop_box") and not full:
        body = cropped_catalog_image(row["s3_bucket"] or settings.s3_bucket, row["s3_key"], tuple(row["crop_box"]))
        return Response(body, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
    if row.get("s3_key"):
        return RedirectResponse(image_url(row), headers={"Cache-Control": "no-store"})
    if not row.get("image_path"):
        raise HTTPException(status_code=404, detail="image not found")
    path = Path(row["image_path"]).resolve()
    allowed_root = settings.storage_root.resolve()
    if not path.is_relative_to(allowed_root) or not path.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(path)


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
    set_session_cookie(response, user_id)
    return load_user(user_id)


@app.post("/api/auth/register", response_model=User, status_code=201)
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


@app.post("/api/auth/login", response_model=User)
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


@app.post("/api/auth/reset-request", status_code=204)
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


@app.post("/api/auth/reset", response_model=User)
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
        # A reset logs out every existing session.
        connection.execute("DELETE FROM sessions WHERE user_id = %s", (user["id"],))
    # The owner proved access to the mailbox, so lift any wrong-password lockout from this IP.
    login_failures.reset(f"{client_ip(request)}|{user['email']}")
    return sign_in(response, user["id"])


@app.post("/api/auth/logout", status_code=204)
def logout(session: str | None = Cookie(None, alias=SESSION_COOKIE)) -> Response:
    if session:
        with connect_db() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash(session),))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/api/auth/me", response_model=User)
def me(user_id: int = Depends(require_user)) -> User:
    return load_user(user_id)


KAKAO_STATE_COOKIE = "lookfind_kakao_state"
KAKAO_COOKIE_PATH = "/api/auth/kakao"


def kakao_failed() -> RedirectResponse:
    response = RedirectResponse(f"{settings.frontend_url}/?login_error=kakao", status_code=302)
    response.delete_cookie(KAKAO_STATE_COOKIE, path=KAKAO_COOKIE_PATH)
    return response


@app.get("/api/auth/kakao")
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


@app.get("/api/auth/kakao/callback")
def kakao_callback(
    code: str = "", state: str = "", error: str = "",
    expected_state: str | None = Cookie(None, alias=KAKAO_STATE_COOKIE),
) -> RedirectResponse:
    if error or not code or not expected_state or not hmac.compare_digest(state, expected_state):
        return kakao_failed()
    try:
        token = httpx.post("https://kauth.kakao.com/oauth/token", timeout=10, data={
            "grant_type": "authorization_code", "client_id": settings.kakao_rest_api_key,
            "redirect_uri": settings.kakao_redirect_uri, "code": code,
            **({"client_secret": settings.kakao_client_secret} if settings.kakao_client_secret else {}),
        }).raise_for_status().json()["access_token"]
        profile = httpx.get("https://kapi.kakao.com/v2/user/me", timeout=10,
                            headers={"Authorization": f"Bearer {token}"}).raise_for_status().json()
        user_id = kakao_user(profile)
    except (httpx.HTTPError, KeyError, ValueError):
        logger.exception("Kakao login failed")
        return kakao_failed()
    response = RedirectResponse(f"{settings.frontend_url}/", status_code=302)
    response.delete_cookie(KAKAO_STATE_COOKIE, path=KAKAO_COOKIE_PATH)
    set_session_cookie(response, user_id)
    return response


HISTORY_PAGE = 24
UNDO_WINDOW = "10 minutes"


def to_history(row: dict) -> HistoryItem:
    return HistoryItem(
        id=str(row["id"]), label=row["label"] or "업로드 사진", count=row["result_count"],
        image_url=row["thumb"], searched_at=row["created_at"].isoformat(),
    )


def event_ids(ids: list[str]) -> list[int]:
    if len(ids) > 1000 or not all(value.isdigit() for value in ids):
        raise HTTPException(status_code=422, detail="잘못된 기록 ID예요.")
    return [int(value) for value in ids]


@app.get("/api/history", response_model=HistoryPage)
def history(before: int | None = Query(None, ge=1), user_id: int = Depends(require_user)) -> HistoryPage:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT id, label, created_at, result_count, thumb FROM search_events "
            "WHERE user_id = %s AND hidden_at IS NULL AND (%s::bigint IS NULL OR id < %s) "
            "ORDER BY id DESC LIMIT %s",
            (user_id, before, before, HISTORY_PAGE + 1),
        ).fetchall()
    items = [to_history(row) for row in rows[:HISTORY_PAGE]]
    return HistoryPage(items=items, next_cursor=int(items[-1].id) if len(rows) > HISTORY_PAGE else None)


@app.get("/api/history/{event_id}", response_model=HistoryDetail)
def history_detail(event_id: int, user_id: int = Depends(require_user)) -> HistoryDetail:
    with connect_db() as connection:
        event = connection.execute(
            "SELECT id, label, created_at, result_count, thumb FROM search_events "
            "WHERE id = %s AND user_id = %s AND hidden_at IS NULL",
            (event_id, user_id),
        ).fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="검색 기록을 찾을 수 없어요.")
        rows = connection.execute(
            f"SELECT {PRODUCT_COLUMNS}, r.similarity FROM search_results r "
            "JOIN products p ON p.platform = r.platform AND p.goods_no = r.goods_no "
            "WHERE r.event_id = %s ORDER BY r.rank",
            (event_id,),
        ).fetchall()
    return HistoryDetail(**to_history(event).model_dump(), results=[to_result(row) for row in rows])


def hide_history(user_id: int, event_id: int | None) -> DeletedHistory:
    """Soft-delete (RETURN can undo it for 10 minutes); entries hidden longer ago leave the account for good."""
    with connect_db() as connection:
        connection.execute(
            "WITH expired AS (UPDATE search_events SET user_id = NULL, thumb = NULL, hidden_at = NULL "
            f"WHERE user_id = %s AND hidden_at < now() - interval '{UNDO_WINDOW}' RETURNING id) "
            "DELETE FROM search_results WHERE event_id IN (SELECT id FROM expired)",
            (user_id,),
        )
        rows = connection.execute(
            "UPDATE search_events SET hidden_at = now() WHERE user_id = %s AND hidden_at IS NULL "
            "AND (%s::bigint IS NULL OR id = %s) RETURNING id",
            (user_id, event_id, event_id),
        ).fetchall()
    return DeletedHistory(deleted_ids=[str(row["id"]) for row in rows])


@app.delete("/api/history/{event_id}", response_model=DeletedHistory)
def remove_history(event_id: int, user_id: int = Depends(require_user)) -> DeletedHistory:
    return hide_history(user_id, event_id)


@app.delete("/api/history", response_model=DeletedHistory)
def clear_history(user_id: int = Depends(require_user)) -> DeletedHistory:
    return hide_history(user_id, None)


@app.post("/api/history/restore", response_model=RestoredHistory)
def restore_history(body: HistoryIds, user_id: int = Depends(require_user)) -> RestoredHistory:
    with connect_db() as connection:
        restored = connection.execute(
            "UPDATE search_events SET hidden_at = NULL WHERE user_id = %s AND id = ANY(%s) "
            f"AND hidden_at >= now() - interval '{UNDO_WINDOW}'",
            (user_id, event_ids(body.ids)),
        ).rowcount
    return RestoredHistory(restored=restored)


@app.get("/api/favorites", response_model=list[SearchResult])
def favorites(user_id: int = Depends(require_user)) -> list[SearchResult]:
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT {PRODUCT_COLUMNS}, 0 AS similarity FROM favorites f "
            "JOIN products p ON p.platform = f.platform AND p.goods_no = f.goods_no "
            "WHERE f.user_id = %s ORDER BY f.created_at DESC",
            (user_id,),
        ).fetchall()
    return [to_result(row) for row in rows]


@app.put("/api/favorites/{platform}/{goods_no}", status_code=204)
def add_favorite(platform: str, goods_no: str, user_id: int = Depends(require_user)) -> Response:
    try:
        with connect_db() as connection:
            connection.execute(
                "INSERT INTO favorites (user_id, platform, goods_no) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (user_id, platform, goods_no),
            )
    except ForeignKeyViolation as exc:
        raise HTTPException(status_code=404, detail="product not found") from exc
    return Response(status_code=204)


@app.delete("/api/favorites/{platform}/{goods_no}", status_code=204)
def remove_favorite(platform: str, goods_no: str, user_id: int = Depends(require_user)) -> Response:
    with connect_db() as connection:
        connection.execute(
            "DELETE FROM favorites WHERE user_id = %s AND platform = %s AND goods_no = %s",
            (user_id, platform, goods_no),
        )
    return Response(status_code=204)
