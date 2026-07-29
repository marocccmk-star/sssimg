"""App configuration. Everything secret comes from environment variables —
nothing is hardcoded (R2 keys, AI keys, DB credentials, model names)."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # database
    database_url: str = "sqlite:///./dev.db"  # Render injects DATABASE_URL

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_public_base_url: str = ""  # e.g. https://images.example.com (no slash)

    # AI provider
    ai_provider: str = "fal"
    fal_api_key: str = ""
    fal_model: str = ""

    # app
    # Public HTTPS URL of THIS backend (used for webhooks and for building
    # media URLs when local storage is active).
    app_base_url: str = "https://editimg.onrender.com"
    cors_origins: str = "*"
    max_upload_mb: int = 15

    # provider keys (all optional; a model whose provider key is missing
    # returns a clean error instead of crashing)
    google_api_key: str = ""
    xai_api_key: str = ""
    luma_api_key: str = ""
    # JSON override for model routing, e.g. {"wan-2.7": {"provider":"fal","remote":"fal-ai/..."}}
    model_routes: str = ""
    max_video_upload_mb: int = 120
    allow_anon_test: bool = False

    # storage: "auto" uses R2 when its keys are set, else local disk
    storage_backend: str = "auto"          # auto | r2 | local
    local_media_dir: str = "media"         # served at /media/*

    # imaging
    enable_rembg: bool = True
    # u2netp (~5 MB) fits small dynos; u2net (~176 MB) is sharper but heavy
    rembg_model: str = "u2netp"
    max_edit_pixels: int = 4_000_000       # downscale bigger inputs first

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
