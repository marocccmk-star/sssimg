"""Multi-provider generation router for the mobile app.

The Android app sends a wire model id (e.g. "veo-3.1-fast"); MODEL_REGISTRY
maps it to a provider + a remote model string. Remote strings are defaults and
can be overridden — without code changes — via the MODEL_ROUTES env var
(JSON: {"wire-id": {"provider": "...", "remote": "..."}}), because provider
catalogues change often.

Contract with the rest of the app:
  submit(job_dict)  -> (provider_job_id | None, result_url | None, error | None)
        result_url set  => the provider finished synchronously (job done)
        provider_job_id => async job, finish via fetch() polling or fal webhook
  fetch(provider, remote, provider_job_id)
        -> (status in {running, done, error}, result_url | None, error | None)

All network errors are caught and surfaced as clean error strings; the app
shows them in its `error` field.
"""
import base64
import json

import httpx

from ..config import get_settings
from . import ai_provider as fal  # existing fal queue implementation

settings = get_settings()

# wire id -> (provider, media_type, default remote model)
_DEFAULTS: dict[str, tuple[str, str, str]] = {
    "happy-horse-1.1":   ("fal",    "image", "fal-ai/flux/dev"),
    "gemini-omni":       ("google", "image", "imagen-3.0-generate-002"),
    "grok-images":       ("xai",    "image", "grok-2-image"),
    "seedance-2.0-fast": ("fal",    "video", "fal-ai/bytedance/seedance/v1/lite/text-to-video"),
    "wan-2.7":           ("fal",    "video", "fal-ai/wan-t2v"),
    "veo-3.1-fast":      ("google", "video", "veo-3.1-fast-generate-001"),
    "veo-3.1":           ("google", "video", "veo-3.1-generate-001"),
    "kling-v3-omni":     ("fal",    "video", "fal-ai/kling-video/v2/master/image-to-video"),
    "kling-v3":          ("fal",    "video", "fal-ai/kling-video/v2/master/text-to-video"),
    "luma":              ("luma",   "video", "ray-2"),
}


def registry() -> dict[str, tuple[str, str, str]]:
    routes = dict(_DEFAULTS)
    if settings.model_routes:
        try:
            for wire, spec in json.loads(settings.model_routes).items():
                prov, mt, remote = routes.get(wire, ("fal", "image", ""))
                routes[wire] = (spec.get("provider", prov),
                                spec.get("media_type", mt),
                                spec.get("remote", remote))
        except (ValueError, AttributeError):
            pass
    return routes


def resolve(model_id: str) -> tuple[str, str, str] | None:
    return registry().get(model_id)


# --------------------------------------------------------------------------- #
#  submit / fetch dispatch
# --------------------------------------------------------------------------- #
def submit(provider: str, remote: str, prompt: str, media_type: str,
           reference_url: str, webhook_url: str | None):
    try:
        if provider == "fal":
            pid = _fal_submit(remote, prompt, reference_url, webhook_url)
            return pid, None, None
        if provider == "google":
            return _google_submit(remote, prompt, media_type, reference_url)
        if provider == "xai":
            return _xai_submit(remote, prompt)
        if provider == "luma":
            return _luma_submit(remote, prompt, reference_url)
        return None, None, f"unknown provider '{provider}'"
    except Exception as exc:
        return None, None, f"{provider}: {exc}"


def fetch(provider: str, remote: str, provider_job_id: str):
    try:
        if provider == "fal":
            st, out, err = fal.fetch_result_for(remote, provider_job_id)
            return {"processing": "running", "completed": "done",
                    "failed": "error"}[st], out, err
        if provider == "google":
            return _google_fetch(provider_job_id)
        if provider == "luma":
            return _luma_fetch(provider_job_id)
        return "error", None, f"provider '{provider}' has no async fetch"
    except Exception as exc:
        return "error", None, f"{provider}: {exc}"


# --------------------------------------------------------------------------- #
#  fal (queue API, async — reuses existing service, model passed per-call)
# --------------------------------------------------------------------------- #
def _fal_submit(remote: str, prompt: str, reference_url: str,
                webhook_url: str | None) -> str:
    if not settings.fal_api_key:
        raise RuntimeError("FAL_API_KEY not configured")
    url = f"https://queue.fal.run/{remote}"
    if webhook_url:
        url += f"?fal_webhook={webhook_url}"
    payload: dict = {"prompt": prompt}
    if reference_url:
        payload["image_url"] = reference_url          # image-to-video / img2img
    with httpx.Client(timeout=30) as cx:
        r = cx.post(url, json=payload,
                    headers={"Authorization": f"Key {settings.fal_api_key}"})
        if r.status_code >= 400:
            raise RuntimeError(f"fal rejected job: {r.status_code} {r.text[:200]}")
        rid = r.json().get("request_id")
    if not rid:
        raise RuntimeError("fal returned no request_id")
    return rid


# --------------------------------------------------------------------------- #
#  Google (Gemini API): Imagen = sync predict; Veo = long-running operation
# --------------------------------------------------------------------------- #
_G = "https://generativelanguage.googleapis.com/v1beta"


def _gheaders():
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not configured")
    return {"x-goog-api-key": settings.google_api_key}


def _google_submit(remote: str, prompt: str, media_type: str, reference_url: str):
    with httpx.Client(timeout=120) as cx:
        if media_type == "image":
            r = cx.post(f"{_G}/models/{remote}:predict", headers=_gheaders(),
                        json={"instances": [{"prompt": prompt}],
                              "parameters": {"sampleCount": 1}})
            if r.status_code >= 400:
                raise RuntimeError(f"google: {r.status_code} {r.text[:200]}")
            preds = r.json().get("predictions") or []
            b64 = preds and preds[0].get("bytesBase64Encoded")
            if not b64:
                raise RuntimeError("google returned no image")
            from . import storage
            _k, url = storage.upload_bytes("generated",
                                           base64.b64decode(b64), "image/png")
            return None, url, None                     # sync: done immediately
        # video (Veo): long-running
        inst: dict = {"prompt": prompt}
        if reference_url:
            img = httpx.get(reference_url, timeout=60)
            inst["image"] = {"bytesBase64Encoded":
                             base64.b64encode(img.content).decode(),
                             "mimeType": img.headers.get("content-type", "image/jpeg")}
        r = cx.post(f"{_G}/models/{remote}:predictLongRunning", headers=_gheaders(),
                    json={"instances": [inst]})
        if r.status_code >= 400:
            raise RuntimeError(f"google: {r.status_code} {r.text[:200]}")
        op = r.json().get("name")
        if not op:
            raise RuntimeError("google returned no operation name")
        return op, None, None


def _google_fetch(op_name: str):
    with httpx.Client(timeout=60) as cx:
        r = cx.get(f"{_G}/{op_name}", headers=_gheaders())
        if r.status_code >= 400:
            return "error", None, f"google: {r.status_code}"
        data = r.json()
    if not data.get("done"):
        return "running", None, None
    if data.get("error"):
        return "error", None, str(data["error"].get("message", "google error"))[:300]
    resp = data.get("response") or {}
    samples = (resp.get("generateVideoResponse") or {}).get("generatedSamples") or []
    uri = samples and (samples[0].get("video") or {}).get("uri")
    if not uri:
        return "error", None, "google returned no video uri"
    # Veo download links need the API key appended
    sep = "&" if "?" in uri else "?"
    return "done", f"{uri}{sep}key={settings.google_api_key}", None


# --------------------------------------------------------------------------- #
#  xAI (Grok image) — synchronous
# --------------------------------------------------------------------------- #
def _xai_submit(remote: str, prompt: str):
    if not settings.xai_api_key:
        raise RuntimeError("XAI_API_KEY not configured")
    with httpx.Client(timeout=120) as cx:
        r = cx.post("https://api.x.ai/v1/images/generations",
                    headers={"Authorization": f"Bearer {settings.xai_api_key}"},
                    json={"model": remote, "prompt": prompt,
                          "response_format": "url", "n": 1})
        if r.status_code >= 400:
            raise RuntimeError(f"xai: {r.status_code} {r.text[:200]}")
        data = r.json().get("data") or []
        url = data and data[0].get("url")
    if not url:
        raise RuntimeError("xai returned no image url")
    return None, url, None                              # sync: done immediately


# --------------------------------------------------------------------------- #
#  Luma Dream Machine — async by id
# --------------------------------------------------------------------------- #
_LUMA = "https://api.lumalabs.ai/dream-machine/v1"


def _lheaders():
    if not settings.luma_api_key:
        raise RuntimeError("LUMA_API_KEY not configured")
    return {"Authorization": f"Bearer {settings.luma_api_key}"}


def _luma_submit(remote: str, prompt: str, reference_url: str):
    payload: dict = {"prompt": prompt, "model": remote}
    if reference_url:
        payload["keyframes"] = {"frame0": {"type": "image", "url": reference_url}}
    with httpx.Client(timeout=30) as cx:
        r = cx.post(f"{_LUMA}/generations", headers=_lheaders(), json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"luma: {r.status_code} {r.text[:200]}")
        gid = r.json().get("id")
    if not gid:
        raise RuntimeError("luma returned no generation id")
    return gid, None, None


def _luma_fetch(gid: str):
    with httpx.Client(timeout=30) as cx:
        r = cx.get(f"{_LUMA}/generations/{gid}", headers=_lheaders())
        if r.status_code >= 400:
            return "error", None, f"luma: {r.status_code}"
        data = r.json()
    state = data.get("state")
    if state in ("queued", "dreaming", "processing"):
        return "running", None, None
    if state != "completed":
        return "error", None, str(data.get("failure_reason") or f"luma state {state}")[:300]
    url = (data.get("assets") or {}).get("video")
    return ("done", url, None) if url else ("error", None, "luma returned no video")
