"""Deterministic headcount / cost trend aggregation. No LLM involved.

Mirrors the "各月总人力成本 & 人数" section of attribution_analysis.py, but
generalized to any department/entity filter and any set of months, and
backed by the DB instead of a pickle file.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot, SupplementalPaySnapshot


def list_available_months(db: Session) -> list[str]:
    base_months = {r[0] for r in db.query(MonthlyEmployeeSnapshot.month).distinct().all()}
    supplemental_months = {r[0] for r in db.query(SupplementalPaySnapshot.month).distinct().all()}
    return sorted(base_months | supplemental_months)


def _supplemental_by_month(
    db: Session, months: list[str] | None, department: str | None, entity: str | None
) -> dict[str, float]:
    q = db.query(SupplementalPaySnapshot.month, func.sum(SupplementalPaySnapshot.amount))
    if months:
        q = q.filter(SupplementalPaySnapshot.month.in_(months))
    if department:
        q = q.filter(SupplementalPaySnapshot.department1 == department)
    if entity:
        q = q.filter(SupplementalPaySnapshot.entity == entity)
    q = q.group_by(SupplementalPaySnapshot.month)
    return {month: amount or 0.0 for month, amount in q.all()}


def get_trend(
    db: Session,
    months: list[str] | None = None,
    department: str | None = None,
    entity: str | None = None,
) -> list[dict]:
    # Headcount/cost here is a "cash flow" measure: everyone who has a payroll
    # record for the month (including someone who resigned mid-month but still
    # got a partial paycheck), matching the validated reference calculation -
    # NOT a snapshot of who is active as of today. See PRD §2.2.
    q = db.query(
        MonthlyEmployeeSnapshot.month,
        func.count(MonthlyEmployeeSnapshot.id).label("headcount"),
        func.sum(MonthlyEmployeeSnapshot.hr_cost).label("total_hr_cost"),
    )

    if months:
        q = q.filter(MonthlyEmployeeSnapshot.month.in_(months))
    if department:
        q = q.filter(MonthlyEmployeeSnapshot.department1 == department)
    if entity:
        q = q.filter(MonthlyEmployeeSnapshot.entity == entity)

    q = q.group_by(MonthlyEmployeeSnapshot.month).order_by(MonthlyEmployeeSnapshot.month)

    # Bonus/backpay files uploaded standalone (salary_type != 'base') add cost
    # on top of the base batch for the same month without creating headcount -
    # see ingestion/commit.py for why these live in a separate table.
    supplemental = _supplemental_by_month(db, months, department, entity)
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


def list_departments(db: Session) -> list[str]:
    rows = db.query(MonthlyEmployeeSnapshot.department1).distinct().order_by(MonthlyEmployeeSnapshot.department1).all()
    return [r[0] for r in rows if r[0]]


def list_entities(db: Session) -> list[str]:
    rows = db.query(MonthlyEmployeeSnapshot.entity).distinct().order_by(MonthlyEmployeeSnapshot.entity).all()
    return [r[0] for r in rows if r[0]]
