"""Month-over-month cost attribution: joiners / leavers / stayers breakdown.

Direct port of the validated attribution_analysis.py logic (PRD §5.3),
generalized to any department/entity scope and backed by the DB. The
three-way checksum against net change is preserved exactly: if it doesn't
reconcile we raise instead of returning a number that might be wrong,
per the PRD's "校验不吻合需要报错而不是硬给一个数字" principle.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import ExitRecord, MonthlyEmployeeSnapshot


@dataclass
class EmployeeCost:
    staff_id: str
    name: str | None
    job_grade: str | None
    hr_cost: float


@dataclass
class AttributionResult:
    prev_month: str
    cur_month: str
    department: str | None
    entity: str | None
    prev_total: float
    cur_total: float
    net_change: float
    joiners_count: int
    joiners_cost: float
    leavers_count: int
    leavers_cost: float
    stayers_count: int
    stayers_prev_cost: float
    stayers_cur_cost: float
    stayers_delta: float
    checksum: float
    reconciled: bool
    top_increases: list[EmployeeCost] = field(default_factory=list)
    top_decreases: list[EmployeeCost] = field(default_factory=list)
    leaver_reasons: dict[str, int] = field(default_factory=dict)


def _fetch_scope(db: Session, month: str, department: str | None, entity: str | None) -> dict[str, MonthlyEmployeeSnapshot]:
    # Same "everyone with a payroll record that month" scope as get_trend - see
    # the comment there. A staff_id present in month M but absent in month M+1
    # is exactly what makes them a "leaver" for attribution purposes.
    q = db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.month == month)
    if department:
        q = q.filter(MonthlyEmployeeSnapshot.department1 == department)
    if entity:
        q = q.filter(MonthlyEmployeeSnapshot.entity == entity)
    return {row.staff_id: row for row in q.all()}


def compute_attribution(
    db: Session,
    prev_month: str,
    cur_month: str,
    department: str | None = None,
    entity: str | None = None,
    top_n: int = 5,
) -> AttributionResult:
    prev_emps = _fetch_scope(db, prev_month, department, entity)
    cur_emps = _fetch_scope(db, cur_month, department, entity)

    prev_ids = set(prev_emps.keys())
    cur_ids = set(cur_emps.keys())

    joiners = cur_ids - prev_ids
    leavers = prev_ids - cur_ids
    stayers = prev_ids & cur_ids

    joiners_cost = sum(cur_emps[i].hr_cost for i in joiners)
    leavers_cost = sum(prev_emps[i].hr_cost for i in leavers)
    stayers_prev_cost = sum(prev_emps[i].hr_cost for i in stayers)
    stayers_cur_cost = sum(cur_emps[i].hr_cost for i in stayers)
    stayers_delta = stayers_cur_cost - stayers_prev_cost

    prev_total = sum(e.hr_cost for e in prev_emps.values())
    cur_total = sum(e.hr_cost for e in cur_emps.values())
    net_change = cur_total - prev_total

    checksum = joiners_cost - leavers_cost + stayers_delta
    reconciled = abs(checksum - net_change) < 1

    stayer_deltas = sorted(
        (
            EmployeeCost(sid, cur_emps[sid].staff_name, cur_emps[sid].job_grade, cur_emps[sid].hr_cost - prev_emps[sid].hr_cost)
            for sid in stayers
        ),
        key=lambda x: -x.hr_cost,
    )
    top_increases = stayer_deltas[:top_n]
    top_decreases = list(reversed(stayer_deltas[-top_n:])) if stayer_deltas else []

    leaver_reasons: dict[str, int] = {}
    if leavers:
        q = db.query(ExitRecord).filter(ExitRecord.staff_id.in_(leavers))
        for rec in q.all():
            key = rec.reason_for_leaving or "未记录原因"
            leaver_reasons[key] = leaver_reasons.get(key, 0) + 1

    return AttributionResult(
        prev_month=prev_month,
        cur_month=cur_month,
        department=department,
        entity=entity,
        prev_total=prev_total,
        cur_total=cur_total,
        net_change=net_change,
        joiners_count=len(joiners),
        joiners_cost=joiners_cost,
        leavers_count=len(leavers),
        leavers_cost=leavers_cost,
        stayers_count=len(stayers),
        stayers_prev_cost=stayers_prev_cost,
        stayers_cur_cost=stayers_cur_cost,
        stayers_delta=stayers_delta,
        checksum=checksum,
        reconciled=reconciled,
        top_increases=top_increases,
        top_decreases=top_decreases,
        leaver_reasons=leaver_reasons,
    )
