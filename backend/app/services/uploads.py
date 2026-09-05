"""Shared helpers for saving user-uploaded images (avatars, pet photos) to
disk under the app's data directory. Kept deliberately simple — no image
resizing/re-encoding library (Pillow) pulled in just for this — the browser
already downscales what it displays, and self-hosters are expected to be
uploading normal phone photos, not arbitrary huge files (which the size
cap below rejects)."""
import os
import uuid

from fastapi import HTTPException, UploadFile

from ..db import DATA_DIR

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
EXT_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}

UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")


async def save_image(upload: UploadFile, subdir: str) -> tuple[str, str]:
    """Validates and saves an uploaded image under uploads/<subdir>/.
    Returns (relative_path, mime_type)."""
    mime_type = upload.content_type or ""
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="unsupported_image_type")

    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="image_too_large")
    if not data:
        raise HTTPException(status_code=400, detail="empty_file")

    target_dir = os.path.join(UPLOADS_DIR, subdir)
    os.makedirs(target_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{EXT_BY_MIME[mime_type]}"
    relative_path = os.path.join(subdir, filename)
    with open(os.path.join(UPLOADS_DIR, relative_path), "wb") as f:
        f.write(data)
    return relative_path, mime_type


def delete_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = os.path.join(UPLOADS_DIR, relative_path)
    try:
        os.remove(full_path)
    except OSError:
        pass  # already gone — fine, this is best-effort cleanup


def full_path(relative_path: str) -> str:
    return os.path.join(UPLOADS_DIR, relative_path)
