"""Salary-category breakdown queries (PRD V1.1 §2.3): trend for a single
category, cross-department comparison for a category in one month, and the
full cost-composition percentage split for a scope/month. All deterministic
SQL aggregation over the component fields ingestion/salary_components.py
extracts - no supplemental (bonus/backpay) folding here, since those only
ever populate hr_cost via compute/trends.py, not the per-component fields.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot
from .scope import apply_scope_filter

ScopeValue = str | list[str] | None

CATEGORY_FIELDS: dict[str, str] = {
    "basic_salary_actual": "底薪",
    "performance_bonus": "绩效薪资",
    "commission_bonus": "奖金/提成",
    "overtime_amount": "加班费",
    "other_income": "其他收入",
    "employer_statutory_cost": "雇主社保成本",
    "gross_salary": "税前薪资总额",
    "net_pay": "实发到手",
    "deduction_total": "员工侧扣款",
    "hr_cost": "人力成本合计",
}

# Categories that make up hr_cost (for composition %), excluding derived/
# informational totals (gross_salary and hr_cost themselves, net_pay/
# deduction_total which are employee-side, not cost components).
COMPOSITION_FIELDS = [
    "basic_salary_actual",
    "performance_bonus",
    "commission_bonus",
    "overtime_amount",
    "other_income",
    "employer_statutory_cost",
]


def _column(category: str):
    if category not in CATEGORY_FIELDS:
        raise ValueError(f"未知薪资类目: {category}，可选值: {list(CATEGORY_FIELDS)}")
    return getattr(MonthlyEmployeeSnapshot, category)


def get_category_trend(
    db: Session,
    category: str,
    months: list[str] | None = None,
    department: ScopeValue = None,
    entity: ScopeValue = None,
) -> list[dict]:
    col = _column(category)
    q = db.query(
        MonthlyEmployeeSnapshot.month,
        func.count(MonthlyEmployeeSnapshot.id).label("headcount"),
        func.sum(col).label("total"),
    ).filter(MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
    if months:
        q = q.filter(MonthlyEmployeeSnapshot.month.in_(months))
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = q.group_by(MonthlyEmployeeSnapshot.month).order_by(MonthlyEmployeeSnapshot.month)

    return [
        {
            "month": month,
            "headcount": headcount,
            "total": total or 0.0,
            "avg": (total or 0.0) / headcount if headcount else 0.0,
        }
        for month, headcount, total in q.all()
    ]


def compare_departments_by_category(
    db: Session, category: str, month: str, entity: ScopeValue = None, allowed_departments: list[str] | None = None
) -> list[dict]:
    col = _column(category)
    hr_cost_q = db.query(MonthlyEmployeeSnapshot.department1, func.sum(MonthlyEmployeeSnapshot.hr_cost)).filter(
        MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    hr_cost_q = apply_scope_filter(hr_cost_q, MonthlyEmployeeSnapshot.entity, entity)
    hr_cost_q = apply_scope_filter(hr_cost_q, MonthlyEmployeeSnapshot.department1, allowed_departments)
    hr_cost_by_dept = {dept: total or 0.0 for dept, total in hr_cost_q.group_by(MonthlyEmployeeSnapshot.department1).all()}

    q = db.query(
        MonthlyEmployeeSnapshot.department1,
        func.count(MonthlyEmployeeSnapshot.id).label("headcount"),
        func.sum(col).label("total"),
    ).filter(MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, allowed_departments)
    q = q.group_by(MonthlyEmployeeSnapshot.department1).order_by(func.sum(col).desc())

    results = []
    for department, headcount, total in q.all():
        total = total or 0.0
        hr_cost = hr_cost_by_dept.get(department, 0.0)
        results.append(
            {
                "department": department,
                "headcount": headcount,
                "total": total,
                "avg": total / headcount if headcount else 0.0,
                "pct_of_hr_cost": (total / hr_cost * 100) if hr_cost else 0.0,
            }
        )
    return results


def get_cost_composition(
    db: Session, month: str, department: ScopeValue = None, entity: ScopeValue = None
) -> dict:
    q = db.query(*[func.sum(_column(c)) for c in COMPOSITION_FIELDS], func.sum(MonthlyEmployeeSnapshot.hr_cost)).filter(
        MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    row = q.first()
    if row is None:
        return {"month": month, "department": department, "entity": entity, "hr_cost": 0.0, "categories": []}

    *component_totals, hr_cost = row
    hr_cost = hr_cost or 0.0
    categories = []
    for field, total in zip(COMPOSITION_FIELDS, component_totals):
        total = total or 0.0
        categories.append(
            {
                "category": field,
                "label": CATEGORY_FIELDS[field],
                "total": total,
                "pct": (total / hr_cost * 100) if hr_cost else 0.0,
            }
        )
    return {"month": month, "department": department, "entity": entity, "hr_cost": hr_cost, "categories": categories}
