from app.compute.attribution import compute_attribution
from app.compute.categories import compare_departments_by_category, get_category_trend, get_cost_composition
from app.ingestion.commit import confirm_upload
from app.ingestion.loader import stage_upload

from .xlsx_fixtures import build_component_workbook

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


def test_no_anomaly_when_formal_raise_happens_in_official_window(db_session):
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)
    _confirm(db_session, "2026-04", MONTH2_EMPLOYEES)  # April - an official raise month

    r = compute_attribution(db_session, "2026-01", "2026-04")
    assert r.anomalies == []


def test_category_trend_and_composition_use_real_column_names(db_session):
    _confirm(db_session, "2026-01", MONTH1_EMPLOYEES)

    trend = get_category_trend(db_session, "basic_salary_actual", months=["2026-01"])
    assert trend[0]["total"] == 100000 + 50000 + 80000
    assert trend[0]["headcount"] == 3

    comparison = compare_departments_by_category(db_session, "overtime_amount", "2026-01")
    assert comparison[0]["department"] == "Ops"
    assert comparison[0]["total"] == 1000  # only Bob has overtime

    composition = get_cost_composition(db_session, "2026-01")
    total_hr_cost = 130000 + 59000 + 98000
    assert composition["hr_cost"] == total_hr_cost
    basic_pct = next(c for c in composition["categories"] if c["category"] == "basic_salary_actual")["pct"]
    assert abs(basic_pct - (230000 / total_hr_cost * 100)) < 0.01
