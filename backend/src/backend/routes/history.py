"""Search history (ARCHIVE): paging, soft delete and 10-minute restore."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.backend.auth import require_user
from src.backend.db import connect_db
from src.backend.products import PRODUCT_COLUMNS, to_result
from src.backend.schemas import DeletedHistory, HistoryDetail, HistoryIds, HistoryItem, HistoryPage, RestoredHistory

router = APIRouter()


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


@router.get("/api/history", response_model=HistoryPage)
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


@router.get("/api/history/{event_id}", response_model=HistoryDetail)
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


@router.delete("/api/history/{event_id}", response_model=DeletedHistory)
def remove_history(event_id: int, user_id: int = Depends(require_user)) -> DeletedHistory:
    return hide_history(user_id, event_id)


@router.delete("/api/history", response_model=DeletedHistory)
def clear_history(user_id: int = Depends(require_user)) -> DeletedHistory:
    return hide_history(user_id, None)


@router.post("/api/history/restore", response_model=RestoredHistory)
def restore_history(body: HistoryIds, user_id: int = Depends(require_user)) -> RestoredHistory:
    with connect_db() as connection:
        restored = connection.execute(
            "UPDATE search_events SET hidden_at = NULL WHERE user_id = %s AND id = ANY(%s) "
            f"AND hidden_at >= now() - interval '{UNDO_WINDOW}'",
            (user_id, event_ids(body.ids)),
        ).rowcount
    return RestoredHistory(restored=restored)
