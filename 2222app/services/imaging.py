"""Image enhancement and background removal.

Enhancement uses Pillow only (always available, tiny memory footprint).
Background removal has three modes so the client can pick the right trade-off:

  auto      -> rembg (ONNX U^2-Net). One tap, no user work. Heaviest.
  mask      -> the app sends a brush mask the user painted; we just apply it.
                Zero ML, instant, fully predictable — this is the "mouse" mode.
  scribble  -> the user marks a few keep/remove strokes and OpenCV GrabCut
                works out the rest. Interactive and much lighter than rembg.

Every heavy import is lazy, so the service starts fine (and the other routes
keep working) even if rembg/OpenCV aren't installed.
"""
import io

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from ..config import get_settings

settings = get_settings()

_rembg_session = None


class ImagingError(Exception):
    """Raised with a user-safe message; routers turn it into {"error": ...}."""


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def load(data: bytes) -> Image.Image:
    """Decode bytes to a PIL image, honouring EXIF rotation and capping size."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ImagingError("could not read the image file")

    img = ImageOps.exif_transpose(img)          # fix phone-camera rotation

    # Cap the working resolution so a huge upload can't exhaust memory.
    max_px = settings.max_edit_pixels
    if img.width * img.height > max_px:
        scale = (max_px / (img.width * img.height)) ** 0.5
        img = img.resize((max(1, int(img.width * scale)),
                          max(1, int(img.height * scale))), Image.LANCZOS)
    return img


def to_png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def to_jpeg(img: Image.Image, quality: int = 90) -> bytes:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True,
             progressive=True)
    return out.getvalue()


# --------------------------------------------------------------------------- #
#  enhancement
# --------------------------------------------------------------------------- #
def enhance(
    data: bytes,
    auto: bool = True,
    brightness: float = 1.0,
    contrast: float = 1.0,
    color: float = 1.0,
    sharpness: float = 1.0,
    denoise: bool = False,
    upscale: float = 1.0,
) -> tuple[bytes, str]:
    """Return (bytes, content_type) for an enhanced image.

    `auto` applies autocontrast + a mild sharpen/saturation lift, which is what
    a one-tap "Enhance" button should do. The numeric factors are multipliers
    where 1.0 = unchanged, so the app can also expose sliders.
    """
    img = load(data)
    had_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if had_alpha else "RGB")

    if denoise:
        img = img.filter(ImageFilter.MedianFilter(size=3))

    if auto:
        # autocontrast only understands RGB, so split alpha off and back.
        if had_alpha:
            rgb, alpha = img.convert("RGB"), img.getchannel("A")
            rgb = ImageOps.autocontrast(rgb, cutoff=1)
            img = rgb.convert("RGBA")
            img.putalpha(alpha)
        else:
            img = ImageOps.autocontrast(img, cutoff=1)
        img = ImageEnhance.Color(img).enhance(1.12)
        img = ImageEnhance.Sharpness(img).enhance(1.35)

    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(_clamp(brightness))
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(_clamp(contrast))
    if color != 1.0:
        img = ImageEnhance.Color(img).enhance(_clamp(color))
    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(_clamp(sharpness))

    if upscale and upscale > 1.0:
        factor = min(float(upscale), 4.0)
        target = (int(img.width * factor), int(img.height * factor))
        if target[0] * target[1] <= settings.max_edit_pixels * 4:
            img = img.resize(target, Image.LANCZOS)
            # a light unsharp mask hides the softness introduced by upscaling
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=60,
                                                     threshold=3))

    if had_alpha:
        return to_png(img), "image/png"
    return to_jpeg(img, quality=92), "image/jpeg"


def _clamp(v: float, lo: float = 0.0, hi: float = 3.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 1.0


# --------------------------------------------------------------------------- #
#  background removal — automatic (rembg)
# --------------------------------------------------------------------------- #
def _session():
    """Lazily build (and cache) the rembg session. First call downloads the
    ONNX model, so it is slow once and fast afterwards."""
    global _rembg_session
    if _rembg_session is not None:
        return _rembg_session
    if not settings.enable_rembg:
        raise ImagingError("automatic background removal is disabled on this server")
    try:
        from rembg import new_session
    except ImportError:
        raise ImagingError(
            "automatic background removal is unavailable on this server; "
            "use the brush or scribble mode instead")
    try:
        _rembg_session = new_session(settings.rembg_model)
    except Exception as exc:
        raise ImagingError(f"could not load the segmentation model: {exc}")
    return _rembg_session


def remove_background(data: bytes) -> bytes:
    """One-tap cutout. Returns PNG bytes with a transparent background."""
    try:
        from rembg import remove  # lazy: keeps startup light
    except ImportError:
        raise ImagingError(
            "automatic background removal is unavailable on this server; "
            "use the brush or smart-selection mode instead")

    img = load(data).convert("RGBA")
    try:
        cut = remove(img, session=_session())
    except ImagingError:
        raise
    except Exception as exc:
        raise ImagingError(f"background removal failed: {exc}")
    if not isinstance(cut, Image.Image):
        cut = Image.open(io.BytesIO(cut))
    return to_png(cut.convert("RGBA"))


# --------------------------------------------------------------------------- #
#  background removal — brush mask (the "mouse" mode)
# --------------------------------------------------------------------------- #
def apply_mask(data: bytes, mask_data: bytes, invert: bool = False,
               feather: int = 2) -> bytes:
    """Cut out using a mask the user painted in the app.

    The mask is any image the same aspect as the photo: white (or opaque) means
    KEEP, black means REMOVE. It's resized to the photo automatically, so the
    app can paint at canvas resolution without matching pixels exactly.
    `feather` blurs the mask edge so the cutout doesn't look like scissors.
    """
    img = load(data).convert("RGBA")
    try:
        mask = Image.open(io.BytesIO(mask_data))
        mask.load()
    except Exception:
        raise ImagingError("could not read the mask image")

    # Prefer the alpha channel when the app sends a transparent brush layer.
    mask = mask.getchannel("A") if mask.mode in ("RGBA", "LA") else mask.convert("L")

    if mask.size != img.size:
        mask = mask.resize(img.size, Image.LANCZOS)
    if invert:
        mask = ImageOps.invert(mask)
    if feather and feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=min(int(feather), 20)))

    # Multiply into any existing alpha so repeated edits compose correctly.
    base_alpha = img.getchannel("A")
    combined = Image.new("L", img.size)
    combined.putdata([int(a * m / 255) for a, m in
                      zip(base_alpha.getdata(), mask.getdata())])
    img.putalpha(combined)
    return to_png(img)


# --------------------------------------------------------------------------- #
#  background removal — scribble / GrabCut (smart mouse mode)
# --------------------------------------------------------------------------- #
def grabcut(data: bytes, hint_data: bytes | None = None,
            rect: tuple[int, int, int, int] | None = None,
            iterations: int = 5) -> bytes:
    """Interactive cutout from a few user strokes.

    `hint_data` is a transparent PNG the app draws on: GREEN strokes mark
    subject ("keep"), RED strokes mark background ("remove"). Alternatively
    pass `rect` (x, y, w, h) to cut out whatever is inside a dragged box.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise ImagingError(
            "smart selection is unavailable on this server; "
            "use the brush mode instead")

    img = load(data).convert("RGB")
    arr = np.array(img)[:, :, ::-1].copy()          # PIL RGB -> OpenCV BGR
    h, w = arr.shape[:2]

    mask = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)
    have_hint = False

    if hint_data:
        try:
            hint = Image.open(io.BytesIO(hint_data)).convert("RGBA")
            hint.load()
        except Exception:
            raise ImagingError("could not read the selection strokes")
        if hint.size != (w, h):
            hint = hint.resize((w, h), Image.NEAREST)
        hb = np.array(hint)
        r, g, b, a = hb[..., 0], hb[..., 1], hb[..., 2], hb[..., 3]
        drawn = a > 40
        keep = drawn & (g > 110) & (g > r.astype(int) + 40) & (g > b.astype(int) + 40)
        drop = drawn & (r > 110) & (r > g.astype(int) + 40) & (r > b.astype(int) + 40)
        if keep.any():
            mask[keep] = cv2.GC_FGD
            have_hint = True
        if drop.any():
            mask[drop] = cv2.GC_BGD
            have_hint = True

    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        if have_hint:
            cv2.grabCut(arr, mask, None, bgd, fgd, int(iterations),
                        cv2.GC_INIT_WITH_MASK)
        else:
            if rect:
                x, y, rw, rh = (int(v) for v in rect)
                x, y = max(0, x), max(0, y)
                rw, rh = min(rw, w - x), min(rh, h - y)
            else:  # sensible default: everything but a 5% border
                mx, my = int(w * 0.05), int(h * 0.05)
                x, y, rw, rh = mx, my, w - 2 * mx, h - 2 * my
            if rw < 8 or rh < 8:
                raise ImagingError("selection area is too small")
            cv2.grabCut(arr, mask, (x, y, rw, rh), bgd, fgd, int(iterations),
                        cv2.GC_INIT_WITH_RECT)
    except ImagingError:
        raise
    except Exception as exc:
        raise ImagingError(f"smart selection failed: {exc}")

    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
    alpha = Image.fromarray(fg, mode="L").filter(
        ImageFilter.GaussianBlur(radius=1.2))          # soften the edge
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return to_png(out)


# --------------------------------------------------------------------------- #
#  background replacement
# --------------------------------------------------------------------------- #
def replace_background(cutout_png: bytes, color: str | None = None,
                       bg_data: bytes | None = None) -> bytes:
    """Composite a transparent cutout over a solid colour or another photo."""
    fg = load(cutout_png).convert("RGBA")
    if bg_data:
        bg = load(bg_data).convert("RGB")
        # cover-fit the background to the cutout
        scale = max(fg.width / bg.width, fg.height / bg.height)
        bg = bg.resize((max(1, int(bg.width * scale)),
                        max(1, int(bg.height * scale))), Image.LANCZOS)
        left, top = (bg.width - fg.width) // 2, (bg.height - fg.height) // 2
        bg = bg.crop((left, top, left + fg.width, top + fg.height))
    else:
        bg = Image.new("RGB", fg.size, _parse_color(color or "#FFFFFF"))
    bg = bg.convert("RGBA")
    bg.alpha_composite(fg)
    return to_jpeg(bg.convert("RGB"), quality=92)


def _parse_color(value: str) -> tuple[int, int, int]:
    v = (value or "").strip()
    if v.startswith("#"):
        v = v[1:]
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except (ValueError, IndexError):
        return (255, 255, 255)
