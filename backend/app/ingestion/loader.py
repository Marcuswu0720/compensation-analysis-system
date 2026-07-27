"""Orchestrates: parse workbook -> normalize -> build staged payload for review.

Nothing here writes to the real snapshot tables. Per PRD 5.1, a month's data
only becomes "official" (written into monthly_employee_snapshot etc.) after a
human reviews the validation summary and confirms it via the /upload/{id}/confirm
endpoint (see routers/upload.py + commit.py).
"""

import io
import json

from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot, UploadBatch
from .bonus_batch import parse_bonus_batch_workbook
from .constants import BONUS_MONTH_OFFSET, BONUS_SHEET_KEYS, EMPLOYEE_SHEET_KEYS
from .date_utils import format_date_value
from .full_fields import (
    ANALYSIS_KEYS,
    CONTRACT_FIELDS,
    FORMAL_FIELDS,
    NEW_DESCRIPTIVE_KEYS,
    TOP_LEVEL_DESCRIPTIVE_KEYS,
    check_field_mapping,
    extract_full_detail,
)
from .header_match import build_header_index
from .normalize import NameResolver
from .parser import get, parse_workbook
from .salary_components import extract_salary_components
from .supplemental import parse_supplemental_workbook

SALARY_TYPES = ("base", "bonus", "backpay")

ROLE_LABEL = {"formal": "正式工", "contract_pp": "合同工(PP)", "contract_flexi": "合同工(Flexi)"}


def shift_month(month: str, offset: int) -> str:
    year, mon = (int(x) for x in month.split("-"))
    idx = year * 12 + (mon - 1) + offset
    y, m = divmod(idx, 12)
    return f"{y:04d}-{m + 1:02d}"


def _is_active_employee(role: str, row: dict, hmap: dict) -> tuple[bool, str | None]:
    if role == "formal":
        resign = get(row, hmap, "resign_date")
        return (resign in (None, ""), format_date_value(resign) if resign else None)
    exit_val = get(row, hmap, "exit_date")
    if exit_val is None or exit_val == "":
        return True, None
    if isinstance(exit_val, str) and exit_val.strip().lower() == "active":
        return True, None
    return False, format_date_value(exit_val)


def _field_mapping_issue(scope_label: str, total: int, matched: int, missing: list[dict]) -> dict:
    """PRD V1.8 §4: the upload-time field-mapping diagnostic - one issue per
    sheet, always present (not just when something's wrong), so the admin
    gets the positive "✓ 全部匹配" confirmation too, not just silence."""
    if not missing:
        return {
            "issue_type": "field_mapping_check",
            "issue_detail": f"{scope_label}：本次解析共 {total} 个目标字段，成功匹配 {matched} 个 ✓",
            "row_count_affected": 0,
        }
    detail_lines = "；".join(
        f"{m['target_label']}（尝试过的别名：{', '.join(m['tried_aliases'])}，均未在原始表头中匹配到，包括归一化大小写空格后）"
        for m in missing
    )
    return {
        "issue_type": "field_mapping_check",
        "issue_detail": (
            f"{scope_label}：本次解析共 {total} 个目标字段，成功匹配 {matched} 个，"
            f"以下字段未能匹配，对应导出结果将为空：{detail_lines}"
        ),
        "row_count_affected": 0,
    }


def stage_upload(
    db: Session,
    month: str,
    file_bytes: bytes,
    filename: str,
    uploaded_by: str,
    salary_type: str = "base",
    category: str | None = None,
) -> UploadBatch:
    if salary_type not in SALARY_TYPES:
        raise ValueError(f"salary_type 必须是 {SALARY_TYPES} 之一")
    if salary_type == "base":
        staged_data = _stage_base(db, month, file_bytes)
    elif salary_type == "bonus":
        staged_data = _stage_bonus_batch(db, month, file_bytes)
    else:
        staged_data = _stage_supplemental(db, month, file_bytes, salary_type)

    batch = UploadBatch(
        month=month,
        salary_type=salary_type,
        # category only means anything for a 补发批次 (see models.py's
        # UploadBatch.category docstring) - a bonus/base upload passing one
        # would be a caller bug, not something to silently store.
        category=category if salary_type == "backpay" else None,
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
    gross_mismatch_count = 0
    field_mapping_issues: list[dict] = []
    for role in EMPLOYEE_SHEET_KEYS:
        sheet_result = parsed.by_role.get(role)
        # NOTE: parse_workbook() always populates every role key with a
        # SheetParseResult (sheet_name=None, rows=[] when nothing matched) -
        # `sheet_result` itself is never falsy, so the check has to be on
        # sheet_name, not truthiness of the dataclass instance. Getting this
        # wrong wouldn't affect the row loop below (it just does 0 iterations
        # on an empty list either way), but it WOULD make the field-mapping
        # diagnostic below fire a bogus "0/N matched" report for a sheet that
        # was never in the file at all (e.g. no Contract-Flexi this month).
        if sheet_result is None or sheet_result.sheet_name is None:
            continue
        salary_role = "formal" if role == "formal" else "contract"
        full_field_specs = FORMAL_FIELDS if salary_role == "formal" else CONTRACT_FIELDS

        # PRD V1.8 §4: the field-mapping diagnostic only needs the sheet's
        # header row, not a pass over every row - and the SAME header_index
        # is reused below for every row's salary-component/full-detail
        # extraction instead of being rebuilt per row.
        header_index = build_header_index(sheet_result.rows[0].keys()) if sheet_result.rows else {}
        total, matched, missing = check_field_mapping(header_index, full_field_specs)
        field_mapping_issues.append(_field_mapping_issue(f"{ROLE_LABEL.get(role, role)} sheet「{sheet_result.sheet_name}」", total, matched, missing))

        for row in sheet_result.rows:
            sid = get(row, sheet_result.header_map, "staff_id")
            if not sid:
                continue
            sid = str(sid).strip()
            is_active, status_date = _is_active_employee(role, row, sheet_result.header_map)
            dept_raw = get(row, sheet_result.header_map, "department1")
            entity_raw = get(row, sheet_result.header_map, "entity")
            components = extract_salary_components(row, salary_role, header_index)
            if components.pop("gross_salary_component_mismatch"):
                gross_mismatch_count += 1

            # PRD V1.6 §2.1: capture the remaining fields (Department 2/3,
            # Position, attendance/deduction detail, etc.) the ~10 analysis
            # columns above never covered - see ingestion/full_fields.py.
            new_descriptive, detail_json_fields, _ = extract_full_detail(
                row, full_field_specs, top_level_keys=NEW_DESCRIPTIVE_KEYS, exclude_keys=ANALYSIS_KEYS | TOP_LEVEL_DESCRIPTIVE_KEYS, header_index=header_index
            )

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
                "is_active": is_active,
                "resign_or_exit_date": status_date,
                "source_sheet": sheet_result.sheet_name,
                **components,
                **new_descriptive,
                "full_detail_json": json.dumps(detail_json_fields),
            }

    bonuses: list[dict] = []
    for role, entity_hint in (("bonus_pp", "PalmPay"), ("bonus_flexi", "Flexi")):
        sheet_result = parsed.by_role.get(role)
        if sheet_result is None or sheet_result.sheet_name is None:
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
                    "exit_date": format_date_value(get(row, exits_sheet.header_map, "exit_date_record")) or None,
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
    issues.extend(field_mapping_issues)
    if gross_mismatch_count:
        issues.append(
            {
                "issue_type": "gross_salary_component_mismatch",
                "issue_detail": (
                    f"有 {gross_mismatch_count} 条记录的「底薪+绩效+奖金+加班+其他收入」加总与表里的税前薪资总额对不上"
                    "（原始表本身的差异，不是解析错误），gross_salary 已按表里现成的值为准，未做任何调整，"
                    "如需要可以在数据库里按 staff_id 查出这些人核实"
                ),
                "row_count_affected": gross_mismatch_count,
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


_BONUS_BASE_FALLBACK_KEYS = ("employment_type", "department2", "department3", "position", "reporting_line", "job_grade", "joining_date")


def _stage_bonus_batch(db: Session, month: str, file_bytes: bytes) -> dict:
    """The standalone 奖金批次 upload: a full structured template, not the
    loose staff_id+amount shape backpay uses - see ingestion/bonus_batch.py.
    PRD V1.8 corrected the V1.6 assumption that this file has no Entity
    column of its own - it does, and is parsed directly like every other
    field; the fallback to the matched base-batch employee's entity (as
    _stage_supplemental already does for backpay) only kicks in when a row's
    own Entity is missing/blank.

    A real production export showed Employment Type/Position/Reporting Line/
    Job Grade/Department 3 coming back blank for every bonus row even though
    staff_name/department1/entity were fine - root cause is that those three
    already fell back to the matched base-batch employee's snapshot when the
    bonus row's own value was missing, but employment_type/department2/
    department3/position/reporting_line/job_grade/joining_date never got the
    same fallback. There's no reason bonus files should be expected to repeat
    every basic-info column the base salary batch already has for the same
    employee, so this applies the identical fallback to all of them instead
    of leaving it as a special case for just three fields."""
    parsed = parse_bonus_batch_workbook(io.BytesIO(file_bytes))
    resolver = NameResolver(db, month)
    resolver.prepare("department", [r["department1_raw"] for r in parsed.rows])

    base_employees = {
        e.staff_id: e for e in db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.month == month).all()
    }

    def _entity_source(r: dict) -> str | None:
        base = base_employees.get(r["staff_id"])
        return r.get("entity_raw") or (base.entity if base else None)

    resolver.prepare("entity", [_entity_source(r) for r in parsed.rows])

    entries = []
    unmatched_count = 0
    for r in parsed.rows:
        base = base_employees.get(r["staff_id"])
        department1_raw = r["department1_raw"] or (base.department1_raw if base else None)
        entity_source = _entity_source(r)
        matched = base is not None
        if not matched:
            unmatched_count += 1
        fallback = {key: r.get(key) or (getattr(base, key, None) if base else None) for key in _BONUS_BASE_FALLBACK_KEYS}
        entries.append(
            {
                "staff_id": r["staff_id"],
                "staff_name": r["staff_name"] or (base.staff_name if base else None),
                "department1": resolver.resolve("department", department1_raw),
                "entity": resolver.resolve("entity", entity_source) if entity_source else None,
                "amount": r["amount"],
                "source_sheet": r["source_sheet"],
                "matched_base_employee": matched,
                "location": r.get("location"),
                "resign_date": r.get("resign_date"),
                "full_detail_json": json.dumps(r["full_detail_json_fields"]),
                **fallback,
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
                    "或该员工当月不在职），这些金额仍会计入公司/部门总成本，但在归因分析里不会被归到具体某个人身上；"
                    "如果这些记录自己的 Entity 列也是空的，会被归入"
                    "「(未标注实体)」分类，权限范围过滤时不会精确出现在某个实体的统计里"
                ),
                "row_count_affected": unmatched_count,
            }
        )
    for report in parsed.field_mapping_reports:
        issues.append(_field_mapping_issue(f"奖金批次 sheet「{report.sheet_name}」", report.total, report.matched, report.missing))
    issues.extend(resolver.flush_issues())

    total_amount = sum(e["amount"] for e in entries)
    return {
        "entries": entries,
        "issues": issues,
        "summary": {
            "salary_type": "bonus",
            "row_count": len(entries),
            "matched_count": len(entries) - unmatched_count,
            "unmatched_count": unmatched_count,
            "total_amount": total_amount,
            "sheets_found": parsed.sheet_names,
        },
    }
