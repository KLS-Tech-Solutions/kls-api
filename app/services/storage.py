"""
Local file storage.

Every stored object — offer letters, certificates, task screenshots, chapter
notes — lives on this server's disk under `MEDIA_ROOT`, and **nothing is served
from a static path**. Files are read back only through API routes that check who
is asking. `upload_bytes` returns an opaque storage key, never a link.

That is deliberate. The original design put documents on a public bucket under
predictable names; certificate numbers were sequential at the time, so anyone
holding one URL could increment it and walk the whole sequence, downloading
every student's offer letter and certificate. Numbers are random now, which
helps, but the real fix is that the files are not reachable without
authenticating, whatever the key.

**This directory is now the only copy of every student document.** There is no
object store behind it. It must live outside the deployment directory so a
redeploy cannot wipe it, and it must be in the backup — see `docs/DEPLOYMENT.md`.
"""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

MEDIA_ROOT = Path(settings.MEDIA_ROOT).resolve()

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


def _safe_path(key: str) -> Path:
    """
    Resolve a storage key to a path, refusing anything that escapes the root.

    Keys are built internally today, so this guards against a future caller
    rather than a current one — but the cost of being wrong here is reading or
    writing arbitrary files as the service user, and `read_bytes` takes its
    argument from a database column. A column is a thing that can be changed by
    some other bug.

    `..`, absolute paths and symlinked escapes are all caught, because the
    comparison is done after `resolve()` rather than on the string.
    """
    candidate = (MEDIA_ROOT / key).resolve()
    if candidate != MEDIA_ROOT and MEDIA_ROOT not in candidate.parents:
        raise StorageError("Invalid storage key")
    return candidate


def upload_bytes(data: bytes, key: str, content_type: str) -> str:
    """
    Stores an object and returns its **key**, not a URL.

    Callers persist this key and hand it to `read_bytes` when an authenticated
    route needs the file. There is deliberately no public link to return.

    The write is atomic: the bytes go to a temporary file in the same directory
    and are then renamed over the target. `os.replace` is atomic within a
    filesystem, so a crash or a full disk midway through leaves either the old
    file or no file — never a half-written PDF that opens to a grey screen and
    looks like a rendering bug.
    """
    target = _safe_path(key)
    target.parent.mkdir(parents=True, exist_ok=True)

    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise StorageError(f"Could not store {key}") from exc

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
    """
    Stores a chapter's study notes. PDF only, verified by content.

    Keyed by chapter id rather than by the uploaded filename, so two chapters
    whose notes are both called `notes.pdf` cannot overwrite each other, and so
    a filename from a browser never reaches the filesystem.
    """
    if len(data) > MAX_PDF_BYTES:
        raise StorageError("Notes must be under 25 MB")

    if _sniff(data) != "application/pdf":
        raise StorageError("Notes must be a PDF")

    return upload_bytes(data, f"chapters/{chapter_id}.pdf", "application/pdf")


def save_document(data: bytes, folder: str, name: str) -> str:
    return upload_bytes(data, f"{folder}/{name}", "application/pdf")


def content_disposition(filename: str, *, download: bool = True) -> dict[str, str]:
    """
    A `Content-Disposition` header that a filename cannot break.

    The names reaching this come from chapter titles and student names, which
    are user-supplied. A quote closes the quoted string early, and a newline
    ends the header and begins another — so an admin could name a chapter
    `x".pdf\\r\\nSet-Cookie: ...` and inject a header into every download of it.
    Stripping to a known-safe set is cheaper to reason about than escaping.

    `attachment` saves the file; `inline` lets the browser render it in its own
    viewer. Reading study notes wants inline, keeping a copy wants attachment,
    and the chapter route offers both.
    """
    cleaned = "".join(
        ch for ch in filename if ch.isalnum() or ch in " ._-()[]"
    ).strip()
    cleaned = cleaned or "document.pdf"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    # Long names are rejected outright by some filesystems on the way down.
    cleaned = cleaned[-120:]

    kind = "attachment" if download else "inline"
    return {"Content-Disposition": f'{kind}; filename="{cleaned}"'}


def read_bytes(url_or_key: str) -> bytes | None:
    """
    Reads a stored object back, or None when it is not there.

    Accepts a bare key, and also the `/media/…` and full-URL forms that earlier
    versions wrote, so records created before storage went private still
    resolve without a data migration.

    A missing file is a normal outcome, not an error: the callers regenerate
    offer letters and certificates from the database record when the rendered
    PDF has gone. The record is the source of truth; the file is a rendering.
    """
    key = url_or_key
    if key.startswith("/media/"):
        key = key[len("/media/"):]
    elif "://" in key:
        # A full URL from the old public-bucket scheme: keep everything after
        # the host.
        key = key.split("://", 1)[1].split("/", 1)[-1]

    try:
        path = _safe_path(key)
    except StorageError:
        return None

    return path.read_bytes() if path.is_file() else None
