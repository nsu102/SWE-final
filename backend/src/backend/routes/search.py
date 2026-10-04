"""Photo search and catalog images."""
from __future__ import annotations

import base64
import io
import time
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from src.backend.auth import optional_user
from src.backend.config import get_settings
from src.backend.db import connect_db, search_similar
from src.backend.ml import get_models
from src.backend.products import to_result
from src.backend.schemas import SearchResponse
from src.backend.storage import image_url, s3_client

router = APIRouter()
settings = get_settings()


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


@router.post("/api/search", response_model=SearchResponse)
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


@router.get("/media/{platform}/{goods_no}")
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
