from app.compute.attribution import compute_attribution
from app.compute.categories import compare_departments_by_category, get_categories_trend, get_cost_composition
from app.compute.trends import get_trend
from app.ingestion.commit import confirm_upload
from app.ingestion.loader import stage_upload

from .xlsx_fixtures import build_component_workbook, build_supplemental_workbook

MONTH1_EMPLOYEES = [
    {"staff_id": "E001", "name": "Alice", "role": "formal", "department": "Ops", "basic": 100000, "perf_bonus": 20000, "commission": 0, "overtime": 0, "statutory": 10000},
    {"staff_id": "E002", "name": "Bob", "role": "contract", "department": "Ops", "basic": 50000, "perf_bonus": 5000, "commission": 0, "overtime": 1000, "statutory": 3000},
    {"staff_id": "E003", "name": "Carol", "role": "formal", "department": "Ops", "basic": 80000, "perf_bonus": 10000, "commission": 0, "overtime": 0, "statutory": 8000},
]

# Same three people, month 2: Alice's performance bonus moves (basic untouched),
# Bob (contract) gets a basic-salary raise, Carol (formal) also gets a basic-salary
# raise - in March, which is NOT one of the official Apr/Oct raise windows.
MONTH2_EMPLOYEES = [
    {"staff_id": "E001", "name": "Alice", "role": "formal", "department": "Ops", "basic": 100000, "perf_bonus": 25000, "commission": 0, "overtime": 0, "statutory": 10000},
    {"staff_id": "E002", "name": "Bob", "role": "contract", "department": "Ops", "basic": 55000, "perf_bonus": 5000, "commission": 0, "overtime": 1000, "statutory": 3000},
    {"staff_id": "E003", "name": "Carol", "role": "formal", "department": "Ops", "basic": 90000, "perf_bonus": 10000, "commission": 0, "overtime": 0, "statutory": 8000},
]

# Two department1s (Ops, Sales), Ops split into department2 sub-teams
# (Ops-A/Ops-B), plus one Ops employee with no department2 at all - for
# testing the department2 filter/drill-down.
DEPT2_EMPLOYEES = [
    {"staff_id": "E010", "name": "Dan", "role": "formal", "department": "Ops", "department2": "Ops-A", "basic": 100000, "perf_bonus": 0, "commission": 0, "overtime": 0, "statutory": 5000},
    {"staff_id": "E011", "name": "Eve", "role": "formal", "department": "Ops", "department2": "Ops-B", "basic": 60000, "perf_bonus": 0, "commission": 0, "overtime": 0, "statutory": 3000},
    {"staff_id": "E012", "name": "Fay", "role": "contract", "department": "Ops", "department2": "Ops-A", "basic": 40000, "perf_bonus": 0, "commission": 0, "overtime": 0, "statutory": 2000},
    {"staff_id": "E013", "name": "Gus", "role": "formal", "department": "Ops", "basic": 20000, "perf_bonus": 0, "commission": 0, "overtime": 0, "statutory": 1000},
    {"staff_id": "E014", "name": "Hana", "role": "formal", "department": "Sales", "department2": "Sales-A", "basic": 70000, "perf_bonus": 0, "commission": 0, "overtime": 0, "statutory": 4000},
]


def _confirm(db, month, employees):
    batch = stage_upload(db, month=month, file_bytes=build_component_workbook(month, employees), filename=f"{month}.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db, batch, operator="tester")
    return batch


def test_component_deltas_reconcile_exactly_to_stayers_delta(db_session):
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    _confirm(db_session, "2026-03", MONTH2_EMPLOYEES)

    r = compute_attribution(db_session, "2026-01", "2026-03")

    assert r.stayers_count == 3
    assert r.stayers_delta == 20000  # 5000 (Alice perf) + 5000 (Bob basic) + 10000 (Carol basic)
    assert r.component_deltas["basic_salary_actual"] == 15000  # Bob + Carol
    assert r.component_deltas["performance_bonus"] == 5000  # Alice
    assert r.component_deltas["commission_bonus"] == 0
    assert r.component_deltas["overtime_amount"] == 0
    assert r.component_deltas["employer_statutory_cost"] == 0
    assert r.component_deltas["other_residual"] == 0
    assert sum(r.component_deltas.values()) == r.stayers_delta
    assert r.reconciled is True


def test_behavior_labels_and_formal_contract_split_and_anomaly(db_session):
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    _confirm(db_session, "2026-03", MONTH2_EMPLOYEES)

    r = compute_attribution(db_session, "2026-01", "2026-03")
    labels = {b.label: b for b in r.behavior_labels}

    raise_label = labels["底薪调整"]
    assert raise_label.count_formal == 1  # Carol
    assert raise_label.count_contract == 1  # Bob
    assert raise_label.amount == 5000 + 10000  # Bob's and Carol's FULL hr_cost delta

    perf_label = labels["绩效薪资波动"]
    assert perf_label.count_formal == 1  # Alice
    assert perf_label.count_contract == 0
    assert perf_label.amount == 5000

    assert labels["奖金/提成变化"].count_formal == 0
    assert labels["奖金/提成变化"].count_contract == 0
    assert labels["加班费变化"].count_formal == 0

    # March is not an official raise month (only April/October are) - a
    # formal employee (Carol) getting a basic-salary bump here must surface
    # as an anomaly to investigate, not pass silently.
    assert len(r.anomalies) == 1
    assert "2026-03" in r.anomalies[0]
    assert "1" in r.anomalies[0]

    # anomaly_details is the structured counterpart the frontend renders
    # (translated to English there instead of hardcoding r.anomalies'
    # Chinese sentence) - both are built from the same underlying event, so
    # they must always come out in lockstep.
    assert len(r.anomaly_details) == 1
    assert r.anomaly_details[0].type == "formal_raise_outside_window"
    assert r.anomaly_details[0].month == "2026-03"
    assert r.anomaly_details[0].count == 1

    # BehaviorLabel.key is the stable identifier the frontend translates by
    # (BEHAVIOR_LABEL_EN) instead of string-matching l.label - verify every
    # label carries the right key alongside its Chinese label.
    keys = {b.label: b.key for b in r.behavior_labels}
    assert keys["底薪调整"] == "basic_salary_adjustment"
    assert keys["绩效薪资波动"] == "performance_bonus_fluctuation"
    assert keys["奖金/提成变化"] == "commission_bonus_change"
    assert keys["加班费变化"] == "overtime_change"


def test_no_anomaly_when_formal_raise_happens_in_official_window(db_session):
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    _confirm(db_session, "2026-04", MONTH2_EMPLOYEES)  # April - an official raise month

    r = compute_attribution(db_session, "2026-01", "2026-04")
    assert r.anomalies == []
    assert r.anomaly_details == []


def test_category_trend_and_composition_use_real_column_names(db_session):
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)

    trend = get_categories_trend(db_session, ["basic_salary_actual"], months=["2026-01"])
    assert trend[0]["categories"]["basic_salary_actual"] == 100000 + 50000 + 80000
    assert trend[0]["headcount"] == 3

    comparison = compare_departments_by_category(db_session, "overtime_amount", "2026-01")
    assert comparison[0]["department"] == "Ops"
    assert comparison[0]["total"] == 1000  # only Bob has overtime

    composition = get_cost_composition(db_session, "2026-01")
    total_hr_cost = 130000 + 59000 + 98000
    assert composition["hr_cost"] == total_hr_cost
    basic_pct = next(c for c in composition["categories"] if c["category"] == "basic_salary_actual")["pct"]
    assert abs(basic_pct - (230000 / total_hr_cost * 100)) < 0.01


def test_get_categories_trend_returns_multiple_categories_side_by_side(db_session):
    """PRD V1.7 §3.1: 薪资类目页面从单选改为多选 - one call must return every
    requested category's total for the same month/headcount, not force N
    separate round trips that could disagree on which months exist."""
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    _confirm(db_session, "2026-03", MONTH2_EMPLOYEES)

    trend = get_categories_trend(db_session, ["basic_salary_actual", "performance_bonus"], months=["2026-01", "2026-03"])
    assert [r["month"] for r in trend] == ["2026-01", "2026-03"]
    assert trend[0]["headcount"] == 3
    assert trend[0]["categories"] == {"basic_salary_actual": 230000, "performance_bonus": 35000}
    assert trend[1]["categories"] == {"basic_salary_actual": 245000, "performance_bonus": 40000}


def test_get_categories_trend_rejects_unknown_category(db_session):
    try:
        get_categories_trend(db_session, ["not_a_real_category"])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not_a_real_category" in str(e)


def test_get_categories_trend_rejects_unknown_category_in_per_capita_mode_too(db_session):
    try:
        get_categories_trend(db_session, ["not_a_real_category"], per_capita=True)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not_a_real_category" in str(e)


def test_get_categories_trend_per_capita_and_median(db_session):
    """PRD V1.9 §2: 人均 = 类目总额 / 当月在职总人数，且必须同时给出中位数
    （不能只算均值）——basic salaries are [100000, 50000, 80000], mean=230000/3,
    median=80000 (the middle value once sorted: 50000, 80000, 100000)."""
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)

    trend = get_categories_trend(db_session, ["basic_salary_actual"], months=["2026-01"], per_capita=True)
    row = trend[0]
    assert row["headcount"] == 3
    assert row["categories"]["basic_salary_actual"] == 230000
    assert abs(row["per_capita"]["basic_salary_actual"] - 230000 / 3) < 1e-6
    assert row["median"]["basic_salary_actual"] == 80000


def test_get_categories_trend_employment_type_filter_uses_its_own_denominator(db_session):
    """PRD V1.9 §2.1: 拆用工类型时，分母各自独立计算，不共用总分母- Formal
    headcount here is 2 (Alice+Carol), not the combined 3."""
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)

    formal = get_categories_trend(db_session, ["basic_salary_actual"], months=["2026-01"], employment_type="Formal")
    assert formal[0]["headcount"] == 2
    assert formal[0]["categories"]["basic_salary_actual"] == 100000 + 80000

    contract = get_categories_trend(db_session, ["basic_salary_actual"], months=["2026-01"], employment_type="Contract")
    assert contract[0]["headcount"] == 1
    assert contract[0]["categories"]["basic_salary_actual"] == 50000


def test_get_categories_trend_hr_cost_includes_supplemental_bonus_and_backpay(db_session):
    """Regression test found against a real user reconciliation done in
    Excel: the "人力成本合计" (hr_cost) category on the 薪资类目 page used to
    only sum the base batch's hr_cost, silently missing whatever a month's
    standalone bonus/backpay batch added on top - unlike get_trend()'s
    total_hr_cost (趋势查询 page), which already folds both in. Every other
    category here (底薪/绩效薪资/etc.) correctly stays base-only, since
    supplemental rows don't have a component breakdown - only hr_cost should
    pick up the extra amount, and headcount must stay unchanged (mirrors
    test_backpay_adds_on_top_of_base_without_touching_headcount in
    test_supplemental.py, using get_categories_trend instead of get_trend)."""
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    base_hr_cost = 130000 + 59000 + 98000  # Alice + Bob + Carol, from test_category_trend_and_composition_use_real_column_names

    backpay = build_supplemental_workbook([("E001", "Alice", "Sales", 500)])
    batch = stage_upload(db_session, month="2026-01", file_bytes=backpay, filename="bp.xlsx", uploaded_by="t", salary_type="backpay")
    confirm_upload(db_session, batch, operator="tester")

    trend = get_categories_trend(db_session, ["basic_salary_actual", "hr_cost"], months=["2026-01"])
    assert trend[0]["headcount"] == 3  # backpay doesn't create headcount
    assert trend[0]["categories"]["basic_salary_actual"] == 230000  # unaffected - no supplemental equivalent for this category
    assert trend[0]["categories"]["hr_cost"] == base_hr_cost + 500


def test_get_categories_trend_hr_cost_per_capita_includes_supplemental_but_median_stays_base_only(db_session):
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    base_hr_cost = 130000 + 59000 + 98000

    backpay = build_supplemental_workbook([("E001", "Alice", "Sales", 900)])
    batch = stage_upload(db_session, month="2026-01", file_bytes=backpay, filename="bp.xlsx", uploaded_by="t", salary_type="backpay")
    confirm_upload(db_session, batch, operator="tester")

    trend = get_categories_trend(db_session, ["hr_cost"], months=["2026-01"], per_capita=True)
    row = trend[0]
    assert row["headcount"] == 3
    assert row["categories"]["hr_cost"] == base_hr_cost + 900
    assert abs(row["per_capita"]["hr_cost"] - (base_hr_cost + 900) / 3) < 1e-6
    # median is a per-employee figure - backpay only applies to whichever
    # staff_ids the batch lists, so it deliberately stays base-batch-only
    # (documented limitation, see _get_categories_trend_per_capita's docstring)
    assert row["median"]["hr_cost"] == sorted([130000, 59000, 98000])[1]


def test_get_categories_trend_employment_type_filter_combines_with_per_capita(db_session):
    """Formal-only per-capita: basic salaries [100000, 80000], mean=90000,
    median=90000 (mean of two middle values happens to equal 90000 here too,
    but computed independently to make sure both are actually right)."""
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)

    formal = get_categories_trend(db_session, ["basic_salary_actual"], months=["2026-01"], employment_type="Formal", per_capita=True)
    row = formal[0]
    assert row["headcount"] == 2
    assert row["per_capita"]["basic_salary_actual"] == 90000
    assert row["median"]["basic_salary_actual"] == 90000


def test_get_trend_employment_type_filter(db_session):
    """趋势查询页面新增的用工类型筛选 - 复用同一个 get_trend()，不是新接口。
    Formal: Alice (hr_cost 130000) + Carol (hr_cost 98000). Contract: Bob only."""
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)

    formal = get_trend(db_session, months=["2026-01"], employment_type="Formal")
    assert formal[0]["headcount"] == 2
    assert formal[0]["total_hr_cost"] == 130000 + 98000

    contract = get_trend(db_session, months=["2026-01"], employment_type="Contract")
    assert contract[0]["headcount"] == 1
    assert contract[0]["total_hr_cost"] == 59000

    combined = get_trend(db_session, months=["2026-01"])
    assert combined[0]["headcount"] == 3
    assert combined[0]["total_hr_cost"] == 130000 + 98000 + 59000


def test_compute_attribution_employment_type_filter(db_session):
    """两点比较模式的用工类型筛选 - same compute_attribution(), called with a
    different employment_type instead of a parallel implementation."""
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    _confirm(db_session, "2026-03", MONTH2_EMPLOYEES)

    formal = compute_attribution(db_session, "2026-01", "2026-03", employment_type="Formal")
    assert formal.stayers_count == 2  # Alice + Carol only, Bob excluded
    assert formal.stayers_delta == 15000  # Alice's +5000 perf bonus + Carol's +10000 basic

    contract = compute_attribution(db_session, "2026-01", "2026-03", employment_type="Contract")
    assert contract.stayers_count == 1  # Bob only
    assert contract.stayers_delta == 5000  # Bob's basic salary raise


def test_get_trend_department2_filter(db_session):
    _confirm(db_session, "2026-01", DEPT2_EMPLOYEES)

    ops_a = get_trend(db_session, months=["2026-01"], department="Ops", department2="Ops-A")
    assert ops_a[0]["headcount"] == 2  # Dan + Fay
    assert ops_a[0]["total_hr_cost"] == 105000 + 42000

    ops_b = get_trend(db_session, months=["2026-01"], department="Ops", department2="Ops-B")
    assert ops_b[0]["headcount"] == 1  # Eve only
    assert ops_b[0]["total_hr_cost"] == 63000

    # Unselected department2 still shows every Ops employee, blank-department2 included.
    ops_all = get_trend(db_session, months=["2026-01"], department="Ops")
    assert ops_all[0]["headcount"] == 4  # Dan, Eve, Fay, Gus


def test_get_categories_trend_department2_filter(db_session):
    _confirm(db_session, "2026-01", DEPT2_EMPLOYEES)

    rows = get_categories_trend(db_session, ["basic_salary_actual"], months=["2026-01"], department="Ops", department2="Ops-A")
    assert rows[0]["headcount"] == 2
    assert rows[0]["categories"]["basic_salary_actual"] == 100000 + 40000


def test_compare_departments_by_category_drilldown_to_department2(db_session):
    """PRD: 部门间横向对比 needs a department1 selected before it drills down
    to comparing the department2s within it - passing `department` switches
    compare_departments_by_category from comparing department1s to comparing
    department2s scoped to that one department1."""
    _confirm(db_session, "2026-01", DEPT2_EMPLOYEES)

    # No drilldown: compares department1s (Ops vs Sales).
    top_level = compare_departments_by_category(db_session, category="hr_cost", month="2026-01")
    by_dept = {r["department"]: r for r in top_level}
    assert by_dept["Ops"]["total"] == 105000 + 63000 + 42000 + 21000
    assert by_dept["Ops"]["headcount"] == 4
    assert by_dept["Sales"]["total"] == 74000

    # Drilldown into Ops: compares Ops-A vs Ops-B vs the unlabeled bucket.
    drilled = compare_departments_by_category(db_session, category="hr_cost", month="2026-01", department="Ops")
    by_dept2 = {r["department"]: r for r in drilled}
    assert set(by_dept2) == {"Ops-A", "Ops-B", "(未标注二级部门)"}
    assert by_dept2["Ops-A"]["total"] == 105000 + 42000  # Dan + Fay
    assert by_dept2["Ops-A"]["headcount"] == 2
    assert by_dept2["Ops-B"]["total"] == 63000  # Eve
    assert by_dept2["(未标注二级部门)"]["total"] == 21000  # Gus, no department2

    # Sales isn't touched by the Ops drilldown - only its own department2 would show up.
    assert "Sales-A" not in by_dept2

    # pct_of_hr_cost is "this group's own total for the selected category as
    # % of this SAME group's own hr_cost" (unchanged meaning from the non-
    # drilldown mode, just re-scoped to department2 groups) - verified with
    # a component category instead of "hr_cost" itself, since comparing
    # hr_cost against hr_cost is trivially 100% in either mode.
    drilled_basic = compare_departments_by_category(db_session, category="basic_salary_actual", month="2026-01", department="Ops")
    ops_a_basic = next(r for r in drilled_basic if r["department"] == "Ops-A")
    assert ops_a_basic["total"] == 100000 + 40000  # Dan + Fay
    assert abs(ops_a_basic["pct_of_hr_cost"] - (140000 / 147000 * 100)) < 1e-6


def test_get_cost_composition_department2_filter(db_session):
    _confirm(db_session, "2026-01", DEPT2_EMPLOYEES)

    comp = get_cost_composition(db_session, month="2026-01", department="Ops", department2="Ops-A")
    assert comp["hr_cost"] == 105000 + 42000
    basic = next(c for c in comp["categories"] if c["category"] == "basic_salary_actual")
    assert basic["total"] == 100000 + 40000
