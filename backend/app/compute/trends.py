"""Deterministic headcount / cost trend aggregation. No LLM involved.

Mirrors the "各月总人力成本 & 人数" section of attribution_analysis.py, but
generalized to any department/entity filter and any set of months, and
backed by the DB instead of a pickle file.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import MonthlyEmployeeSnapshot


def list_available_months(db: Session) -> list[str]:
    rows = db.query(MonthlyEmployeeSnapshot.month).distinct().order_by(MonthlyEmployeeSnapshot.month).all()
    return [r[0] for r in rows]


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

    results = []
    for month, headcount, total_hr_cost in q.all():
        total_hr_cost = total_hr_cost or 0.0
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
