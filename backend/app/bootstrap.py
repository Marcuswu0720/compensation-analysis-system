"""Optional first-admin auto-seeding, for deployments (e.g. Render) where
there's no interactive terminal to run seed_admin.py by hand. Controlled
entirely by the ADMIN_USERNAME / ADMIN_PASSWORD environment variables - if
either is unset, this is a no-op, so local dev (which uses seed_admin.py
directly) is unaffected. Idempotent: only creates the account if a user
with that username doesn't already exist, so it's safe to leave the env
vars set permanently across restarts/redeploys.
"""

import os

from .database import SessionLocal
from .models import User
from .security import hash_password, normalize_username


def seed_admin_from_env() -> None:
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        return

    username = normalize_username(username)
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first():
            return
        db.add(User(username=username, password_hash=hash_password(password), role="admin"))
        db.commit()
    finally:
        db.close()
