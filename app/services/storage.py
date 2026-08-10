"""
Cloudflare R2 (S3-compatible) storage.

Falls back to writing into ./media when R2 credentials are absent, so the API
runs end to end on a laptop before the bucket exists.
"""

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

MEDIA_ROOT = Path("media")
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class StorageError(Exception):
    pass


def _r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def upload_bytes(data: bytes, key: str, content_type: str) -> str:
    """Returns the public URL of the stored object."""
    if not settings.storage_configured:
        target = MEDIA_ROOT / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"/media/{key}"

    _r2_client().put_object(
        Bucket=settings.R2_BUCKET, Key=key, Body=data, ContentType=content_type
    )
    base = settings.R2_PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/{key}"


def save_screenshot(file: UploadFile, submission_id: uuid.UUID, order: int) -> str:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise StorageError("Screenshots must be PNG, JPG or WebP")

    data = file.file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise StorageError("Each screenshot must be under 5 MB")

    suffix = Path(file.filename or "shot.png").suffix or ".png"
    key = f"submissions/{submission_id}/{order:02d}{suffix}"
    return upload_bytes(data, key, file.content_type or "image/png")


def save_document(data: bytes, folder: str, name: str) -> str:
    return upload_bytes(data, f"{folder}/{name}", "application/pdf")


def read_bytes(url_or_key: str) -> bytes | None:
    """
    Reads a stored object back. Accepts either the URL we handed out or the
    raw key, so callers do not have to care which storage backend produced it.
    """
    key = url_or_key
    if key.startswith("/media/"):
        key = key[len("/media/"):]
    elif settings.R2_PUBLIC_BASE_URL and key.startswith(settings.R2_PUBLIC_BASE_URL):
        key = key[len(settings.R2_PUBLIC_BASE_URL.rstrip("/")) + 1:]

    if not settings.storage_configured:
        path = MEDIA_ROOT / key
        return path.read_bytes() if path.exists() else None

    try:
        response = _r2_client().get_object(Bucket=settings.R2_BUCKET, Key=key)
        return response["Body"].read()
    except Exception:  # noqa: BLE001 — a missing object is a normal outcome
        return None
