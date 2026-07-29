"""Diagnostics: one call that tells you exactly why something is failing.

    GET /api/diag/

Checks the four things that actually break a fresh deploy:
  1. database  — can we connect, and do the tables exist?
  2. storage   — which backend is active, and can we really write a file?
  3. imaging   — are Pillow / OpenCV / rembg importable?
  4. providers — which AI keys are configured?

No secrets are ever returned — only booleans and lengths. Safe to leave on,
but you can delete this router once everything is green.
"""
from fastapi import APIRouter
from sqlalchemy import inspect, text

from ..config import get_settings
from ..database import Base, engine
from ..services import storage

router = APIRouter(prefix="/api/diag", tags=["diag"])
settings = get_settings()

# tables the mobile app needs before it can do anything
_REQUIRED = ["app_users", "user_posts", "post_likes", "post_saves",
             "post_comments", "gen_jobs", "media_assets", "feed_posts"]


@router.get("/")
def diagnose():
    report: dict = {"ok": True, "problems": []}

    # ---------------------------------------------------------------- database
    db_info: dict = {"url_scheme": settings.database_url.split("://")[0]}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_info["connect"] = True
        existing = set(inspect(engine).get_table_names())
        db_info["tables_found"] = len(existing)
        missing = [t for t in _REQUIRED if t not in existing]
        db_info["missing_tables"] = missing
        if missing:
            report["ok"] = False
            report["problems"].append(
                f"missing tables: {', '.join(missing)} — run `alembic upgrade head` "
                f"or restart (startup now auto-creates them)")
    except Exception as exc:
        db_info["connect"] = False
        db_info["error"] = str(exc)[:300]
        report["ok"] = False
        report["problems"].append("cannot connect to the database — check DATABASE_URL")
    report["database"] = db_info

    # ----------------------------------------------------------------- storage
    st: dict = {
        "backend": "r2" if storage.use_r2() else "local",
        "r2_configured": storage.r2_configured(),
        "public_base": (settings.r2_public_base_url if storage.use_r2()
                        else f"{settings.app_base_url.rstrip('/')}/media"),
    }
    try:  # a real end-to-end write, because this is what uploads actually do
        key, url = storage.upload_bytes("diag", b"ok", "image/png")
        st["write_test"] = True
        st["sample_url"] = url
        st["key"] = key
    except Exception as exc:
        st["write_test"] = False
        st["error"] = str(exc)[:300]
        report["ok"] = False
        report["problems"].append(
            "storage write failed — if backend is r2 check the R2 keys/bucket; "
            "if local check the dyno's disk is writable")
    if storage.use_r2() and not settings.r2_public_base_url:
        report["problems"].append(
            "R2 is active but R2_PUBLIC_BASE_URL is empty — saved files will "
            "have unusable URLs")
        report["ok"] = False
    report["storage"] = st

    # ----------------------------------------------------------------- imaging
    img: dict = {}
    for name, mod in (("pillow", "PIL"), ("opencv", "cv2"), ("rembg", "rembg"),
                      ("onnxruntime", "onnxruntime"), ("numpy", "numpy")):
        try:
            __import__(mod)
            img[name] = True
        except Exception:
            img[name] = False
    img["enable_rembg"] = settings.enable_rembg
    img["rembg_model"] = settings.rembg_model
    if not img["pillow"]:
        report["ok"] = False
        report["problems"].append("Pillow is missing — enhancement cannot work")
    report["imaging"] = img

    # --------------------------------------------------------------- providers
    prov = {
        "fal": bool(settings.fal_api_key),
        "google": bool(settings.google_api_key),
        "xai": bool(settings.xai_api_key),
        "luma": bool(settings.luma_api_key),
        "default_fal_model": bool(settings.fal_model),
    }
    if not any([prov["fal"], prov["google"], prov["xai"], prov["luma"]]):
        report["problems"].append(
            "no AI provider keys set — /api/generate/ will always return an "
            "error (set FAL_API_KEY, GOOGLE_API_KEY, XAI_API_KEY or LUMA_API_KEY)")
    report["providers"] = prov

    # ------------------------------------------------------------------- misc
    report["app_base_url"] = settings.app_base_url
    report["allow_anon_test"] = settings.allow_anon_test
    report["max_upload_mb"] = settings.max_upload_mb
    report["max_video_upload_mb"] = settings.max_video_upload_mb
    return report
