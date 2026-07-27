"""Generation jobs: create → AI provider (async) → webhook or poll → R2 → done.

Android → POST /generations → {id, status: processing}
        → GET  /generations/{id}   (poll until completed/failed)
        → completed ⇒ output_image_url is a permanent R2 URL.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import Pagination, get_current_user
<<<<<<< HEAD
from ..models import GenerationJob, GenerationStatus, GenJob, Template
=======
from ..models import GenerationJob, GenerationStatus, Template
>>>>>>> origin/main
from ..schemas import GenerationCreate, GenerationOut, Page
from ..services import ai_provider, storage

router = APIRouter(prefix="/api/v1", tags=["generations"])
settings = get_settings()


def _webhook_url() -> str | None:
    if not settings.app_base_url:
        return None
    return f"{settings.app_base_url.rstrip('/')}/api/v1/webhooks/ai"


@router.post("/generations", response_model=GenerationOut, status_code=201)
def create_generation(body: GenerationCreate, db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    template = db.get(Template, body.template_id)
    if not template or not template.is_active:
        raise HTTPException(404, "Template not found")
    # Only accept inputs that live in OUR bucket (uploaded via /uploads).
    if settings.r2_public_base_url and \
            not body.input_image_url.startswith(settings.r2_public_base_url):
        raise HTTPException(400, "input_image_url must come from /api/v1/uploads")

    job = GenerationJob(user_id=user.id, template_id=template.id,
                        input_image_url=body.input_image_url,
                        status=GenerationStatus.pending)
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        pid = ai_provider.submit(job.input_image_url,
                                 template.original_image_url,
                                 template.ai_prompt,
                                 _webhook_url())
        job.provider_job_id = pid
        job.status = GenerationStatus.processing
    except ai_provider.AIProviderError as exc:
        job.status = GenerationStatus.failed
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def _finalize(db: Session, job: GenerationJob, provider_image_url: str | None,
              error: str | None):
    if provider_image_url:
        try:
            job.output_image_url = storage.save_remote_image(provider_image_url)
            job.status = GenerationStatus.completed
        except Exception as exc:  # R2 save failed
            job.status = GenerationStatus.failed
            job.error_message = f"could not store result: {exc}"
    else:
        job.status = GenerationStatus.failed
        job.error_message = error or "generation failed"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/generations/{generation_id}", response_model=GenerationOut)
def get_generation(generation_id: int, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    job = db.get(GenerationJob, generation_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Generation not found")

    # Poll fallback: if the webhook hasn't arrived yet, ask the provider.
    if job.status == GenerationStatus.processing and job.provider_job_id:
        st, out_url, err = ai_provider.fetch_result(job.provider_job_id)
        if st == "completed":
            _finalize(db, job, out_url, None)
        elif st == "failed":
            _finalize(db, job, None, err)
        db.refresh(job)
    return job


@router.get("/generations", response_model=Page[GenerationOut])
def list_generations(db: Session = Depends(get_db), pg: Pagination = Depends(),
                     user=Depends(get_current_user)):
    base = select(GenerationJob).where(GenerationJob.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(GenerationJob.created_at.desc())
                      .offset(pg.offset).limit(pg.page_size)).all()
    return Page(items=rows, page=pg.page, page_size=pg.page_size, total=total,
                has_more=pg.offset + len(rows) < total)


@router.post("/webhooks/ai")
async def ai_webhook(request: Request, db: Session = Depends(get_db)):
    """fal.ai calls this when a job finishes. Body carries request_id + payload."""
    body = await request.json()
    request_id = body.get("request_id") or body.get("requestId")
    if not request_id:
        raise HTTPException(400, "missing request_id")

    job = db.scalar(select(GenerationJob)
                    .where(GenerationJob.provider_job_id == str(request_id)))
    if not job:
<<<<<<< HEAD
        # maybe it's a mobile (multi-model) job
        mjob = db.scalar(select(GenJob)
                         .where(GenJob.provider_job_id == str(request_id)))
        if mjob and mjob.status == "running":
            status = (body.get("status") or "").upper()
            payload = body.get("payload") or body.get("response") or {}
            if status in ("OK", "COMPLETED"):
                out = ai_provider.extract_image_url(payload)
                try:
                    mjob.result_url = storage.save_remote_media(out)
                    mjob.status = "done"
                except Exception as exc:
                    mjob.status, mjob.error_message = "error", f"could not store result: {exc}"
            else:
                mjob.status = "error"
                mjob.error_message = str(body.get("error") or f"provider status {status}")[:500]
            mjob.completed_at = datetime.now(timezone.utc)
            db.commit()
=======
>>>>>>> origin/main
        return {"ok": True}                     # unknown job → ack, don't retry
    if job.status in (GenerationStatus.completed, GenerationStatus.failed):
        return {"ok": True}                     # idempotent

    status = (body.get("status") or "").upper()
    payload = body.get("payload") or body.get("response") or {}
    if status == "OK" or status == "COMPLETED":
        _finalize(db, job, ai_provider.extract_image_url(payload), None)
    else:
        err = body.get("error") or payload.get("detail") or f"provider status {status}"
        _finalize(db, job, None, str(err)[:500])
    return {"ok": True}
