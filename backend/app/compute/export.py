"""Employee-level salary detail rows for the Excel export (PRD V1.3, fully
reworked by PRD V1.6 to cover the complete field templates instead of the
~17 analysis columns V1.5 was limited to - see ingestion/full_fields.py for
why those extra ~20 columns never made it into the database in the first
place, and models.py's MonthlyEmployeeSnapshot/SupplementalPaySnapshot for
where they're now stored).

Deliberately reuses the exact same permission primitives as every other
compute/*.py query (`apply_scope_filter` for the caller's explicit
department/entity choice, `apply_permission_scope` for the viewer's granted
rules) - see scope.py's docstring. The PRD is explicit that download must
NOT invent a separate "match department1 by string" filter, since that is
exactly the cross-entity leak V1.2 closed.
"""

import json

from sqlalchemy.orm import Session

from ..ingestion.full_fields import BONUS_FIELDS, CONTRACT_FIELDS, FORMAL_FIELDS, export_header
from ..models import MonthlyEmployeeSnapshot, SupplementalPaySnapshot
from .scope import ScopeRule, apply_permission_scope, apply_scope_filter

ScopeValue = str | list[str] | None

SALARY_TYPE_LABEL = {"base": "底薪批次", "bonus": "奖金批次", "backpay": "补发批次"}
SALARY_TYPES = ("base", "bonus", "backpay")

# "Month" is a convenience column prepended to every detail sheet for
# readability across a multi-month export - NOT part of the PRD field
# templates, so it's excluded from the field-count self-check in
# routers/export.py on purpose. Still given the same bilingual header format
# as every other export column per V1.6's "no exceptions" rule.
#
# PRD V1.8 note: "Entity" used to live here too (V1.6 treated it as a
# convenience column resolved separately from the field templates), but the
# authoritative V1.8 field-mapping file lists Entity as a real target field
# for all three batch types - it's now a proper FieldSpec inside
# FORMAL_FIELDS/CONTRACT_FIELDS/BONUS_FIELDS instead, so it isn't repeated
# here (that would produce two Entity columns in the exported sheet).
_CONVENIENCE_COLUMNS = [("month", "Month（月份）")]


def formal_sheet_columns() -> list[tuple[str, str]]:
    return _CONVENIENCE_COLUMNS + [(s.key, export_header(s)) for s in FORMAL_FIELDS]


def contract_sheet_columns() -> list[tuple[str, str]]:
    return _CONVENIENCE_COLUMNS + [(s.key, export_header(s)) for s in CONTRACT_FIELDS]


def bonus_sheet_columns() -> list[tuple[str, str]]:
    return _CONVENIENCE_COLUMNS + [(s.key, export_header(s)) for s in BONUS_FIELDS]


BACKPAY_EXPORT_COLUMNS = [
    ("month", "Month（月份）"),
    ("entity", "Entity（实体）"),
    ("department1", "Department 1（一级部门）"),
    ("staff_name", "Staff Name（员工姓名）"),
    ("staff_id", "Staff ID（员工工号）"),
    ("amount", "Amount（金额）"),
    ("matched_label", "Matched（是否关联到底薪批次在职员工）"),
]


RECONCILIATION_SUM_FIELDS = [
    "basic_salary_actual",
    "performance_bonus",
    "commission_bonus",
    "overtime_amount",
    "other_income",
    "gross_salary",
    "employer_statutory_cost",
    "hr_cost",
]

RECONCILIATION_COLUMNS = [
    ("entity", "Entity"),
    ("department1", "部门"),
    ("headcount", "人数"),
    ("basic_salary_actual", "底薪合计"),
    ("performance_bonus", "绩效薪资合计"),
    ("commission_bonus", "奖金/提成合计"),
    ("overtime_amount", "加班费合计"),
    ("other_income", "其他收入合计"),
    ("gross_salary", "税前薪资合计"),
    ("employer_statutory_cost", "雇主社保成本合计"),
    ("hr_cost", "HR Cost合计"),
]


def build_department_category_summary(employees: list[dict]) -> list[dict]:
    """PRD V1.5 §1: groups a staged (not-yet-confirmed) base batch's employee
    rows by (Entity, Department1) and sums the PRD V1.1 salary-component
    fields - for the admin to download and cross-check offline before
    clicking "确认无误，正式入库". Pure reshaping of numbers already computed
    by ingestion/salary_components.py, no new calculation."""
    groups: dict[tuple, dict] = {}
    for emp in employees:
        key = (emp.get("entity"), emp.get("department1"))
        g = groups.setdefault(
            key,
            {"entity": emp.get("entity"), "department1": emp.get("department1"), "headcount": 0, **{f: 0.0 for f in RECONCILIATION_SUM_FIELDS}},
        )
        g["headcount"] += 1
        for field in RECONCILIATION_SUM_FIELDS:
            g[field] += emp.get(field) or 0.0
    return sorted(groups.values(), key=lambda g: (g["entity"] or "", g["department1"] or ""))


def _base_row_to_dict(r: MonthlyEmployeeSnapshot) -> dict:
    detail = json.loads(r.full_detail_json) if r.full_detail_json else {}
    return {
        "month": r.month,
        "entity": r.entity,
        "employment_type": r.employment_type,
        "staff_id": r.staff_id,
        "staff_name": r.staff_name,
        "department1": r.department1,
        "department2": r.department2,
        "department3": r.department3,
        "position": r.position,
        "reporting_line": r.reporting_line,
        "job_grade": r.job_grade,
        "state": r.state,
        "work_station": r.work_station,
        "joining_date": r.joining_date,
        "resign_date": r.resign_or_exit_date,
        "basic_salary_actual": r.basic_salary_actual,
        "performance_std": r.performance_std,
        "performance_coefficient": r.performance_coefficient,
        "performance_bonus": r.performance_bonus,
        "commission_bonus": r.commission_bonus,
        "overtime_amount": r.overtime_amount,
        "gross_salary": r.gross_salary,
        "employer_statutory_cost": r.employer_statutory_cost,
        "net_pay": r.net_pay,
        "hr_cost": r.hr_cost,
        **detail,
    }


def get_base_full_detail_rows(
    db: Session,
    months: list[str],
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> list[dict]:
    """One row per employee per month, with every PRD V1.6 field populated
    (from MonthlyEmployeeSnapshot's dedicated columns plus its
    full_detail_json blob) - the caller picks FORMAL_FIELDS or
    CONTRACT_FIELDS to know which keys/order to render for a given row's
    employment_type. hr_cost here is always the pure 底薪批次 figure - PRD
    V1.5 already established that bonus/backpay show up in their own sheet,
    never folded in here."""
    q = db.query(MonthlyEmployeeSnapshot).filter(
        MonthlyEmployeeSnapshot.month.in_(months), MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    rows = q.order_by(
        MonthlyEmployeeSnapshot.month, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, MonthlyEmployeeSnapshot.staff_name
    ).all()
    return [_base_row_to_dict(r) for r in rows]


def get_bonus_detail_rows(
    db: Session,
    months: list[str],
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> list[dict]:
    """The standalone 奖金批次 upload's full structured detail (PRD V1.6,
    field list rebuilt by V1.8) - see ingestion/bonus_batch.py. Distinct
    from get_backpay_detail_rows(), which
    stays the deliberately simple shape backpay files use."""
    q = db.query(SupplementalPaySnapshot).filter(
        SupplementalPaySnapshot.month.in_(months),
        SupplementalPaySnapshot.pay_type == "bonus",
        SupplementalPaySnapshot.is_deleted == False,  # noqa: E712
    )
    q = apply_scope_filter(q, SupplementalPaySnapshot.department1, department)
    q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
    q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
    rows = q.order_by(SupplementalPaySnapshot.month, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1).all()

    result = []
    for r in rows:
        detail = json.loads(r.full_detail_json) if r.full_detail_json else {}
        result.append(
            {
                "month": r.month,
                "entity": r.entity,
                "employment_type": r.employment_type,
                "staff_id": r.staff_id,
                "staff_name": r.staff_name,
                "department1": r.department1,
                "department2": r.department2,
                "department3": r.department3,
                "position": r.position,
                "reporting_line": r.reporting_line,
                "job_grade": r.job_grade,
                "location": r.location,
                "joining_date": r.joining_date,
                "resign_date": r.resign_date,
                "hr_cost": r.amount,
                **detail,
            }
        )
    return result


def get_backpay_detail_rows(
    db: Session,
    months: list[str],
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> list[dict]:
    """补发批次 stays the simple staff_id+amount shape - confirmed with the
    user (V1.5 §0.2) that backpay files really are just a loose list, not a
    full payroll template like the standalone 奖金批次 upload turned out to
    be (PRD V1.6's background section)."""
    q = db.query(SupplementalPaySnapshot).filter(
        SupplementalPaySnapshot.month.in_(months),
        SupplementalPaySnapshot.pay_type == "backpay",
        SupplementalPaySnapshot.is_deleted == False,  # noqa: E712
    )
    q = apply_scope_filter(q, SupplementalPaySnapshot.department1, department)
    q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
    q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
    rows = q.order_by(SupplementalPaySnapshot.month, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1).all()

    return [
        {
            "month": r.month,
            "entity": r.entity,
            "department1": r.department1,
            "staff_name": r.staff_name,
            "staff_id": r.staff_id,
            "amount": r.amount,
            "matched_label": "是" if r.matched_base_employee else "否",
        }
        for r in rows
    ]


EXPECTED_FIELD_COUNTS = {"正式工明细": 40, "合同工明细": 33, "奖金明细": 24}


def verify_sheet_field_count(sheet_label: str, columns: list[tuple[str, str]]) -> None:
    """PRD V1.6's single most-emphasized requirement ("本次迭代最重要的一条，
    不是可选项"): before a structured sheet is written, check that its
    column count - minus the convenience column(s) that aren't part of the
    PRD's field templates - exactly matches the current field count (40/33/24
    per PRD V1.8's authoritative field-mapping file). Raises loudly instead
    of letting an incomplete file go out the door silently, which is the
    exact failure mode PRD V1.6 exists to fix (V1.5's export silently had
    ~20 fewer columns than it should have)."""
    expected = EXPECTED_FIELD_COUNTS[sheet_label]
    actual = len(columns) - len(_CONVENIENCE_COLUMNS)
    if actual != expected:
        raise ValueError(
            f"导出字段数量与规范不符，请检查：{sheet_label}应为 {expected} 个字段（不含月份/实体两个辅助列），实际拼出了 {actual} 个"
        )


def check_month_type_availability(
    db: Session,
    months: list[str],
    salary_types: list[str],
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> dict[tuple[str, str], bool]:
    """PRD V1.5 §2.1: before generating a file, check whether each requested
    (month, batch_type) combination actually has any confirmed data in
    scope - returns {(month, salary_type): has_data}. Never used to decide
    *what* to include (that's apply_permission_scope's job at query time),
    only to decide whether to refuse the whole request with a clear message
    instead of silently generating an empty file."""
    result = {(m, t): False for m in months for t in salary_types}

    if "base" in salary_types:
        q = db.query(MonthlyEmployeeSnapshot.month).filter(
            MonthlyEmployeeSnapshot.month.in_(months), MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
        )
        q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
        q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
        q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
        for (month,) in q.distinct().all():
            result[(month, "base")] = True

    supplemental_types = [t for t in ("bonus", "backpay") if t in salary_types]
    if supplemental_types:
        q = db.query(SupplementalPaySnapshot.month, SupplementalPaySnapshot.pay_type).filter(
            SupplementalPaySnapshot.month.in_(months),
            SupplementalPaySnapshot.pay_type.in_(supplemental_types),
            SupplementalPaySnapshot.is_deleted == False,  # noqa: E712
        )
        q = apply_scope_filter(q, SupplementalPaySnapshot.department1, department)
        q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
        q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
        for month, pay_type in q.distinct().all():
            result[(month, pay_type)] = True

    return result
