from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
from pathlib import Path

from PIL import Image

from src.backend.config import get_settings
from src.backend.db import connect_db, initialize_database, vector_literal
from src.backend.ml import get_models
from src.backend.storage import s3_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed selected catalog images into pgvector")
    parser.add_argument("--platform", choices=["musinsa", "ably"], required=True)
    parser.add_argument("--products", type=Path)
    parser.add_argument("--selections", type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    size = parser.add_mutually_exclusive_group()
    size.add_argument("--limit", type=int, help="maximum new records to index")
    size.add_argument(
        "--target-count", type=int,
        help="stop when this platform has the requested number of indexed products",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="do not recompute embeddings for goods already in the database",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def defaults(args: argparse.Namespace) -> tuple[Path, Path]:
    base = Path("data") / args.platform / "tops"
    return args.products or base / "products.csv", args.selections or base / "selected/selections.jsonl"


def load_records(products_path: Path, selections_path: Path, platform: str) -> list[dict]:
    with products_path.open(encoding="utf-8-sig", newline="") as stream:
        products = {row["goods_no"]: row for row in csv.DictReader(stream)}
    records = []
    for line in selections_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        selection = json.loads(line)
        if selection.get("status") != "selected":
            continue
        product = products.get(str(selection["goods_no"]))
        local_path = selection.get("local_path")
        source = Path(local_path) if local_path else None
        has_local = bool(source and source.is_file())
        has_s3 = bool(selection.get("s3_key"))
        if product and (has_local or has_s3):
            records.append({
                "platform": platform,
                "product": product,
                "source": source if has_local else None,
                "s3_bucket": selection.get("s3_bucket"),
                "s3_key": selection.get("s3_key"),
            })
    return records


def load_image(record: dict, default_bucket: str) -> Image.Image:
    if record["source"]:
        with Image.open(record["source"]) as image:
            return image.convert("RGB")
    bucket = record["s3_bucket"] or default_bucket
    response = s3_client().get_object(Bucket=bucket, Key=record["s3_key"])
    body = response["Body"].read()
    with Image.open(io.BytesIO(body)) as image:
        return image.convert("RGB")


def existing_goods_numbers(platform: str) -> set[str]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT goods_no FROM products WHERE platform = %s", (platform,)
        ).fetchall()
    return {str(row["goods_no"]) for row in rows}


def plan_records(
    records: list[dict],
    existing: set[str],
    *,
    limit: int | None,
    target_count: int | None,
    skip_existing: bool,
) -> list[dict]:
    unseen = [
        record for record in records
        if str(record["product"]["goods_no"]) not in existing
    ]
    if target_count is not None:
        return unseen[:max(0, target_count - len(existing))]
    candidates = unseen if skip_existing else records
    return candidates[:limit] if limit is not None else candidates


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be >= 1")
    if args.target_count is not None and args.target_count < 1:
        raise SystemExit("--target-count must be >= 1")
    products_path, selections_path = defaults(args)
    available_records = load_records(products_path, selections_path, args.platform)
    settings = get_settings()
    initialize_database()
    existing = existing_goods_numbers(args.platform)
    records = plan_records(
        available_records,
        existing,
        limit=args.limit,
        target_count=args.target_count,
        skip_existing=args.skip_existing,
    )
    target = args.target_count if args.target_count is not None else "not set"
    print(
        f"Catalog plan: available={len(available_records)}, existing={len(existing)}, "
        f"to_index={len(records)}, target={target}",
        flush=True,
    )
    if args.dry_run or not records:
        return 0

    models = get_models()
    indexed = 0
    for start in range(0, len(records), args.batch_size):
        batch = records[start:start + args.batch_size]
        images = [load_image(record, settings.s3_bucket) for record in batch]
        # Match the query pipeline: crop to the garment so catalog embeddings are
        # not dominated by model pose / background. Use the box (tight crop) view;
        # falls back to the full image when no top is detected.
        # ponytail: single box view to fit the one-vector schema. Store box+masked
        # as multi-vector if recall needs it (query already embeds both views).
        prepared = [models.prepare_query(image) for image in images]
        embeddings = models.embed([view.box_image for view in prepared])
        with connect_db() as connection:
            for record, embedding in zip(batch, embeddings):
                product = record["product"]
                destination = None
                if record["source"] and not record["s3_key"]:
                    suffix = record["source"].suffix.lower() or ".jpg"
                    destination = settings.storage_root / "products" / args.platform / f"{product['goods_no']}{suffix}"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(record["source"], destination)
                connection.execute("""
                    INSERT INTO products (
                        platform, goods_no, goods_name, brand_name, price,
                        product_url, image_path, s3_bucket, s3_key,
                        embedding, embedding_model
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (platform, goods_no) DO UPDATE SET
                        goods_name = EXCLUDED.goods_name,
                        brand_name = EXCLUDED.brand_name,
                        price = EXCLUDED.price,
                        product_url = EXCLUDED.product_url,
                        image_path = EXCLUDED.image_path,
                        s3_bucket = EXCLUDED.s3_bucket,
                        s3_key = EXCLUDED.s3_key,
                        embedding = EXCLUDED.embedding,
                        embedding_model = EXCLUDED.embedding_model,
                        updated_at = now()
                """, (
                    args.platform, product["goods_no"], product["goods_name"],
                    product.get("brand_name", ""), int(product["final_price"] or product["price"] or 0) or None,
                    product["product_url"], str(destination.resolve()) if destination else None,
                    record["s3_bucket"] or settings.s3_bucket if record["s3_key"] else None,
                    record["s3_key"],
                    vector_literal(embedding.tolist()), settings.fashion_clip_model,
                ))
        indexed += len(batch)
        print(f"Indexed {indexed}/{len(records)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
