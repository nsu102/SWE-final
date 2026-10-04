"""Catalog rows -> API results."""
from __future__ import annotations

from src.backend.schemas import SearchResult
from src.backend.storage import image_url

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
