# v3 backend — audit & fixes

Ran the app under a live test client with concurrency stress and edge-case
probes. Below is every issue found and the fix applied. Final state: **29/29
regression checks pass; the critical data-corruption bug is resolved.**

## Critical

**1. Duplicate likes/saves + corrupted counters under concurrency (data integrity).**
The `PostLike` / `PostSave` **models had no unique constraint** — only the
Alembic migration did. So any DB created via `create_all` (tests, dev, and any
environment where migrations lagged) had no protection, and the toggle logic
(`SELECT` then `INSERT`) let concurrent requests from the same user insert
multiple rows. Result: a post could show 5 likes from one user, and on Postgres
the second insert could raise an uncaught `IntegrityError` → HTTP 500.
*Fix:* added `UniqueConstraint("post_id","user_id")` to both models (now matches
migration 0003), and rewrote `_toggle` to be race-safe — insert, catch
`IntegrityError`, recount from the rows as the source of truth. Verified: 20
concurrent likes now leave ≤1 row, counter always matches, zero 500s.

## High

**2. Validation errors used the wrong JSON shape.** FastAPI returns
`{"detail":[...]}` on a 422; your Android client reads `optString("error")`, so
every malformed request showed a generic "HTTP 422" instead of the real reason.
*Fix:* added handlers for `RequestValidationError` and `HTTPException` that
return `{"error": "..."}`, so **all** error responses now match the app's parser.

**3. Unbounded request bodies read into memory before the size check.** Every
upload did `await file.read()` (whole body into RAM) *then* checked the limit —
a large POST could exhaust memory first. *Fix:* middleware rejects any request
whose `Content-Length` exceeds the video ceiling +5 MB, before the body is read.

**4. Comment counter off-by-one risk.** `comment_create` set
`count()+1` *before* commit. *Fix:* commit first, then read the authoritative
`count()`; same for delete (was `max(0, count-1)`). Counts are now always exact.

**5. `share` used read-modify-write.** Concurrent shares could lose increments.
*Fix:* atomic `UPDATE ... shares_count = shares_count + 1`.

## Medium

**6. `optional_user` swallowed every exception.** A real DB error would be
silently masked as "anonymous viewer". *Fix:* only `AuthError` → anonymous;
everything else propagates.

**7. N+1 queries in list/feed.** `post_json` ran 2 queries per post for
liked/saved state — a 12-item page = 24 extra queries. *Fix:* the list endpoints
now batch the viewer's liked/saved post-ids in 2 queries total per page.

**8. Author display name could crash on a null email.** *Fix:* `_display_name`
falls back name → email-prefix → `user{id}`.

**9. Dead code in `_toggle`** (`count = ... + (0 if row else 0)` immediately
overwritten). Removed in the rewrite.

## Notes / recommendations (not code-changed)

- **Rate limiting:** the global 120/min (slowapi) is active. `POST /api/generate/`
  spends real provider money — consider a tighter scoped limit (e.g. 10/min per
  user) before launch. Left as a config decision.
- **Content-type spoofing:** uploads trust the client `Content-Type`. For
  stronger safety, sniff magic bytes server-side (e.g. `python-magic`). Low risk
  since files go to R2, not executed.
- **Video thumbnails:** still fall back to the video URL (no ffmpeg on Render) —
  unchanged from v3; extract a poster on-device or add a thumbnail service.
