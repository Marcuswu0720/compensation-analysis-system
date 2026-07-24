"""Month-over-month cost attribution: joiners / leavers / stayers breakdown,
plus (PRD V1.1 §4) a component-level decomposition of the stayers' change and
a behavioral narrative (who got a raise vs whose performance bonus moved vs
whose commission/overtime changed).

Direct port of the validated attribution_analysis.py logic (PRD §5.3),
generalized to any department/entity scope and backed by the DB. The
checksum against net change is preserved exactly: if it doesn't reconcile we
say so instead of returning a number that might be wrong, per the PRD's
"校验不吻合需要报错而不是硬给一个数字" principle.

Standalone bonus/backpay uploads (salary_type != 'base', see
ingestion/commit.py) fold into whichever staff_id they're tagged to before
the joiner/leaver/stayer split runs, so a backpay payment shows up as part of
that person's cost change rather than an unexplained gap. A supplemental
entry whose staff_id isn't in the base roster for that month at all (person
already gone, or base not uploaded yet) can't be attributed to anyone -
those are tracked separately as `unattributed_delta` and still added into
the checksum so it keeps reconciling against the real net change. Because
supplemental pay has no per-category breakdown (it's a lump sum from a
standalone file), it shows up inside the stayers' component decomposition as
part of `other_residual`, not one of the six named categories - see
`_component_deltas`.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import ExitRecord, MonthlyEmployeeSnapshot, SupplementalPaySnapshot
from .scope import ScopeRule, apply_permission_scope, apply_scope_filter

ScopeValue = str | list[str] | None

COMPONENT_FIELDS = [
    "basic_salary_actual",
    "performance_bonus",
    "commission_bonus",
    "overtime_amount",
    "other_income",
    "employer_statutory_cost",
]
COMPONENT_LABELS = {
    "basic_salary_actual": "底薪",
    "performance_bonus": "绩效薪资",
    "commission_bonus": "奖金/提成",
    "overtime_amount": "加班费",
    "other_income": "其他收入",
    "employer_statutory_cost": "雇主社保成本",
    "other_residual": "其他/无法拆分的差异（含奖金补发等未分类项目）",
}
CHANGE_TOLERANCE = 1.0  # naira - below this, treat two amounts as "unchanged" (rounding noise)
FORMAL_RAISE_MONTHS = {4, 10}  # per PRD §4.3: formal salary adjustments are only expected in April/October


@dataclass
class EmployeeCost:
    staff_id: str
    name: str | None
    job_grade: str | None
    hr_cost: float


@dataclass
class BehaviorLabel:
    label: str
    count_formal: int
    count_contract: int
    amount: float
    pct_of_net_change: float | None


@dataclass
class _ScopedEmployee:
    staff_id: str
    staff_name: str | None
    job_grade: str | None
    employment_type: str | None
    hr_cost: float
    basic_salary_actual: float
    performance_bonus: float
    commission_bonus: float
    overtime_amount: float
    other_income: float
    employer_statutory_cost: float


@dataclass
class AttributionResult:
    prev_month: str
    cur_month: str
    department: ScopeValue
    entity: ScopeValue
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
    unattributed_prev: float
    unattributed_cur: float
    unattributed_delta: float
    checksum: float
    reconciled: bool
    joiners_pct: float | None
    leavers_pct: float | None
    stayers_pct: float | None
    component_deltas: dict[str, float] = field(default_factory=dict)
    behavior_labels: list[BehaviorLabel] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    top_increases: list[EmployeeCost] = field(default_factory=list)
    top_decreases: list[EmployeeCost] = field(default_factory=list)
    leaver_reasons: dict[str, int] = field(default_factory=dict)


def _fetch_scope(
    db: Session,
    month: str,
    department: ScopeValue,
    entity: ScopeValue,
    scope_rules: list[ScopeRule] | None,
) -> tuple[dict[str, _ScopedEmployee], float]:
    # Same "everyone with a payroll record that month" scope as get_trend - see
    # the comment there. A staff_id present in month M but absent in month M+1
    # is exactly what makes them a "leaver" for attribution purposes.
    q = db.query(MonthlyEmployeeSnapshot).filter(
        MonthlyEmployeeSnapshot.month == month, MonthlyEmployeeSnapshot.is_deleted == False  # noqa: E712
    )
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.department1, department)
    q = apply_scope_filter(q, MonthlyEmployeeSnapshot.entity, entity)
    q = apply_permission_scope(q, MonthlyEmployeeSnapshot.entity, MonthlyEmployeeSnapshot.department1, scope_rules)
    scoped = {
        row.staff_id: _ScopedEmployee(
            staff_id=row.staff_id,
            staff_name=row.staff_name,
            job_grade=row.job_grade,
            employment_type=row.employment_type,
            hr_cost=row.hr_cost,
            basic_salary_actual=row.basic_salary_actual or 0.0,
            performance_bonus=row.performance_bonus or 0.0,
            commission_bonus=row.commission_bonus or 0.0,
            overtime_amount=row.overtime_amount or 0.0,
            other_income=row.other_income or 0.0,
            employer_statutory_cost=row.employer_statutory_cost or 0.0,
        )
        for row in q.all()
    }

    supq = db.query(SupplementalPaySnapshot).filter(
        SupplementalPaySnapshot.month == month, SupplementalPaySnapshot.is_deleted == False  # noqa: E712
    )
    supq = apply_scope_filter(supq, SupplementalPaySnapshot.department1, department)
    supq = apply_scope_filter(supq, SupplementalPaySnapshot.entity, entity)
    supq = apply_permission_scope(supq, SupplementalPaySnapshot.entity, SupplementalPaySnapshot.department1, scope_rules)

    unattributed = 0.0
    for row in supq.all():
        if row.staff_id in scoped:
            # Supplemental pay has no category breakdown of its own, so it
            # only adds to hr_cost - it shows up as "other_residual" once the
            # component decomposition below can't account for it either.
            scoped[row.staff_id].hr_cost += row.amount
        else:
            unattributed += row.amount

    return scoped, unattributed


def _pct(amount: float, net_change: float) -> float | None:
    return (amount / net_change * 100) if net_change else None


def _component_deltas(prev_emps: dict, cur_emps: dict, stayers: set[str], stayers_delta: float) -> dict[str, float]:
    deltas = {
        field: sum(getattr(cur_emps[sid], field) - getattr(prev_emps[sid], field) for sid in stayers)
        for field in COMPONENT_FIELDS
    }
    # hr_cost = the 6 named components + whatever isn't captured by them
    # (supplemental pay, or the small number of rows where the source file's
    # own gross_salary doesn't exactly equal its component columns - see
    # ingestion/salary_components.py). Defining the residual this way means
    # the seven lines always reconcile to stayers_delta exactly, by
    # construction, regardless of upstream data quirks.
    deltas["other_residual"] = stayers_delta - sum(deltas.values())
    return deltas


def _behavior_labels(prev_emps: dict, cur_emps: dict, stayers: set[str], net_change: float) -> list[BehaviorLabel]:
    def changed(sid: str, field: str) -> bool:
        return abs(getattr(cur_emps[sid], field) - getattr(prev_emps[sid], field)) > CHANGE_TOLERANCE

    predicates = {
        "底薪调整": lambda sid: changed(sid, "basic_salary_actual"),
        "绩效薪资波动": lambda sid: not changed(sid, "basic_salary_actual") and changed(sid, "performance_bonus"),
        "奖金/提成变化": lambda sid: changed(sid, "commission_bonus"),
        "加班费变化": lambda sid: changed(sid, "overtime_amount"),
    }

    labels = []
    for name, predicate in predicates.items():
        matching = [sid for sid in stayers if predicate(sid)]
        count_formal = sum(1 for sid in matching if cur_emps[sid].employment_type == "Formal")
        count_contract = len(matching) - count_formal
        amount = sum(cur_emps[sid].hr_cost - prev_emps[sid].hr_cost for sid in matching)
        labels.append(
            BehaviorLabel(
                label=name,
                count_formal=count_formal,
                count_contract=count_contract,
                amount=amount,
                pct_of_net_change=_pct(amount, net_change),
            )
        )
    return labels


def _anomalies(behavior_labels: list[BehaviorLabel], cur_month: str) -> list[str]:
    anomalies = []
    raise_label = next((b for b in behavior_labels if b.label == "底薪调整"), None)
    cur_month_num = int(cur_month.split("-")[1])
    if raise_label and raise_label.count_formal > 0 and cur_month_num not in FORMAL_RAISE_MONTHS:
        anomalies.append(
            f"正式工调薪窗口通常固定在4月/10月，但 {cur_month} 检测到 {raise_label.count_formal} 名正式工发生了底薪调整，建议核实原因"
        )
    return anomalies


def compute_attribution(
    db: Session,
    prev_month: str,
    cur_month: str,
    department: ScopeValue = None,
    entity: ScopeValue = None,
    scope_rules: list[ScopeRule] | None = None,
    top_n: int = 5,
) -> AttributionResult:
    prev_emps, unattributed_prev = _fetch_scope(db, prev_month, department, entity, scope_rules)
    cur_emps, unattributed_cur = _fetch_scope(db, cur_month, department, entity, scope_rules)

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

    prev_total = sum(e.hr_cost for e in prev_emps.values()) + unattributed_prev
    cur_total = sum(e.hr_cost for e in cur_emps.values()) + unattributed_cur
    net_change = cur_total - prev_total
    unattributed_delta = unattributed_cur - unattributed_prev

    checksum = joiners_cost - leavers_cost + stayers_delta + unattributed_delta
    reconciled = abs(checksum - net_change) < 1

    component_deltas = _component_deltas(prev_emps, cur_emps, stayers, stayers_delta)
    behavior_labels = _behavior_labels(prev_emps, cur_emps, stayers, net_change)
    anomalies = _anomalies(behavior_labels, cur_month)

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
        q = db.query(ExitRecord).filter(ExitRecord.staff_id.in_(leavers), ExitRecord.is_deleted == False)  # noqa: E712
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
        unattributed_prev=unattributed_prev,
        unattributed_cur=unattributed_cur,
        unattributed_delta=unattributed_delta,
        checksum=checksum,
        reconciled=reconciled,
        joiners_pct=_pct(joiners_cost, net_change),
        leavers_pct=_pct(-leavers_cost, net_change),
        stayers_pct=_pct(stayers_delta, net_change),
        component_deltas=component_deltas,
        behavior_labels=behavior_labels,
        anomalies=anomalies,
        top_increases=top_increases,
        top_decreases=top_decreases,
        leaver_reasons=leaver_reasons,
    )
