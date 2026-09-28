"""Short-lived URLs for private catalog objects; credentials come from the IAM role."""
from functools import lru_cache

import boto3
from botocore.config import Config

from src.backend.config import get_settings


@lru_cache
def s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.s3_endpoint_url,
        config=Config(signature_version="s3v4"),
    )


def image_url(row: dict) -> str:
    if row.get("s3_key"):
        bucket = row.get("s3_bucket") or get_settings().s3_bucket
        if bucket != get_settings().s3_bucket:
            raise ValueError("Unexpected catalog bucket")
        return s3_client().generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": row["s3_key"]}, ExpiresIn=900
        )
    return f"/media/{row['platform']}/{row['goods_no']}"
