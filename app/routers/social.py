"""Social layer for the Android app — user posts, grid & TikTok feed,
like / save / share / comments. Same conventions as routers/mobile.py:
Token auth, {"error": ...} failures, snake_case JSON.

  GET  /api/categories/                          -> {items:[...]}
  GET  /api/posts/?offset=&category=&type=&sort=&mine=1&saved=1
                                                 -> {items:[Post], next_offset}
  GET  /api/posts/feed/?offset=&type=video       -> TikTok feed (same shape)
  POST /api/posts/create/   multipart title,category[,prompt,media_type]
                            + file media [+ file thumb]        -> Post
  GET  /api/posts/{id}/                                        -> Post
  POST /api/posts/{id}/update/   json {title?,category?,prompt?} -> Post
  POST /api/posts/{id}/delete/   (owner)                       -> {ok:true}
  POST /api/posts/{id}/like/                                   -> {liked,likes}
  POST /api/posts/{id}/save/                                   -> {saved,saves}
  POST /api/posts/{id}/share/                                  -> {shares}
  GET  /api/posts/{id}/comments/                               -> {items,count}
  POST /api/posts/{id}/comments/create/  json {text}           -> {comment,count}
  POST /api/comments/{id}/delete/        (owner)               -> {ok:true}
"""
from fastapi import APIRouter, Depends, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AppUser, PostComment, PostLike, PostSave, UserPost
from ..security import AuthError, get_app_user
from ..services import storage

router = APIRouter(prefix="/api", tags=["social"])
settings = get_settings()

_PAGE = 12
CATEGORIES = ["Art", "Anime", "Nature", "People", "Memes", "Sports",
              "Travel", "Food", "Fashion", "Tech", "Music", "Other"]
IMG_TYPES = {"image/jpeg", "image/png", "image/webp"}
VID_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


def _display_name(user: AppUser) -> str:
    """Safe display name: real name, else email prefix, else user#id."""
    if user.name:
        return user.name
    if user.email and "@" in user.email:
        return user.email.split("@")[0]
    return f"user{user.id}"



def err(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": message})


def optional_user(db: Session = Depends(get_db),
                  authorization: str | None = Header(None)) -> AppUser | None:
    """Reads are public; a valid token personalizes liked/saved/is_owner.

    Only an auth failure yields None (anonymous). Any other error propagates so
    real bugs aren't silently masked as 'not logged in'.
    """
    if not authorization:
        return None
    try:
        return get_app_user(db=db, authorization=authorization)
    except AuthError:
        return None


def post_json(p: UserPost, db: Session, viewer: AppUser | None,
              liked_ids: set[int] | None = None,
              saved_ids: set[int] | None = None) -> dict:
    uid = viewer.id if viewer else None
    liked = saved = False
    if uid:
        # Use precomputed sets when available (list endpoints), else query once
        # (single-post endpoints).
        if liked_ids is not None:
            liked = p.id in liked_ids
        else:
            liked = db.query(PostLike).filter_by(post_id=p.id, user_id=uid).first() is not None
        if saved_ids is not None:
            saved = p.id in saved_ids
        else:
            saved = db.query(PostSave).filter_by(post_id=p.id, user_id=uid).first() is not None
    a = p.author
    return {
        "id": p.id, "title": p.title, "prompt": p.prompt, "category": p.category,
        "media_type": p.media_type, "media_url": p.media_url,
        "thumb_url": p.thumb_url or p.media_url,
        "likes": p.likes_count, "saves": p.saves_count,
        "shares": p.shares_count, "comments": p.comments_count,
        "liked": liked, "saved": saved,
        "is_owner": uid == p.user_id,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "author": {"id": a.id, "name": _display_name(a),
                   "avatar": a.avatar_url or ""},
    }


@router.get("/categories/")
def categories():
    return {"items": CATEGORIES}


# --------------------------------------------------------------------------- #
#  Lists: grid + TikTok feed
# --------------------------------------------------------------------------- #
def _list(db, viewer, offset, category=None, mtype=None, sort="new",
          mine=False, saved=False):
    q = select(UserPost).join(AppUser, UserPost.user_id == AppUser.id)
    if category:
        q = q.where(UserPost.category == category)
    if mtype in ("image", "video"):
        q = q.where(UserPost.media_type == mtype)
    if mine and viewer:
        q = q.where(UserPost.user_id == viewer.id)
    if saved and viewer:
        sub = select(PostSave.post_id).where(PostSave.user_id == viewer.id)
        q = q.where(UserPost.id.in_(sub))
    if sort == "top":
        q = q.order_by(UserPost.likes_count.desc(), UserPost.id.desc())
    else:
        q = q.order_by(UserPost.id.desc())
    rows = db.scalars(q.offset(offset).limit(_PAGE + 1)).all()
    page = rows[:_PAGE]

    # Batch the viewer's liked/saved lookups for the whole page (avoids N+1).
    liked_ids: set[int] = set()
    saved_ids: set[int] = set()
    if viewer and page:
        ids = [p.id for p in page]
        liked_ids = set(db.scalars(
            select(PostLike.post_id).where(PostLike.user_id == viewer.id,
                                           PostLike.post_id.in_(ids))).all())
        saved_ids = set(db.scalars(
            select(PostSave.post_id).where(PostSave.user_id == viewer.id,
                                           PostSave.post_id.in_(ids))).all())

    items = [post_json(p, db, viewer, liked_ids, saved_ids) for p in page]
    return {"items": items,
            "next_offset": offset + _PAGE if len(rows) > _PAGE else None}


@router.get("/posts/")
def posts_list(request: Request, db: Session = Depends(get_db),
               viewer: AppUser | None = Depends(optional_user)):
    qp = request.query_params
    try:
        offset = max(0, int(qp.get("offset", 0)))
    except ValueError:
        offset = 0
    return _list(db, viewer, offset,
                 category=qp.get("category") or None,
                 mtype=qp.get("type") or None,
                 sort=qp.get("sort", "new"),
                 mine=qp.get("mine") == "1",
                 saved=qp.get("saved") == "1")


@router.get("/posts/feed/")
def posts_feed(request: Request, db: Session = Depends(get_db),
               viewer: AppUser | None = Depends(optional_user)):
    """TikTok-style vertical feed. Defaults to videos; pass type=all for both."""
    qp = request.query_params
    try:
        offset = max(0, int(qp.get("offset", 0)))
    except ValueError:
        offset = 0
    mtype = qp.get("type", "video")
    return _list(db, viewer, offset,
                 mtype=None if mtype == "all" else mtype, sort="new")


# --------------------------------------------------------------------------- #
#  Create / read / update / delete
# --------------------------------------------------------------------------- #
@router.post("/posts/create/")
async def post_create(title: str = Form(...), category: str = Form("Other"),
                      prompt: str = Form(""), media_type: str = Form(""),
                      media: UploadFile | None = None,
                      thumb: UploadFile | None = None,
                      db: Session = Depends(get_db),
                      user: AppUser = Depends(get_app_user)):
    if media is None:
        return err(400, "media file is required")
    if not title.strip():
        return err(400, "title is required")
    if category not in CATEGORIES:
        category = "Other"

    data = await media.read()
    ctype = media.content_type or "application/octet-stream"
    if ctype == "application/octet-stream":
        name = (media.filename or "").lower()
        ctype = ("video/mp4" if media_type == "video"
                 or name.endswith((".mp4", ".mov", ".webm")) else "image/jpeg")
    if ctype in VID_TYPES:
        if len(data) > settings.max_video_upload_mb * 1024 * 1024:
            return err(413, f"video too large (max {settings.max_video_upload_mb} MB)")
        media_type = "video"
    elif ctype in IMG_TYPES:
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            return err(413, f"image too large (max {settings.max_upload_mb} MB)")
        media_type = "image"
    else:
        return err(415, "unsupported media type")

    _k, url = storage.upload_bytes("uploads", data, ctype)
    thumb_url = url if media_type == "image" else ""
    if thumb is not None:                     # app-extracted poster frame
        tdata = await thumb.read()
        tctype = thumb.content_type or "image/jpeg"
        if tctype == "application/octet-stream":
            tctype = "image/jpeg"
        if tctype in IMG_TYPES and tdata:
            _tk, thumb_url = storage.upload_bytes("uploads", tdata, tctype)

    p = UserPost(user_id=user.id, title=title.strip()[:200],
                 prompt=prompt.strip(), category=category,
                 media_type=media_type, media_url=url, thumb_url=thumb_url)
    db.add(p); db.commit(); db.refresh(p)
    return post_json(p, db, user)


def _get_post(db, post_id) -> UserPost | None:
    return db.get(UserPost, post_id)


@router.get("/posts/{post_id}/")
def post_detail(post_id: int, db: Session = Depends(get_db),
                viewer: AppUser | None = Depends(optional_user)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    return post_json(p, db, viewer)


@router.post("/posts/{post_id}/update/")
async def post_update(post_id: int, request: Request,
                      db: Session = Depends(get_db),
                      user: AppUser = Depends(get_app_user)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    if p.user_id != user.id:
        return err(403, "not allowed")
    b = await request.json()
    if "title" in b and (b.get("title") or "").strip():
        p.title = b["title"].strip()[:200]
    if "prompt" in b:
        p.prompt = (b.get("prompt") or "").strip()
    if "category" in b and b.get("category") in CATEGORIES:
        p.category = b["category"]
    db.commit(); db.refresh(p)
    return post_json(p, db, user)


@router.post("/posts/{post_id}/delete/")
def post_delete(post_id: int, db: Session = Depends(get_db),
                user: AppUser = Depends(get_app_user)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    if p.user_id != user.id:
        return err(403, "not allowed")
    db.query(PostLike).filter_by(post_id=p.id).delete()
    db.query(PostSave).filter_by(post_id=p.id).delete()
    db.query(PostComment).filter_by(post_id=p.id).delete()
    db.delete(p); db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
#  Reactions
# --------------------------------------------------------------------------- #
def _toggle(db, model, p: UserPost, user: AppUser, counter: str):
    """Race-safe like/save toggle.

    Two concurrent requests from the same user used to both pass the existence
    check and insert duplicate rows (corrupting the count and, on Postgres,
    raising an uncaught IntegrityError -> 500). We now rely on the DB unique
    constraint: try to insert; if it already exists, delete instead; recount
    from the rows themselves as the single source of truth.
    """
    from sqlalchemy.exc import IntegrityError

    existing = db.query(model).filter_by(post_id=p.id, user_id=user.id).first()
    if existing:
        db.delete(existing)
        db.commit()
        on = False
    else:
        db.add(model(post_id=p.id, user_id=user.id))
        try:
            db.commit()
            on = True
        except IntegrityError:
            # Lost a race: the row was created by a concurrent request. Treat
            # this call as the toggle-off so the user still gets a consistent
            # result, then remove it.
            db.rollback()
            dup = db.query(model).filter_by(post_id=p.id, user_id=user.id).first()
            if dup:
                db.delete(dup)
                db.commit()
            on = False
    count = db.query(model).filter_by(post_id=p.id).count()
    # keep the denormalized counter in sync (best-effort; count() is truth)
    db.query(UserPost).filter_by(id=p.id).update({counter: count})
    db.commit()
    return on, count


@router.post("/posts/{post_id}/like/")
def post_like(post_id: int, db: Session = Depends(get_db),
              user: AppUser = Depends(get_app_user)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    on, count = _toggle(db, PostLike, p, user, "likes_count")
    return {"liked": on, "likes": count}


@router.post("/posts/{post_id}/save/")
def post_save(post_id: int, db: Session = Depends(get_db),
              user: AppUser = Depends(get_app_user)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    on, count = _toggle(db, PostSave, p, user, "saves_count")
    return {"saved": on, "saves": count}


@router.post("/posts/{post_id}/share/")
def post_share(post_id: int, db: Session = Depends(get_db),
               viewer: AppUser | None = Depends(optional_user)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    from sqlalchemy import update as _upd
    db.execute(_upd(UserPost).where(UserPost.id == p.id)
               .values(shares_count=UserPost.shares_count + 1))
    db.commit()
    db.refresh(p)
    return {"shares": p.shares_count}


# --------------------------------------------------------------------------- #
#  Comments
# --------------------------------------------------------------------------- #
def _comment_json(c: PostComment) -> dict:
    a = c.author
    return {"id": c.id, "text": c.text,
            "created_at": c.created_at.isoformat() if c.created_at else "",
            "author": {"id": a.id, "name": _display_name(a),
                       "avatar": a.avatar_url or ""}}


@router.get("/posts/{post_id}/comments/")
def comments_list(post_id: int, db: Session = Depends(get_db)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    rows = db.scalars(select(PostComment).where(PostComment.post_id == p.id)
                      .order_by(PostComment.id.desc()).limit(200)).all()
    return {"items": [_comment_json(c) for c in rows], "count": p.comments_count}


@router.post("/posts/{post_id}/comments/create/")
async def comment_create(post_id: int, request: Request,
                         db: Session = Depends(get_db),
                         user: AppUser = Depends(get_app_user)):
    p = _get_post(db, post_id)
    if not p:
        return err(404, "post not found")
    b = await request.json()
    text = (b.get("text") or "").strip()
    if not text:
        return err(400, "comment is empty")
    c = PostComment(post_id=p.id, user_id=user.id, text=text[:1000])
    db.add(c)
    db.commit(); db.refresh(c)
    # authoritative count AFTER the row is committed (no off-by-one under load)
    count = db.query(PostComment).filter_by(post_id=p.id).count()
    db.query(UserPost).filter_by(id=p.id).update({"comments_count": count})
    db.commit()
    return {"comment": _comment_json(c), "count": count}


@router.post("/comments/{comment_id}/delete/")
def comment_delete(comment_id: int, db: Session = Depends(get_db),
                   user: AppUser = Depends(get_app_user)):
    c = db.get(PostComment, comment_id)
    if not c:
        return err(404, "comment not found")
    p = _get_post(db, c.post_id)
    if c.user_id != user.id and (not p or p.user_id != user.id):
        return err(403, "not allowed")
    db.delete(c)
    db.commit()
    if p:
        count = db.query(PostComment).filter_by(post_id=p.id).count()
        db.query(UserPost).filter_by(id=p.id).update({"comments_count": count})
        db.commit()
    return {"ok": True}
