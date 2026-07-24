from dataclasses import dataclass

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User, ViewerPermission

serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")


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
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可执行此操作")
    return user


@dataclass
class AllowedScope:
    """A viewer's visible-data allowlist. `None` on either field means
    unrestricted (always true for admin); an empty list means "no grants of
    this type" and is treated as no additional restriction on that axis,
    UNLESS the viewer has zero grants of both types at all - a freshly
    created viewer sees nothing until an admin grants them something, rather
    than defaulting to full access (see resolve_scope_filters)."""

    departments: list[str] | None
    entities: list[str] | None


NO_ACCESS_SENTINEL = ["__no_department_or_entity_granted__"]


def get_allowed_scope(db: Session, user: User) -> AllowedScope:
    if user.role == "admin":
        return AllowedScope(departments=None, entities=None)
    grants = db.query(ViewerPermission).filter(ViewerPermission.user_id == user.id).all()
    departments = [g.scope_value for g in grants if g.scope_type == "department"]
    entities = [g.scope_value for g in grants if g.scope_type == "entity"]
    return AllowedScope(departments=departments, entities=entities)


def resolve_scope_filters(
    scope: AllowedScope, requested_department: str | None, requested_entity: str | None
) -> tuple[str | list[str] | None, str | list[str] | None]:
    """Turns a viewer's allowlist + whatever they asked for into the actual
    department/entity filter values to pass into compute/*.py. Raises 403 if
    they explicitly asked for something outside their grants."""
    if scope.departments is None:  # admin - unrestricted
        return requested_department, requested_entity

    if not scope.departments and not scope.entities:
        # No grants of either type yet - see nothing, not everything.
        return NO_ACCESS_SENTINEL, requested_entity

    if requested_department:
        if requested_department not in scope.departments:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"无权查看「{requested_department}」部门的数据")
        department_filter: str | list[str] | None = requested_department
    else:
        department_filter = scope.departments or None

    if requested_entity:
        if requested_entity not in scope.entities:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"无权查看「{requested_entity}」实体的数据")
        entity_filter: str | list[str] | None = requested_entity
    else:
        entity_filter = scope.entities or None

    return department_filter, entity_filter


def resolve_department_axis(scope: AllowedScope) -> list[str] | None:
    """For endpoints that compare *across* departments (so a single
    department/entity filter doesn't apply) - the same empty-means-
    unrestricted-on-this-axis rule as resolve_scope_filters, standalone."""
    if scope.departments is None:  # admin
        return None
    if not scope.departments and not scope.entities:
        return NO_ACCESS_SENTINEL
    return scope.departments or None
