"""FastAPI entrypoint.

Run locally:   uvicorn app.main:app --reload
Production:    uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .config import get_settings
from .routers import catalog, generations, mobile, social, uploads
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


# Hard body-size ceiling: reject before anything reads the stream into memory.
# Covers video uploads (max_video_upload_mb) plus a small overhead for fields.
MAX_REQUEST_BYTES = (settings.max_video_upload_mb + 5) * 1024 * 1024


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_REQUEST_BYTES:
                return JSONResponse(status_code=413,
                                    content={"error": "request body too large"})
        except ValueError:
            pass
    return await call_next(request)


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


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError):
    # Android reads {"error": ...}; translate FastAPI's default {"detail":[...]}.
    try:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = f"{loc}: {first.get('msg')}" if loc else first.get("msg", "invalid request")
    except Exception:
        msg = "invalid request"
    return JSONResponse(status_code=422, content={"error": msg})


from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
def http_error(request: Request, exc: StarletteHTTPException):
    # Normalize any raise HTTPException(detail=...) to the app's {"error":...} shape.
    detail = exc.detail if isinstance(exc.detail, str) else "error"
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


app.include_router(mobile.router)
app.include_router(social.router)
app.include_router(catalog.router)
app.include_router(uploads.router)
app.include_router(generations.router)
