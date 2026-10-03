from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_root: Path
    fashion_clip_model: str
    human_parser_model: str
    max_upload_bytes: int
    cors_origins: tuple[str, ...]
    auto_migrate: bool
    s3_bucket: str
    aws_region: str
    s3_endpoint_url: str | None
    frontend_url: str
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    mail_from: str
    color_weight: float
    cookie_secure: bool
    kakao_rest_api_key: str | None
    kakao_client_secret: str | None
    kakao_redirect_uri: str


@lru_cache
def get_settings() -> Settings:
    origins = tuple(
        value.strip() for value in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        ).split(",") if value.strip()
    )
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", "postgresql://fashion:fashion@localhost:5432/fashion"
        ),
        storage_root=Path(os.getenv("LOCAL_STORAGE_ROOT", "storage")).resolve(),
        fashion_clip_model=os.getenv("FASHION_CLIP_MODEL", "yainage90/fashion-image-feature-extractor"),
        human_parser_model=os.getenv("HUMAN_PARSER_MODEL", "fashn-ai/fashn-human-parser"),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024,
        cors_origins=origins,
        auto_migrate=os.getenv("AUTO_MIGRATE", "true").lower() == "true",
        s3_bucket=os.getenv("AWS_BUCKET_NAME", "software2026"),
        aws_region=os.getenv("AWS_REGION", "ap-northeast-2"),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        mail_from=os.getenv("MAIL_FROM", "LookFind <no-reply@lookfind.local>"),
        # How much garment colour difference lowers the score (0 = embedding only).
        color_weight=float(os.getenv("COLOR_WEIGHT", "0.15")),
        # The browser reaches the API through the frontend origin (Next.js proxy), so cookies follow its scheme.
        cookie_secure=os.getenv("FRONTEND_URL", "http://localhost:3000").startswith("https://"),
        kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY") or None,
        kakao_client_secret=os.getenv("KAKAO_CLIENT_SECRET") or None,
        # Must match a Redirect URI registered in Kakao Developers; the frontend proxies it to the backend.
        kakao_redirect_uri=os.getenv("KAKAO_REDIRECT_URI")
        or os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/") + "/api/auth/kakao/callback",
    )
