"""PRD V1.3 (base) + V1.5 §2 (batch-type filter, availability check, and
Formal/Contract sheet split) + V1.6 (full field templates + field-count
self-check): employee-level salary detail Excel export.

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

from ..compute.export import (
    BACKPAY_EXPORT_COLUMNS,
    SALARY_TYPE_LABEL,
    SALARY_TYPES,
    bonus_sheet_columns,
    check_month_type_availability,
    contract_sheet_columns,
    formal_sheet_columns,
    get_backpay_detail_rows,
    get_base_full_detail_rows,
    get_bonus_detail_rows,
    verify_sheet_field_count,
)
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

    salary_types = payload.salary_types or list(SALARY_TYPES)
    invalid = set(salary_types) - set(SALARY_TYPES)
    if invalid:
        raise HTTPException(status_code=400, detail=f"salary_types 里有无法识别的批次类型: {sorted(invalid)}，可选值是 {SALARY_TYPES}")

    available = list_available_months(db)
    if not available:
        raise HTTPException(status_code=400, detail="还没有任何已入库的数据可以导出")
    start_month = payload.start_month or available[0]
    end_month = payload.end_month or available[-1]
    months = [m for m in available if start_month <= m <= end_month]
    if not months:
        raise HTTPException(status_code=400, detail=f"{start_month} 至 {end_month} 之间没有任何已入库的数据")

    availability = check_month_type_availability(
        db, months=months, salary_types=salary_types, department=department, entity=entity, scope_rules=scope.rules
    )
    missing = [(m, t) for m in months for t in salary_types if not availability[(m, t)]]
    if len(missing) == len(months) * len(salary_types):
        # Nothing at all in the requested range/type/scope - PRD V1.5 §2.1:
        # refuse with a clear reason instead of generating an empty file.
        if len(months) == 1 and len(salary_types) == 1:
            detail = f"{months[0]} 的{SALARY_TYPE_LABEL[salary_types[0]]}暂无数据，可能尚未上传"
        else:
            detail = "所选月份/批次类型范围内暂无数据，可能尚未上传：" + "、".join(f"{m} {SALARY_TYPE_LABEL[t]}" for m, t in missing)
        raise HTTPException(status_code=400, detail=detail)

    base_rows: list[dict] = []
    if "base" in salary_types:
        base_rows = get_base_full_detail_rows(db, months=months, department=department, entity=entity, scope_rules=scope.rules)
    bonus_rows: list[dict] = []
    if "bonus" in salary_types:
        bonus_rows = get_bonus_detail_rows(db, months=months, department=department, entity=entity, scope_rules=scope.rules)
    backpay_rows: list[dict] = []
    if "backpay" in salary_types:
        backpay_rows = get_backpay_detail_rows(db, months=months, department=department, entity=entity, scope_rules=scope.rules)

    entity_label = _scope_label(entity, scope.rules, "entity")
    department_label = _scope_label(department, scope.rules, "department")
    now = datetime.utcnow()

    try:
        workbook_bytes = _build_workbook(
            base_rows,
            bonus_rows,
            backpay_rows,
            salary_types,
            user.username,
            now,
            entity_label,
            department_label,
            start_month,
            end_month,
            missing,
        )
    except ValueError as exc:
        # PRD V1.6's field-count self-check tripped - surface loudly instead
        # of ever handing out a silently-incomplete file (this is the
        # failure mode the self-check exists to catch).
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    db.add(
        DownloadLog(
            user_id=user.id,
            username=user.username,
            download_time=now,
            entity_scope=entity_label,
            department_scope=department_label,
            month_range_start=start_month,
            month_range_end=end_month,
            row_count=len(base_rows) + len(bonus_rows) + len(backpay_rows),
            salary_types=",".join(salary_types),
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


def _write_watermark_sheet(wb, username, now, entity_label, department_label, start_month, end_month, salary_types, missing) -> None:
    ws = wb.active
    ws.title = "说明"
    lines = [
        f"本文件由 {username} 于 {now.strftime('%Y-%m-%d %H:%M:%S')} 导出",
        f"数据范围：{entity_label}-{department_label}，{start_month} 至 {end_month}",
        "批次类型：" + "、".join(SALARY_TYPE_LABEL[t] for t in salary_types),
        "内容涉及员工薪酬明细，请遵守公司薪酬保密规定，不得外传",
    ]
    if missing:
        lines.append(
            "提示：以下月份/批次类型组合在所选范围内暂无数据，可能尚未上传，未包含在下面的sheet里："
            + "、".join(f"{m} {SALARY_TYPE_LABEL[t]}" for m, t in missing)
        )
    for line in lines:
        ws.append([line])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, size=9, color="666666")


def _write_data_sheet(wb, title: str, rows: list[dict], columns: list[tuple]) -> None:
    ws = wb.create_sheet(title)
    ws.append([label for _, label in columns])
    for col_idx in range(1, len(columns) + 1):
        ws.cell(row=1, column=col_idx).font = Font(bold=True)
    for row in rows:
        ws.append([row.get(key) for key, _ in columns])
    for col_idx, (_, label) in enumerate(columns, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max(len(label) * 1.8, 12)


def _build_workbook(base_rows, bonus_rows, backpay_rows, salary_types, username, now, entity_label, department_label, start_month, end_month, missing) -> bytes:
    wb = openpyxl.Workbook()
    _write_watermark_sheet(wb, username, now, entity_label, department_label, start_month, end_month, salary_types, missing)

    if "base" in salary_types:
        formal_columns = formal_sheet_columns()
        contract_columns = contract_sheet_columns()
        verify_sheet_field_count("正式工明细", formal_columns)
        verify_sheet_field_count("合同工明细", contract_columns)
        formal_rows = [r for r in base_rows if r["employment_type"] == "Formal"]
        contract_rows = [r for r in base_rows if r["employment_type"] != "Formal"]
        _write_data_sheet(wb, "正式工明细", formal_rows, formal_columns)
        _write_data_sheet(wb, "合同工明细", contract_rows, contract_columns)

    if "bonus" in salary_types:
        bonus_columns = bonus_sheet_columns()
        verify_sheet_field_count("奖金明细", bonus_columns)
        _write_data_sheet(wb, "奖金明细", bonus_rows, bonus_columns)

    if "backpay" in salary_types:
        _write_data_sheet(wb, "补发明细", backpay_rows, BACKPAY_EXPORT_COLUMNS)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
