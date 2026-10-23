"""Image uploads for tokens, maps, cards and the art library.

Raster images are decoded and saved again as WebP: the real format is checked (a file
that only claims to be an image is refused), hidden data and metadata such as the GPS
position are dropped, oversized pictures are scaled down, and a small thumbnail is made
for the art library. Animated GIFs and SVGs are kept as they are.

Stored on local disk for now; swap for S3/R2 in production.
"""

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_BYTES = 15 * 1024 * 1024
# Longest side kept: larger maps are scaled down (and load faster).
MAX_SIDE = 8192
THUMB_SIDE = 256
WEBP_QUALITY = 88
ALLOWED = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}
# What Pillow must find inside, per declared type.
RASTER_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
}

router = APIRouter(prefix="/api", tags=["assets"])


def _save(data: bytes, ext: str) -> str:
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return f"/uploads/{name}"


def _webp(image: Image.Image, side: int) -> bytes:
    image = image.copy()
    image.thumbnail((side, side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "WEBP", quality=WEBP_QUALITY, method=4)
    return out.getvalue()


@router.post("/assets")
async def upload_asset(file: UploadFile) -> dict[str, str | int | None]:
    content_type = file.content_type or ""
    ext = ALLOWED.get(content_type)
    if ext is None:
        raise HTTPException(415, "Unsupported format: use PNG, JPG, WEBP, GIF or SVG")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 15 MB)")
    if content_type == "image/svg+xml":
        return {"url": _save(data, ext), "thumb": None, "width": 0, "height": 0, "size": len(data)}

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise HTTPException(415, "Not a valid image") from e
    if image.format != RASTER_FORMATS[content_type]:
        raise HTTPException(415, f"The file is not really {ext[1:].upper()}")
    if getattr(image, "is_animated", False):
        # Re-encoding would lose the animation.
        width, height = image.size
        return {
            "url": _save(data, ext),
            "thumb": None,
            "width": width,
            "height": height,
            "size": len(data),
        }

    # Phone photos are stored sideways with a rotation tag: apply it.
    image = ImageOps.exif_transpose(image)
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")
    full = _webp(image, MAX_SIDE)
    width, height = image.size
    if max(width, height) > MAX_SIDE:
        scale = MAX_SIDE / max(width, height)
        width, height = round(width * scale), round(height * scale)
    return {
        "url": _save(full, ".webp"),
        "thumb": _save(_webp(image, THUMB_SIDE), ".webp"),
        "width": width,
        "height": height,
        "size": len(full),
    }
