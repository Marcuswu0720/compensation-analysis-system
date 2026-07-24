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


def _supplemental_by_month(
    db: Session,
    months: list[str] | None,
    department: ScopeValue,
    entity: ScopeValue,
    scope_rules: list[ScopeRule] | None,
) -> dict[str, float]:
    q = db.query(SupplementalPaySnapshot.month, func.sum(SupplementalPaySnapshot.amount)).filter(
        SupplementalPaySnapshot.is_deleted == False  # noqa: E712
    )
    if months:
        q = q.filter(SupplementalPaySnapshot.month.in_(months))
    q = apply_scope_filter(q, SupplementalPaySnapshot.department1, department)
    q = apply_scope_filter(q, SupplementalPaySnapshot.entity, entity)
    q = apply_permission_scope(q, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)
    q = q.group_by(SupplementalPaySnapshot.month)
    return {month: amount or 0.0 for month, amount in q.all()}


def get_trend(
    db: Session,
    months: list[str] | None = None,
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
) -> list[dict]:
    # Headcount/cost here is a "cash flow" measure: everyone who has a payroll
    # record for the month (including someone who resigned mid-month but still
    # got a partial paycheck), matching the validated reference calculation -
    # NOT a snapshot of who is active as of today. See PRD §2.2.
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

    q = q.group_by(MonthlyEmployeeSnapshot.month).order_by(MonthlyEmployeeSnapshot.month)

    # Bonus/backpay files uploaded standalone (salary_type != 'base') add cost
    # on top of the base batch for the same month without creating headcount -
    # see ingestion/commit.py for why these live in a separate table.
    supplemental = _supplemental_by_month(db, months, department, entity, scope_rules)
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
