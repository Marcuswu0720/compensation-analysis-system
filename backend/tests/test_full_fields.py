"""PRD V1.6: coverage for the pieces V1.5's test suite had no equivalent of
at all - the full field templates (ingestion/full_fields.py), the rewritten
standalone 奖金批次 parser (ingestion/bonus_batch.py), and the loader/commit
wiring that carries the new descriptive columns + full_detail_json through
to the confirmed snapshot tables.
"""

import io
import json

import openpyxl

from app.ingestion.bonus_batch import parse_bonus_batch_workbook
from app.ingestion.commit import confirm_upload
from app.ingestion.full_fields import (
    ANALYSIS_KEYS,
    BONUS_EXCLUDE_KEYS,
    BONUS_FIELDS,
    BONUS_TOP_LEVEL_KEYS,
    NEW_DESCRIPTIVE_KEYS,
    TOP_LEVEL_DESCRIPTIVE_KEYS,
    FieldSpec,
    export_header,
    extract_full_detail,
)
from app.ingestion.loader import stage_upload
from app.models import MonthlyEmployeeSnapshot, SupplementalPaySnapshot

from .xlsx_fixtures import _sheet, build_month1_workbook


def test_export_header_formats_english_and_chinese():
    spec = FieldSpec("staff_id", "Staff ID", "员工工号", ("Staff ID",), True)
    assert export_header(spec) == "Staff ID（员工工号）"


def test_extract_full_detail_skips_excluded_keys_entirely():
    """Regression test for the bug fixed mid-implementation: excluded keys
    must not be checked for presence at all, even if their alias list
    happens not to match this row - they're handled by a separate,
    already-working mechanism (extract_salary_components / loader.py)."""
    specs = [
        FieldSpec("basic_salary_actual", "Actual Monthly Basic", "当月应发底薪", ("Actual Monthly Basic Salary",), True),
        FieldSpec("call_allowance", "Call Allowance", "话补", ("Call Allowance",), True),
    ]
    row = {"Call Allowance": 200}  # no "Actual Monthly Basic Salary" column at all
    top_level, detail_json, missing = extract_full_detail(
        row, specs, top_level_keys=set(), exclude_keys={"basic_salary_actual"}
    )
    assert missing == []  # excluded key is never reported as missing
    assert detail_json == {"call_allowance": 200}
    assert top_level == {}


def test_extract_full_detail_splits_top_level_vs_detail_json():
    specs = [
        FieldSpec("position", "Position", "职位", ("Position",), False),
        FieldSpec("performance_std", "Performance STD", "绩效标准薪酬", ("Performance STD",), True),
        FieldSpec("state", "State", "所在州", ("State",), False),
    ]
    row = {"Position": "Engineer", "Performance STD": 5000}  # "State" column missing
    top_level, detail_json, missing = extract_full_detail(
        row, specs, top_level_keys={"position", "state"}, exclude_keys=set()
    )
    assert top_level == {"position": "Engineer", "state": None}
    assert detail_json == {"performance_std": 5000}
    assert missing == ["state"]


def test_stage_base_reports_missing_full_detail_fields_for_minimal_sheet(db_session):
    """build_month1_workbook's Formal sheet only has 7 columns - almost none
    of FORMAL_FIELDS' 37 aliases match, so this must surface as a loud
    validation issue (not a silently-incomplete export) exactly like PRD
    V1.6's background section describes V1.5's failure."""
    batch = stage_upload(db_session, month="2026-01", file_bytes=build_month1_workbook(), filename="x.xlsx", uploaded_by="t")
    payload = json.loads(batch.staged_data)

    alice = next(e for e in payload["employees"] if e["staff_id"] == "E001")
    assert "department2" in alice and alice["department2"] is None
    detail = json.loads(alice["full_detail_json"])
    assert "call_allowance" in detail and detail["call_allowance"] is None

    issue = next(i for i in payload["issues"] if i["issue_type"] == "full_detail_field_not_found" and "正式工" in i["issue_detail"])
    assert "call_allowance" in issue["issue_detail"]


def test_stage_base_captures_full_fields_when_present(db_session):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(
        wb,
        "Formal",
        ["Staff ID", "Staff Name", "Entity", "Department 1", "Department 2", "Position", "Job Grade", "HR Cost", "Resign Date", "Call Allowance"],
        [["E001", "Alice", "PalmPay", "Sales", "Sub-Sales", "Engineer", "P1", 1000, None, 250]],
    )
    buf = io.BytesIO()
    wb.save(buf)

    batch = stage_upload(db_session, month="2026-01", file_bytes=buf.getvalue(), filename="x.xlsx", uploaded_by="t")
    payload = json.loads(batch.staged_data)
    alice = next(e for e in payload["employees"] if e["staff_id"] == "E001")
    assert alice["department2"] == "Sub-Sales"
    assert alice["position"] == "Engineer"
    detail = json.loads(alice["full_detail_json"])
    assert detail["call_allowance"] == 250

    issue = next((i for i in payload["issues"] if i["issue_type"] == "full_detail_field_not_found" and "正式工" in i["issue_detail"]), None)
    assert issue is None or "call_allowance" not in issue["issue_detail"]


BONUS_HEADERS = [
    "Staff ID", "Staff Name", "Department 1", "Department 2", "Department 3", "Position", "Reporting Line",
    "Job Grade", "State", "Work Station", "Joining Date", "Resign Date", "Cost Center", "Work Country",
    "Performance Standard", "KPI Score", "Performance Bonus", "Commission", "Other", "Deduction",
    "Gross Total Amount", "PAYE", "ITF (ER)", "Bank Charges", "HR Cost", "Net Amount",
]


def _bonus_row(staff_id="E001", staff_name="Alice", hr_cost=500, **overrides):
    row = {h: None for h in BONUS_HEADERS}
    row.update(
        {
            "Staff ID": staff_id,
            "Staff Name": staff_name,
            "Department 1": "Sales",
            "Department 2": "Sub-Sales",
            "Cost Center": "CC-001",
            "KPI Score": 92,
            "PAYE": 40,
            "HR Cost": hr_cost,
        }
    )
    row.update(overrides)
    return [row[h] for h in BONUS_HEADERS]


def build_full_bonus_workbook(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Bonus", BONUS_HEADERS, rows)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_bonus_batch_parser_finds_no_missing_fields_when_headers_match_prd_list():
    wb_bytes = build_full_bonus_workbook([_bonus_row()])
    result = parse_bonus_batch_workbook(io.BytesIO(wb_bytes))
    assert result.missing_fields == set()
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["staff_id"] == "E001"
    assert row["amount"] == 500
    assert row["department2"] == "Sub-Sales"
    assert row["cost_center"] == "CC-001"
    assert row["full_detail_json_fields"]["kpi_score"] == 92
    assert row["full_detail_json_fields"]["paye"] == 40


def test_bonus_batch_parser_reports_missing_fields_and_skips_sheet_without_staff_id():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    # No PAYE/ITF/Bank Charges columns at all this month.
    headers = [h for h in BONUS_HEADERS if h not in ("PAYE", "ITF (ER)", "Bank Charges")]
    data_row = [None] * len(headers)
    data_row[headers.index("Staff ID")] = "E001"
    _sheet(wb, "Bonus", headers, [data_row])
    _sheet(wb, "Weird", ["Not Staff ID"], [["x"]])
    buf = io.BytesIO()
    wb.save(buf)

    result = parse_bonus_batch_workbook(io.BytesIO(buf.getvalue()))
    assert "paye" in result.missing_fields
    assert "itf_er" in result.missing_fields
    assert "bank_charges" in result.missing_fields
    assert any("Weird" in s for s in result.skipped_sheets)
    assert [r["staff_id"] for r in result.rows] == ["E001"]


def test_bonus_batch_parser_skips_summary_rows():
    wb_bytes = build_full_bonus_workbook(
        [_bonus_row(staff_id="E001"), _bonus_row(staff_id="TOTAL", staff_name="TOTAL", hr_cost=999)]
    )
    result = parse_bonus_batch_workbook(io.BytesIO(wb_bytes))
    assert [r["staff_id"] for r in result.rows] == ["E001"]


def test_confirmed_bonus_batch_writes_full_detail_and_resolves_entity_from_base(db_session):
    """End-to-end: stage+confirm a base batch first (so E001 has an entity),
    then stage+confirm a standalone bonus batch - PRD V1.6 confirmed this
    file has no Entity column of its own, so entity must be resolved via the
    matched base-batch employee, exactly like backpay's existing behavior."""
    base_batch = stage_upload(db_session, month="2026-01", file_bytes=build_month1_workbook(), filename="base.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db_session, base_batch, operator="tester")

    bonus_bytes = build_full_bonus_workbook([_bonus_row(staff_id="E001", hr_cost=500), _bonus_row(staff_id="GHOST", staff_name="Nobody", hr_cost=200)])
    bonus_batch = stage_upload(db_session, month="2026-01", file_bytes=bonus_bytes, filename="bonus.xlsx", uploaded_by="t", salary_type="bonus")
    payload = json.loads(bonus_batch.staged_data)
    assert payload["summary"]["salary_type"] == "bonus"
    assert payload["summary"]["unmatched_count"] == 1
    issue_types = [i["issue_type"] for i in payload["issues"]]
    assert "unmatched_supplemental_staff" in issue_types

    confirm_upload(db_session, bonus_batch, operator="tester")

    rows = db_session.query(SupplementalPaySnapshot).filter(SupplementalPaySnapshot.pay_type == "bonus").all()
    alice = next(r for r in rows if r.staff_id == "E001")
    assert alice.entity == "PalmPay"  # resolved from the matched base employee
    assert alice.department2 == "Sub-Sales"
    assert alice.cost_center == "CC-001"
    detail = json.loads(alice.full_detail_json)
    assert detail["kpi_score"] == 92

    ghost = next(r for r in rows if r.staff_id == "GHOST")
    assert ghost.entity is None  # no base match, no entity column in the file - can't resolve


def test_full_field_key_sets_do_not_overlap():
    """ANALYSIS_KEYS/TOP_LEVEL_DESCRIPTIVE_KEYS/NEW_DESCRIPTIVE_KEYS partition
    FORMAL/CONTRACT fields between "already handled elsewhere" (excluded),
    real top-level columns, and full_detail_json - an overlap would mean a
    field is silently double-counted or dropped."""
    assert ANALYSIS_KEYS.isdisjoint(NEW_DESCRIPTIVE_KEYS)
    assert TOP_LEVEL_DESCRIPTIVE_KEYS.isdisjoint(NEW_DESCRIPTIVE_KEYS)
    assert BONUS_EXCLUDE_KEYS.isdisjoint(BONUS_TOP_LEVEL_KEYS)
    bonus_keys = {s.key for s in BONUS_FIELDS}
    assert BONUS_EXCLUDE_KEYS <= bonus_keys
    assert BONUS_TOP_LEVEL_KEYS <= bonus_keys
