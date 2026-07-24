from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import DataOperationLog, User, ViewerPermission
from ..schemas import CreateUserRequest, GrantPermissionRequest, LoginRequest
from ..security import create_session_token, get_current_user, hash_password, require_admin, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_session_token(user.id)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
    )
    return {"username": user.username, "role": user.role}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.session_cookie_name)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}


@router.post("/users")
def create_user(payload: CreateUserRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if payload.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="role 必须是 admin 或 viewer")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    return {"username": user.username, "role": user.role}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    users = db.query(User).order_by(User.username).all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]


@router.get("/users/{user_id}/permissions")
def list_permissions(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    grants = db.query(ViewerPermission).filter(ViewerPermission.user_id == user_id).all()
    return [{"id": g.id, "scope_type": g.scope_type, "scope_value": g.scope_value} for g in grants]


@router.post("/users/{user_id}/permissions")
def grant_permission(
    user_id: int, payload: GrantPermissionRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    if payload.scope_type not in ("department", "entity"):
        raise HTTPException(status_code=400, detail="scope_type 必须是 department 或 entity")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    exists = (
        db.query(ViewerPermission)
        .filter(
            ViewerPermission.user_id == user_id,
            ViewerPermission.scope_type == payload.scope_type,
            ViewerPermission.scope_value == payload.scope_value,
        )
        .first()
    )
    if exists:
        return {"id": exists.id, "scope_type": exists.scope_type, "scope_value": exists.scope_value}
    grant = ViewerPermission(user_id=user_id, scope_type=payload.scope_type, scope_value=payload.scope_value)
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return {"id": grant.id, "scope_type": grant.scope_type, "scope_value": grant.scope_value}


@router.delete("/users/{user_id}/permissions/{permission_id}")
def revoke_permission(
    user_id: int, permission_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    grant = (
        db.query(ViewerPermission)
        .filter(ViewerPermission.id == permission_id, ViewerPermission.user_id == user_id)
        .first()
    )
    if not grant:
        raise HTTPException(status_code=404, detail="权限记录不存在")
    db.delete(grant)
    db.commit()
    return {"ok": True}


@router.get("/operation-log")
def operation_log(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    logs = db.query(DataOperationLog).order_by(DataOperationLog.operation_time.desc()).limit(200).all()
    return [
        {
            "id": log.id,
            "operator": log.operator,
            "operation_type": log.operation_type,
            "target_month": log.target_month,
            "operation_time": log.operation_time.isoformat(),
            "detail": log.detail,
        }
        for log in logs
    ]
