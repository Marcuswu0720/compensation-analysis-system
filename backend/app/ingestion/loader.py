"""Orchestrates: parse workbook -> normalize -> build staged payload for review.

Nothing here writes to the real snapshot tables. Per PRD 5.1, a month's data
only becomes "official" (written into monthly_employee_snapshot etc.) after a
human reviews the validation summary and confirms it via the /upload/{id}/confirm
endpoint (see routers/upload.py + commit.py).
"""

import io
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import DataQualityLog, MonthlyEmployeeSnapshot, UploadBatch
from .constants import BONUS_MONTH_OFFSET, BONUS_SHEET_KEYS, EMPLOYEE_SHEET_KEYS
from .normalize import NameResolver
from .parser import get, parse_workbook
from .supplemental import parse_supplemental_workbook

SALARY_TYPES = ("base", "bonus", "backpay")


def shift_month(month: str, offset: int) -> str:
    year, mon = (int(x) for x in month.split("-"))
    idx = year * 12 + (mon - 1) + offset
    y, m = divmod(idx, 12)
    return f"{y:04d}-{m + 1:02d}"


def _is_active_employee(role: str, row: dict, hmap: dict) -> tuple[bool, str | None]:
    if role == "formal":
        resign = get(row, hmap, "resign_date")
        return (resign in (None, ""), str(resign) if resign else None)
    exit_val = get(row, hmap, "exit_date")
    if exit_val is None or exit_val == "":
        return True, None
    if isinstance(exit_val, str) and exit_val.strip().lower() == "active":
        return True, None
    return False, str(exit_val)


def stage_upload(
    db: Session, month: str, file_bytes: bytes, filename: str, uploaded_by: str, salary_type: str = "base"
) -> UploadBatch:
    if salary_type not in SALARY_TYPES:
        raise ValueError(f"salary_type 必须是 {SALARY_TYPES} 之一")
    if salary_type == "base":
        staged_data = _stage_base(db, month, file_bytes)
    else:
        staged_data = _stage_supplemental(db, month, file_bytes, salary_type)

    batch = UploadBatch(
        month=month,
        salary_type=salary_type,
        original_filename=filename,
        uploaded_by=uploaded_by,
        status="pending_review",
        staged_data=json.dumps(staged_data),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def _stage_base(db: Session, month: str, file_bytes: bytes) -> dict:
    parsed = parse_workbook(io.BytesIO(file_bytes))
    resolver = NameResolver(db, month)

    # Pass 1: tally every raw department/entity label in the whole workbook so
    # canonical forms are stable before any row gets tagged (see normalize.py
    # docstring for why this must happen before the per-row resolve() calls).
    raw_depts: list = []
    raw_entities: list = []
    for role in EMPLOYEE_SHEET_KEYS + BONUS_SHEET_KEYS + ["exits"]:
        sheet_result = parsed.by_role.get(role)
        if not sheet_result:
            continue
        for row in sheet_result.rows:
            raw_depts.append(get(row, sheet_result.header_map, "department1"))
            raw_entities.append(get(row, sheet_result.header_map, "entity"))
    resolver.prepare("department", raw_depts)
    resolver.prepare("entity", raw_entities)

    employees: dict[str, dict] = {}
    for role in EMPLOYEE_SHEET_KEYS:
        sheet_result = parsed.by_role.get(role)
        if not sheet_result:
            continue
        for row in sheet_result.rows:
            sid = get(row, sheet_result.header_map, "staff_id")
            if not sid:
                continue
            sid = str(sid).strip()
            is_active, status_date = _is_active_employee(role, row, sheet_result.header_map)
            dept_raw = get(row, sheet_result.header_map, "department1")
            entity_raw = get(row, sheet_result.header_map, "entity")
            employees[sid] = {
                "staff_id": sid,
                "staff_name": get(row, sheet_result.header_map, "staff_name"),
                "entity": resolver.resolve("entity", entity_raw),
                "entity_raw": entity_raw,
                "employment_type": "Formal" if role == "formal" else "Contract",
                "department1": resolver.resolve("department", dept_raw),
                "department1_raw": dept_raw,
                "job_grade": get(row, sheet_result.header_map, "job_grade"),
                "hr_cost": float(get(row, sheet_result.header_map, "hr_cost") or 0),
                "total_gross_salary": get(row, sheet_result.header_map, "total_gross"),
                "is_active": is_active,
                "resign_or_exit_date": status_date,
                "source_sheet": sheet_result.sheet_name,
            }

    bonuses: list[dict] = []
    for role, entity_hint in (("bonus_pp", "PalmPay"), ("bonus_flexi", "Flexi")):
        sheet_result = parsed.by_role.get(role)
        if not sheet_result:
            continue
        performance_month = shift_month(month, BONUS_MONTH_OFFSET)
        for row in sheet_result.rows:
            sid = get(row, sheet_result.header_map, "staff_id")
            if not sid:
                continue
            dept_raw = get(row, sheet_result.header_map, "department1")
            bonuses.append(
                {
                    "performance_month": performance_month,
                    "payment_month": month,
                    "staff_id": str(sid).strip(),
                    "entity": resolver.resolve("entity", get(row, sheet_result.header_map, "entity") or entity_hint),
                    "department1": resolver.resolve("department", dept_raw),
                    "performance_bonus": float(get(row, sheet_result.header_map, "performance_bonus") or 0),
                    "commission": float(get(row, sheet_result.header_map, "commission") or 0),
                    "other_income": float(get(row, sheet_result.header_map, "other_income") or 0),
                    "deduction": float(get(row, sheet_result.header_map, "deduction") or 0),
                    "bonus_total": float(get(row, sheet_result.header_map, "bonus_total") or 0),
                }
            )

    exits: list[dict] = []
    exits_sheet = parsed.by_role.get("exits")
    if exits_sheet:
        for row in exits_sheet.rows:
            sid = get(row, exits_sheet.header_map, "staff_id")
            if not sid:
                continue
            dept_raw = get(row, exits_sheet.header_map, "department1")
            exits.append(
                {
                    "staff_id": str(sid).strip(),
                    "staff_name": get(row, exits_sheet.header_map, "staff_name"),
                    "entity": resolver.resolve("entity", get(row, exits_sheet.header_map, "entity")),
                    "department1": resolver.resolve("department", dept_raw),
                    "reason_for_leaving": get(row, exits_sheet.header_map, "reason_for_leaving"),
                    "exit_type": get(row, exits_sheet.header_map, "exit_type"),
                    "attrition_type": get(row, exits_sheet.header_map, "attrition_type"),
                    "exit_date": str(get(row, exits_sheet.header_map, "exit_date_record") or "") or None,
                }
            )

    issues = []
    for msg in parsed.missing_field_issues:
        issues.append({"issue_type": "missing_field", "issue_detail": msg, "row_count_affected": 0})
    if parsed.unmatched_sheets:
        issues.append(
            {
                "issue_type": "unrecognized_sheet",
                "issue_detail": f"未识别的sheet，未纳入本次统计: {parsed.unmatched_sheets}",
                "row_count_affected": 0,
            }
        )
    if not exits_sheet or not exits_sheet.sheet_name:
        issues.append(
            {
                "issue_type": "missing_sheet",
                "issue_detail": "未找到离职名单 sheet（本月可能确实没有维护离职表，请人工确认）",
                "row_count_affected": 0,
            }
        )
    issues.extend(resolver.flush_issues())

    prev_month_headcount = (
        db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.month == shift_month(month, -1)).count()
    )
    all_employees = list(employees.values())
    active_employees = [e for e in all_employees if e["is_active"]]
    # "本月总人数" = everyone with a payroll record this month (cash-flow basis,
    # same definition used by get_trend/compute_attribution) - this is what
    # the confirmed snapshot table will report, not just the still-active subset.
    total_hr_cost = sum(e["hr_cost"] for e in all_employees)

    staged_data = {
        "employees": all_employees,
        "bonuses": bonuses,
        "exits": exits,
        "issues": issues,
        "summary": {
            "headcount_total": len(all_employees),
            "headcount_still_active": len(active_employees),
            "headcount_resigned_this_month": len(all_employees) - len(active_employees),
            "total_hr_cost": total_hr_cost,
            "prev_month_headcount": prev_month_headcount,
            "headcount_delta": (len(all_employees) - prev_month_headcount) if prev_month_headcount else None,
            "sheets_found": {role: r.sheet_name for role, r in parsed.by_role.items()},
        },
    }
    return staged_data


def _stage_supplemental(db: Session, month: str, file_bytes: bytes, salary_type: str) -> dict:
    parsed = parse_supplemental_workbook(io.BytesIO(file_bytes))
    resolver = NameResolver(db, month)

    resolver.prepare("department", [r["department1_raw"] for r in parsed.rows])
    resolver.prepare("entity", [r["entity_raw"] for r in parsed.rows])

    base_employees = {
        e.staff_id: e
        for e in db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.month == month).all()
    }

    entries = []
    unmatched_count = 0
    for r in parsed.rows:
        base = base_employees.get(r["staff_id"])
        department1_raw = r["department1_raw"] or (base.department1_raw if base else None)
        entity_raw = r["entity_raw"] or (base.entity if base else None)
        matched = base is not None
        if not matched:
            unmatched_count += 1
        entries.append(
            {
                "staff_id": r["staff_id"],
                "staff_name": r["staff_name"] or (base.staff_name if base else None),
                "department1": resolver.resolve("department", department1_raw),
                "entity": resolver.resolve("entity", entity_raw),
                "amount": r["amount"],
                "source_sheet": r["source_sheet"],
                "matched_base_employee": matched,
            }
        )

    issues = [
        {"issue_type": "unrecognized_sheet", "issue_detail": f"未能解析的sheet: {s}", "row_count_affected": 0}
        for s in parsed.skipped_sheets
    ]
    if unmatched_count:
        issues.append(
            {
                "issue_type": "unmatched_supplemental_staff",
                "issue_detail": (
                    f"有 {unmatched_count} 条记录的员工工号在 {month} 的底薪批次里找不到（可能底薪还没上传，"
                    "或该员工当月不在职），这些金额仍会计入公司/部门总成本，但在归因分析里不会被归到具体某个人身上"
                ),
                "row_count_affected": unmatched_count,
            }
        )
    issues.extend(resolver.flush_issues())

    total_amount = sum(e["amount"] for e in entries)
    return {
        "entries": entries,
        "issues": issues,
        "summary": {
            "salary_type": salary_type,
            "row_count": len(entries),
            "matched_count": len(entries) - unmatched_count,
            "unmatched_count": unmatched_count,
            "total_amount": total_amount,
            "sheets_found": parsed.sheet_names,
        },
    }
