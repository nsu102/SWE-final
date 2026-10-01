#!/usr/bin/env python3
"""Select the first person-free top image from each Musinsa product gallery.

The product page is fetched once. Candidate images are then downloaded in UI
order and discarded immediately unless selected. Results are resumable and can
optionally be uploaded to an S3-compatible bucket.
"""

from __future__ import annotations

import argparse
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
import mimetypes
import re
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, SegformerForSemanticSegmentation

from src.common.http import Fetcher, NEXT_DATA_RE
from src.common.human_parser import DEFAULT_MODEL, label_ids_for_tops, select_device


IMAGE_BASE = "https://image.msscdn.net"
# Worker threads overlap network I/O; the GPU runs one parse at a time (processes would contend).
MODEL_LOCK = threading.Lock()
# CDN images take ~1.5s each, mostly latency, so keep this many downloads in flight per product.
PREFETCH = 6
# Musinsa's CDN serves the same image at 320px (~42% of the bytes). Bandwidth is the crawl's
# bottleneck, so detection runs on the small copy and only the chosen image is fetched full size.
CDN_500 = re.compile(r"_500\.(jpe?g|png|webp|gif)$", re.IGNORECASE)


def small_variant(url: str) -> str:
    return CDN_500.sub(r"_320.\1", url)
FACE_IDS: list[int] = []  # filled in main() from the parser's labels
BODY_EVIDENCE = 0.002
HUMAN_LABELS = {"face", "hair", "arms", "hands", "legs", "feet"}


def load_project_env(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries without overwriting shell variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)


def parse_args() -> argparse.Namespace:
    load_project_env()
    parser = argparse.ArgumentParser(description="Crawl and select Musinsa detail images")
    parser.add_argument("--products", type=Path, default=Path("data/musinsa/tops/products.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/musinsa/tops/selected"))
    parser.add_argument("--limit", type=int, help="maximum new products to process")
    parser.add_argument("--goods-no", help="process only one goods_no")
    parser.add_argument("--start-after", help="skip rows through this goods_no")
    parser.add_argument(
        "--shard", default="0/1",
        help="K/N: only goods_no %% N == K, so N processes can split a full run",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="delay between product pages (per worker)")
    parser.add_argument("--workers", type=int, default=1, help="products processed concurrently")
    # Keep the model's native 576x384: at 448x288 it hallucinated "face" on flat garment shots.
    parser.add_argument("--parser-size", default="576x384", help="human parser input HxW")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--human-threshold", type=float, default=0.005)
    parser.add_argument("--top-threshold", type=float, default=0.05)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--retry-no-match", action="store_true")
    parser.add_argument(
        "--max-checks", type=int, default=40,
        help="stop after this many parsed views per product (tall detail sheets split into many)",
    )
    parser.add_argument(
        "--delete-local-after-upload",
        action="store_true",
        help="remove the local selected image after a successful S3 upload",
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.getenv("MUSINSA_S3_BUCKET") or os.getenv("AWS_BUCKET_NAME"),
    )
    parser.add_argument("--s3-prefix", default="musinsa/products")
    parser.add_argument("--s3-endpoint-url", default=os.getenv("S3_ENDPOINT_URL"))
    return parser.parse_args()


class ProductUnavailable(Exception):
    """Musinsa no longer serves this product; record it as excluded instead of retrying."""


def parse_gallery_urls(
    body: bytes,
    thumbnail_url: str | None = None,
) -> list[str]:
    match = NEXT_DATA_RE.search(body)
    if not match:
        raise ValueError("__NEXT_DATA__ missing from product page")
    document = json.loads(match.group(1))
    page_props = document["props"]["pageProps"]
    meta = page_props.get("meta") or {}
    status = meta.get("meta") or {}
    if meta.get("data") is None and status.get("result") == "FAIL":
        # e.g. DISPLAY_000_0006 "유효하지 않은 상품 입니다." (deleted / no longer sold)
        raise ProductUnavailable(f"{status.get('errorCode')}: {status.get('message')}")
    product = meta.get("data") or {}
    # The page's current representative image; products.csv thumbnails go stale (404) when
    # Musinsa re-uploads images.
    if product.get("thumbnailImageUrl"):
        thumbnail_url = urljoin(IMAGE_BASE, product["thumbnailImageUrl"])
    gallery = product.get("goodsImages")
    if gallery is None:
        for query in page_props.get("dehydratedState", {}).get("queries", []):
            candidate = query.get("state", {}).get("data", {}).get("data", {})
            if candidate.get("goodsImages") is not None:
                gallery = candidate["goodsImages"]
                product = candidate
                break

    urls: list[str] = []
    if thumbnail_url:
        urls.append(thumbnail_url)
    for item in gallery or []:
        url = item.get("imageUrl") if isinstance(item, dict) else None
        if url:
            urls.append(urljoin(IMAGE_BASE, url))
    # Preserve thumbnail -> gallery -> product-detail order and remove duplicates.
    return list(dict.fromkeys(urls))


def predict_classes(
    image: Image.Image,
    processor: AutoImageProcessor,
    model: SegformerForSemanticSegmentation,
    device: torch.device,
) -> np.ndarray:
    inputs = processor(images=image, return_tensors="pt")
    inputs = {key: value.to(device, model.dtype) for key, value in inputs.items()}
    with MODEL_LOCK, torch.inference_mode():
        logits = model(**inputs).logits
        # Labels at the fixed model input size (e.g. 576x384), not the source size: only area
        # ratios are used, which resizing preserves, and a fixed shape keeps the GPU graph cached.
        logits = torch.nn.functional.interpolate(
            logits, size=inputs["pixel_values"].shape[-2:], mode="bilinear", align_corners=False
        )
        return logits.argmax(dim=1)[0].cpu().numpy()


def score_image(
    image: Image.Image,
    processor: AutoImageProcessor,
    model: SegformerForSemanticSegmentation,
    device: torch.device,
    human_ids: list[int],
    top_ids: list[int],
) -> tuple[float, float, np.ndarray]:
    prediction = predict_classes(image, processor, model, device)
    # The parser hallucinates "face" (3-5%) on hood openings and necklines of flat garment shots.
    # A real person also shows hair or limbs, so a face only counts alongside those.
    body_ratio = float(np.isin(prediction, [i for i in human_ids if i not in FACE_IDS]).mean())
    face_ratio = float(np.isin(prediction, FACE_IDS).mean())
    human_ratio = body_ratio + (face_ratio if body_ratio >= BODY_EVIDENCE else 0.0)
    top_mask = np.isin(prediction, top_ids)
    top_ratio = float(top_mask.mean())
    return human_ratio, top_ratio, top_mask


def analysis_views(image: Image.Image) -> list[tuple[Image.Image, tuple[int, int, int, int] | None]]:
    """Split very tall detail sheets into overlapping viewport-like crops."""
    if image.height <= image.width * 3:
        return [(image, None)]
    window_height = min(image.height, round(image.width * 1.5))
    step = max(1, round(window_height * 0.50))
    top_positions = list(range(0, image.height - window_height + 1, step))
    final_top = image.height - window_height
    if not top_positions or top_positions[-1] != final_top:
        top_positions.append(final_top)
    views = []
    for top in top_positions:
        box = (0, top, image.width, top + window_height)
        views.append((image.crop(box), box))
    return views


def mask_border_ratio(mask: np.ndarray) -> float:
    """Measure whether the detected garment is cut off by the crop boundary."""
    band = max(1, round(min(mask.shape) * 0.03))
    border = np.zeros_like(mask, dtype=bool)
    border[:band, :] = True
    border[-band:, :] = True
    border[:, :band] = True
    border[:, -band:] = True
    garment_pixels = int(mask.sum())
    return float((mask & border).sum() / garment_pixels) if garment_pixels else 1.0


def drop_partial_last_line(path: Path) -> None:
    """A hard kill can leave half a JSON line; cut it so the next append starts on a fresh line."""
    if not path.exists() or path.stat().st_size == 0:
        return
    data = path.read_bytes()
    if not data.endswith(b"\n"):
        path.write_bytes(data[: data.rfind(b"\n") + 1])


def load_completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
                goods_no = str(row["goods_no"])
            except (json.JSONDecodeError, KeyError):
                continue
            # "Excluded" only counts when every image was actually checked. If downloads failed
            # (e.g. the network dropped), the verdict is unreliable, so retry that product.
            if row.get("status") != "selected" and any(
                candidate.get("error") and "not found" not in candidate["error"]
                for candidate in row.get("checked_images") or []
            ):
                completed.discard(goods_no)
                continue
            completed.add(goods_no)
    return completed


def load_statuses(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    statuses: dict[str, str] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("goods_no"):
                statuses[str(row["goods_no"])] = str(row.get("status", ""))
    return statuses


def extension_for(url: str, image: Image.Image) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".png" if image.format == "PNG" else ".jpg"


def save_image(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    if path.suffix.lower() == ".png":
        image.save(temporary, format="PNG", optimize=True)
    else:
        image.convert("RGB").save(temporary, format="JPEG", quality=95)
    temporary.replace(path)


def get_s3_client(args: argparse.Namespace):
    if not args.s3_bucket:
        return None
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("S3 upload requires: pip install boto3") from exc
    return boto3.client(
        "s3",
        endpoint_url=args.s3_endpoint_url,
        region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    )


def upload_s3(client, bucket: str, local_path: Path, key: str) -> None:
    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    client.upload_file(
        str(local_path), bucket, key,
        ExtraArgs={"ContentType": content_type, "CacheControl": "public,max-age=31536000,immutable"},
    )


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def save_result(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if not overwrite or not path.exists():
        append_jsonl(path, payload)
        return
    goods_no = str(payload["goods_no"])
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("goods_no")) != goods_no:
                rows.append(row)
    rows.append(payload)
    temporary = path.with_suffix(".jsonl.part")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def process_product(
    row: dict[str, str], args: argparse.Namespace, fetcher: Fetcher,
    processor: AutoImageProcessor, model: SegformerForSemanticSegmentation,
    device: torch.device, human_ids: list[int], top_ids: list[int], s3_client,
) -> dict[str, Any]:
    goods_no = row["goods_no"]
    product_url = row.get("product_url") or f"https://www.musinsa.com/products/{goods_no}"
    page_body = fetcher.get(product_url)

    def excluded(reason: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "platform": "musinsa",
            "goods_no": goods_no,
            "product_url": product_url,
            "status": "excluded",
            "exclude_reason": reason,
            "selected_index": None,
            "selected_url": None,
            "local_path": None,
            "s3_bucket": args.s3_bucket,
            "s3_key": None,
            "human_ratio": None,
            "top_ratio": None,
            "mask_path": None,
            "checked_images": candidates,
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "model": args.model,
        }

    unavailable = None
    try:
        urls = parse_gallery_urls(page_body, row.get("thumbnail_url"))
    except ProductUnavailable as exc:
        # No longer sold: the page is gone, but the crawled thumbnail may still be on the CDN.
        unavailable = str(exc)
        urls = [row["thumbnail_url"]] if row.get("thumbnail_url") else []
        if not urls:
            return {**excluded("product_unavailable", []), "message": unavailable}
    if not urls:
        raise ValueError("product gallery is empty")

    candidates: list[dict[str, Any]] = []
    selected: tuple[
        int, str, Image.Image, float, float, np.ndarray, tuple[int, int, int, int] | None
    ] | None = None

    def fetch(url: str) -> Image.Image:
        return Image.open(io.BytesIO(fetcher.get(url, referer=product_url))).convert("RGB")

    def download(url: str) -> Image.Image:
        small = small_variant(url)
        if small != url:
            try:
                return fetch(small)
            except Exception:
                pass  # no 320px copy; fall back to the original
        return fetch(url)

    # ponytail: a finished product may leave a few unused prefetched downloads; fine for a CDN.
    pool = ThreadPoolExecutor(PREFETCH)
    pending = deque(pool.submit(download, url) for url in urls[:PREFETCH])
    for index, url in enumerate(urls):
        if args.max_checks and len(candidates) >= args.max_checks:
            break
        future = pending.popleft()
        if index + PREFETCH < len(urls):
            pending.append(pool.submit(download, urls[index + PREFETCH]))
        try:
            image = future.result()
        except Exception as exc:
            candidates.append({"index": index, "url": url, "error": str(exc)})
            continue
        matches = []
        for view, crop_box in analysis_views(image):
            human_ratio, top_ratio, top_mask = score_image(
                view, processor, model, device, human_ids, top_ids
            )
            border_ratio = mask_border_ratio(top_mask)
            candidate = {
                "index": index, "url": url, "human_ratio": human_ratio,
                "top_ratio": top_ratio, "width": view.width, "height": view.height,
                "top_border_ratio": border_ratio,
            }
            if crop_box:
                candidate["source_size"] = [image.width, image.height]
                candidate["crop_box"] = list(crop_box)
            candidates.append(candidate)
            # Prefer little/no visible person and a meaningful amount of upper clothing.
            if human_ratio <= args.human_threshold and top_ratio >= args.top_threshold:
                matches.append((
                    index, url, view.copy(), human_ratio, top_ratio, top_mask.copy(), crop_box
                ))
        if matches:
            # A catalog-style garment is surrounded by background rather than cut by crop edges.
            selected = min(matches, key=lambda item: (mask_border_ratio(item[5]), -item[4]))
            break
    pool.shutdown(wait=False, cancel_futures=True)
    if selected is None:
        result = excluded("product_unavailable" if unavailable else "no_person_free_top_image", candidates)
        return {**result, "message": unavailable} if unavailable else result

    index, url, image, human_ratio, top_ratio, top_mask, crop_box = selected
    if small_variant(url) != url and image.width < 500:
        # Judged on the 320px copy: store the full-size image (raises -> retried next pass).
        full = fetch(url)
        if crop_box:
            scale = full.width / image.width  # tall-sheet views span the full width
            full = full.crop(tuple(round(value * scale) for value in crop_box))
        image = full
    suffix = extension_for(url, image)
    image_hash = hashlib.sha256(image.tobytes()).hexdigest()[:12]
    local_path = args.output / "images" / goods_no / f"selected-{image_hash}{suffix}"
    save_image(image, local_path)

    s3_key = None
    if s3_client:
        s3_key = f"{args.s3_prefix.strip('/')}/{goods_no}/{local_path.name}"
        upload_s3(s3_client, args.s3_bucket, local_path, s3_key)

    local_path_value: str | None = str(local_path.resolve())
    if args.delete_local_after_upload and s3_key:
        local_path.unlink()
        local_path_value = None

    return {
        "platform": "musinsa",
        "goods_no": goods_no,
        "product_url": product_url,
        "status": "selected",
        "selected_index": index,
        "selected_url": url,
        "selected_crop_box": list(crop_box) if crop_box else None,
        "local_path": local_path_value,
        "s3_bucket": args.s3_bucket,
        "s3_key": s3_key,
        "human_ratio": human_ratio,
        "top_ratio": top_ratio,
        "mask_path": None,
        "checked_images": candidates,
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": args.model,
    }


def main() -> int:
    args = parse_args()
    if (
        args.delay < 0
        or args.human_threshold < 0
        or args.top_threshold < 0
    ):
        raise SystemExit("delay and thresholds must be non-negative")
    shard, shards = (int(part) for part in args.shard.split("/"))
    if not 0 <= shard < shards:
        raise SystemExit("--shard must be K/N with 0 <= K < N")
    args.output = args.output.resolve()
    results_path = args.output / "selections.jsonl"
    errors_path = args.output / "errors.jsonl"
    drop_partial_last_line(results_path)
    completed = set() if args.overwrite else load_completed(results_path)
    statuses = load_statuses(results_path)
    fetcher = Fetcher(args.timeout, args.retries)
    s3_client = get_s3_client(args)

    device = select_device()
    print(f"Loading {args.model} on {device}...", flush=True)
    height, width = (int(v) for v in args.parser_size.split("x"))
    processor = AutoImageProcessor.from_pretrained(args.model, size={"height": height, "width": width})
    model = SegformerForSemanticSegmentation.from_pretrained(args.model).to(device).eval()
    if device.type in {"mps", "cuda"}:
        # fp16 is ~1.5x faster on GPUs with identical argmax labels (measured on Apple MPS).
        model = model.half()
    top_ids, labels = label_ids_for_tops(model.config.id2label)
    labels = {int(key): value for key, value in model.config.id2label.items()}
    human_ids = [idx for idx, label in labels.items() if label.lower() in HUMAN_LABELS]
    FACE_IDS[:] = [idx for idx, label in labels.items() if label.lower() == "face"]
    print(f"Human classes: {[(i, labels[i]) for i in human_ids]}", flush=True)

    rows: list[dict[str, str]] = []
    start_reached = args.start_after is None
    with args.products.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            goods_no = row.get("goods_no", "")
            if args.goods_no and goods_no != args.goods_no:
                continue
            if args.retry_no_match and statuses.get(goods_no) not in {"no_match", "excluded"}:
                continue
            if not start_reached:
                if goods_no == args.start_after:
                    start_reached = True
                continue
            if not goods_no or goods_no in completed:
                continue
            if shards > 1 and int(goods_no) % shards != shard:
                continue
            if args.limit is not None and len(rows) >= args.limit:
                break
            rows.append(row)
    print(f"{len(rows)} products to process with {args.workers} workers", flush=True)

    processed = failed = 0
    write_lock = threading.Lock()

    def work(row: dict[str, str]) -> None:
        nonlocal processed, failed
        goods_no = row["goods_no"]
        try:
            result = process_product(
                row, args, fetcher, processor, model, device,
                human_ids, top_ids, s3_client,
            )
            with write_lock:
                save_result(results_path, result, args.overwrite)
                processed += 1
                print(
                    f"{goods_no}: " + (
                        f"selected image {result['selected_index']} "
                        f"(human={result['human_ratio']:.2%}, top={result['top_ratio']:.2%})"
                        if result["status"] == "selected"
                        else result.get("message") or "no person-free gallery image"
                    ), flush=True,
                )
        except Exception as exc:
            with write_lock:
                failed += 1
                append_jsonl(errors_path, {
                    "goods_no": goods_no, "error": str(exc),
                    "failed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                })
                print(f"{goods_no}: FAILED: {exc}", flush=True)
        if args.delay:
            time.sleep(args.delay)

    pool = ThreadPoolExecutor(max(1, args.workers))
    try:
        list(pool.map(work, rows))
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()

    print(f"Done: {processed} processed, {failed} failed. Results: {results_path}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
