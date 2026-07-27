"""Cloudflare R2 storage service (S3-compatible via boto3).

Folder layout: templates/  uploads/  generated/
Nothing is ever stored permanently on the Render disk — bytes go straight
from memory to R2.
"""
import uuid

import boto3
import httpx

from ..config import get_settings

settings = get_settings()

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
        "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def public_url(key: str) -> str:
    return f"{settings.r2_public_base_url.rstrip('/')}/{key}"


def upload_bytes(folder: str, data: bytes, content_type: str) -> tuple[str, str]:
    """Store bytes under folder/ with a random name. Returns (key, public_url)."""
    ext = _EXT.get(content_type, "bin")
    key = f"{folder}/{uuid.uuid4().hex}.{ext}"
    _client().put_object(Bucket=settings.r2_bucket, Key=key, Body=data,
                         ContentType=content_type)
    return key, public_url(key)


def save_remote_media(url: str, folder: str = "generated") -> str:
    """Download an image the AI produced and persist it to R2. Returns public URL."""
    with httpx.Client(timeout=60) as cx:
        r = cx.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "image/png").split(";")[0]
        _key, purl = upload_bytes(folder, r.content, ctype)
        return purl


# backwards-compat alias (v1 routes)
save_remote_image = save_remote_media
