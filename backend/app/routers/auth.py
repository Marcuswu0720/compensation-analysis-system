from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..compute.trends import list_departments_by_entity
from ..config import settings
from ..database import get_db
from ..models import DataOperationLog, DownloadLog, User, ViewerPermission
from ..schemas import CreateUserRequest, GrantPermissionRequest, LoginRequest, ResetPasswordRequest, SetUserActiveRequest
from ..security import create_session_token, get_current_user, hash_password, normalize_username, require_admin, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    username = normalize_username(payload.username)
    password = payload.password.strip()
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="账号已被禁用，请联系管理员")
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
    username = normalize_username(payload.username)
    password = payload.password.strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=username, password_hash=hash_password(password), role=payload.role)
    db.add(user)
    db.commit()
    return {"username": user.username, "role": user.role}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    users = db.query(User).order_by(User.username).all()
    return [{"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active} for u in users]


@router.post("/users/{user_id}/active")
def set_user_active(
    user_id: int, payload: SetUserActiveRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    if user_id == admin.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="不能禁用自己当前登录的账号")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    target.is_active = payload.is_active
    db.commit()
    return {"id": target.id, "username": target.username, "is_active": target.is_active}


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int, payload: ResetPasswordRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    new_password = payload.new_password.strip()
    if not new_password:
        raise HTTPException(status_code=400, detail="新密码不能为空")
    target.password_hash = hash_password(new_password)
    db.commit()
    return {"ok": True}


@router.get("/entity-departments")
def entity_departments(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Entity -> department list, unrestricted, for the permission-grant
    form's linked dropdowns (PRD V1.2 §1.4) - admin only, since it exposes
    the full org structure regardless of any viewer's own scope."""
    return list_departments_by_entity(db)


@router.get("/users/{user_id}/permissions")
def list_permissions(
    user_id: int, include_revoked: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    q = db.query(ViewerPermission).filter(ViewerPermission.user_id == user_id)
    if not include_revoked:
        q = q.filter(ViewerPermission.is_active == True)  # noqa: E712
    grants = q.order_by(ViewerPermission.granted_time.desc()).all()
    return [
        {
            "id": g.id,
            "scope_type": g.scope_type,
            "entity": g.entity,
            "department1": g.department1,
            "is_active": g.is_active,
            "granted_by": g.granted_by,
            "granted_time": g.granted_time.isoformat(),
            "revoked_by": g.revoked_by,
            "revoked_time": g.revoked_time.isoformat() if g.revoked_time else None,
        }
        for g in grants
    ]


@router.post("/users/{user_id}/permissions")
def grant_permission(
    user_id: int, payload: GrantPermissionRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    if payload.scope_type not in ("entity", "entity_department"):
        raise HTTPException(status_code=400, detail="scope_type 必须是 entity 或 entity_department")
    if not payload.entity:
        raise HTTPException(status_code=400, detail="entity 不能为空")
    if payload.scope_type == "entity_department" and not payload.department1:
        raise HTTPException(status_code=400, detail="选择“实体下的特定部门”时必须指定 department1")
    department1 = payload.department1 if payload.scope_type == "entity_department" else None

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    exists = (
        db.query(ViewerPermission)
        .filter(
            ViewerPermission.user_id == user_id,
            ViewerPermission.scope_type == payload.scope_type,
            ViewerPermission.entity == payload.entity,
            ViewerPermission.department1 == department1,
            ViewerPermission.is_active == True,  # noqa: E712
        )
        .first()
    )
    if exists:
        return {"id": exists.id, "scope_type": exists.scope_type, "entity": exists.entity, "department1": exists.department1}

    grant = ViewerPermission(
        user_id=user_id,
        scope_type=payload.scope_type,
        entity=payload.entity,
        department1=department1,
        granted_by=admin.username,
        granted_time=datetime.utcnow(),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return {"id": grant.id, "scope_type": grant.scope_type, "entity": grant.entity, "department1": grant.department1}


@router.delete("/users/{user_id}/permissions/{permission_id}")
def revoke_permission(
    user_id: int, permission_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    grant = (
        db.query(ViewerPermission)
        .filter(ViewerPermission.id == permission_id, ViewerPermission.user_id == user_id)
        .first()
    )
    if not grant:
        raise HTTPException(status_code=404, detail="权限记录不存在")
    # Soft-revoke (PRD V1.2 §3.2): keep the row, stamp who/when revoked it, so
    # "what could this account see, and when" stays fully reconstructable.
    grant.is_active = False
    grant.revoked_by = admin.username
    grant.revoked_time = datetime.utcnow()
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


@router.get("/download-log")
def download_log(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """PRD V1.3 §4: who downloaded what range, when - a downloaded file is
    outside the system's access control the moment it leaves, so this is
    the trace that matters most if salary data ever leaks."""
    logs = db.query(DownloadLog).order_by(DownloadLog.download_time.desc()).limit(200).all()
    return [
        {
            "id": log.id,
            "username": log.username,
            "download_time": log.download_time.isoformat(),
            "entity_scope": log.entity_scope,
            "department_scope": log.department_scope,
            "month_range_start": log.month_range_start,
            "month_range_end": log.month_range_end,
            "row_count": log.row_count,
        }
        for log in logs
    ]
