"""
Cloudflare R2 (S3-compatible) storage.

**Nothing here is served from a public URL.** Every stored object — offer
letters, certificates, task screenshots, chapter notes — is read back through
an authenticated API route that checks who is asking. `upload_bytes` returns an
opaque storage key, not a link.

That is a deliberate change from the original design, which put documents on a
public bucket under predictable names. Certificate numbers were sequential at
the time, so anyone who saw one URL could increment it and walk the whole
sequence, downloading every student's offer letter and certificate. Numbers are
random now, which helps, but the real fix is that guessing a key gains nothing
because the bucket does not answer to the public at all.

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
MAX_PDF_BYTES = 25 * 1024 * 1024

# The first bytes of a file, which cannot be faked by setting a header. The
# browser's Content-Type is a claim by the client; this is evidence.
MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"%PDF": "application/pdf",
}


class StorageError(Exception):
    pass


def _sniff(data: bytes) -> str | None:
    """The real content type, or None when it is not one we accept."""
    for signature, content_type in MAGIC.items():
        if data.startswith(signature):
            return content_type
    # WebP is RIFF....WEBP — the marker sits at byte 8, not byte 0.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


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
    """
    Stores an object and returns its **key**, not a URL.

    Callers persist this key and hand it to `read_bytes` when an authenticated
    route needs the file. There is deliberately no public link to return.
    """
    if not settings.storage_configured:
        target = MEDIA_ROOT / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return key

    _r2_client().put_object(
        Bucket=settings.R2_BUCKET, Key=key, Body=data, ContentType=content_type
    )
    return key


def save_screenshot(file: UploadFile, submission_id: uuid.UUID, order: int) -> str:
    data = file.file.read()

    if len(data) > MAX_IMAGE_BYTES:
        raise StorageError("Each screenshot must be under 5 MB")

    # Validated by content, not by the Content-Type the client asserted.
    actual = _sniff(data)
    if actual is None or actual not in ALLOWED_IMAGE_TYPES:
        raise StorageError("Screenshots must be PNG, JPG or WebP")

    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[actual]
    key = f"submissions/{submission_id}/{order:02d}{suffix}"
    return upload_bytes(data, key, actual)


def save_chapter_pdf(
    data: bytes, chapter_id: uuid.UUID, filename: str | None, claimed_type: str | None
) -> str:
    """Stores a chapter's study notes. PDF only, verified by content."""
    if len(data) > MAX_PDF_BYTES:
        raise StorageError("Notes must be under 25 MB")

    if _sniff(data) != "application/pdf":
        raise StorageError("Notes must be a PDF")

    return upload_bytes(data, f"chapters/{chapter_id}.pdf", "application/pdf")


def save_document(data: bytes, folder: str, name: str) -> str:
    return upload_bytes(data, f"{folder}/{name}", "application/pdf")


def read_bytes(url_or_key: str) -> bytes | None:
    """
    Reads a stored object back.

    Accepts a bare key, and also the `/media/…` and public-URL forms that
    earlier versions handed out, so records written before storage went private
    still resolve without a data migration.
    """
    key = url_or_key
    if key.startswith("/media/"):
        key = key[len("/media/"):]
    elif "://" in key:
        # A full URL from the old public-bucket scheme: keep everything after
        # the host.
        key = key.split("://", 1)[1].split("/", 1)[-1]

    if not settings.storage_configured:
        path = MEDIA_ROOT / key
        return path.read_bytes() if path.exists() else None

    try:
        response = _r2_client().get_object(Bucket=settings.R2_BUCKET, Key=key)
        return response["Body"].read()
    except Exception:  # noqa: BLE001 — a missing object is a normal outcome
        return None
