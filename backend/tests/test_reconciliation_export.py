from fastapi import HTTPException
from starlette.responses import StreamingResponse

from app.compute.export import build_department_category_summary
from app.ingestion.loader import stage_upload
from app.models import User
from app.routers.upload import _build_reconciliation_workbook, reconciliation_export

from .xlsx_fixtures import build_component_workbook, build_month1_workbook, build_supplemental_workbook

# build_month1_workbook: Alice/Bob/Carol/Dave = PalmPay+Sales except Carol who
# is PalmPay+Ops, Eve = Flexi+Ops. See test_permissions.py for the same map.


def _make_admin(db):
    u = User(username="marcus", password_hash="x", role="admin")
    db.add(u)
    db.commit()
    return u


def test_build_department_category_summary_groups_and_sums_by_entity_department():
    employees = [
        {"entity": "PalmPay", "department1": "Ops", "basic_salary_actual": 100000, "performance_bonus": 20000, "commission_bonus": 0, "overtime_amount": 0, "other_income": 0, "gross_salary": 120000, "employer_statutory_cost": 10000, "hr_cost": 130000},
        {"entity": "PalmPay", "department1": "Ops", "basic_salary_actual": 50000, "performance_bonus": 5000, "commission_bonus": 0, "overtime_amount": 1000, "other_income": 0, "gross_salary": 56000, "employer_statutory_cost": 3000, "hr_cost": 59000},
        {"entity": "Flexi", "department1": "Sales", "basic_salary_actual": 30000, "performance_bonus": 0, "commission_bonus": 2000, "overtime_amount": 0, "other_income": 0, "gross_salary": 32000, "employer_statutory_cost": 1000, "hr_cost": 33000},
    ]

    rows = build_department_category_summary(employees)
    assert len(rows) == 2

    palmpay_ops = next(r for r in rows if r["entity"] == "PalmPay" and r["department1"] == "Ops")
    assert palmpay_ops["headcount"] == 2
    assert palmpay_ops["basic_salary_actual"] == 150000
    assert palmpay_ops["performance_bonus"] == 25000
    assert palmpay_ops["overtime_amount"] == 1000
    assert palmpay_ops["hr_cost"] == 189000

    flexi_sales = next(r for r in rows if r["entity"] == "Flexi")
    assert flexi_sales["headcount"] == 1
    assert flexi_sales["commission_bonus"] == 2000
    assert flexi_sales["hr_cost"] == 33000


def test_build_department_category_summary_handles_missing_fields_as_zero():
    # A row missing some component keys entirely (e.g. an older staged
    # payload) must not crash the aggregation - treat as 0, not error.
    employees = [{"entity": "PalmPay", "department1": "Sales", "hr_cost": 1000}]
    rows = build_department_category_summary(employees)
    assert rows[0]["basic_salary_actual"] == 0
    assert rows[0]["hr_cost"] == 1000


def test_reconciliation_export_works_on_pending_review_batch(db_session):
    admin = _make_admin(db_session)
    batch = stage_upload(db_session, month="2026-01", file_bytes=build_month1_workbook(), filename="m1.xlsx", uploaded_by="t", salary_type="base")
    assert batch.status == "pending_review"  # not confirmed yet - export must still work

    response = reconciliation_export(batch.id, db_session, admin)
    assert isinstance(response, StreamingResponse)
    assert "分部门核对" in response.headers["content-disposition"] or "filename*=UTF-8''" in response.headers["content-disposition"]


def test_reconciliation_export_totals_match_batch_summary(db_session):
    import io
    import json

    import openpyxl

    employees_input = [
        {"staff_id": "E001", "name": "Alice", "role": "formal", "department": "Ops", "basic": 100000, "perf_bonus": 20000, "commission": 0, "overtime": 0, "statutory": 10000},
        {"staff_id": "E002", "name": "Bob", "role": "contract", "department": "Ops", "basic": 50000, "perf_bonus": 5000, "commission": 0, "overtime": 1000, "statutory": 3000},
    ]
    batch = stage_upload(
        db_session, month="2026-02", file_bytes=build_component_workbook("2026-02", employees_input), filename="m2.xlsx", uploaded_by="t", salary_type="base"
    )
    payload = json.loads(batch.staged_data)
    batch_total_hr_cost = payload["summary"]["total_hr_cost"]

    rows = build_department_category_summary(payload["employees"])
    workbook_bytes = _build_reconciliation_workbook(rows, batch.month)
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    ws = wb.active
    out_rows = list(ws.iter_rows(values_only=True))
    total_row = out_rows[-1]
    assert total_row[0] == "合计"
    assert total_row[-1] == batch_total_hr_cost == 189000


def test_reconciliation_export_rejects_non_base_batch(db_session):
    admin = _make_admin(db_session)
    batch = stage_upload(
        db_session,
        month="2026-01",
        file_bytes=build_supplemental_workbook([("E001", "Alice", "Sales", 500)]),
        filename="bp.xlsx",
        uploaded_by="t",
        salary_type="backpay",
    )

    try:
        reconciliation_export(batch.id, db_session, admin)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400
        assert "底薪批次" in e.detail
