"""Salary-category breakdown queries (PRD V1.1 §2.3, multi-category trend
added by PRD V1.7 §3.1, per-capita/median/employment-type split added by
PRD V1.9 §1-3): trend for one or more categories at once, cross-department
comparison for a category in one month, and the full cost-composition
percentage split for a scope/month. All deterministic SQL aggregation over
the component fields ingestion/salary_components.py extracts.

Found against a real reconciliation the user did in Excel: get_categories_
trend()'s "人力成本合计" (hr_cost) category used to be base-batch-only, same
as every other category here (底薪/绩效薪资/奖金提成/加班/其他收入/雇主社保
etc.). But "人力成本合计" specifically is supposed to be the SAME "total
cost" figure get_trend() already reports elsewhere in the app (趋势查询
page's total), which DOES fold in bonus/backpay (see compute/trends.py's
get_trend() and get_supplemental_cost_by_month()) - leaving it out here made
this page's total silently short of the real total cost whenever a month had
a sizeable bonus batch.

A second reconciliation round found the flip side of that fix: with
"人力成本合计" correctly including bonus/backpay, the other categories
summed to less than it whenever a month had a sizeable 奖金批次/补发批次 -
that money was real cost, present in the total, but invisible in every
category breakdown (a bonus/backpay row is a flat SupplementalPaySnapshot.
amount, never split into 底薪/绩效薪资/奖金提成 the way a base-batch row is).
Two things followed from that:

1. 奖金批次/补发批次 became their own categories (SUPPLEMENTAL_CATEGORIES
   below) so a bonus batch's money (which genuinely has no natural home in
   底薪/绩效薪资/etc.) is at least visible somewhere, instead of only ever
   showing up in the "人力成本合计" total.
2. A 补发批次 (backpay) upload can now optionally be tagged, at upload time,
   with an EXISTING category it should actually be attributed to (e.g. a
   "客服团队加班费补发" file tagged as 加班费/overtime_amount) - see models.py's
   UploadBatch.category / SupplementalPaySnapshot.category docstrings. A
   tagged backpay batch's amount folds into that real category's own total
   instead of the generic "补发批次" bucket, which now only ever represents
   backpay left uncategorized.

Every category's supplemental contribution (if it has one at all) is
resolved through the single `_supplemental_spec()` below, so every function
in this module (grouped-SUM trend, per-capita trend, department comparison,
composition %) sources it the same way instead of five parallel
re-implementations of "what does this category's supplemental slice look
like" - see HANDOFF.md's "计算逻辑只写一套" principle.
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
# - purely a SupplementalPaySnapshot total (see _supplemental_spec below).
# Every function that iterates `categories` has to skip these when building
# the MonthlyEmployeeSnapshot SQL query and call _column() only for the rest.
SUPPLEMENTAL_CATEGORIES: dict[str, str] = {
    "supplemental_bonus": "bonus",
    "supplemental_backpay": "backpay",
}

# Real (MonthlyEmployeeSnapshot-column) categories that make up hr_cost, for
# get_cost_composition's percentage split and for validating a 补发批次
# upload's chosen category (routers/upload.py) - excludes derived/
# informational totals (gross_salary and hr_cost themselves, net_pay/
# deduction_total which are employee-side, not cost components) and
# SUPPLEMENTAL_CATEGORIES, which aren't real columns at all.
COMPOSITION_REAL_FIELDS = [
    "basic_salary_actual",
    "performance_bonus",
    "commission_bonus",
    "overtime_amount",
    "other_income",
    "employer_statutory_cost",
]


def _supplemental_spec(cat: str) -> dict | None:
    """What SupplementalPaySnapshot slice (if any) folds into category `cat`'s
    total, as kwargs for get_supplemental_cost_by_month/
    get_supplemental_amounts_by_month. None means this category has no
    supplemental equivalent at all (gross_salary/net_pay/deduction_total)."""
    if cat == "hr_cost":
        return {}  # every bonus+backpay row, regardless of tag
    if cat == "supplemental_bonus":
        return {"pay_type": "bonus"}
    if cat == "supplemental_backpay":
        return {"pay_type": "backpay", "uncategorized": True}
    if cat in COMPOSITION_REAL_FIELDS:
        return {"pay_type": "backpay", "category": cat}
    return None


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

    # Every requested category's supplemental slice (see _supplemental_spec)
    # - hr_cost gets everything, supplemental_bonus/supplemental_backpay get
    # their own dedicated slice, a real column category gets whatever backpay
    # was explicitly tagged with it at upload time (module docstring point 2).
    supplemental_by_category: dict[str, dict[str, float]] = {}
    for cat in categories:
        spec = _supplemental_spec(cat)
        if spec is not None:
            supplemental_by_category[cat] = get_supplemental_cost_by_month(db, months, department, entity, scope_rules, employment_type, **spec)

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
            base_val = base_totals.get(cat, 0.0)  # 0.0 for SUPPLEMENTAL_CATEGORIES, which never appear here
            supp_val = supplemental_by_category.get(cat, {}).get(month, 0.0)
            cat_totals[cat] = base_val + supp_val
        results.append({"month": month, "headcount": headcount, "categories": cat_totals})
    return results


def _get_categories_trend_per_capita(db, categories, months, department, entity, scope_rules, employment_type) -> list[dict]:
    """PRD V1.9 §2.1: 人均 = 类目总额 ÷ 该范围内当月在职总人数（跟 get_trend
    的"在职人数（含当月内离职）"口径一致），拆用工类型时分母各自独立计算，
    不共用总分母 - which falls out naturally here since `employment_type`
    filters the underlying row set BEFORE headcount is computed as len(rows).

    Every category's total/per-capita mean folds in its supplemental slice
    (see _supplemental_spec) the same way as the non-per-capita path above -
    per-capita always divides by the SAME headcount as every other category
    (everyone on the base batch that month, not just a bonus/backpay batch's
    recipients), so the mean stays comparable across categories.

    Median is different: it needs each individual employee's own value, and
    a bonus/backpay row only applies to whichever staff_ids that batch
    actually lists (not every employee), so spreading a category's
    supplemental slice evenly across every employee's value before taking
    the median would misrepresent the actual distribution. For a real
    (base-column) category or "hr_cost", the median here stays base-only -
    a known, documented gap rather than a guess. "supplemental_bonus"/
    "supplemental_backpay" are the one exception: a bonus/backpay row IS
    already an individual per-recipient value (unlike a real category, where
    the supplemental slice would need a staff_id join against the base rows
    to even attempt a merge), so their median is taken directly across the
    batch's actual recipients - not padded with zeros for non-recipients
    like the mean is, so it isn't on the exact same population as the other
    categories' medians."""
    real_categories = [c for c in categories if c not in SUPPLEMENTAL_CATEGORIES]
    cols = [_column(c) for c in real_categories]
    q = _base_query(db, department, entity, scope_rules, months, employment_type).with_entities(MonthlyEmployeeSnapshot.month, *cols)
    rows = q.order_by(MonthlyEmployeeSnapshot.month).all()

    by_month: dict[str, list] = {}
    for row in rows:
        by_month.setdefault(row[0], []).append(row[1:])

    supplemental_by_category: dict[str, dict[str, float]] = {}
    supplemental_recipient_values: dict[str, dict[str, list[float]]] = {}
    for cat in categories:
        spec = _supplemental_spec(cat)
        if spec is None:
            continue
        if cat in SUPPLEMENTAL_CATEGORIES:
            supplemental_recipient_values[cat] = get_supplemental_amounts_by_month(
                db, months, department, entity, scope_rules, employment_type, **spec
            )
        else:
            supplemental_by_category[cat] = get_supplemental_cost_by_month(db, months, department, entity, scope_rules, employment_type, **spec)

    all_months = set(by_month)
    for by_month_totals in supplemental_by_category.values():
        all_months |= set(by_month_totals)
    for by_month_values in supplemental_recipient_values.values():
        all_months |= set(by_month_values)
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
            total = sum(values) + supplemental_by_category.get(cat, {}).get(month, 0.0)
            totals[cat] = total
            per_capita_vals[cat] = (total / headcount) if headcount else 0.0
            median_vals[cat] = statistics.median(values) if values else 0.0
        for cat in categories:
            if cat not in SUPPLEMENTAL_CATEGORIES:
                continue
            recipient_values = supplemental_recipient_values[cat].get(month, [])
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
    db: Session,
    month: str,
    entity: ScopeValue,
    scope_rules: list[ScopeRule] | None,
    pay_type: str | None = None,
    category: str | None = None,
    uncategorized: bool = False,
) -> dict[str | None, float]:
    q = db.query(SupplementalPaySnapshot.department1, func.sum(SupplementalPaySnapshot.amount)).filter(
        SupplementalPaySnapshot.month == month, SupplementalPaySnapshot.is_deleted == False  # noqa: E712
    )
    if pay_type:
        q = q.filter(SupplementalPaySnapshot.pay_type == pay_type)
    if uncategorized:
        q = q.filter(SupplementalPaySnapshot.category.is_(None))
    elif category:
        q = q.filter(SupplementalPaySnapshot.category == category)
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
    # bonus+backpay combined, any category tag) - not just the base-batch sum
    # above, same reasoning as the module docstring's "second reconciliation
    # round".
    for dept, supp_total in _supplemental_by_dept(db, month, entity, scope_rules).items():
        hr_cost_by_dept[dept] = hr_cost_by_dept.get(dept, 0.0) + supp_total

    spec = _supplemental_spec(category)
    supplemental_total_by_dept = _supplemental_by_dept(db, month, entity, scope_rules, **spec) if spec is not None else {}

    if category in SUPPLEMENTAL_CATEGORIES:
        headcount_q = db.query(MonthlyEmployeeSnapshot.department1, func.count(MonthlyEmployeeSnapshot.id)).filter(
            MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
        )
        headcount_q = apply_scope_filter(headcount_q, MonthlyEmployeeSnapshot.entity, entity)
        headcount_q = apply_permission_scope(headcount_q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
        headcount_by_dept = dict(headcount_q.group_by(MonthlyEmployeeSnapshot.department1).all())

        results = []
        for department, total in supplemental_total_by_dept.items():
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

    # A department can have ONLY a supplemental contribution to this category
    # this month (e.g. hr_cost via a bonus-only department, or a real
    # category via a tagged backpay batch covering a department with no base
    # employees at all) - same "don't silently drop a supplemental-only
    # slot" guard get_trend()/get_categories_trend() already apply per-month.
    departments = set(base_total_by_dept) | set(hr_cost_by_dept if category == "hr_cost" else supplemental_total_by_dept)

    results = []
    for department in departments:
        headcount = headcount_by_dept.get(department, 0)
        if category == "hr_cost":
            total = hr_cost_by_dept.get(department, 0.0)
        else:
            total = base_total_by_dept.get(department, 0.0) + supplemental_total_by_dept.get(department, 0.0)
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

    # 奖金批次/补发批次、以及被打上标签的补发批次金额都不是 MonthlyEmployeeSnapshot
    # 列（见模块文档），一律走 SupplementalPaySnapshot - 每个 COMPOSITION_REAL_FIELDS
    # 类目也要把自己被标记的补发批次金额加进去，成本构成的百分比总和才会重新等于100%，
    # 而不是悄悄漏掉某个月奖金/补发批次贡献的那部分。
    display_fields = COMPOSITION_REAL_FIELDS + list(SUPPLEMENTAL_CATEGORIES)
    supplemental_totals = {
        field: get_supplemental_cost_by_month(db, [month], department, entity, scope_rules, **_supplemental_spec(field)).get(month, 0.0)
        for field in display_fields
    }
    all_supplemental = get_supplemental_cost_by_month(db, [month], department, entity, scope_rules).get(month, 0.0)
    hr_cost = base_hr_cost + all_supplemental

    categories = []
    for field, base_total in zip(COMPOSITION_REAL_FIELDS, component_totals):
        total = (base_total or 0.0) + supplemental_totals[field]
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
