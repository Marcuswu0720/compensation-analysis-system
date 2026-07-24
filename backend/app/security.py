import re
from dataclasses import dataclass

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .compute.scope import ScopeRule
from .config import settings
from .database import get_db
from .models import User, ViewerPermission

serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")


def normalize_username(username: str) -> str:
    """Collapses any run of whitespace (including a full-width IME space,
    which Python's \\s matches) down to a single regular space and trims the
    ends. Account creation, password reset, and login all funnel the
    username through this, so a full-width space typed by accident in one
    place but not the other (an easy mistake when switching in/out of a
    Chinese input method) can't silently make two identical-looking
    usernames fail to match."""
    return re.sub(r"\s+", " ", username.strip())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = serializer.loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    uid = read_session_token(token)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not user.is_active:
        # PRD V1.2 §3.1: disabling an account must take effect immediately,
        # not just block the next login - an already-open session is cut off
        # here on its very next request.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已被禁用，请联系管理员")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可执行此操作")
    return user


@dataclass
class AllowedScope:
    """A viewer's visible-data allowlist (PRD V1.2 §1). `rules is None` means
    unrestricted (always true for admin). Otherwise it's the list of that
    viewer's active grant rules - each already a self-contained (entity[,
    department]) pair - and their visible data is the UNION of those rules
    (see compute/scope.py's apply_permission_scope, which does the actual
    query-level filtering). An empty list means zero grants: sees nothing,
    not everything."""

    rules: list[ScopeRule] | None


def get_allowed_scope(db: Session, user: User) -> AllowedScope:
    if user.role == "admin":
        return AllowedScope(rules=None)
    grants = (
        db.query(ViewerPermission)
        .filter(ViewerPermission.user_id == user.id, ViewerPermission.is_active == True)  # noqa: E712
        .all()
    )
    return AllowedScope(rules=[ScopeRule(entity=g.entity, department1=g.department1) for g in grants])


def resolve_requested_filters(
    scope: AllowedScope, requested_department: str | None, requested_entity: str | None
) -> tuple[str | None, str | None]:
    """Validates whatever the caller explicitly asked to view (a specific
    department and/or entity picked in the UI) against their granted rules,
    raising a clear 403 for a request that's obviously outside every rule.
    This is a UX nicety, not the security boundary itself - the real
    enforcement is apply_permission_scope at the query layer, which every
    compute/*.py call site also applies with `scope.rules`, so even a
    request that slips past this check can never read outside the granted
    rules (it would just come back empty)."""
    if scope.rules is None:  # admin - unrestricted
        return requested_department, requested_entity

    if requested_entity and requested_entity not in {r.entity for r in scope.rules}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"无权查看「{requested_entity}」实体的数据")

    if requested_department:
        explicit_departments = {r.department1 for r in scope.rules if r.department1}
        has_entity_wide_rule = any(r.department1 is None for r in scope.rules)
        if requested_department not in explicit_departments and not has_entity_wide_rule:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"无权查看「{requested_department}」部门的数据")

    return requested_department, requested_entity
