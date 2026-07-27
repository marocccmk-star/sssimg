# AI Photo Backend (FastAPI)

Backend for an Android AI photo app: browse categories → pick a template →
upload a photo → AI generates a new image → result stored on Cloudflare R2 →
history in PostgreSQL.

```
Android App → FastAPI (JSON/HTTPS) → PostgreSQL
                     ↓
              Cloudflare R2  ←  AI provider (fal.ai)
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health` | `{"status":"ok"}` |
| GET | `/api/v1/categories?page=&page_size=` | paginated |
| GET | `/api/v1/templates?category_id=&page=&page_size=` | paginated |
| GET | `/api/v1/templates/{id}` | detail (no `ai_prompt` exposed) |
| POST | `/api/v1/uploads` | multipart `file`; JPEG/PNG/WebP; max `MAX_UPLOAD_MB` |
| POST | `/api/v1/generations` | `{"template_id":1,"input_image_url":"..."}` |
| GET | `/api/v1/generations/{id}` | poll until `completed` / `failed` |
| GET | `/api/v1/generations?page=&page_size=` | current user's history |
| POST | `/api/v1/webhooks/ai` | called by the AI provider, not by the app |

**Identity:** every request from the app sends header `X-Device-ID: <stable
installation uuid>`. A user row is auto-created. (If your Android app uses real
accounts, swap `app/deps.py:get_current_user` for token auth — the rest stays.)

**List envelope (all paginated endpoints):**
```json
{"items":[...],"page":1,"page_size":20,"total":57,"has_more":true}
```

**Generation lifecycle:** `pending → processing → completed | failed`.
`output_image_url` is a permanent R2 URL under `generated/`. The AI provider
key never reaches the app; the app only ever sees R2 URLs.

## Android flow (Retrofit)

1. `GET /categories`, `GET /templates?category_id=`
2. `POST /uploads` (Multipart) → `{"url": ...}`
3. `POST /generations` with that url → `{"id": 12, "status": "processing"}`
4. Poll `GET /generations/12` every ~2s → `status:"completed"`, show
   `output_image_url`.
5. History: `GET /generations`.

## Local run

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill values
alembic upgrade head
python seed.py         # optional demo data
uvicorn app.main:app --reload
# docs: http://127.0.0.1:8000/docs
```

## Deploy on Render

1. Push this folder to a Git repo.
2. Render → New → **Blueprint** → pick the repo (`render.yaml` creates the web
   service + Postgres).
3. Fill the secret env vars (R2 keys, FAL key/model, `APP_BASE_URL` = the
   service's own https URL — needed so the AI webhook can call back).
4. The Docker CMD runs `alembic upgrade head` automatically on boot, then
   starts uvicorn on `0.0.0.0:$PORT`.

## Cloudflare R2 setup

- Create a bucket, generate an S3 API token (Access Key ID / Secret).
- Enable public access via a custom domain or the r2.dev URL; put that in
  `R2_PUBLIC_BASE_URL`.
- Folders used: `templates/` (you upload these), `uploads/` (user photos),
  `generated/` (AI results). Nothing is stored on the Render disk.

## AI provider

`app/services/ai_provider.py` talks to fal.ai's queue API. The model comes from
`FAL_MODEL`. If your chosen model uses different input field names, adjust only
the `payload` dict in `submit()` — everything else (webhook, polling, R2 save)
is model-agnostic. Failed generations record `error_message`; the webhook is
idempotent and unknown request ids are acked to prevent retry storms.

## Security summary

CORS from env; strict upload validation (type + size); per-IP rate limiting
(default 120/min via slowapi); generic 500 responses (no stack traces to the
client); all credentials from env; `ai_prompt` and provider keys never leave
the server; `input_image_url` must point at our own R2 bucket.

## ⚠ Contract decisions to confirm against your Android app

I could not inspect the Android project (it wasn't provided). These are the
points most likely to differ from your Retrofit models — send me your API
interfaces + data classes and I'll align them exactly:

1. Identity header `X-Device-ID` (vs. real auth tokens).
2. Pagination style `page`/`page_size` + `items/total/has_more` envelope
   (vs. offset/limit or cursor).
3. Upload response field names (`key`, `url`, `content_type`, `size_bytes`).
4. Generation JSON field names (`input_image_url`, `output_image_url`,
   `status` lowercase strings).
5. Error shape `{"detail": "..."}` (FastAPI default).
