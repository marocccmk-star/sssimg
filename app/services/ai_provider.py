"""AI generation provider abstraction. Default implementation: fal.ai queue API.

Configured entirely by env vars (AI_PROVIDER, FAL_API_KEY, FAL_MODEL) — no
hardcoded keys or model names. The Android app never sees any of this.

To add another provider later, implement the same three functions and switch
on settings.ai_provider.
"""
import httpx

from ..config import get_settings

settings = get_settings()

_QUEUE = "https://queue.fal.run"


class AIProviderError(Exception):
    pass


def _headers():
    return {"Authorization": f"Key {settings.fal_api_key}"}


def submit(input_image_url: str, template_image_url: str, prompt: str,
           webhook_url: str | None) -> str:
    """Start an async generation. Returns the provider job (request) id.

    Payload note: image-to-image models on fal generally accept `prompt` and
    `image_url`; we also pass the template image as `reference_image_url` so
    style-transfer models can use it. If your chosen FAL_MODEL uses different
    field names, adjust ONLY this payload dict.
    """
    if not settings.fal_api_key or not settings.fal_model:
        raise AIProviderError("AI provider is not configured (FAL_API_KEY / FAL_MODEL).")

    url = f"{_QUEUE}/{settings.fal_model}"
    if webhook_url:
        url += f"?fal_webhook={webhook_url}"

    payload = {
        "prompt": prompt,
        "image_url": input_image_url,
        "reference_image_url": template_image_url,
    }
    with httpx.Client(timeout=30) as cx:
        r = cx.post(url, json=payload, headers=_headers())
        if r.status_code >= 400:
            raise AIProviderError(f"provider rejected job: {r.status_code} {r.text[:300]}")
        data = r.json()
    request_id = data.get("request_id")
    if not request_id:
        raise AIProviderError("provider did not return a request_id")
    return request_id


def fetch_result(provider_job_id: str) -> tuple[str, str | None, str | None]:
    """Poll fallback. Returns (status, output_image_url, error).
    status in {processing, completed, failed}."""
    base = f"{_QUEUE}/{settings.fal_model}/requests/{provider_job_id}"
    with httpx.Client(timeout=30) as cx:
        s = cx.get(f"{base}/status", headers=_headers())
        if s.status_code >= 400:
            return "failed", None, f"status check failed: {s.status_code}"
        st = (s.json().get("status") or "").upper()
        if st in ("IN_QUEUE", "IN_PROGRESS"):
            return "processing", None, None
        if st != "COMPLETED":
            return "failed", None, f"provider status {st}"
        r = cx.get(base, headers=_headers())
        if r.status_code >= 400:
            return "failed", None, "result fetch failed"
        return "completed", extract_image_url(r.json()), None


def extract_image_url(result: dict) -> str | None:
    """Find the generated image URL in a fal result payload (shape varies a
    little by model: images[0].url, image.url, or output.url)."""
    if not isinstance(result, dict):
        return None
    imgs = result.get("images")
    if isinstance(imgs, list) and imgs and isinstance(imgs[0], dict):
        return imgs[0].get("url")
    vids = result.get("videos")
    if isinstance(vids, list) and vids and isinstance(vids[0], dict):
        return vids[0].get("url")
    for k in ("image", "output", "video"):
        v = result.get(k)
        if isinstance(v, dict) and v.get("url"):
            return v["url"]
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def fetch_result_for(remote_model: str, provider_job_id: str):
    """Same as fetch_result but for an explicit model (mobile multi-model path)."""
    base = f"{_QUEUE}/{remote_model}/requests/{provider_job_id}"
    with httpx.Client(timeout=30) as cx:
        s = cx.get(f"{base}/status", headers=_headers())
        if s.status_code >= 400:
            return "failed", None, f"status check failed: {s.status_code}"
        st = (s.json().get("status") or "").upper()
        if st in ("IN_QUEUE", "IN_PROGRESS"):
            return "processing", None, None
        if st != "COMPLETED":
            return "failed", None, f"provider status {st}"
        r = cx.get(base, headers=_headers())
        if r.status_code >= 400:
            return "failed", None, "result fetch failed"
        return "completed", extract_image_url(r.json()), None
