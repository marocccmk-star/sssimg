"""FastAPI entrypoint.

Run locally:   uvicorn app.main:app --reload
Production:    uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .config import get_settings
from .services import storage
from .routers import catalog, edit, generations, mobile, social, uploads
from .security import AuthError

settings = get_settings()

app = FastAPI(title="AI Photo Backend", version="1.0.0",
              docs_url="/docs", redoc_url=None)

# --- CORS (mobile apps don't need it, but web/test clients do) ---
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate limiting (per client IP). Heavier endpoints get stricter limits. ---
limiter = Limiter(key_func=get_remote_address,
                  default_limits=["120/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429,
                        content={"detail": "Too many requests, slow down."})


# --- Secure error handling: never leak internals in 500s ---
@app.exception_handler(Exception)
def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500,
                        content={"detail": "Internal server error"})


@app.exception_handler(AuthError)
def auth_error(request: Request, exc: AuthError):
    return JSONResponse(status_code=401, content={"error": str(exc)})


# Serve locally-stored media at /media/* when R2 isn't configured, so the API
# is usable immediately. (Render's disk is ephemeral — use R2 for anything
# that must survive a restart.)
if not storage.use_r2():
    app.mount("/media", StaticFiles(directory=str(storage.media_root())),
              name="media")

app.include_router(edit.router)
app.include_router(mobile.router)
app.include_router(social.router)
app.include_router(catalog.router)
app.include_router(uploads.router)
app.include_router(generations.router)
