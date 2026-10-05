from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote


def database_url() -> str:
    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct
    secret_arn = os.getenv("DATABASE_SECRET_ARN")
    if not secret_arn:
        return "postgresql://fashion:fashion@localhost:5432/fashion"
    import boto3
    secret = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
    value = json.loads(secret.get_secret_value(SecretId=secret_arn)["SecretString"])
    user = quote(value["username"], safe="")
    password = quote(value["password"], safe="")
    host = os.environ["DATABASE_HOST"]
    port = os.getenv("DATABASE_PORT", "5432")
    name = os.getenv("DATABASE_NAME", "fashion")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"



def cookie_secure() -> bool:
    """Secure cookies: COOKIE_SECURE=true/false if set, else follow FRONTEND_URL's scheme.

    The browser reaches the API through the frontend origin (Next.js proxy / CloudFront),
    so by default the cookies follow its scheme.
    """
    explicit = os.getenv("COOKIE_SECURE", "").strip().lower()
    if explicit in {"true", "false"}:
        return explicit == "true"
    return os.getenv("FRONTEND_URL", "http://localhost:3000").startswith("https://")

def jwt_secret(secure: bool) -> str:
    """HS256 signing key. Required in production; a throwaway key is fine for local http dev."""
    secret = os.getenv("JWT_SECRET")
    if secret:
        if len(secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters")
        return secret
    if secure:
        raise RuntimeError("JWT_SECRET is required when FRONTEND_URL is https")
    logging.getLogger("uvicorn.error").warning("JWT_SECRET is not set; using a random key (logins reset on restart).")
    return secrets.token_urlsafe(48)


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
    jwt_secret: str


@lru_cache
def get_settings() -> Settings:
    origins = tuple(
        value.strip() for value in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        ).split(",") if value.strip()
    )
    return Settings(
        database_url=database_url(),
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
        cookie_secure=cookie_secure(),
        kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY") or None,
        kakao_client_secret=os.getenv("KAKAO_CLIENT_SECRET") or None,
        # Must match a Redirect URI registered in Kakao Developers; the frontend proxies it to the backend.
        kakao_redirect_uri=os.getenv("KAKAO_REDIRECT_URI")
        or os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/") + "/api/auth/kakao/callback",
        jwt_secret=jwt_secret(cookie_secure()),
    )
