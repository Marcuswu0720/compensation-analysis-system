"""Employee-level salary detail rows for the Excel export (PRD V1.3).

Deliberately reuses the exact same permission primitives as every other
compute/*.py query (`apply_scope_filter` for the caller's explicit
department/entity choice, `apply_permission_scope` for the viewer's granted
rules) - see scope.py's docstring. The PRD is explicit that download must
NOT invent a separate "match department1 by string" filter, since that is
exactly the cross-entity leak V1.2 closed.
"""

from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot, SupplementalPaySnapshot
from .scope import ScopeRule, apply_permission_scope, apply_scope_filter

ScopeValue = str | list[str] | None

EMPLOYMENT_TYPE_LABEL = {"Formal": "正式工", "Contract": "合同工"}
SALARY_TYPE_LABEL = {"base": "底薪批次", "bonus": "奖金批次", "backpay": "补发批次"}
SALARY_TYPES = ("base", "bonus", "backpay")

EXPORT_COLUMNS = [
    ("month", "月份"),
    ("entity", "实体"),
    ("department1", "部门"),
    ("staff_name", "员工姓名"),
    ("staff_id", "员工工号"),
    ("employment_type_label", "用工类型"),
    ("job_grade", "职级"),
    ("basic_salary_actual", "实发底薪"),
    ("performance_bonus", "绩效薪资"),
    ("commission_bonus", "奖金/提成"),
    ("overtime_amount", "加班薪资"),
    ("other_income", "其他收入"),
    ("gross_salary", "税前薪资合计"),
    ("employer_statutory_cost", "雇主承担社保成本"),
    ("hr_cost", "人力成本 HR Cost"),
    ("deduction_total", "扣款合计"),
    ("net_pay", "实发到手"),
    ("status_label", "在职状态"),
]

SUPPLEMENTAL_EXPORT_COLUMNS = [
    ("month", "月份"),
    ("batch_type_label", "批次类型"),
    ("entity", "实体"),
    ("department1", "部门"),
    ("staff_name", "员工姓名"),
    ("staff_id", "员工工号"),
    ("amount", "金额"),
    ("matched_label", "是否关联到底薪批次在职员工"),
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


def get_employee_detail_rows(
    db: Session,
    months: list[str],
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
    fold_supplemental: bool = True,
) -> tuple[list[dict], dict[str, float]]:
    """Returns (rows, unattributed_supplemental_by_month). Each row is one
    employee's one month.

    fold_supplemental=True (the original V1.3 behaviour) folds any
    bonus/backpay pay matched to that staff_id that month into hr_cost -
    same reconciliation approach as compute/attribution.py's _fetch_scope,
    so totals agree with the dashboard rather than under-reporting cost for
    anyone paid through a standalone bonus/backpay file. Supplemental pay
    that can't be matched to anyone in the exported scope is never silently
    dropped - it comes back as unattributed_supplemental_by_month.

    fold_supplemental=False (PRD V1.5 §2.1) leaves hr_cost as the pure
    底薪批次 figure - used when the caller wants base data reported strictly
    on its own, with bonus/backpay shown separately via
    get_supplemental_detail_rows() instead of blended in."""
    q = db.query(MonthlyEmployeeSnapshot).filter(
        MonthlyEmployeeSnapshot.month.in_(months), MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    employee_rows = q.order_by(
        MonthlyEmployeeSnapshot.month, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, MonthlyEmployeeSnapshot.staff_name
    ).all()

    supplemental_by_key: dict[tuple[str, str], float] = {}
    unattributed_by_month: dict[str, float] = {}
    if fold_supplemental:
        supq = db.query(SupplementalPaySnapshot).filter(
            SupplementalPaySnapshot.month.in_(months), SupplementalPaySnapshot.is_deleted == False  # noqa: E712
        )
        supq = apply_scope_filter(supq, SupplementalPaySnapshot.department1, department)
        supq = apply_scope_filter(supq, SupplementalPaySnapshot.entity, entity)
        supq = apply_permission_scope(supq, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)

        employee_keys = {(r.month, r.staff_id) for r in employee_rows}
        for row in supq.all():
            key = (row.month, row.staff_id)
            if key in employee_keys:
                supplemental_by_key[key] = supplemental_by_key.get(key, 0.0) + row.amount
            else:
                unattributed_by_month[row.month] = unattributed_by_month.get(row.month, 0.0) + row.amount

    rows = []
    for r in employee_rows:
        supplemental = supplemental_by_key.get((r.month, r.staff_id), 0.0)
        if r.is_active:
            status_label = "在职"
        else:
            status_label = f"已离职（{r.resign_or_exit_date}）" if r.resign_or_exit_date else "已离职"
        rows.append(
            {
                "month": r.month,
                "entity": r.entity,
                "department1": r.department1,
                "staff_name": r.staff_name,
                "staff_id": r.staff_id,
                "employment_type": r.employment_type,
                "employment_type_label": EMPLOYMENT_TYPE_LABEL.get(r.employment_type, r.employment_type),
                "job_grade": r.job_grade,
                "basic_salary_actual": r.basic_salary_actual or 0.0,
                "performance_bonus": r.performance_bonus or 0.0,
                "commission_bonus": r.commission_bonus or 0.0,
                "overtime_amount": r.overtime_amount or 0.0,
                "other_income": r.other_income or 0.0,
                "gross_salary": r.gross_salary or 0.0,
                "employer_statutory_cost": r.employer_statutory_cost or 0.0,
                "hr_cost": (r.hr_cost or 0.0) + supplemental,
                "deduction_total": r.deduction_total or 0.0,
                "net_pay": r.net_pay or 0.0,
                "status_label": status_label,
            }
        )
    return rows, unattributed_by_month


def get_supplemental_detail_rows(
    db: Session,
    months: list[str],
    pay_types: list[str],
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> list[dict]:
    """Raw 奖金/补发批次 entries (PRD V1.5 §2.1/§2.4) - these never had a full
    salary-component breakdown (see ingestion/supplemental.py), so unlike
    base rows they're reported as their own simple sheet: who, how much,
    which batch type, and whether it could be matched to a base-batch
    employee - not folded into anyone's hr_cost here."""
    if not pay_types:
        return []
    q = db.query(SupplementalPaySnapshot).filter(
        SupplementalPaySnapshot.month.in_(months),
        SupplementalPaySnapshot.pay_type.in_(pay_types),
        SupplementalPaySnapshot.is_deleted == False,  # noqa: E712
    )
    q = apply_scope_filter(q, SupplementalPaySnapshot.department1, department)
    q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
    q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
    rows = q.order_by(SupplementalPaySnapshot.month, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1).all()

    return [
        {
            "month": r.month,
            "batch_type_label": SALARY_TYPE_LABEL.get(r.pay_type, r.pay_type),
            "entity": r.entity,
            "department1": r.department1,
            "staff_name": r.staff_name,
            "staff_id": r.staff_id,
            "amount": r.amount,
            "matched_label": "是" if r.matched_base_employee else "否",
        }
        for r in rows
    ]


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
