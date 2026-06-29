"""
Cloudflare R2 storage service (S3-compatible, via boto3).

Objects are stored under a per-customer prefix: customers/{customer_id}/
All functions are synchronous; call them from async code with asyncio.to_thread.
"""
import mimetypes
from pathlib import Path
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ..core.config import settings


@lru_cache(maxsize=1)
def _client():
    if not (settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY):
        raise RuntimeError("R2 credentials are not configured (R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY)")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def customer_prefix(customer_id: str) -> str:
    return f"customers/{customer_id}/"


def upload_file(local_path: Path, key: str, content_type: str | None = None):
    ct = content_type or mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    _client().upload_file(
        str(local_path), settings.R2_BUCKET_NAME, key,
        ExtraArgs={"ContentType": ct},
    )


def upload_bytes(data: bytes, key: str, content_type: str = "application/octet-stream"):
    _client().put_object(Bucket=settings.R2_BUCKET_NAME, Key=key, Body=data, ContentType=content_type)


def download_bytes(key: str) -> bytes:
    obj = _client().get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    return obj["Body"].read()


def object_exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False


def list_objects(prefix: str) -> list[dict]:
    """Returns [{key, name, size}] for every object under prefix."""
    paginator = _client().get_paginator("list_objects_v2")
    out: list[dict] = []
    for page in paginator.paginate(Bucket=settings.R2_BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            out.append({"key": key, "name": key.rsplit("/", 1)[-1], "size": obj["Size"]})
    return out


def delete_prefix(prefix: str):
    """Delete every object under prefix."""
    client = _client()
    paginator = client.get_paginator("list_objects_v2")
    to_delete: list[dict] = []
    for page in paginator.paginate(Bucket=settings.R2_BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            to_delete.append({"Key": obj["Key"]})
    _delete_keys([d["Key"] for d in to_delete])


def delete_keys(keys: list[str]):
    """Delete an explicit list of object keys in batched delete_objects calls.

    Avoids a separate LIST+DELETE per key when the caller already knows the
    exact keys (e.g. stale PDFs from a prior generation)."""
    _delete_keys(keys)


def _delete_keys(keys: list[str]):
    if not keys:
        return
    client = _client()
    for i in range(0, len(keys), 1000):
        client.delete_objects(
            Bucket=settings.R2_BUCKET_NAME,
            Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]]},
        )


def presigned_url(key: str, expires_seconds: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_seconds,
    )
