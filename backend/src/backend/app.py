from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.backend.config import get_settings
from src.backend.db import count_products, initialize_database
from src.backend.routes import account, auth, favorites, history, kakao, search


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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
for module in (auth, account, kakao, search, history, favorites):
    app.include_router(module.router)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "products": count_products()}


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}
