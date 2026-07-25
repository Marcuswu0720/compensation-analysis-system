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


def get_employee_detail_rows(
    db: Session,
    months: list[str],
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> tuple[list[dict], dict[str, float]]:
    """Returns (rows, unattributed_supplemental_by_month). Each row is one
    employee's one month, folding in any supplemental (bonus/backpay) pay
    matched to that staff_id that month into hr_cost - same reconciliation
    approach as compute/attribution.py's _fetch_scope, so this export's
    totals agree with what the dashboard already shows rather than quietly
    under-reporting cost for anyone paid through a standalone bonus/backpay
    file. Supplemental pay that can't be matched to anyone in the exported
    scope is never silently dropped - it comes back as
    unattributed_supplemental_by_month for the caller to disclose."""
    q = db.query(MonthlyEmployeeSnapshot).filter(
        MonthlyEmployeeSnapshot.month.in_(months), MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    employee_rows = q.order_by(
        MonthlyEmployeeSnapshot.month, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, MonthlyEmployeeSnapshot.staff_name
    ).all()

    supq = db.query(SupplementalPaySnapshot).filter(
        SupplementalPaySnapshot.month.in_(months), SupplementalPaySnapshot.is_deleted == False  # noqa: E712
    )
    supq = apply_scope_filter(supq, SupplementalPaySnapshot.department1, department)
    supq = apply_scope_filter(supq, SupplementalPaySnapshot.entity, entity)
    supq = apply_permission_scope(supq, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)

    employee_keys = {(r.month, r.staff_id) for r in employee_rows}
    supplemental_by_key: dict[tuple[str, str], float] = {}
    unattributed_by_month: dict[str, float] = {}
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
