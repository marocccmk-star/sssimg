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
    app_base_url: str = ""        # public https URL of this backend (webhooks)
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

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
