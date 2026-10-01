from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from psycopg import Connection, connect
from psycopg.rows import dict_row

from src.backend.config import get_settings


def connect_db() -> Connection:
    return connect(get_settings().database_url, row_factory=dict_row, connect_timeout=10)


def initialize_database() -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with connect_db() as connection:
        connection.execute(schema)


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def search_products(
    embedding: list[float], limit: int, platform: str | None = None
) -> list[dict[str, Any]]:
    vector = vector_literal(embedding)
    where = "WHERE platform = %s" if platform else ""
    params: list[Any] = [vector]
    if platform:
        params.append(platform)
    params.extend([vector, limit])
    query = f"""
        SELECT platform, goods_no, goods_name, brand_name, price,
               product_url, image_path, s3_bucket, s3_key, color_lab,
               1 - (embedding <=> %s::vector) AS similarity
        FROM products
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with connect_db() as connection:
        return list(connection.execute(query, params).fetchall())


# Lightness differs with lighting/exposure far more than hue does, so it counts half.
MAX_COLOR_DISTANCE = 60.0


def color_distance(a: list[float], b: list[float]) -> float:
    return math.sqrt((0.5 * (a[0] - b[0])) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def rerank_by_color(
    rows: list[dict[str, Any]], query_lab: tuple[float, float, float] | None, weight: float
) -> list[dict[str, Any]]:
    """similarity -= weight * (garment colour distance, capped and scaled to 0..1)."""
    if query_lab is None or weight <= 0:
        return rows
    for row in rows:
        if row.get("color_lab"):
            distance = min(color_distance(query_lab, row["color_lab"]), MAX_COLOR_DISTANCE)
            row["similarity"] = float(row["similarity"]) - weight * distance / MAX_COLOR_DISTANCE
    return sorted(rows, key=lambda row: float(row["similarity"]), reverse=True)


def search_similar(
    embedding: list[float], limit: int, platform: str | None,
    query_lab: tuple[float, float, float] | None, color_weight: float,
) -> list[dict[str, Any]]:
    # Colour can only reorder what the vector search found, so over-fetch candidates.
    candidates = search_products(embedding, min(200, max(60, limit * 5)), platform)
    return rerank_by_color(candidates, query_lab, color_weight)[:limit]


def count_products() -> int:
    with connect_db() as connection:
        row = connection.execute("SELECT count(*) AS count FROM products").fetchone()
        return int(row["count"])
