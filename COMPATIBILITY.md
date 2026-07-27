# Android ↔ Backend compatibility report (v2)

Read from your Android source (`data/net/BackendApi.kt`, `data/repo/Repositories.kt`,
`data/SessionManager.kt`, `GenerateViewModel.kt`). Every endpoint below is now
implemented **exactly** as the app calls it — no Android changes required.

## Contract implemented

| App call | Backend route | Matched details |
|---|---|---|
| `signup(email,password,name)` | `POST /api/auth/signup/` | returns `{token, user{id,email,name,avatar,uploads,generations}}` |
| `login(email,password)` | `POST /api/auth/login/` | same shape |
| `socialLogin(provider,id_token,email,name)` | `POST /api/auth/social/` | same shape (see ⚠ below) |
| `me()` | `GET /api/auth/me/` | flat user JSON (app accepts flat or `user{}`) |
| `updateProfile(name, avatar)` | `POST /api/auth/profile/` | multipart `name` + file `avatar` |
| `suggestions()` | `GET /api/feed/` | `{items:[{id,title,prompt,media_url,thumb_url,media_type,author,model_name}]}` |
| `start(prompt,model,media_type,reference)` | `POST /api/generate/` | multipart; optional file `reference` |
| `poll(jobId)` (every 2 s) | `GET /api/generate/{id}/` | `{job_id,status,result_url,media_type,error}` |
| `myUploads()` | `GET /api/uploads/` | `{items:[{id,media_url,thumb_url,prompt,media_type,created_at}]}` |
| `upload(media,prompt,type)` | `POST /api/uploads/create/` | multipart `prompt`,`media_type` + file `media` |

Also matched: `Authorization: Token <t>` header; error JSON `{"error": "..."}`
(the app reads `error`, not FastAPI's default `detail`); statuses
`queued|running|done|error`; `application/octet-stream` uploads sniffed to the
right type; relative-URL tolerance (we return absolute R2 URLs, which the app's
`abs()` passes through unchanged).

## The 10 models, routed

image: happy-horse-1.1→fal · gemini-omni→google (Imagen, sync) · grok-images→xai (sync)
video: seedance-2.0-fast, wan-2.7, kling-v3-omni, kling-v3→fal (queue+webhook) ·
veo-3.1-fast, veo-3.1→google (long-running op, polled) · luma→luma (polled)

Text→image, text→video, and **image→video** (send `reference`) all work; sync
providers return `status:"done"` directly from `POST /api/generate/`, async ones
finish via the fal webhook or the 2-second poll. Results are always persisted to
R2 `generated/` and served from there.

⚠ Honest caveats you must know:
1. **Model names are routed via env.** Several wire ids (wan-2.7, kling-v3,
   veo-3.1, seedance-2.0) are newer than the provider catalogues I can verify.
   Defaults are my best guesses; fix any of them WITHOUT code changes via
   `MODEL_ROUTES` JSON env (see `.env.example`). If a route 404s at the
   provider, the job returns a clean `error` naming the model.
2. **`/api/auth/social/` does not yet verify the id_token signature** — it
   trusts the email the app sends. Fine for development; before production,
   give me your Google/Facebook client IDs and I'll add real verification.
3. Your `SessionManager` ships a placeholder token and `isLoggedIn=true`
   (test scaffolding). `ALLOW_ANON_TEST=true` (default in `.env.example`) maps
   unknown tokens to a shared tester account so the app works immediately.
   **Set it to false in production**, and consider removing the mock fallbacks
   in `Repositories.kt` once the backend is live.
4. Android `baseUrl` defaults to `http://10.0.2.2:8000` (emulator). For a real
   device or production, set `api.baseUrl` to your Render URL — it's already a
   `@Volatile var`, so one line at app start.
5. Video uploads get no auto-poster (no ffmpeg on Render); `thumb_url` falls
   back to `media_url`, which your app already handles (`ifBlank` fallback).

## Old v1 API
The previous `/api/v1/*` template endpoints still exist untouched — nothing to
migrate; new migration `0002` only adds tables.
