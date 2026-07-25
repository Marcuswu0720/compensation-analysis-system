"""PRD V1.3: employee-level salary detail Excel export.

Available to both admin and viewer accounts - the permission boundary is
entirely the same entity/entity_department rule set used everywhere else
(see compute/scope.py, security.get_allowed_scope), never a separate
department-name string filter. Every download is logged to download_log
(PRD V1.3 §4) since a downloaded file is completely outside the system's
access control the moment it leaves - that log is what lets someone later
reconstruct which export a leak came from.
"""

import io
from datetime import datetime
from urllib.parse import quote

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from ..compute.export import EXPORT_COLUMNS, get_employee_detail_rows
from ..compute.trends import list_available_months
from ..database import get_db
from ..models import DownloadLog, User
from ..schemas import ExportDetailRequest
from ..security import get_allowed_scope, get_current_user, resolve_requested_filters

router = APIRouter(prefix="/api/export", tags=["export"])

_UNSAFE_FILENAME_CHARS = str.maketrans({c: "_" for c in '/\\:*?"<>|'})


def _scope_label(requested: str | None, rules, kind: str) -> str:
    """Best-effort human label for the filename/watermark - never used for
    any access-control decision, purely descriptive."""
    if requested:
        return requested
    if rules is None:
        return "全公司" if kind == "entity" else "全部部门"
    if len(rules) == 1:
        r = rules[0]
        if kind == "entity":
            return r.entity
        return r.department1 or "全部部门"
    return "已授权范围"


@router.post("/detail")
def export_detail(payload: ExportDetailRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = get_allowed_scope(db, user)
    if scope.rules is not None and not scope.rules:
        raise HTTPException(status_code=403, detail="你的账号还没有被分配任何可查看的部门/实体范围，找管理员开通权限后再来下载。")

    department, entity = resolve_requested_filters(scope, payload.department, payload.entity)

    available = list_available_months(db)
    if not available:
        raise HTTPException(status_code=400, detail="还没有任何已入库的数据可以导出")
    start_month = payload.start_month or available[0]
    end_month = payload.end_month or available[-1]
    months = [m for m in available if start_month <= m <= end_month]
    if not months:
        raise HTTPException(status_code=400, detail=f"{start_month} 至 {end_month} 之间没有任何已入库的数据")

    rows, unattributed_by_month = get_employee_detail_rows(
        db, months=months, department=department, entity=entity, scope_rules=scope.rules
    )

    entity_label = _scope_label(entity, scope.rules, "entity")
    department_label = _scope_label(department, scope.rules, "department")
    now = datetime.utcnow()

    workbook_bytes = _build_workbook(rows, user.username, now, entity_label, department_label, start_month, end_month, unattributed_by_month)

    db.add(
        DownloadLog(
            user_id=user.id,
            username=user.username,
            download_time=now,
            entity_scope=entity_label,
            department_scope=department_label,
            month_range_start=start_month,
            month_range_end=end_month,
            row_count=len(rows),
        )
    )
    db.commit()

    safe_entity = entity_label.translate(_UNSAFE_FILENAME_CHARS)
    safe_department = department_label.translate(_UNSAFE_FILENAME_CHARS)
    filename = f"薪酬明细_{safe_entity}_{safe_department}_{start_month}至{end_month}_{now.strftime('%Y%m%d%H%M%S')}.xlsx"
    return StreamingResponse(
        io.BytesIO(workbook_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def _build_workbook(rows, username, now, entity_label, department_label, start_month, end_month, unattributed_by_month) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "薪酬明细"

    # Metadata/watermark block (PRD V1.3 §3.2) - a low-cost but genuinely
    # useful traceability measure: if this file is ever forwarded outside
    # the company, whoever finds it can see exactly who exported it and when.
    watermark_lines = [
        f"本文件由 {username} 于 {now.strftime('%Y-%m-%d %H:%M:%S')} 导出",
        f"数据范围：{entity_label}-{department_label}，{start_month} 至 {end_month}",
        "内容涉及员工薪酬明细，请遵守公司薪酬保密规定，不得外传",
    ]
    if unattributed_by_month:
        detail = "；".join(f"{m}: ₦{amt:,.2f}" for m, amt in sorted(unattributed_by_month.items()))
        watermark_lines.append(f"提示：以下月份存在无法关联到具体在职员工的奖金/补发金额，未计入下表个人明细，但已计入公司/部门总成本：{detail}")

    for line in watermark_lines:
        ws.append([line])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, size=9, color="666666")
    ws.append([])

    header_row = ws.max_row + 1
    ws.append([label for _, label in EXPORT_COLUMNS])
    for col_idx in range(1, len(EXPORT_COLUMNS) + 1):
        ws.cell(row=header_row, column=col_idx).font = Font(bold=True)

    for row in rows:
        ws.append([row[key] for key, _ in EXPORT_COLUMNS])

    for col_idx, (key, label) in enumerate(EXPORT_COLUMNS, start=1):
        width = max(len(label) * 1.8, 12)
        ws.column_dimensions[ws.cell(row=header_row, column=col_idx).column_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
