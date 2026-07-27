"""Health, categories and templates."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import Pagination
from ..models import Category, Template
from ..schemas import CategoryOut, Page, TemplateDetail, TemplateOut

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/categories", response_model=Page[CategoryOut])
def categories(db: Session = Depends(get_db), pg: Pagination = Depends()):
    base = select(Category).where(Category.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Category.name)
                      .offset(pg.offset).limit(pg.page_size)).all()
    return Page(items=rows, page=pg.page, page_size=pg.page_size, total=total,
                has_more=pg.offset + len(rows) < total)


@router.get("/templates", response_model=Page[TemplateOut])
def templates(db: Session = Depends(get_db), pg: Pagination = Depends(),
              category_id: int | None = Query(None)):
    base = select(Template).where(Template.is_active.is_(True))
    if category_id:
        base = base.where(Template.category_id == category_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Template.sort_order, Template.id)
                      .offset(pg.offset).limit(pg.page_size)).all()
    return Page(items=rows, page=pg.page, page_size=pg.page_size, total=total,
                has_more=pg.offset + len(rows) < total)


@router.get("/templates/{template_id}", response_model=TemplateDetail)
def template_detail(template_id: int, db: Session = Depends(get_db)):
    t = db.get(Template, template_id)
    if not t or not t.is_active:
        raise HTTPException(404, "Template not found")
    return t
