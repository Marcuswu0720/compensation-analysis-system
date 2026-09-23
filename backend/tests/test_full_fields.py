"""Coverage for the pieces the plain ingestion-flow tests don't exercise:
the full field templates (ingestion/full_fields.py), PRD V1.8's normalized
header matching (ingestion/header_match.py), the field-mapping diagnostic,
the standalone 奖金批次 parser (ingestion/bonus_batch.py), and the
loader/commit wiring that carries the new descriptive columns +
full_detail_json through to the confirmed snapshot tables.
"""

import datetime
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
    CONTRACT_FIELDS,
    FORMAL_FIELDS,
    NEW_DESCRIPTIVE_KEYS,
    TOP_LEVEL_DESCRIPTIVE_KEYS,
    FieldSpec,
    check_field_mapping,
    export_header,
    extract_full_detail,
)
from app.ingestion.header_match import build_header_index, find_alias, normalize_header
from app.ingestion.loader import stage_upload
from app.models import SupplementalPaySnapshot

from .xlsx_fixtures import _sheet, build_month1_workbook

# ---------- header_match.py: PRD V1.8 §1's normalization layer ----------


def test_normalize_header_strips_collapses_and_lowercases():
    assert normalize_header("Staff Name") == "staff name"
    assert normalize_header("Staff name") == "staff name"
    assert normalize_header("  Staff   Name  ") == "staff name"
    assert normalize_header("Joining Date \n(other)") == "joining date (other)"
    assert normalize_header(None) == ""


def test_find_alias_matches_case_and_whitespace_variants():
    index = build_header_index(["Staff name", "  Joining Date  ", "Exit Date "])
    assert find_alias(index, ("Staff Name",)) == "Staff name"
    assert find_alias(index, ("Joining Date",)) == "  Joining Date  "
    assert find_alias(index, ("Exit Date",)) == "Exit Date "
    assert find_alias(index, ("Nonexistent",)) is None


def test_find_alias_still_needs_a_real_synonym_for_different_wording():
    index = build_header_index(["Leaving date"])
    assert find_alias(index, ("Resign Date",)) is None  # genuinely different word, not a case/space issue
    assert find_alias(index, ("Resign Date", "Leaving date")) == "Leaving date"


# ---------- extract_full_detail / check_field_mapping ----------


def test_export_header_formats_english_and_chinese():
    spec = FieldSpec("staff_id", "Staff ID", "员工工号", ("Staff ID",), True)
    assert export_header(spec) == "Staff ID（员工工号）"


def test_extract_full_detail_skips_excluded_keys_entirely():
    """Regression test: excluded keys must not be checked for presence at
    all, even if their alias list happens not to match this row - they're
    handled by a separate, already-working mechanism (extract_salary_components
    / loader.py)."""
    specs = [
        FieldSpec("basic_salary_actual", "Actual Monthly Basic", "当月应发底薪", ("Actual Monthly Basic Salary",), True),
        FieldSpec("call_allowance", "Call Allowance", "话补", ("Call Allowance",), True),
    ]
    row = {"Call Allowance": 200}  # no "Actual Monthly Basic Salary" column at all
    top_level, detail_json, missing = extract_full_detail(row, specs, top_level_keys=set(), exclude_keys={"basic_salary_actual"})
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
    top_level, detail_json, missing = extract_full_detail(row, specs, top_level_keys={"position", "state"}, exclude_keys=set())
    assert top_level == {"position": "Engineer", "state": None}
    assert detail_json == {"performance_std": 5000}
    assert missing == ["state"]


def test_extract_full_detail_matches_case_and_whitespace_variants():
    """PRD V1.8 §1: this used to require an exact string match - a header
    spelled "position" (lowercase) or with a trailing space would silently
    come up empty."""
    specs = [FieldSpec("position", "Position", "职位", ("Position",), True)]
    row = {"position ": "Engineer"}
    top_level, _, missing = extract_full_detail(row, specs, top_level_keys={"position"}, exclude_keys=set())
    assert missing == []
    assert top_level["position"] == "Engineer"


def test_extract_full_detail_converts_datetime_cells_to_date_only_strings():
    """Regression test: openpyxl hands back real datetime.datetime objects
    for date-formatted cells (Joining Date, Resign Date, etc.), not strings
    like the synthetic test fixtures use. PRD V1.8 §3: the stored value must
    be a plain YYYY-MM-DD string, not "...T00:00:00" - both because that's
    what the PRD asks for, and because the earlier isoformat()-based fix
    still leaked the always-00:00:00 time part through to every export."""
    specs = [FieldSpec("joining_date", "Joining Date", "入职日期", ("Joining Date",), True)]
    row = {"Joining Date": datetime.datetime(2020, 1, 15)}
    top_level, _, missing = extract_full_detail(row, specs, top_level_keys={"joining_date"}, exclude_keys=set())
    assert missing == []
    assert top_level["joining_date"] == "2020-01-15"
    json.dumps(top_level)  # must not raise


def test_check_field_mapping_reports_total_matched_and_missing_details():
    specs = [
        FieldSpec("staff_id", "Staff ID", "工号", ("Staff ID",), True),
        FieldSpec("resign_date", "Resign Date", "离职时间", ("Resign Date", "Leaving date"), True),
    ]
    index = build_header_index(["staff id", "Joining Date"])  # staff_id matches (case-insensitive), resign_date doesn't
    total, matched, missing = check_field_mapping(index, specs)
    assert total == 2
    assert matched == 1
    assert missing == [{"key": "resign_date", "target_label": "Resign Date", "tried_aliases": ["Resign Date", "Leaving date"]}]


def test_check_field_mapping_ignores_exclude_keys_unlike_extract_full_detail():
    """The diagnostic checks EVERY target field regardless of whether some
    other mechanism (analysis layer, loader.py's direct lookups) actually
    supplies its value - that's the whole point of decoupling it from
    extract_full_detail's routing."""
    specs = [FieldSpec("entity", "Entity", "公司实体", ("Entity",), True)]
    index = build_header_index(["Entity"])
    total, matched, missing = check_field_mapping(index, specs)
    assert (total, matched, missing) == (1, 1, [])


def test_contract_fields_matches_flexi_alternate_headers():
    """Regression test found against a real January file: Contract-Flexi
    uses different header wording than Contract-PP for several columns
    (Position vs Job Title, Chinese Reporting line vs Reporting Line, Work
    Location vs Work Station, Should Working Days vs Working Days, and a
    longer Airtime/Data Allowance name) - relying on a single alias per
    field left every one of these blank for Flexi rows even though the
    column genuinely existed."""
    flexi_headers = [
        "Staff ID", "Entity", "Employment Type", "Name", "Department 1", "Department 2", "Department 3",
        "Position", "Chinese Reporting line", "Job Grade", "State", "Work Location", "Joining Date", "Exit Date",
        "Should Working Days", "Basic Salary", "Airtime / Data Allowance / POS Storage Subcidy",
        "Transport Allowance", "Performance Standard", "Attendance Days", "Attendance rate", "KPI Coeff.",
        "Perfomance bonus", "Hourly Late", "Lateness deduction", "Commission/Bonus", "Overtime Hour",
        "Overtime income", "Arrears/Other Income", "Actual Gross Total Amount", "ER COST", "Net Amount Due", "HR Cost",
    ]
    index = build_header_index(flexi_headers)
    total, matched, missing = check_field_mapping(index, CONTRACT_FIELDS)
    # basic_salary_actual is missing here simply because this fixture's
    # header list doesn't include "Actual Monthly Basic Salary" - not a
    # mismatch, see test_contract_basic_salary_diagnostic_matches_real_column
    # below for the case where that column is present.
    missing_keys = {m["key"] for m in missing}
    assert missing_keys == {"basic_salary_actual"}
    assert matched == total - 1

    row = {h: f"value-of-{h}" for h in flexi_headers}
    top_level, detail_json, _ = extract_full_detail(
        row, CONTRACT_FIELDS, top_level_keys=NEW_DESCRIPTIVE_KEYS, exclude_keys=ANALYSIS_KEYS | TOP_LEVEL_DESCRIPTIVE_KEYS, header_index=index
    )
    assert top_level["position"] == "value-of-Position"
    assert top_level["reporting_line"] == "value-of-Chinese Reporting line"
    assert top_level["work_station"] == "value-of-Work Location"
    assert detail_json["should_work_days"] == "value-of-Should Working Days"
    assert detail_json["airtime_data_allowance"] == "value-of-Airtime / Data Allowance / POS Storage Subcidy"


def test_contract_basic_salary_diagnostic_matches_real_column():
    """Regression test found against a real production upload: the
    field-mapping diagnostic reported "Basic Salary" as missing on every
    Contract-PP/Contract-Flexi upload even though the exported value was
    always correct - the diagnostic's alias ("Monthly Basic Salary") didn't
    match any real column, while the actual analysis-layer number (see
    salary_components.py) is read from "Actual Monthly Basic Salary", which
    the real file does have. Checking for the same column the analysis layer
    actually reads makes the diagnostic agree with reality instead of
    falsely reporting the field as missing on every single upload."""
    index = build_header_index(["Staff ID", "Actual Monthly Basic Salary"])
    spec = next(s for s in CONTRACT_FIELDS if s.key == "basic_salary_actual")
    assert find_alias(index, spec.source_aliases) == "Actual Monthly Basic Salary"

    total, matched, missing = check_field_mapping(index, CONTRACT_FIELDS)
    assert "basic_salary_actual" not in {m["key"] for m in missing}


def test_formal_and_contract_deduction_fields_match_spelled_out_headers():
    """Regression test found against a real production export: Late
    Deduction/Porated Days Deduction/Absent Deduction (Formal) and Late
    Deduction (Contract) came back blank for every row - the coded aliases
    ("Late Ded.", "Porated Days Ded.", "Absent Ded.", "Lateness deduction")
    don't match the real files, which spell every attendance/deduction
    column out in full like their neighbors (Hourly Late, Porated Days,
    Absent Days)."""
    formal_index = build_header_index(["Late Deduction", "Porated Days Deduction", "Absent Deduction"])
    assert find_alias(formal_index, next(s for s in FORMAL_FIELDS if s.key == "late_deduction").source_aliases) == "Late Deduction"
    assert (
        find_alias(formal_index, next(s for s in FORMAL_FIELDS if s.key == "porated_days_deduction").source_aliases)
        == "Porated Days Deduction"
    )
    assert (
        find_alias(formal_index, next(s for s in FORMAL_FIELDS if s.key == "absent_deduction").source_aliases) == "Absent Deduction"
    )

    contract_index = build_header_index(["Late Deduction"])
    assert find_alias(contract_index, next(s for s in CONTRACT_FIELDS if s.key == "late_deduction").source_aliases) == "Late Deduction"


def test_bonus_fields_matches_real_alternate_headers():
    """Regression test found against a real January bonus file: its actual
    headers are Staff Type / Position / Line Manager, not the mapping
    file's Employment Type / Job Title / Reporting Line - the mapping
    file's wording is kept as the primary alias (it's still correct for
    other months/entities), these are added as a second, genuinely
    different-wording alias per PRD V1.8 §1's rule."""
    index = build_header_index(["Staff Type", "Position", "Line Manager"])
    assert find_alias(index, next(s for s in BONUS_FIELDS if s.key == "employment_type").source_aliases) == "Staff Type"
    assert find_alias(index, next(s for s in BONUS_FIELDS if s.key == "position").source_aliases) == "Position"
    assert find_alias(index, next(s for s in BONUS_FIELDS if s.key == "reporting_line").source_aliases) == "Line Manager"


# ---------- loader.py: base batch field-mapping diagnostic + date fix ----------


def test_stage_base_handles_real_datetime_cells_without_crashing(db_session):
    """End-to-end version of the datetime regression above, through the
    actual upload path a real Excel file with a date-formatted Joining Date
    column goes through."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(
        wb,
        "Formal",
        ["Staff ID", "Staff Name", "Entity", "Department 1", "Job Grade", "HR Cost", "Resign Date", "Joining Date"],
        [["E001", "Alice", "PalmPay", "Sales", "P1", 1000, None, datetime.datetime(2020, 1, 15)]],
    )
    buf = io.BytesIO()
    wb.save(buf)

    batch = stage_upload(db_session, month="2026-01", file_bytes=buf.getvalue(), filename="x.xlsx", uploaded_by="t", salary_type="base")
    payload = json.loads(batch.staged_data)
    alice = next(e for e in payload["employees"] if e["staff_id"] == "E001")
    assert alice["joining_date"] == "2020-01-15"


def test_stage_base_reports_field_mapping_check_for_minimal_sheet(db_session):
    """build_month1_workbook's Formal sheet only has 7 columns - almost none
    of FORMAL_FIELDS' 40 aliases match, so this must surface as a loud
    validation issue (not a silently-incomplete export)."""
    batch = stage_upload(db_session, month="2026-01", file_bytes=build_month1_workbook(), filename="x.xlsx", uploaded_by="t")
    payload = json.loads(batch.staged_data)

    alice = next(e for e in payload["employees"] if e["staff_id"] == "E001")
    assert "department2" in alice and alice["department2"] is None
    detail = json.loads(alice["full_detail_json"])
    assert "call_allowance" in detail and detail["call_allowance"] is None

    issue = next(i for i in payload["issues"] if i["issue_type"] == "field_mapping_check" and "正式工" in i["issue_detail"])
    assert "本次解析共 40 个目标字段" in issue["issue_detail"]
    assert "Call Allowance" in issue["issue_detail"]


def test_stage_base_does_not_report_field_mapping_check_for_absent_sheets(db_session):
    """Regression test: parse_workbook() always populates every role key
    with a SheetParseResult (sheet_name=None when nothing matched) - a
    truthiness check on that object is always True, so a naive `if not
    sheet_result: continue` guard never actually skips a genuinely-absent
    sheet. Caught via a real bug during manual smoke testing: uploading a
    file with no Contract-Flexi sheet at all produced a bogus "合同工(Flexi)
    sheet「None」：本次解析共 33 个目标字段，成功匹配 0 个" warning."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Formal", ["Staff ID", "Staff Name", "Entity", "Department 1", "Job Grade", "HR Cost"], [["E001", "Alice", "PalmPay", "Sales", "P1", 1000]])
    buf = io.BytesIO()
    wb.save(buf)

    batch = stage_upload(db_session, month="2026-01", file_bytes=buf.getvalue(), filename="x.xlsx", uploaded_by="t")
    payload = json.loads(batch.staged_data)
    field_mapping_issues = [i for i in payload["issues"] if i["issue_type"] == "field_mapping_check"]
    assert len(field_mapping_issues) == 1  # only for the Formal sheet that's actually in the file
    assert "正式工" in field_mapping_issues[0]["issue_detail"]


def test_stage_base_field_mapping_check_confirms_full_match(db_session):
    """When every field's alias is found, the diagnostic reports the
    positive "✓" case instead of staying silent."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    headers = [alias for spec in __import__("app.ingestion.full_fields", fromlist=["FORMAL_FIELDS"]).FORMAL_FIELDS for alias in spec.source_aliases]
    row = [None] * len(headers)
    row[headers.index("Staff ID")] = "E001"
    row[headers.index("Entity")] = "PalmPay"
    row[headers.index("Department 1")] = "Sales"
    row[headers.index("HR Cost")] = 1000
    _sheet(wb, "Formal", headers, [row])
    buf = io.BytesIO()
    wb.save(buf)

    batch = stage_upload(db_session, month="2026-01", file_bytes=buf.getvalue(), filename="x.xlsx", uploaded_by="t")
    payload = json.loads(batch.staged_data)
    issue = next(i for i in payload["issues"] if i["issue_type"] == "field_mapping_check" and "正式工" in i["issue_detail"])
    assert "本次解析共 40 个目标字段，成功匹配 40 个 ✓" in issue["issue_detail"]


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


# ---------- bonus_batch.py: PRD V1.8's rebuilt field list ----------

# Raw source column names, taken directly from full_fields.py's BONUS_FIELDS
# source_aliases (the authoritative field-mapping file - NOT the same text
# as the target labels: staff_name/position/resign_date's real source
# columns are "Name"/"Job Title"/"Leaving date").
BONUS_HEADERS = [
    "Entity", "Staff ID", "Employment Type", "Name", "Department 1", "Department 2", "Department 3",
    "Job Title", "Reporting Line", "Job Grade", "Location", "Joining Date", "Leaving date",
    "Performance Standard", "KPI Score", "Performance Bonus", "Commission", "Other", "Deduction",
    "Gross Total Amount", "ITF", "Net Amount", "HR Cost", "Remark",
]


def _bonus_row(staff_id="E001", staff_name="Alice", hr_cost=500, **overrides):
    row = {h: None for h in BONUS_HEADERS}
    row.update(
        {
            "Entity": "PalmPay",
            "Staff ID": staff_id,
            "Employment Type": "Formal",
            "Name": staff_name,
            "Department 1": "Sales",
            "Department 2": "Sub-Sales",
            "KPI Score": 92,
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


def test_bonus_batch_parser_finds_no_missing_fields_when_headers_match_mapping_file():
    wb_bytes = build_full_bonus_workbook([_bonus_row()])
    result = parse_bonus_batch_workbook(io.BytesIO(wb_bytes))
    assert len(result.field_mapping_reports) == 1
    report = result.field_mapping_reports[0]
    assert (report.total, report.matched, report.missing) == (24, 24, [])
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["staff_id"] == "E001"
    assert row["entity_raw"] == "PalmPay"
    assert row["employment_type"] == "Formal"
    assert row["amount"] == 500
    assert row["department2"] == "Sub-Sales"
    assert row["full_detail_json_fields"]["kpi_score"] == 92


def test_bonus_batch_parser_reports_missing_fields_and_skips_sheet_without_staff_id():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    # No ITF/Remark columns at all this month.
    headers = [h for h in BONUS_HEADERS if h not in ("ITF", "Remark")]
    data_row = [None] * len(headers)
    data_row[headers.index("Staff ID")] = "E001"
    _sheet(wb, "Bonus", headers, [data_row])
    _sheet(wb, "Weird", ["Not Staff ID"], [["x"]])
    buf = io.BytesIO()
    wb.save(buf)

    result = parse_bonus_batch_workbook(io.BytesIO(buf.getvalue()))
    report = result.field_mapping_reports[0]
    missing_keys = {m["key"] for m in report.missing}
    assert missing_keys == {"itf_er", "remark"}
    assert any("Weird" in s for s in result.skipped_sheets)
    assert [r["staff_id"] for r in result.rows] == ["E001"]


def test_bonus_batch_parser_resolves_entity_from_bare_entity_sheet_name():
    """User's planned future convention: standalone 奖金批次 files split by
    entity into separate sheets named just "PP"/"Blooms"/"Flexi"/"Jupiter",
    with no Entity column of their own at all - the sheet name itself is the
    entity. Must resolve entity_raw from the sheet name and NOT report
    "Entity" as a missing/unmatched field in the diagnostic (that would be
    the exact same false-alarm class as the basic_salary_actual diagnostic
    bug fixed earlier this session, on a field that's genuinely never
    expected to have a column here)."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    headers = [h for h in BONUS_HEADERS if h != "Entity"]
    row = [None] * len(headers)
    row[headers.index("Staff ID")] = "E010"
    row[headers.index("Name")] = "Grace"
    row[headers.index("HR Cost")] = 400
    _sheet(wb, "Blooms", headers, [row])
    buf = io.BytesIO()
    wb.save(buf)

    result = parse_bonus_batch_workbook(io.BytesIO(buf.getvalue()), known_entities=frozenset({"Blooms"}))
    assert result.rows[0]["entity_raw"] == "Blooms"
    report = result.field_mapping_reports[0]
    assert "entity" not in {m["key"] for m in report.missing}


def test_bonus_batch_parser_does_not_guess_entity_from_descriptive_sheet_name():
    """A real sheet named "Feb Bonus-PP" (entity embedded with other words,
    not a bare entity name) must keep resolving entity purely from its own
    Entity column / the matched base employee - not from a guess extracted
    out of a sheet name that isn't actually just the entity."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    headers = [h for h in BONUS_HEADERS if h != "Entity"]
    row = [None] * len(headers)
    row[headers.index("Staff ID")] = "E011"
    row[headers.index("Name")] = "Hank"
    row[headers.index("HR Cost")] = 400
    _sheet(wb, "Feb Bonus-PP", headers, [row])
    buf = io.BytesIO()
    wb.save(buf)

    result = parse_bonus_batch_workbook(io.BytesIO(buf.getvalue()))
    assert result.rows[0]["entity_raw"] is None
    report = result.field_mapping_reports[0]
    assert "entity" in {m["key"] for m in report.missing}


def test_confirmed_bonus_batch_resolves_entity_from_sheet_name_end_to_end(db_session):
    """Full stage_upload -> confirm_upload path: once "Blooms" is a known
    entity (established here by a Formal-Blooms base-batch sheet, matching
    the realistic upload order - base batch first, standalone bonus batch
    after), a "Blooms" bonus sheet with no Entity column of its own and no
    matching base-batch employee (a standalone recipient never listed in the
    base batch) must still resolve entity="Blooms" in the confirmed
    SupplementalPaySnapshot row, purely from the sheet name."""
    base_wb = openpyxl.Workbook()
    base_wb.remove(base_wb.active)
    _sheet(base_wb, "Formal-Blooms", ["Staff ID", "Staff Name", "Department 1", "HR Cost"], [["E001", "Alice", "Ops", 1000]])
    base_buf = io.BytesIO()
    base_wb.save(base_buf)
    base_batch = stage_upload(db_session, month="2026-01", file_bytes=base_buf.getvalue(), filename="base.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db_session, base_batch, operator="tester")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    headers = [h for h in BONUS_HEADERS if h != "Entity"]
    row = [None] * len(headers)
    row[headers.index("Staff ID")] = "STANDALONE-BLOOMS"
    row[headers.index("Name")] = "Ivy"
    row[headers.index("HR Cost")] = 400
    _sheet(wb, "Blooms", headers, [row])
    buf = io.BytesIO()
    wb.save(buf)

    batch = stage_upload(db_session, month="2026-01", file_bytes=buf.getvalue(), filename="bonus.xlsx", uploaded_by="t", salary_type="bonus")
    confirm_upload(db_session, batch, operator="tester")

    ivy = db_session.query(SupplementalPaySnapshot).filter(SupplementalPaySnapshot.staff_id == "STANDALONE-BLOOMS").one()
    assert ivy.entity == "Blooms"


def test_bonus_batch_parser_skips_summary_rows():
    wb_bytes = build_full_bonus_workbook([_bonus_row(staff_id="E001"), _bonus_row(staff_id="TOTAL", staff_name="TOTAL", hr_cost=999)])
    result = parse_bonus_batch_workbook(io.BytesIO(wb_bytes))
    assert [r["staff_id"] for r in result.rows] == ["E001"]


def test_bonus_batch_parser_handles_real_datetime_cells_without_crashing():
    wb_bytes = build_full_bonus_workbook([_bonus_row(**{"Joining Date": datetime.datetime(2021, 3, 1)})])
    result = parse_bonus_batch_workbook(io.BytesIO(wb_bytes))
    json.dumps(result.rows[0])  # must not raise
    assert result.rows[0]["joining_date"] == "2021-03-01"


def test_bonus_batch_parser_handles_bare_time_cells_without_crashing():
    """Regression test found against a real February bonus file: a handful
    of Contract-Flexi rows had a Joining Date cell that openpyxl reads back
    as datetime.time(0, 0) (date part lost upstream, only a time-of-day
    left) - this crashed the whole upload with "Object of type time is not
    JSON serializable" before format_date_value() learned to handle it."""
    wb_bytes = build_full_bonus_workbook([_bonus_row(**{"Joining Date": datetime.time(0, 0)})])
    result = parse_bonus_batch_workbook(io.BytesIO(wb_bytes))
    json.dumps(result.rows[0])  # must not raise
    assert result.rows[0]["joining_date"] == "00:00:00"


def test_confirmed_bonus_batch_parses_entity_and_employment_type_directly(db_session):
    """PRD V1.8 correction: the bonus template DOES have its own Entity and
    Employment Type columns (V1.6 wrongly assumed neither existed) - a row
    with a real Entity value doesn't need a base-batch match to resolve one."""
    bonus_bytes = build_full_bonus_workbook([_bonus_row(staff_id="STANDALONE", staff_name="NoBaseMatch")])
    batch = stage_upload(db_session, month="2026-01", file_bytes=bonus_bytes, filename="bonus.xlsx", uploaded_by="t", salary_type="bonus")
    confirm_upload(db_session, batch, operator="tester")

    row = db_session.query(SupplementalPaySnapshot).filter(SupplementalPaySnapshot.staff_id == "STANDALONE").one()
    assert row.entity == "PalmPay"  # parsed directly from the row's own Entity column
    assert row.employment_type == "Formal"
    assert row.matched_base_employee is False  # still correctly reported as unmatched to any base-batch employee


def test_confirmed_bonus_batch_falls_back_to_base_employee_entity_when_blank(db_session):
    """Safety net for rows whose own Entity column is blank - still resolves
    via the matched base-batch employee, same as V1.6."""
    base_batch = stage_upload(db_session, month="2026-01", file_bytes=build_month1_workbook(), filename="base.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db_session, base_batch, operator="tester")

    bonus_bytes = build_full_bonus_workbook([_bonus_row(staff_id="E001", hr_cost=500, Entity=None), _bonus_row(staff_id="GHOST", staff_name="Nobody", hr_cost=200, Entity=None)])
    bonus_batch = stage_upload(db_session, month="2026-01", file_bytes=bonus_bytes, filename="bonus.xlsx", uploaded_by="t", salary_type="bonus")
    payload = json.loads(bonus_batch.staged_data)
    assert payload["summary"]["salary_type"] == "bonus"
    assert payload["summary"]["unmatched_count"] == 1
    issue_types = [i["issue_type"] for i in payload["issues"]]
    assert "unmatched_supplemental_staff" in issue_types

    confirm_upload(db_session, bonus_batch, operator="tester")

    rows = db_session.query(SupplementalPaySnapshot).filter(SupplementalPaySnapshot.pay_type == "bonus").all()
    alice = next(r for r in rows if r.staff_id == "E001")
    assert alice.entity == "PalmPay"  # resolved from the matched base employee, own Entity column was blank
    assert alice.department2 == "Sub-Sales"
    detail = json.loads(alice.full_detail_json)
    assert detail["kpi_score"] == 92

    ghost = next(r for r in rows if r.staff_id == "GHOST")
    assert ghost.entity is None  # no base match, own Entity column also blank - genuinely can't resolve


def test_confirmed_bonus_batch_falls_back_to_base_employee_descriptive_fields_when_blank(db_session):
    """Regression test found against a real production export: Employment
    Type/Position/Reporting Line/Job Grade/Department 3 came back blank for
    every bonus row, even for employees matched to a base-batch employee that
    had all of these. staff_name/department1/entity already had this
    fallback (see the test above); the rest of the descriptive fields need
    the identical fallback, not a separate mechanism."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(
        wb,
        "Formal",
        ["Staff ID", "Staff Name", "Entity", "Department 1", "Department 2", "Department 3", "Position", "Reporting Line", "Job Grade", "HR Cost", "Resign Date"],
        [["E001", "Alice", "PalmPay", "Sales", "Sub-Sales", "Team A", "Engineer", "Manager Mike", "P1", 1000, None]],
    )
    buf = io.BytesIO()
    wb.save(buf)
    base_batch = stage_upload(db_session, month="2026-01", file_bytes=buf.getvalue(), filename="base.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db_session, base_batch, operator="tester")

    bonus_bytes = build_full_bonus_workbook(
        [_bonus_row(staff_id="E001", hr_cost=500, **{"Employment Type": None, "Department 2": None, "Department 3": None, "Job Title": None, "Reporting Line": None, "Job Grade": None})]
    )
    bonus_batch = stage_upload(db_session, month="2026-01", file_bytes=bonus_bytes, filename="bonus.xlsx", uploaded_by="t", salary_type="bonus")
    confirm_upload(db_session, bonus_batch, operator="tester")

    alice = db_session.query(SupplementalPaySnapshot).filter(SupplementalPaySnapshot.staff_id == "E001", SupplementalPaySnapshot.pay_type == "bonus").one()
    assert alice.employment_type == "Formal"
    assert alice.department2 == "Sub-Sales"
    assert alice.department3 == "Team A"
    assert alice.position == "Engineer"
    assert alice.reporting_line == "Manager Mike"
    assert alice.job_grade == "P1"


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
