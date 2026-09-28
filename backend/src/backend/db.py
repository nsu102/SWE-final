from __future__ import annotations

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
               product_url, image_path, s3_bucket, s3_key,
               1 - (embedding <=> %s::vector) AS similarity
        FROM products
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with connect_db() as connection:
        return list(connection.execute(query, params).fetchall())


def merge_search_results(
    result_sets: list[list[dict[str, Any]]], limit: int
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for rows in result_sets:
        for row in rows:
            key = (str(row["platform"]), str(row["goods_no"]))
            if key not in merged or float(row["similarity"]) > float(merged[key]["similarity"]):
                merged[key] = row
    return sorted(
        merged.values(), key=lambda row: float(row["similarity"]), reverse=True
    )[:limit]


def search_products_multi(
    embeddings: list[list[float]], limit: int, platform: str | None = None
) -> list[dict[str, Any]]:
    candidate_limit = min(200, max(50, limit * 4))
    result_sets = [
        search_products(embedding, candidate_limit, platform)
        for embedding in embeddings
    ]
    return merge_search_results(result_sets, limit)


def count_products() -> int:
    with connect_db() as connection:
        row = connection.execute("SELECT count(*) AS count FROM products").fetchone()
        return int(row["count"])
