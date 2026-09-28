from __future__ import annotations

import base64
import io
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

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
    allow_methods=["GET", "POST"],
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

    with connect_db() as connection:
        connection.execute(
            "INSERT INTO search_events (query_id, platform_filter, result_count, elapsed_ms) VALUES (%s, %s, %s, %s)",
            (query_id, platform, len(rows), elapsed_ms),
        )

    results = [SearchResult(
        platform=row["platform"], goods_no=row["goods_no"], goods_name=row["goods_name"],
        brand_name=row["brand_name"], price=row["price"], product_url=row["product_url"],
        image_url=image_url(row), similarity=float(row["similarity"]),
    ) for row in rows]
    return SearchResponse(
        query_id=query_id, used_top_mask=prepared.used_top_mask,
        top_ratio=prepared.top_ratio,
        box_preview=preview_data_url(prepared.box_image),
        masked_preview=(
            preview_data_url(prepared.masked_image) if prepared.masked_image else None
        ),
        elapsed_ms=elapsed_ms, results=results,
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
