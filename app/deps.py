"""Shared dependencies: current user (device-based) and pagination params."""
from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


def get_current_user(
    db: Session = Depends(get_db),
    x_device_id: str = Header(..., min_length=8, max_length=128,
                              description="Stable device installation id"),
) -> User:
    """Lightweight identity: the Android app sends a stable X-Device-ID header
    (e.g. its installation UUID). A user row is created on first sight.

    ⚠ CONTRACT DECISION — confirm against your Android code. If your app
    already has real accounts (email login / Firebase), tell me and I'll swap
    this for token auth without touching the other endpoints.
    """
    user = db.query(User).filter(User.username == x_device_id).first()
    if user is None:
        user = User(username=x_device_id, email=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


class Pagination:
    def __init__(self,
                 page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100)):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
