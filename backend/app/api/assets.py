"""Image uploads for tokens and map backgrounds.

Stored on local disk for now; swap for S3/R2 in production.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_BYTES = 15 * 1024 * 1024
ALLOWED = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}

router = APIRouter(prefix="/api", tags=["assets"])


@router.post("/assets")
async def upload_asset(file: UploadFile) -> dict[str, str | int]:
    ext = ALLOWED.get(file.content_type or "")
    if ext is None:
        raise HTTPException(415, "Unsupported format: use PNG, JPG, WEBP, GIF or SVG")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 15 MB)")
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return {"url": f"/uploads/{name}", "size": len(data)}
