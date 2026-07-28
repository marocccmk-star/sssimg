"""Pydantic schemas — the JSON contract the Android app consumes.

Every list endpoint returns the same predictable envelope:
  {"items": [...], "page": 1, "page_size": 20, "total": 57, "has_more": true}
"""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    has_more: bool


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    image_url: str
    is_active: bool


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category_id: int
    name: str
    slug: str
    description: str
    thumbnail_url: str
    is_active: bool
    sort_order: int


class TemplateDetail(TemplateOut):
    original_image_url: str
    # NOTE: ai_prompt is intentionally NOT exposed to the app (server-side only).


class UploadOut(BaseModel):
    key: str
    url: str
    content_type: str
    size_bytes: int


class GenerationCreate(BaseModel):
    template_id: int
    input_image_url: str = Field(min_length=8, max_length=500)


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template_id: int
    input_image_url: str
    output_image_url: str | None
    status: str
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class ErrorOut(BaseModel):
    detail: str
