"""Deterministic headcount / cost trend aggregation. No LLM involved.

Mirrors the "各月总人力成本 & 人数" section of attribution_analysis.py, but
generalized to any department/entity filter and any set of months, and
backed by the DB instead of a pickle file.

`department`/`entity` accept either a single name or a list of names (used
when a restricted viewer has no specific selection - see security.py's
get_allowed_scope) - apply_scope_filter in scope.py handles both forms.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot, SupplementalPaySnapshot
from .scope import ScopeRule, apply_permission_scope, apply_scope_filter

ScopeValue = str | list[str] | None


def list_available_months(db: Session) -> list[str]:
    base_months = {
        r[0] for r in db.query(MonthlyEmployeeSnapshot.month).filter(MonthlyEmployeeSnapshot.is_deleted == False).distinct().all()  # noqa: E712
    }
    supplemental_months = {
        r[0] for r in db.query(SupplementalPaySnapshot.month).filter(SupplementalPaySnapshot.is_deleted == False).distinct().all()  # noqa: E712
    }
    return sorted(base_months | supplemental_months)


def get_supplemental_cost_by_month(
    db: Session,
    months: list[str] | None,
    department: ScopeValue,
    entity: ScopeValue,
    scope_rules: list[ScopeRule] | None,
    employment_type: str | None = None,
    pay_type: str | None = None,
    category: str | None = None,
    uncategorized: bool = False,
    department2: str | None = None,
) -> dict[str, float]:
    """The bonus/backpay total (SupplementalPaySnapshot.amount) that
    get_trend() folds into total_hr_cost on top of the base batch - broken
    out as its own function (not private to this module) so any other
    "总成本/人力成本" figure elsewhere in the app can add the exact same
    number instead of re-deriving its own, potentially-divergent version of
    "what does bonus+backpay contribute this month" (see compute/
    categories.py's get_categories_trend, which folds this into its
    "人力成本合计" category for the same reason).

    `employment_type` is optional and unused by get_trend() itself (that
    figure is never split by employment type) - it exists for callers like
    get_categories_trend that do support a Formal/Contract filter and need
    the supplemental total scoped to match the same filtered headcount.

    `pay_type` ('bonus' | 'backpay' | None for both combined) is optional too
    and unused by get_trend() (total_hr_cost always wants both combined) - it
    exists for callers like get_categories_trend's dedicated 奖金批次/补发批次
    categories (PRD: 薪资类目页面新增类目，让这部分金额不再只隐藏在"人力成本
    合计"里) that need just one pay_type's contribution broken out.

    `category`/`uncategorized`: a 补发批次 upload can optionally be tagged
    with an existing 薪资类目 (e.g. 加班费) at upload time - see models.py's
    UploadBatch.category docstring. `category="overtime_amount"` sums only
    backpay rows tagged with that category (folded into that category's own
    total elsewhere instead of the generic "补发批次" bucket); `uncategorized=
    True` sums backpay rows with NO tag (still the generic "补发批次" bucket,
    for batches uploaded before this feature existed or left unassigned).
    Mutually exclusive with each other; unused by get_trend() (the grand
    total wants every backpay row regardless of tag).

    `department2` is the same "narrow down further within the already-
    permission-scoped department1" filter get_trend()/compute_attribution()
    support - like `employment_type`, a 补发批次 (backpay) row's own
    department2 column is always NULL (that loose upload shape never
    captures it, only a 奖金批次 row does - see ingestion/loader.py), so
    filtering by department2 drops backpay rows out of scope entirely rather
    than guessing which department2 they belonged to."""
    q = db.query(SupplementalPaySnapshot.month, func.sum(SupplementalPaySnapshot.amount)).filter(
        SupplementalPaySnapshot.is_deleted == False  # noqa: E712
    )
    if months:
        q = q.filter(SupplementalPaySnapshot.month.in_(months))
    q = apply_scope_filter(q, SupplementalPaySnapshot.department1, department)
    q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
    q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
    if employment_type:
        q = q.filter(SupplementalPaySnapshot.employment_type == employment_type)
    if pay_type:
        q = q.filter(SupplementalPaySnapshot.pay_type == pay_type)
    if uncategorized:
        q = q.filter(SupplementalPaySnapshot.category.is_(None))
    elif category:
        q = q.filter(SupplementalPaySnapshot.category == category)
    if department2:
        q = q.filter(SupplementalPaySnapshot.department2 == department2)
    q = q.group_by(SupplementalPaySnapshot.month)
    return {month: amount or 0.0 for month, amount in q.all()}


def get_supplemental_amounts_by_month(
    db: Session,
    months: list[str] | None,
    department: ScopeValue,
    entity: ScopeValue,
    scope_rules: list[ScopeRule] | None,
    employment_type: str | None = None,
    pay_type: str | None = None,
    category: str | None = None,
    uncategorized: bool = False,
    department2: str | None = None,
) -> dict[str, list[float]]:
    """Same filters as get_supplemental_cost_by_month (including category/
    uncategorized/department2), but returns each month's individual row
    amounts instead of a pre-summed total. Needed by get_categories_trend's
    per-capita path for the 奖金批次/补发批次 categories' median (a median
    needs the actual per-recipient values, a SQL SUM can't give you that)."""
    q = db.query(SupplementalPaySnapshot.month, SupplementalPaySnapshot.amount).filter(
        SupplementalPaySnapshot.is_deleted == False  # noqa: E712
    )
    if months:
        q = q.filter(SupplementalPaySnapshot.month.in_(months))
    q = apply_scope_filter(q, SupplementalPaySnapshot.department1, department)
    q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
    q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
    if employment_type:
        q = q.filter(SupplementalPaySnapshot.employment_type == employment_type)
    if pay_type:
        q = q.filter(SupplementalPaySnapshot.pay_type == pay_type)
    if uncategorized:
        q = q.filter(SupplementalPaySnapshot.category.is_(None))
    elif category:
        q = q.filter(SupplementalPaySnapshot.category == category)
    if department2:
        q = q.filter(SupplementalPaySnapshot.department2 == department2)
    result: dict[str, list[float]] = {}
    for month, amount in q.all():
        result.setdefault(month, []).append(amount or 0.0)
    return result


def get_trend(
    db: Session,
    months: list[str] | None = None,
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
    employment_type: str | None = None,
    department2: str | None = None,
) -> list[dict]:
    # Headcount/cost here is a "cash flow" measure: everyone who has a payroll
    # record for the month (including someone who resigned mid-month but still
    # got a partial paycheck), matching the validated reference calculation -
    # NOT a snapshot of who is active as of today. See PRD §2.2.
    #
    # `employment_type` ('Formal' | 'Contract' | None for both combined) is a
    # plain filter, same as compute/categories.py's get_categories_trend -
    # "对比 Formal vs Contract" on the 趋势查询 page is just calling this
    # function twice with each value and combining client-side, not a third
    # mode this function needs to know about.
    #
    # `department2` narrows further within `department` - unlike department1/
    # entity, it's not a permission boundary (ViewerPermission only ever
    # grants at the entity/department1 level), so it's just one more plain
    # filter on top of whatever apply_permission_scope already restricted the
    # query to. The frontend only offers it once a single department1 is
    # picked (see /api/meta's department2_by_department1), but nothing here
    # requires that - it's a harmless no-op if department2 doesn't actually
    # belong to `department`.
    q = db.query(
        MonthlyEmployeeSnapshot.month,
        func.count(MonthlyEmployeeSnapshot.id).label("headcount"),
        func.sum(MonthlyEmployeeSnapshot.hr_cost).label("total_hr_cost"),
    ).filter(MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712

    if months:
        q = q.filter(MonthlyEmployeeSnapshot.month.in_(months))
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    if employment_type:
        q = q.filter(MonthlyEmployeeSnapshot.employment_type == employment_type)
    if department2:
        q = q.filter(MonthlyEmployeeSnapshot.department2 == department2)

    q = q.group_by(MonthlyEmployeeSnapshot.month).order_by(MonthlyEmployeeSnapshot.month)

    # Bonus/backpay files uploaded standalone (salary_type != 'base') add cost
    # on top of the base batch for the same month without creating headcount -
    # see ingestion/commit.py for why these live in a separate table.
    supplemental = get_supplemental_cost_by_month(db, months, department, entity, scope_rules, employment_type, department2=department2)
    base_rows = {month: (headcount, total_hr_cost or 0.0) for month, headcount, total_hr_cost in q.all()}

    # A month can have supplemental data uploaded before (or reassigned without)
    # a base batch - don't silently drop that cost just because there's no
    # base row to iterate from.
    all_months = sorted(set(base_rows) | set(supplemental))

    results = []
    for month in all_months:
        headcount, base_cost = base_rows.get(month, (0, 0.0))
        total_hr_cost = base_cost + supplemental.get(month, 0.0)
        results.append(
            {
                "month": month,
                "headcount": headcount,
                "total_hr_cost": total_hr_cost,
                "avg_hr_cost": (total_hr_cost / headcount) if headcount else 0.0,
            }
        )
    return results


def list_departments(db: Session, scope_rules: list[ScopeRule] | None = None) -> list[str]:
    """scope_rules=None (admin) returns every department; otherwise only
    departments actually reachable under the viewer's granted rules - an
    entity-wide rule reaches every department under that entity, an
    entity_department rule reaches exactly that one pair (PRD V1.2 §1)."""
    q = db.query(MonthlyEmployeeSnapshot.department1, MonthlyEmployeeSnapshot.entity).filter(
        MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    rows = q.distinct().all()
    return sorted({d for d, _ in rows if d})


def list_entities(db: Session, scope_rules: list[ScopeRule] | None = None) -> list[str]:
    q = db.query(MonthlyEmployeeSnapshot.entity).filter(MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
    if scope_rules is not None:
        allowed = {r.entity for r in scope_rules}
        q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, list(allowed))
    rows = q.distinct().order_by(MonthlyEmployeeSnapshot.entity).all()
    return [r[0] for r in rows if r[0]]


def list_departments2_by_department1(db: Session, scope_rules: list[ScopeRule] | None = None) -> dict[str, list[str]]:
    """department1 -> sorted list of department2 values seen under it, for
    the 趋势查询/薪资类目 filter rows' cascading dropdown (department2 select
    only enables once a single department1 is picked). Deliberately NOT
    entity-scoped, matching list_departments()'s own flat (entity-agnostic)
    shape - the department1 dropdown these filter rows already use doesn't
    care about the entity selection either, so department2 shouldn't be the
    first place that inconsistency shows up.

    department2 has no canonical-name resolution pass the way department1/
    entity do (see ingestion/normalize.py) - it's stored exactly as it
    appears in the source file, so casing/wording variants across months
    will show up here as separate options rather than being merged. Blank
    department2 values are dropped (not offered as a fake option) - leaving
    department2 unselected already shows everyone under the chosen
    department1, blank-department2 employees included."""
    q = db.query(MonthlyEmployeeSnapshot.department1, MonthlyEmployeeSnapshot.department2).filter(
        MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    result: dict[str, set[str]] = {}
    for department1, department2 in q.distinct().all():
        if not department1 or not department2:
            continue
        result.setdefault(department1, set()).add(department2)
    return {department1: sorted(values) for department1, values in sorted(result.items())}


def list_departments_by_entity(db: Session) -> dict[str, list[str]]:
    """Unrestricted entity -> sorted department list, for the admin-only
    permission-grant UI's linked entity/department dropdowns (PRD V1.2 §1.4)."""
    rows = (
        db.query(MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1)
        .filter(MonthlyEmployeeSnapshot.is_deleted == False)  # noqa: E712
        .distinct()
        .all()
    )
    result: dict[str, set[str]] = {}
    for entity, department in rows:
        if not entity or not department:
            continue
        result.setdefault(entity, set()).add(department)
    return {entity: sorted(depts) for entity, depts in sorted(result.items())}
