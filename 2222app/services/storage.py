"""Storage service: Cloudflare R2 (S3-compatible) with a local-disk fallback.

Folder layout: templates/  uploads/  generated/  edits/

Backend selection (settings.storage_backend):
  auto  -> R2 when its credentials are configured, otherwise local disk
  r2    -> always R2
  local -> always local disk (served by FastAPI at /media/*)

The local mode exists so the API works out of the box on Render before R2 is
wired up. Render's disk is ephemeral, so local mode is for development/demo —
switch to R2 for anything you need to keep.
"""
import uuid
from pathlib import Path

import httpx

from ..config import get_settings

settings = get_settings()

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
        "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}


def r2_configured() -> bool:
    return bool(settings.r2_account_id and settings.r2_access_key_id
                and settings.r2_secret_access_key and settings.r2_bucket)


def use_r2() -> bool:
    mode = (settings.storage_backend or "auto").lower()
    if mode == "r2":
        return True
    if mode == "local":
        return False
    return r2_configured()


def media_root() -> Path:
    d = Path(settings.local_media_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _client():
    import boto3  # imported lazily so local mode doesn't need credentials
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def public_url(key: str) -> str:
    """Absolute URL for a stored object, for whichever backend is active."""
    if use_r2():
        base = settings.r2_public_base_url or ""
        return f"{base.rstrip('/')}/{key}"
    base = (settings.app_base_url or "").rstrip("/")
    return f"{base}/media/{key}"


def upload_bytes(folder: str, data: bytes, content_type: str) -> tuple[str, str]:
    """Store bytes under folder/ with a random name. Returns (key, public_url)."""
    ext = _EXT.get(content_type, "bin")
    key = f"{folder}/{uuid.uuid4().hex}.{ext}"
    if use_r2():
        _client().put_object(Bucket=settings.r2_bucket, Key=key, Body=data,
                             ContentType=content_type)
    else:
        path = media_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return key, public_url(key)


def save_remote_media(url: str, folder: str = "generated") -> str:
    """Download media a provider produced and persist it. Returns public URL."""
    with httpx.Client(timeout=120, follow_redirects=True) as cx:
        r = cx.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "image/png").split(";")[0].strip()
        _key, purl = upload_bytes(folder, r.content, ctype)
        return purl


# backwards-compat alias (v1 routes)
save_remote_image = save_remote_media
