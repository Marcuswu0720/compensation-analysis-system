"""Salary-category breakdown queries (PRD V1.1 §2.3, multi-category trend
added by PRD V1.7 §3.1, per-capita/median/employment-type split added by
PRD V1.9 §1-3): trend for one or more categories at once, cross-department
comparison for a category in one month, and the full cost-composition
percentage split for a scope/month. All deterministic SQL aggregation over
the component fields ingestion/salary_components.py extracts.

Found against a real reconciliation the user did in Excel: get_categories_
trend()'s "人力成本合计" (hr_cost) category used to be base-batch-only, same
as every other category here (底薪/绩效薪资/奖金提成/加班/其他收入/雇主社保
etc. - none of those have a supplemental-batch equivalent, since a bonus/
backpay row is just a flat amount, not a full component breakdown). But
"人力成本合计" specifically is supposed to be the SAME "total cost" figure
get_trend() already reports elsewhere in the app (趋势查询 page's total),
which DOES fold in bonus/backpay (see compute/trends.py's get_trend() and
get_supplemental_cost_by_month()) - leaving it out here made this page's
total silently ~10% short of the real total cost whenever a month had a
sizeable bonus batch. Fixed by adding the same get_supplemental_cost_by_month()
figure on top of the hr_cost category specifically (not the other
categories, which have no supplemental equivalent to add), both in the
grouped-SUM path and the per-capita path.
"""

import statistics

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot
from .scope import ScopeRule, apply_permission_scope, apply_scope_filter
from .trends import get_supplemental_cost_by_month

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


def _base_query(db: Session, department: ScopeValue, entity: ScopeValue, scope_rules, months, employment_type):
    q = db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
    if months:
        q = q.filter(MonthlyEmployeeSnapshot.month.in_(months))
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    if employment_type:
        q = q.filter(MonthlyEmployeeSnapshot.employment_type == employment_type)
    return q


def get_categories_trend(
    db: Session,
    categories: list[str],
    months: list[str] | None = None,
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
    employment_type: str | None = None,
    per_capita: bool = False,
) -> list[dict]:
    """PRD V1.7 §3.1: 薪资类目页面从单选改为多选 - one query returns every
    requested category's monthly total side by side (same headcount
    denominator for all of them), instead of one round trip per category
    that could return a different set of months per category and force the
    caller to reconcile them. Also backs the page's "两点比较" mode: the
    caller just picks out the two rows matching start/end month from the
    same response instead of a second endpoint.

    PRD V1.9 extends this SAME function (not a parallel implementation) with
    two independent optional parameters instead of adding a new endpoint per
    page, so any other page that later needs a per-capita or employment-type
    view can reuse it directly:
      - `employment_type` ('Formal' | 'Contract' | None for both combined):
        a plain filter - "对比 Formal vs Contract" is just calling this
        function twice with each value and combining client-side, not a
        third mode this function needs to know about.
      - `per_capita`: also computes each category's per-head average AND
        median for that month/scope (PRD §2.2: median must always be shown
        alongside the mean, not hidden behind an extra click - a median
        needs the individual per-employee values, not just a SQL SUM, so
        this path queries raw rows instead of a grouped aggregate; when
        `per_capita` is False the lighter grouped-SUM query below is used
        instead, unchanged from V1.7).
    """
    if per_capita:
        return _get_categories_trend_per_capita(db, categories, months, department, entity, scope_rules, employment_type)

    cols = [_column(c) for c in categories]
    q = db.query(
        MonthlyEmployeeSnapshot.month,
        func.count(MonthlyEmployeeSnapshot.id).label("headcount"),
        *[func.sum(c) for c in cols],
    ).filter(MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
    if months:
        q = q.filter(MonthlyEmployeeSnapshot.month.in_(months))
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    if employment_type:
        q = q.filter(MonthlyEmployeeSnapshot.employment_type == employment_type)
    q = q.group_by(MonthlyEmployeeSnapshot.month).order_by(MonthlyEmployeeSnapshot.month)

    supplemental_by_month = (
        get_supplemental_cost_by_month(db, months, department, entity, scope_rules, employment_type) if "hr_cost" in categories else {}
    )

    base_by_month = {}
    for row in q.all():
        month, headcount, *totals = row
        base_by_month[month] = (headcount, {cat: (total or 0.0) for cat, total in zip(categories, totals)})

    # A month can have a bonus/backpay batch uploaded without a base batch
    # (or with the base batch not yet uploaded) - same edge case get_trend()
    # already guards against (see compute/trends.py) - don't silently drop
    # that month's supplemental cost just because there's no base row for it.
    all_months = sorted(set(base_by_month) | set(supplemental_by_month))
    results = []
    for month in all_months:
        headcount, cat_totals = base_by_month.get(month, (0, {cat: 0.0 for cat in categories}))
        cat_totals = dict(cat_totals)
        if "hr_cost" in cat_totals:
            cat_totals["hr_cost"] += supplemental_by_month.get(month, 0.0)
        results.append({"month": month, "headcount": headcount, "categories": cat_totals})
    return results


def _get_categories_trend_per_capita(db, categories, months, department, entity, scope_rules, employment_type) -> list[dict]:
    """PRD V1.9 §2.1: 人均 = 类目总额 ÷ 该范围内当月在职总人数（跟 get_trend
    的"在职人数（含当月内离职）"口径一致），拆用工类型时分母各自独立计算，
    不共用总分母 - which falls out naturally here since `employment_type`
    filters the underlying row set BEFORE headcount is computed as len(rows).

    Same supplemental (bonus/backpay) fold-in as the non-per-capita branch
    above for the "hr_cost" category's total/per-capita figures - but NOT
    for its median: median needs each individual employee's own value, and
    supplemental amounts only apply to whichever staff_ids the bonus/backpay
    batch actually lists (not every employee), so spreading the month's
    supplemental total evenly across every employee's hr_cost before taking
    the median would misrepresent the actual distribution. Left as a known
    gap rather than guessed at - hr_cost's median here still reflects the
    base batch only."""
    cols = [_column(c) for c in categories]
    q = _base_query(db, department, entity, scope_rules, months, employment_type).with_entities(MonthlyEmployeeSnapshot.month, *cols)
    rows = q.order_by(MonthlyEmployeeSnapshot.month).all()

    by_month: dict[str, list] = {}
    for row in rows:
        by_month.setdefault(row[0], []).append(row[1:])

    supplemental_by_month = (
        get_supplemental_cost_by_month(db, months, department, entity, scope_rules, employment_type) if "hr_cost" in categories else {}
    )

    all_months = sorted(set(by_month) | set(supplemental_by_month))
    results = []
    for month in all_months:
        employee_rows = by_month.get(month, [])
        headcount = len(employee_rows)
        totals: dict[str, float] = {}
        per_capita_vals: dict[str, float] = {}
        median_vals: dict[str, float] = {}
        for i, cat in enumerate(categories):
            values = [(r[i] or 0.0) for r in employee_rows]
            total = sum(values)
            if cat == "hr_cost":
                total += supplemental_by_month.get(month, 0.0)
            totals[cat] = total
            per_capita_vals[cat] = (total / headcount) if headcount else 0.0
            median_vals[cat] = statistics.median(values) if values else 0.0
        results.append({"month": month, "headcount": headcount, "categories": totals, "per_capita": per_capita_vals, "median": median_vals})
    return results


def compare_departments_by_category(
    db: Session,
    category: str,
    month: str,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> list[dict]:
    col = _column(category)
    hr_cost_q = db.query(MonthlyEmployeeSnapshot.department1, func.sum(MonthlyEmployeeSnapshot.hr_cost)).filter(
        MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    hr_cost_q = apply_scope_filter(hr_cost_q, MonthlyEmployeeSnapshot.entity, entity)
    hr_cost_q = apply_permission_scope(hr_cost_q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    hr_cost_by_dept = {dept: total or 0.0 for dept, total in hr_cost_q.group_by(MonthlyEmployeeSnapshot.department1).all()}

    q = db.query(
        MonthlyEmployeeSnapshot.department1,
        func.count(MonthlyEmployeeSnapshot.id).label("headcount"),
        func.sum(col).label("total"),
    ).filter(MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
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
    db: Session,
    month: str,
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> dict:
    q = db.query(*[func.sum(_column(c)) for c in COMPOSITION_FIELDS], func.sum(MonthlyEmployeeSnapshot.hr_cost)).filter(
        MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
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
