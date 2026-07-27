"""Token auth for the mobile app (DRF style: `Authorization: Token <t>`).

The Android SessionManager ships with a placeholder token ("dummy_test_token")
and mock fallbacks; set ALLOW_ANON_TEST=true in dev to map any unknown token to
a shared tester account so the app works before real signup is wired. Leave it
false in production.
"""
import hashlib
import os
import secrets

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AppUser

settings = get_settings()
_ITER = 200_000


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), _ITER).hex()
    return f"pbkdf2${salt}${h}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _algo, salt, h = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), _ITER).hex()
    return secrets.compare_digest(calc, h)


def new_token() -> str:
    return secrets.token_hex(24)


class AuthError(Exception):
    pass


def get_app_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> AppUser:
    token = ""
    if authorization and authorization.lower().startswith("token "):
        token = authorization.split(" ", 1)[1].strip()
    if token:
        user = db.query(AppUser).filter(AppUser.token == token).first()
        if user:
            return user
    if settings.allow_anon_test:
        user = db.query(AppUser).filter(AppUser.email == "tester@example.com").first()
        if user is None:
            user = AppUser(email="tester@example.com", name="Test User",
                           password_hash="", token=new_token())
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    raise AuthError("authentication required")
