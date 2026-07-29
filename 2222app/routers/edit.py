"""Image editing endpoints: enhance + background removal.

Conventions match the rest of the mobile API: Token auth, snake_case JSON,
`{"error": "..."}` on failure. Every endpoint accepts a multipart file and
returns the saved result:

    {"url": "...", "width": 1024, "height": 1024, "media_type": "image"}

  POST /api/edit/enhance/          file image [+ auto, brightness, contrast,
                                     color, sharpness, denoise, upscale]
  POST /api/edit/removebg/         file image                    (automatic)
  POST /api/edit/removebg/mask/    file image + file mask        (brush/mouse)
  POST /api/edit/removebg/smart/   file image [+ file hints | rect]  (GrabCut)
  POST /api/edit/replacebg/        file image [+ color | file background]
  GET  /api/edit/capabilities/     which modes this server can actually do
"""
from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..security import get_app_user
from ..services import imaging, storage

router = APIRouter(prefix="/api/edit", tags=["edit"])
settings = get_settings()

IMG_TYPES = {"image/jpeg", "image/png", "image/webp", "application/octet-stream"}


def err(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": message})


async def _read(file: UploadFile | None, label: str) -> bytes:
    if file is None:
        return b""
    ctype = (file.content_type or "application/octet-stream").split(";")[0]
    if ctype not in IMG_TYPES:
        raise ValueError(f"{label} must be a JPEG, PNG or WebP image")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"{label} is too large (max {settings.max_upload_mb} MB)")
    if not data:
        raise ValueError(f"{label} is empty")
    return data


def _save(data: bytes, content_type: str) -> dict:
    _key, url = storage.upload_bytes("edits", data, content_type)
    img = imaging.load(data)
    return {"url": url, "width": img.width, "height": img.height,
            "media_type": "image"}


@router.get("/capabilities/")
def capabilities():
    """Lets the app hide buttons the server can't serve (rembg/OpenCV missing)."""
    auto = settings.enable_rembg
    if auto:
        try:
            import rembg  # noqa: F401
        except ImportError:
            auto = False
    try:
        import cv2  # noqa: F401
        smart = True
    except ImportError:
        smart = False
    return {"enhance": True, "removebg_auto": auto, "removebg_mask": True,
            "removebg_smart": smart, "replacebg": True,
            "model": settings.rembg_model if auto else ""}


@router.post("/enhance/")
async def enhance(
    image: UploadFile | None = None,
    auto: bool = Form(True),
    brightness: float = Form(1.0),
    contrast: float = Form(1.0),
    color: float = Form(1.0),
    sharpness: float = Form(1.0),
    denoise: bool = Form(False),
    upscale: float = Form(1.0),
    user=Depends(get_app_user),
):
    try:
        data = await _read(image, "image")
        if not data:
            return err(400, "image file is required")
        out, ctype = imaging.enhance(
            data, auto=auto, brightness=brightness, contrast=contrast,
            color=color, sharpness=sharpness, denoise=denoise, upscale=upscale)
    except ValueError as exc:
        return err(400, str(exc))
    except imaging.ImagingError as exc:
        return err(400, str(exc))
    return _save(out, ctype)


@router.post("/removebg/")
async def removebg(image: UploadFile | None = None, user=Depends(get_app_user)):
    """Automatic one-tap cutout (rembg)."""
    try:
        data = await _read(image, "image")
        if not data:
            return err(400, "image file is required")
        out = imaging.remove_background(data)
    except ValueError as exc:
        return err(400, str(exc))
    except imaging.ImagingError as exc:
        return err(503, str(exc))
    return _save(out, "image/png")


@router.post("/removebg/mask/")
async def removebg_mask(
    image: UploadFile | None = None,
    mask: UploadFile | None = None,
    invert: bool = Form(False),
    feather: int = Form(2),
    user=Depends(get_app_user),
):
    """Apply a brush mask the user painted (white = keep, black = remove)."""
    try:
        data = await _read(image, "image")
        mdata = await _read(mask, "mask")
        if not data:
            return err(400, "image file is required")
        if not mdata:
            return err(400, "mask file is required")
        out = imaging.apply_mask(data, mdata, invert=invert, feather=feather)
    except ValueError as exc:
        return err(400, str(exc))
    except imaging.ImagingError as exc:
        return err(400, str(exc))
    return _save(out, "image/png")


@router.post("/removebg/smart/")
async def removebg_smart(
    image: UploadFile | None = None,
    hints: UploadFile | None = None,
    x: int = Form(0), y: int = Form(0),
    width: int = Form(0), height: int = Form(0),
    iterations: int = Form(5),
    user=Depends(get_app_user),
):
    """GrabCut from green (keep) / red (remove) strokes, or a dragged box."""
    try:
        data = await _read(image, "image")
        hdata = await _read(hints, "hints")
        if not data:
            return err(400, "image file is required")
        rect = (x, y, width, height) if width > 0 and height > 0 else None
        out = imaging.grabcut(data, hint_data=hdata or None, rect=rect,
                              iterations=max(1, min(int(iterations), 10)))
    except ValueError as exc:
        return err(400, str(exc))
    except imaging.ImagingError as exc:
        return err(503, str(exc))
    return _save(out, "image/png")


@router.post("/replacebg/")
async def replacebg(
    image: UploadFile | None = None,
    background: UploadFile | None = None,
    color: str = Form(""),
    user=Depends(get_app_user),
):
    """Composite a transparent cutout onto a colour or another photo."""
    try:
        data = await _read(image, "image")
        bdata = await _read(background, "background")
        if not data:
            return err(400, "image file is required")
        out = imaging.replace_background(data, color=color or None,
                                         bg_data=bdata or None)
    except ValueError as exc:
        return err(400, str(exc))
    except imaging.ImagingError as exc:
        return err(400, str(exc))
    return _save(out, "image/jpeg")
