"""Request/response models shared by the API routes."""
from __future__ import annotations

import uuid

from pydantic import BaseModel


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


class User(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


class ResetRequest(BaseModel):
    email: str


class PasswordReset(BaseModel):
    token: str
    password: str


class HistoryItem(BaseModel):
    id: str
    label: str
    searched_at: str
    count: int
    image_url: str | None


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_cursor: int | None


class HistoryDetail(HistoryItem):
    results: list[SearchResult]


class HistoryIds(BaseModel):
    ids: list[str]


class DeletedHistory(BaseModel):
    deleted_ids: list[str]


class RestoredHistory(BaseModel):
    restored: int
