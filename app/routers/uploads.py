"""User photo upload → validated → straight to R2 uploads/ (never kept on disk)."""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from ..config import get_settings
from ..deps import get_current_user
from ..services import storage

router = APIRouter(prefix="/api/v1", tags=["uploads"])
settings = get_settings()

ALLOWED = {"image/jpeg", "image/png", "image/webp"}


@router.post("/uploads", status_code=201)
async def upload_photo(request: Request, file: UploadFile,
                       user=Depends(get_current_user)):
    if file.content_type not in ALLOWED:
        raise HTTPException(415, "Unsupported image type. Use JPEG, PNG or WebP.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(413, f"Image too large (max {settings.max_upload_mb} MB).")
    if len(data) < 100:
        raise HTTPException(400, "Empty or corrupt file.")

    key, url = storage.upload_bytes("uploads", data, file.content_type)
    return {"key": key, "url": url,
            "content_type": file.content_type, "size_bytes": len(data)}
