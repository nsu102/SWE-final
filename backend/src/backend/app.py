from __future__ import annotations

import base64
import io
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel

from src.backend.auth import (
    FailureLimiter, bearer, create_reset_token, create_session, hash_password, optional_user,
    raise_if_limited, require_user, send_reset_mail, token_hash, verify_password,
)
from src.backend.config import get_settings
from src.backend.db import connect_db, count_products, initialize_database, search_products_multi
from src.backend.ml import get_models
from src.backend.storage import image_url


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


class Session(BaseModel):
    token: str
    email: str


class Account(BaseModel):
    email: str


class ResetRequest(BaseModel):
    email: str


class PasswordReset(BaseModel):
    token: str
    password: str


class HistoryItem(BaseModel):
    id: int
    label: str
    searched_at: str
    count: int
    thumb: str | None


PRODUCT_COLUMNS = (
    "p.platform, p.goods_no, p.goods_name, p.brand_name, p.price, p.product_url, "
    "p.image_path, p.s3_bucket, p.s3_key"
)


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
    embeddings = models.embed(list(prepared.images)).tolist()
    return prepared, embeddings


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

    prepared, embeddings = await run_in_threadpool(infer, source)
    rows = await run_in_threadpool(search_products_multi, embeddings, limit, platform)
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


@app.get("/media/{platform}/{goods_no}")
def product_image(platform: str, goods_no: str):
    if platform not in {"musinsa", "ably"} or not goods_no.isdigit():
        raise HTTPException(status_code=404, detail="image not found")
    with connect_db() as connection:
        row = connection.execute(
            "SELECT platform, goods_no, image_path, s3_bucket, s3_key FROM products WHERE platform = %s AND goods_no = %s",
            (platform, goods_no),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="image not found")
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


@app.post("/api/auth/signup", response_model=Session, status_code=201)
def signup(body: Credentials) -> Session:
    email, password = valid_credentials(body)
    try:
        with connect_db() as connection:
            user = connection.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (email, hash_password(password)),
            ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일이에요.") from exc
    return Session(token=create_session(user["id"]), email=email)


@app.post("/api/auth/login", response_model=Session)
def login(body: Credentials, request: Request) -> Session:
    email = body.email.strip().lower()
    ip = client_ip(request)
    key = f"{ip}|{email}"
    raise_if_limited(login_failures, key)
    raise_if_limited(ip_failures, ip)
    with connect_db() as connection:
        user = connection.execute(
            "SELECT id, password_hash FROM users WHERE email = %s", (email,)
        ).fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        login_failures.hit(key)
        ip_failures.hit(ip)
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 맞지 않아요.")
    login_failures.reset(key)
    return Session(token=create_session(user["id"]), email=email)


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


@app.post("/api/auth/reset", response_model=Session)
def reset_password(body: PasswordReset, request: Request) -> Session:
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
    return Session(token=create_session(user["id"]), email=user["email"])


@app.post("/api/auth/logout", status_code=204)
def logout(authorization: str | None = Header(None)) -> Response:
    token = bearer(authorization)
    if token:
        with connect_db() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash(token),))
    return Response(status_code=204)


@app.get("/api/auth/me", response_model=Account)
def me(user_id: int = Depends(require_user)) -> Account:
    with connect_db() as connection:
        row = connection.execute("SELECT email FROM users WHERE id = %s", (user_id,)).fetchone()
    return Account(email=row["email"])


@app.get("/api/history", response_model=list[HistoryItem])
def history(user_id: int = Depends(require_user)) -> list[HistoryItem]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT id, label, created_at, result_count, thumb FROM search_events "
            "WHERE user_id = %s AND hidden_at IS NULL ORDER BY created_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()
    return [HistoryItem(
        id=row["id"], label=row["label"] or "업로드 사진", count=row["result_count"], thumb=row["thumb"],
        searched_at=row["created_at"].isoformat(),
    ) for row in rows]


@app.get("/api/history/{event_id}", response_model=list[SearchResult])
def history_results(event_id: int, user_id: int = Depends(require_user)) -> list[SearchResult]:
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT {PRODUCT_COLUMNS}, r.similarity FROM search_results r "
            "JOIN search_events e ON e.id = r.event_id "
            "JOIN products p ON p.platform = r.platform AND p.goods_no = r.goods_no "
            "WHERE r.event_id = %s AND e.user_id = %s ORDER BY r.rank",
            (event_id, user_id),
        ).fetchall()
    return [to_result(row) for row in rows]


@app.delete("/api/history/{event_id}", status_code=204)
def remove_history(event_id: int, user_id: int = Depends(require_user)) -> Response:
    # Removing one entry detaches it from the account; the anonymous search log row stays.
    with connect_db() as connection:
        connection.execute("DELETE FROM search_results WHERE event_id = %s AND event_id IN "
                           "(SELECT id FROM search_events WHERE user_id = %s)", (event_id, user_id))
        connection.execute("UPDATE search_events SET user_id = NULL, thumb = NULL "
                           "WHERE id = %s AND user_id = %s", (event_id, user_id))
    return Response(status_code=204)


@app.delete("/api/history", status_code=204)
def clear_history(user_id: int = Depends(require_user)) -> Response:
    with connect_db() as connection:
        connection.execute("UPDATE search_events SET hidden_at = now() "
                           "WHERE user_id = %s AND hidden_at IS NULL", (user_id,))
    return Response(status_code=204)


@app.post("/api/history/restore", status_code=204)
def restore_history(user_id: int = Depends(require_user)) -> Response:
    # Undo the most recent CLEAR ALL (all rows hidden in that statement share its now()).
    with connect_db() as connection:
        connection.execute(
            "UPDATE search_events SET hidden_at = NULL WHERE user_id = %s AND hidden_at = "
            "(SELECT max(hidden_at) FROM search_events WHERE user_id = %s)",
            (user_id, user_id),
        )
    return Response(status_code=204)


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
