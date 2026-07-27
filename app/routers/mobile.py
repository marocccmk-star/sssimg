"""Mobile app API — the EXACT contract of the sssimg Android client
(read from data/net/BackendApi.kt + data/repo/Repositories.kt):

  Auth header  : Authorization: Token <token>
  Error shape  : non-2xx JSON {"error": "..."}       (app reads `error`)
  Job statuses : queued | running | done | error      (app switch on these)

  POST /api/auth/signup/      {email,password,name}      -> {token, user{...}}
  POST /api/auth/login/       {email,password}           -> {token, user{...}}
  POST /api/auth/social/      {provider,id_token,email,name} -> {token, user{...}}
  GET  /api/auth/me/                                     -> user{...}
  POST /api/auth/profile/     multipart name + avatar    -> user{...}
  GET  /api/feed/                                        -> {items:[FeedItem]}
  POST /api/generate/         multipart prompt,model,media_type[,reference]
                                                         -> GenerationResult
  GET  /api/generate/{id}/                               -> GenerationResult
  GET  /api/uploads/                                     -> {items:[UploadItem]}
  POST /api/uploads/create/   multipart prompt,media_type,media -> UploadItem
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AppUser, FeedPost, GenJob, MediaAsset
from ..security import (AuthError, get_app_user, hash_password, new_token,
                        verify_password)
from ..services import providers, storage

router = APIRouter(prefix="/api", tags=["mobile"])
settings = get_settings()

IMG_TYPES = {"image/jpeg", "image/png", "image/webp"}
VID_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


def err(code: int, message: str) -> JSONResponse:
    """The Android client reads the `error` key — not FastAPI's `detail`."""
    return JSONResponse(status_code=code, content={"error": message})


def user_json(u: AppUser, db: Session) -> dict:
    uploads = db.query(MediaAsset).filter(MediaAsset.user_id == u.id).count()
    gens = db.query(GenJob).filter(GenJob.user_id == u.id).count()
    return {"id": u.id, "email": u.email, "name": u.name,
            "avatar": u.avatar_url or "", "uploads": uploads, "generations": gens}


# --------------------------------------------------------------------------- #
#  Auth
# --------------------------------------------------------------------------- #
@router.post("/auth/signup/")
async def signup(request: Request, db: Session = Depends(get_db)):
    b = await request.json()
    email = (b.get("email") or "").strip().lower()
    password = b.get("password") or ""
    name = (b.get("name") or "").strip()
    if not email or not password:
        return err(400, "email and password are required")
    if db.query(AppUser).filter(AppUser.email == email).first():
        return err(400, "email already registered")
    u = AppUser(email=email, name=name or email.split("@")[0],
                password_hash=hash_password(password), token=new_token())
    db.add(u); db.commit(); db.refresh(u)
    return {"token": u.token, "user": user_json(u, db)}


@router.post("/auth/login/")
async def login(request: Request, db: Session = Depends(get_db)):
    b = await request.json()
    email = (b.get("email") or "").strip().lower()
    u = db.query(AppUser).filter(AppUser.email == email).first()
    if not u or not verify_password(b.get("password") or "", u.password_hash):
        return err(400, "invalid email or password")
    return {"token": u.token, "user": user_json(u, db)}


@router.post("/auth/social/")
async def social(request: Request, db: Session = Depends(get_db)):
    """Google/Facebook sign-in. The app sends the provider id_token; full
    signature verification needs your OAuth client ids — until you provide
    them, we accept the token's email claim as sent by the app (documented
    limitation; do NOT ship to production without real verification)."""
    b = await request.json()
    email = (b.get("email") or "").strip().lower()
    if not email:
        return err(400, "email is required")
    u = db.query(AppUser).filter(AppUser.email == email).first()
    if u is None:
        u = AppUser(email=email, name=(b.get("name") or email.split("@")[0]),
                    password_hash="", token=new_token())
        db.add(u); db.commit(); db.refresh(u)
    return {"token": u.token, "user": user_json(u, db)}


@router.get("/auth/me/")
def me(db: Session = Depends(get_db), user: AppUser = Depends(get_app_user)):
    return user_json(user, db)


@router.post("/auth/profile/")
async def profile(name: str = Form(""), avatar: UploadFile | None = None,
                  db: Session = Depends(get_db),
                  user: AppUser = Depends(get_app_user)):
    if name.strip():
        user.name = name.strip()
    if avatar is not None:
        data = await avatar.read()
        ctype = avatar.content_type or "image/jpeg"
        if ctype not in IMG_TYPES:
            return err(415, "avatar must be JPEG, PNG or WebP")
        _k, url = storage.upload_bytes("uploads", data, ctype)
        user.avatar_url = url
    db.commit(); db.refresh(user)
    return user_json(user, db)


# --------------------------------------------------------------------------- #
#  Feed
# --------------------------------------------------------------------------- #
@router.get("/feed/")
def feed(db: Session = Depends(get_db)):
    rows = db.scalars(select(FeedPost).where(FeedPost.is_active.is_(True))
                      .order_by(FeedPost.sort_order, FeedPost.id.desc())
                      .limit(60)).all()
    return {"items": [{
        "id": p.id, "title": p.title, "prompt": p.prompt,
        "media_url": p.media_url, "thumb_url": p.thumb_url or p.media_url,
        "media_type": p.media_type, "author": p.author,
        "model_name": p.model_name,
    } for p in rows]}


# --------------------------------------------------------------------------- #
#  Generate (prompt → image/video; optional reference for image-to-video)
# --------------------------------------------------------------------------- #
def _job_json(j: GenJob) -> dict:
    return {"job_id": j.id, "status": j.status,
            "result_url": j.result_url or "",
            "media_type": j.media_type, "error": j.error_message or ""}


def _webhook_url() -> str | None:
    if not settings.app_base_url:
        return None
    return f"{settings.app_base_url.rstrip('/')}/api/v1/webhooks/ai"


@router.post("/generate/")
async def generate(prompt: str = Form(...), model: str = Form(...),
                   media_type: str = Form("image"),
                   reference: UploadFile | None = None,
                   db: Session = Depends(get_db),
                   user: AppUser = Depends(get_app_user)):
    route = providers.resolve(model)
    if route is None:
        return err(400, f"unknown model '{model}'")
    provider, route_media, remote = route
    media_type = media_type if media_type in ("image", "video") else route_media

    reference_url = ""
    if reference is not None:
        data = await reference.read()
        ctype = reference.content_type or "image/jpeg"
        if ctype == "application/octet-stream":       # the app sends this
            ctype = "image/jpeg"
        if ctype not in IMG_TYPES:
            return err(415, "reference must be an image")
        _k, reference_url = storage.upload_bytes("uploads", data, ctype)

    job = GenJob(user_id=user.id, prompt=prompt.strip(), model_id=model,
                 provider=provider, media_type=media_type,
                 reference_url=reference_url, status="queued")
    db.add(job); db.commit(); db.refresh(job)

    pid, sync_url, error = providers.submit(
        provider, remote, job.prompt, media_type, reference_url,
        _webhook_url() if provider == "fal" else None)

    if error:
        job.status, job.error_message = "error", error
        job.completed_at = datetime.now(timezone.utc)
    elif sync_url:                                    # provider finished now
        try:
            job.result_url = storage.save_remote_media(sync_url)
            job.status = "done"
        except Exception as exc:
            job.status, job.error_message = "error", f"could not store result: {exc}"
        job.completed_at = datetime.now(timezone.utc)
    else:
        job.provider_job_id, job.status = pid, "running"
    db.commit(); db.refresh(job)
    return _job_json(job)


@router.get("/generate/{job_id}/")
def generate_poll(job_id: int, db: Session = Depends(get_db),
                  user: AppUser = Depends(get_app_user)):
    job = db.get(GenJob, job_id)
    if not job or job.user_id != user.id:
        return err(404, "job not found")
    if job.status == "running" and job.provider_job_id:
        route = providers.resolve(job.model_id) or (job.provider, job.media_type, "")
        st, out_url, e = providers.fetch(route[0], route[2], job.provider_job_id)
        if st == "done":
            try:
                job.result_url = storage.save_remote_media(out_url)
                job.status = "done"
            except Exception as exc:
                job.status, job.error_message = "error", f"could not store result: {exc}"
            job.completed_at = datetime.now(timezone.utc)
        elif st == "error":
            job.status, job.error_message = "error", e
            job.completed_at = datetime.now(timezone.utc)
        db.commit(); db.refresh(job)
    return _job_json(job)


# --------------------------------------------------------------------------- #
#  Uploads (user library: image or video + prompt)
# --------------------------------------------------------------------------- #
def _asset_json(a: MediaAsset) -> dict:
    return {"id": a.id, "media_url": a.media_url,
            "thumb_url": a.thumb_url or a.media_url, "prompt": a.prompt,
            "media_type": a.media_type,
            "created_at": a.created_at.isoformat() if a.created_at else ""}


@router.get("/uploads/")
def uploads_list(db: Session = Depends(get_db),
                 user: AppUser = Depends(get_app_user)):
    rows = db.scalars(select(MediaAsset).where(MediaAsset.user_id == user.id)
                      .order_by(MediaAsset.id.desc()).limit(200)).all()
    return {"items": [_asset_json(a) for a in rows]}


@router.post("/uploads/create/")
async def uploads_create(prompt: str = Form(""), media_type: str = Form("image"),
                         media: UploadFile | None = None,
                         db: Session = Depends(get_db),
                         user: AppUser = Depends(get_app_user)):
    if media is None:
        return err(400, "media file is required")
    data = await media.read()
    ctype = media.content_type or "application/octet-stream"
    if ctype == "application/octet-stream":           # app sends octet-stream
        name = (media.filename or "").lower()
        ctype = ("video/mp4" if media_type == "video" or name.endswith((".mp4", ".mov", ".webm"))
                 else "image/jpeg")
    if media_type == "video" or ctype in VID_TYPES:
        if ctype not in VID_TYPES:
            return err(415, "unsupported video type (mp4/webm/mov)")
        if len(data) > settings.max_video_upload_mb * 1024 * 1024:
            return err(413, f"video too large (max {settings.max_video_upload_mb} MB)")
        media_type = "video"
    else:
        if ctype not in IMG_TYPES:
            return err(415, "unsupported image type (jpeg/png/webp)")
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            return err(413, f"image too large (max {settings.max_upload_mb} MB)")
        media_type = "image"

    _k, url = storage.upload_bytes("uploads", data, ctype)
    a = MediaAsset(user_id=user.id, media_type=media_type, media_url=url,
                   thumb_url=url if media_type == "image" else "",
                   prompt=prompt.strip())
    db.add(a); db.commit(); db.refresh(a)
    return _asset_json(a)
