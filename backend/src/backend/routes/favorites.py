"""Per-account favorites (SAVED)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg.errors import ForeignKeyViolation

from src.backend.auth import require_user
from src.backend.db import connect_db
from src.backend.products import PRODUCT_COLUMNS, to_result
from src.backend.schemas import SearchResult

router = APIRouter()


@router.get("/api/favorites", response_model=list[SearchResult])
def favorites(user_id: int = Depends(require_user)) -> list[SearchResult]:
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT {PRODUCT_COLUMNS}, 0 AS similarity FROM favorites f "
            "JOIN products p ON p.platform = f.platform AND p.goods_no = f.goods_no "
            "WHERE f.user_id = %s ORDER BY f.created_at DESC",
            (user_id,),
        ).fetchall()
    return [to_result(row) for row in rows]


@router.put("/api/favorites/{platform}/{goods_no}", status_code=204)
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


@router.delete("/api/favorites/{platform}/{goods_no}", status_code=204)
def remove_favorite(platform: str, goods_no: str, user_id: int = Depends(require_user)) -> Response:
    with connect_db() as connection:
        connection.execute(
            "DELETE FROM favorites WHERE user_id = %s AND platform = %s AND goods_no = %s",
            (user_id, platform, goods_no),
        )
    return Response(status_code=204)
