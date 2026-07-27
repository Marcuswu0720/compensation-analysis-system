import io
import json
import re
from datetime import datetime
from urllib.parse import quote

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from ..compute.categories import COMPOSITION_REAL_FIELDS
from ..compute.export import RECONCILIATION_COLUMNS, build_department_category_summary
from ..database import get_db
from ..ingestion.commit import confirm_upload, delete_confirmed_batch, reassign_month
from ..ingestion.loader import SALARY_TYPES, stage_upload
from ..models import User, UploadBatch
from ..schemas import ReassignMonthRequest
from ..security import require_admin

router = APIRouter(prefix="/api/upload", tags=["upload"])

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Per PRD V1.1 §3.1: only the admin uploads/confirms/rejects/deletes/corrects
# data. Viewers are read-only and never touch this router.


@router.post("")
async def upload_file(
    month: str,
    salary_type: str,
    file: UploadFile,
    category: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if not MONTH_RE.match(month):
        raise HTTPException(status_code=400, detail="month 格式必须为 YYYY-MM")
    if salary_type not in SALARY_TYPES:
        raise HTTPException(status_code=400, detail=f"salary_type 必须是 {SALARY_TYPES} 之一")
    if category:
        if salary_type != "backpay":
            raise HTTPException(status_code=400, detail="category 只能在上传补发薪资批次时指定")
        if category not in COMPOSITION_REAL_FIELDS:
            raise HTTPException(status_code=400, detail=f"category 必须是 {COMPOSITION_REAL_FIELDS} 之一")
    content = await file.read()
    try:
        batch = stage_upload(
            db,
            month=month,
            file_bytes=content,
            filename=file.filename,
            uploaded_by=user.username,
            salary_type=salary_type,
            category=category,
        )
    except Exception as e:  # noqa: BLE001 - surface parsing failures to the uploader
        raise HTTPException(status_code=422, detail=f"解析失败: {e}") from e
    return _batch_summary(batch)


@router.get("")
def list_batches(
    status: str | None = None,
    salary_type: str | None = None,
    month: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(UploadBatch)
    if status:
        query = query.filter(UploadBatch.status == status)
    if salary_type:
        query = query.filter(UploadBatch.salary_type == salary_type)
    if month:
        query = query.filter(UploadBatch.month == month)
    # 数据管理页面需要看到全部批次，不只是最近的一小部分，所以这里不做 limit。
    batches = query.order_by(UploadBatch.uploaded_at.desc()).all()
    return [
        {
            "id": b.id,
            "month": b.month,
            "salary_type": b.salary_type,
            "category": b.category,
            "status": b.status,
            "original_filename": b.original_filename,
            "uploaded_by": b.uploaded_by,
            "uploaded_at": b.uploaded_at.isoformat(),
        }
        for b in batches
    ]


@router.get("/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    batch = _get_batch_or_404(db, batch_id)
    return _batch_summary(batch)


@router.get("/{batch_id}/reconciliation-export")
def reconciliation_export(batch_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """PRD V1.5 §1: a per-(Entity, Department1) x salary-category Excel of a
    staged batch, for the admin to cross-check offline against the comp
    team's historical numbers before confirming. Works on the staged JSON
    payload directly - the batch doesn't need to be confirmed yet."""
    batch = _get_batch_or_404(db, batch_id)
    if batch.salary_type != "base":
        raise HTTPException(status_code=400, detail="只有底薪批次支持分部门×分薪资类目核对导出")
    payload = json.loads(batch.staged_data)
    employees = payload.get("employees", [])
    if not employees:
        raise HTTPException(status_code=400, detail="这个批次没有员工数据，无法生成核对文件")

    rows = build_department_category_summary(employees)
    workbook_bytes = _build_reconciliation_workbook(rows, batch.month)
    filename = f"分部门核对_{batch.month}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.xlsx"
    return StreamingResponse(
        io.BytesIO(workbook_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/{batch_id}/confirm")
def confirm(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    batch = _get_batch_or_404(db, batch_id)
    try:
        confirm_upload(db, batch, operator=user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _batch_summary(batch)


@router.post("/{batch_id}/reject")
def reject(batch_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    batch = _get_batch_or_404(db, batch_id)
    if batch.status == "confirmed":
        raise HTTPException(status_code=400, detail="该批次已确认，不能撤销，如需撤销请使用删除")
    batch.status = "rejected"
    db.commit()
    return _batch_summary(batch)


@router.delete("/{batch_id}")
def delete_batch(batch_id: int, reason: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    batch = _get_batch_or_404(db, batch_id)
    try:
        delete_confirmed_batch(db, batch, operator=user.username, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.post("/{batch_id}/reassign-month")
def reassign(
    batch_id: int,
    payload: ReassignMonthRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if not MONTH_RE.match(payload.new_month):
        raise HTTPException(status_code=400, detail="new_month 格式必须为 YYYY-MM")
    batch = _get_batch_or_404(db, batch_id)
    try:
        reassign_month(db, batch, payload.new_month, operator=user.username)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _batch_summary(batch)


def _get_batch_or_404(db: Session, batch_id: int) -> UploadBatch:
    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="上传批次不存在")
    return batch


def _build_reconciliation_workbook(rows: list[dict], month: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "分部门核对"

    ws.append([f"{month} 分部门 × 分薪资类目核对（校验用，尚未确认入库的数据）"])
    ws.cell(row=1, column=1).font = Font(italic=True, size=9, color="666666")
    ws.append([])

    header_row = ws.max_row + 1
    ws.append([label for _, label in RECONCILIATION_COLUMNS])
    for col_idx in range(1, len(RECONCILIATION_COLUMNS) + 1):
        ws.cell(row=header_row, column=col_idx).font = Font(bold=True)

    totals = {key: 0 for key, _ in RECONCILIATION_COLUMNS if key not in ("entity", "department1")}
    for row in rows:
        ws.append([row[key] for key, _ in RECONCILIATION_COLUMNS])
        for key in totals:
            totals[key] += row[key]

    total_row = ["合计", ""] + [totals[key] for key, _ in RECONCILIATION_COLUMNS if key not in ("entity", "department1")]
    ws.append(total_row)
    for col_idx in range(1, len(RECONCILIATION_COLUMNS) + 1):
        ws.cell(row=ws.max_row, column=col_idx).font = Font(bold=True)

    for col_idx, (_, label) in enumerate(RECONCILIATION_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=header_row, column=col_idx).column_letter].width = max(len(label) * 1.8, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _batch_summary(batch: UploadBatch) -> dict:
    payload = json.loads(batch.staged_data)
    return {
        "id": batch.id,
        "month": batch.month,
        "salary_type": batch.salary_type,
        "category": batch.category,
        "status": batch.status,
        "original_filename": batch.original_filename,
        "uploaded_by": batch.uploaded_by,
        "uploaded_at": batch.uploaded_at.isoformat(),
        "summary": payload["summary"],
        "issues": payload["issues"],
    }
