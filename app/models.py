"""Database models — exactly the tables from the spec."""
import enum
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Enum, ForeignKey, Integer, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    generations = relationship("GenerationJob", back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    image_url: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    templates = relationship("Template", back_populates="category")


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    thumbnail_url: Mapped[str] = mapped_column(String(500), default="")
    original_image_url: Mapped[str] = mapped_column(String(500), default="")
    ai_prompt: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(),
                                                 onupdate=func.now())

    category = relationship("Category", back_populates="templates")


class GenerationStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), index=True)
    input_image_url: Mapped[str] = mapped_column(String(500))
    output_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, name="generation_status"),
        default=GenerationStatus.pending, index=True)
    provider_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True,
                                                        index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)

    user = relationship("User", back_populates="generations")
    template = relationship("Template")


# ===========================================================================
#  Mobile app (sssimg) tables — v2: prompt-based image & video generation
# ===========================================================================
class AppUser(Base):
    """Account for the Android app: email+password or social, Token auth."""
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(300), default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class MediaAsset(Base):
    """One item in the user's uploads: an image or video + its prompt."""
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    media_type: Mapped[str] = mapped_column(String(10))          # image | video
    media_url: Mapped[str] = mapped_column(String(500))
    thumb_url: Mapped[str] = mapped_column(String(500), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class FeedPost(Base):
    """Curated 'For you' suggestion cards (Picsart-style)."""
    __tablename__ = "feed_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    media_type: Mapped[str] = mapped_column(String(10), default="image")
    media_url: Mapped[str] = mapped_column(String(500))
    thumb_url: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str] = mapped_column(String(120), default="sssimg")
    model_name: Mapped[str] = mapped_column(String(60), default="gemini-omni")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class GenJob(Base):
    """A prompt→image/video generation job for the mobile app.
    Status wire values (what the app expects): queued | running | done | error.
    """
    __tablename__ = "gen_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(String(60), index=True)   # wire id
    provider: Mapped[str] = mapped_column(String(20), default="fal")
    media_type: Mapped[str] = mapped_column(String(10), default="image")
    reference_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    result_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_job_id: Mapped[str | None] = mapped_column(String(300), nullable=True,
                                                        index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)


# ===========================================================================
#  Mobile social layer — v3: user posts (grid + TikTok feed), likes, comments
# ===========================================================================
class UserPost(Base):
    """A user-published image/video with title, category and optional prompt."""
    __tablename__ = "user_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), index=True)
    media_type: Mapped[str] = mapped_column(String(10))          # image | video
    media_url: Mapped[str] = mapped_column(String(500))
    thumb_url: Mapped[str] = mapped_column(String(500), default="")
    likes_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    saves_count: Mapped[int] = mapped_column(Integer, default=0)
    shares_count: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(),
                                                 onupdate=func.now())

    author = relationship("AppUser")


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id",
                                       name="uq_post_likes_post_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("user_posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class PostSave(Base):
    __tablename__ = "post_saves"
    __table_args__ = (UniqueConstraint("post_id", "user_id",
                                       name="uq_post_saves_post_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("user_posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class PostComment(Base):
    __tablename__ = "post_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("user_posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    text: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    author = relationship("AppUser")
