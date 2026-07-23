import json
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..ingestion.commit import confirm_upload, delete_confirmed_batch, reassign_month
from ..ingestion.loader import SALARY_TYPES, stage_upload
from ..models import User, UploadBatch
from ..schemas import ReassignMonthRequest
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/upload", tags=["upload"])

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.post("")
async def upload_file(
    month: str,
    salary_type: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not MONTH_RE.match(month):
        raise HTTPException(status_code=400, detail="month 格式必须为 YYYY-MM")
    if salary_type not in SALARY_TYPES:
        raise HTTPException(status_code=400, detail=f"salary_type 必须是 {SALARY_TYPES} 之一")
    content = await file.read()
    try:
        batch = stage_upload(
            db, month=month, file_bytes=content, filename=file.filename, uploaded_by=user.username, salary_type=salary_type
        )
    except Exception as e:  # noqa: BLE001 - surface parsing failures to the uploader
        raise HTTPException(status_code=422, detail=f"解析失败: {e}") from e
    return _batch_summary(batch)


@router.get("")
def list_batches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batches = db.query(UploadBatch).order_by(UploadBatch.uploaded_at.desc()).limit(50).all()
    return [
        {
            "id": b.id,
            "month": b.month,
            "salary_type": b.salary_type,
            "status": b.status,
            "original_filename": b.original_filename,
            "uploaded_by": b.uploaded_by,
            "uploaded_at": b.uploaded_at.isoformat(),
        }
        for b in batches
    ]


@router.get("/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _get_batch_or_404(db, batch_id)
    return _batch_summary(batch)


@router.post("/{batch_id}/confirm")
def confirm(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _get_batch_or_404(db, batch_id)
    try:
        confirm_upload(db, batch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _batch_summary(batch)


@router.post("/{batch_id}/reject")
def reject(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _get_batch_or_404(db, batch_id)
    if batch.status == "confirmed":
        raise HTTPException(status_code=400, detail="该批次已确认，不能撤销，如需撤销请使用删除")
    batch.status = "rejected"
    db.commit()
    return _batch_summary(batch)


@router.delete("/{batch_id}")
def delete_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    batch = _get_batch_or_404(db, batch_id)
    try:
        delete_confirmed_batch(db, batch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.post("/{batch_id}/reassign-month")
def reassign(
    batch_id: int,
    payload: ReassignMonthRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not MONTH_RE.match(payload.new_month):
        raise HTTPException(status_code=400, detail="new_month 格式必须为 YYYY-MM")
    batch = _get_batch_or_404(db, batch_id)
    try:
        reassign_month(db, batch, payload.new_month)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _batch_summary(batch)


def _get_batch_or_404(db: Session, batch_id: int) -> UploadBatch:
    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="上传批次不存在")
    return batch


def _batch_summary(batch: UploadBatch) -> dict:
    payload = json.loads(batch.staged_data)
    return {
        "id": batch.id,
        "month": batch.month,
        "salary_type": batch.salary_type,
        "status": batch.status,
        "original_filename": batch.original_filename,
        "uploaded_by": batch.uploaded_by,
        "uploaded_at": batch.uploaded_at.isoformat(),
        "summary": payload["summary"],
        "issues": payload["issues"],
    }
