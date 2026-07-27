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

A second reconciliation round found the flip side of that same fix: with
"人力成本合计" now correctly including bonus/backpay, the OTHER categories
sum to less than it whenever a month has a sizeable 奖金批次/补发批次 - that
money is real cost, present in the total, but invisible in every category
breakdown (a bonus/backpay row is a flat SupplementalPaySnapshot.amount,
never split into 底薪/绩效薪资/奖金提成 the way a base-batch row is, so it
was never folding into any of THOSE categories - see above). Rather than
leave that gap unexplained, 奖金批次/补发批次 are now their own categories
(SUPPLEMENTAL_CATEGORIES below) - not real MonthlyEmployeeSnapshot columns,
sourced straight from SupplementalPaySnapshot via get_supplemental_cost_
by_month(pay_type=...)/get_supplemental_amounts_by_month - so 底薪+绩效薪资+
奖金/提成+奖金批次+补发批次+加班费+其他收入+雇主社保成本 now actually sums
back up to 人力成本合计.
"""

import statistics

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot, SupplementalPaySnapshot
from .scope import ScopeRule, apply_permission_scope, apply_scope_filter
from .trends import get_supplemental_amounts_by_month, get_supplemental_cost_by_month

ScopeValue = str | list[str] | None

CATEGORY_FIELDS: dict[str, str] = {
    "basic_salary_actual": "底薪",
    "performance_bonus": "绩效薪资",
    "commission_bonus": "奖金/提成",
    "overtime_amount": "加班费",
    "other_income": "其他收入",
    "employer_statutory_cost": "雇主社保成本",
    "supplemental_bonus": "奖金批次",
    "supplemental_backpay": "补发批次",
    "gross_salary": "税前薪资总额",
    "net_pay": "实发到手",
    "deduction_total": "员工侧扣款",
    "hr_cost": "人力成本合计",
}

# Categories in CATEGORY_FIELDS that are NOT a MonthlyEmployeeSnapshot column
# - each is this scope/month's SupplementalPaySnapshot total for the given
# pay_type instead (see module docstring). Every function below that iterates
# `categories` branches on this set instead of calling _column() for these.
SUPPLEMENTAL_CATEGORIES: dict[str, str] = {
    "supplemental_bonus": "bonus",
    "supplemental_backpay": "backpay",
}

# Real (MonthlyEmployeeSnapshot-column) categories that make up hr_cost, for
# get_cost_composition's percentage split - excludes derived/informational
# totals (gross_salary and hr_cost themselves, net_pay/deduction_total which
# are employee-side, not cost components) and SUPPLEMENTAL_CATEGORIES, which
# get_cost_composition appends separately since they aren't real columns.
COMPOSITION_REAL_FIELDS = [
    "basic_salary_actual",
    "performance_bonus",
    "commission_bonus",
    "overtime_amount",
    "other_income",
    "employer_statutory_cost",
]


def _column(category: str):
    if category not in CATEGORY_FIELDS or category in SUPPLEMENTAL_CATEGORIES:
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

    real_categories = [c for c in categories if c not in SUPPLEMENTAL_CATEGORIES]
    cols = [_column(c) for c in real_categories]
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

    # "hr_cost" folds in the supplemental TOTAL (bonus+backpay combined, same
    # figure 趋势查询's total_hr_cost uses); "supplemental_bonus"/
    # "supplemental_backpay" each fold in only their own pay_type instead -
    # see SUPPLEMENTAL_CATEGORIES/module docstring above.
    supplemental_by_category: dict[str, dict[str, float]] = {}
    if "hr_cost" in categories:
        supplemental_by_category["hr_cost"] = get_supplemental_cost_by_month(db, months, department, entity, scope_rules, employment_type)
    for cat, pay_type in SUPPLEMENTAL_CATEGORIES.items():
        if cat in categories:
            supplemental_by_category[cat] = get_supplemental_cost_by_month(
                db, months, department, entity, scope_rules, employment_type, pay_type=pay_type
            )

    base_by_month = {}
    for row in q.all():
        month, headcount, *totals = row
        base_by_month[month] = (headcount, {cat: (total or 0.0) for cat, total in zip(real_categories, totals)})

    # A month can have a bonus/backpay batch uploaded without a base batch
    # (or with the base batch not yet uploaded) - same edge case get_trend()
    # already guards against (see compute/trends.py) - don't silently drop
    # that month's supplemental cost just because there's no base row for it.
    all_months = set(base_by_month)
    for by_month in supplemental_by_category.values():
        all_months |= set(by_month)
    all_months = sorted(all_months)

    results = []
    for month in all_months:
        headcount, base_totals = base_by_month.get(month, (0, {}))
        cat_totals = {}
        for cat in categories:
            if cat in SUPPLEMENTAL_CATEGORIES:
                cat_totals[cat] = supplemental_by_category[cat].get(month, 0.0)
            elif cat == "hr_cost":
                cat_totals[cat] = base_totals.get(cat, 0.0) + supplemental_by_category["hr_cost"].get(month, 0.0)
            else:
                cat_totals[cat] = base_totals.get(cat, 0.0)
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
    base batch only.

    "supplemental_bonus"/"supplemental_backpay" (see SUPPLEMENTAL_CATEGORIES)
    have the same total/per-capita treatment - total is that pay_type's
    SupplementalPaySnapshot sum, per-capita divides it by the SAME headcount
    as every other category (everyone on the base batch that month, not just
    the batch's recipients) so it stays comparable to the other categories'
    per-capita figures. Median is the one place these differ from "hr_cost":
    a bonus/backpay row IS an individual per-recipient value (unlike hr_cost,
    which would need a staff_id join against the base rows to isolate one),
    so the median here is taken directly across the batch's actual recipients
    - not padded with zeros for non-recipients like the mean is, so it isn't
    on the exact same population as the other categories' medians."""
    real_categories = [c for c in categories if c not in SUPPLEMENTAL_CATEGORIES]
    cols = [_column(c) for c in real_categories]
    q = _base_query(db, department, entity, scope_rules, months, employment_type).with_entities(MonthlyEmployeeSnapshot.month, *cols)
    rows = q.order_by(MonthlyEmployeeSnapshot.month).all()

    by_month: dict[str, list] = {}
    for row in rows:
        by_month.setdefault(row[0], []).append(row[1:])

    hr_cost_supplemental_by_month = (
        get_supplemental_cost_by_month(db, months, department, entity, scope_rules, employment_type) if "hr_cost" in categories else {}
    )
    supplemental_amounts_by_category: dict[str, dict[str, list[float]]] = {
        cat: get_supplemental_amounts_by_month(db, months, department, entity, scope_rules, employment_type, pay_type=pay_type)
        for cat, pay_type in SUPPLEMENTAL_CATEGORIES.items()
        if cat in categories
    }

    all_months = set(by_month) | set(hr_cost_supplemental_by_month)
    for by_month_amounts in supplemental_amounts_by_category.values():
        all_months |= set(by_month_amounts)
    all_months = sorted(all_months)

    results = []
    for month in all_months:
        employee_rows = by_month.get(month, [])
        headcount = len(employee_rows)
        totals: dict[str, float] = {}
        per_capita_vals: dict[str, float] = {}
        median_vals: dict[str, float] = {}
        for i, cat in enumerate(real_categories):
            values = [(r[i] or 0.0) for r in employee_rows]
            total = sum(values)
            if cat == "hr_cost":
                total += hr_cost_supplemental_by_month.get(month, 0.0)
            totals[cat] = total
            per_capita_vals[cat] = (total / headcount) if headcount else 0.0
            median_vals[cat] = statistics.median(values) if values else 0.0
        for cat in categories:
            if cat not in SUPPLEMENTAL_CATEGORIES:
                continue
            recipient_values = supplemental_amounts_by_category[cat].get(month, [])
            total = sum(recipient_values)
            totals[cat] = total
            per_capita_vals[cat] = (total / headcount) if headcount else 0.0
            median_vals[cat] = statistics.median(recipient_values) if recipient_values else 0.0
        totals = {cat: totals[cat] for cat in categories}
        per_capita_vals = {cat: per_capita_vals[cat] for cat in categories}
        median_vals = {cat: median_vals[cat] for cat in categories}
        results.append({"month": month, "headcount": headcount, "categories": totals, "per_capita": per_capita_vals, "median": median_vals})
    return results


def _supplemental_by_dept(
    db: Session, month: str, entity: ScopeValue, scope_rules: list[ScopeRule] | None, pay_type: str | None = None
) -> dict[str | None, float]:
    q = db.query(SupplementalPaySnapshot.department1, func.sum(SupplementalPaySnapshot.amount)).filter(
        SupplementalPaySnapshot.month == month, SupplementalPaySnapshot.is_deleted == False  # noqa: E712
    )
    if pay_type:
        q = q.filter(SupplementalPaySnapshot.pay_type == pay_type)
    q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
    q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
    return {dept: total or 0.0 for dept, total in q.group_by(SupplementalPaySnapshot.department1).all()}


def compare_departments_by_category(
    db: Session,
    category: str,
    month: str,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> list[dict]:
    hr_cost_q = db.query(MonthlyEmployeeSnapshot.department1, func.sum(MonthlyEmployeeSnapshot.hr_cost)).filter(
        MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    hr_cost_q = apply_scope_filter(hr_cost_q, MonthlyEmployeeSnapshot.entity, entity)
    hr_cost_q = apply_permission_scope(hr_cost_q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    hr_cost_by_dept = {dept: total or 0.0 for dept, total in hr_cost_q.group_by(MonthlyEmployeeSnapshot.department1).all()}
    # pct_of_hr_cost's denominator has to be the same "人力成本合计" figure
    # get_trend()/get_categories_trend() report (base + supplemental,
    # bonus+backpay combined) - not just the base-batch sum above, same
    # reasoning as the module docstring's "second reconciliation round".
    for dept, supp_total in _supplemental_by_dept(db, month, entity, scope_rules).items():
        hr_cost_by_dept[dept] = hr_cost_by_dept.get(dept, 0.0) + supp_total

    if category in SUPPLEMENTAL_CATEGORIES:
        headcount_q = db.query(MonthlyEmployeeSnapshot.department1, func.count(MonthlyEmployeeSnapshot.id)).filter(
            MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
        )
        headcount_q = apply_scope_filter(headcount_q, MonthlyEmployeeSnapshot.entity, entity)
        headcount_q = apply_permission_scope(headcount_q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
        headcount_by_dept = dict(headcount_q.group_by(MonthlyEmployeeSnapshot.department1).all())
        totals_by_dept = _supplemental_by_dept(db, month, entity, scope_rules, pay_type=SUPPLEMENTAL_CATEGORIES[category])

        results = []
        for department, total in totals_by_dept.items():
            headcount = headcount_by_dept.get(department, 0)
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
        results.sort(key=lambda r: r["total"], reverse=True)
        return results

    col = _column(category)
    q = db.query(
        MonthlyEmployeeSnapshot.department1,
        func.count(MonthlyEmployeeSnapshot.id).label("headcount"),
        func.sum(col).label("total"),
    ).filter(MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    q = q.group_by(MonthlyEmployeeSnapshot.department1)

    headcount_by_dept = {}
    base_total_by_dept = {}
    for department, headcount, total in q.all():
        headcount_by_dept[department] = headcount
        base_total_by_dept[department] = total or 0.0

    # "hr_cost" needs the same base+supplemental fold-in as everywhere else
    # that reports it - including a department that has ONLY a supplemental
    # (bonus/backpay) batch and no base-batch employees at all this month,
    # same "don't silently drop a supplemental-only slot" guard get_trend()/
    # get_categories_trend() already apply per-month.
    departments = set(base_total_by_dept) | (set(hr_cost_by_dept) if category == "hr_cost" else set())

    results = []
    for department in departments:
        headcount = headcount_by_dept.get(department, 0)
        total = hr_cost_by_dept.get(department, 0.0) if category == "hr_cost" else base_total_by_dept.get(department, 0.0)
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
    results.sort(key=lambda r: r["total"], reverse=True)
    return results


def get_cost_composition(
    db: Session,
    month: str,
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> dict:
    q = db.query(*[func.sum(_column(c)) for c in COMPOSITION_REAL_FIELDS], func.sum(MonthlyEmployeeSnapshot.hr_cost)).filter(
        MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    row = q.first()
    if row is None:
        return {"month": month, "department": department, "entity": entity, "hr_cost": 0.0, "categories": []}

    *component_totals, base_hr_cost = row
    base_hr_cost = base_hr_cost or 0.0

    # 奖金批次/补发批次 aren't MonthlyEmployeeSnapshot columns (see module
    # docstring) - pulled from SupplementalPaySnapshot instead, and folded
    # into hr_cost here too so this view's percentages sum to 100% again
    # instead of silently excluding whatever a month's bonus/backpay batch
    # added to the real total.
    supplemental_totals = {
        cat: get_supplemental_cost_by_month(db, [month], department, entity, scope_rules, pay_type=pay_type).get(month, 0.0)
        for cat, pay_type in SUPPLEMENTAL_CATEGORIES.items()
    }
    hr_cost = base_hr_cost + sum(supplemental_totals.values())

    categories = []
    for field, total in zip(COMPOSITION_REAL_FIELDS, component_totals):
        total = total or 0.0
        categories.append(
            {
                "category": field,
                "label": CATEGORY_FIELDS[field],
                "total": total,
                "pct": (total / hr_cost * 100) if hr_cost else 0.0,
            }
        )
    for field in SUPPLEMENTAL_CATEGORIES:
        total = supplemental_totals[field]
        categories.append(
            {
                "category": field,
                "label": CATEGORY_FIELDS[field],
                "total": total,
                "pct": (total / hr_cost * 100) if hr_cost else 0.0,
            }
        )
    return {"month": month, "department": department, "entity": entity, "hr_cost": hr_cost, "categories": categories}
