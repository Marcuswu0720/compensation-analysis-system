import io
import json

import openpyxl

from app.compute.attribution import compute_attribution
from app.compute.trends import get_trend, list_departments, list_entities
from app.ingestion.commit import confirm_upload
from app.ingestion.loader import stage_upload
from app.ingestion.parser import default_entity_for_suffix, entity_hint_from_sheet_name, match_base_sheet_role

from .xlsx_fixtures import _sheet, build_month1_workbook, build_month2_workbook


def _upload_and_confirm(db, month, content):
    batch = stage_upload(db, month=month, file_bytes=content, filename=f"{month}.xlsx", uploaded_by="tester")
    confirm_upload(db, batch, operator="tester")
    return batch


def test_headcount_and_cost_include_mid_month_resignations(db_session):
    batch = _upload_and_confirm(db_session, "2026-01", build_month1_workbook())
    payload = json.loads(batch.staged_data)

    # Carol (E003) resigned mid-January but still drew a January paycheck, so
    # she must count in this month's cash-flow headcount/cost (PRD §2.2) even
    # though is_active is False for her.
    assert payload["summary"]["headcount_total"] == 5
    assert payload["summary"]["total_hr_cost"] == 1000 + 1200 + 900 + 500 + 600

    trend = get_trend(db_session, months=["2026-01"])
    assert trend == [{"month": "2026-01", "headcount": 5, "total_hr_cost": 4200.0, "avg_hr_cost": 840.0}]


def test_department_casing_variant_merges_to_proper_case(db_session):
    _upload_and_confirm(db_session, "2026-01", build_month1_workbook())

    # "Sales" and "sales" both appear in the same file; the properly
    # capitalized form should win regardless of which one is more frequent.
    departments = list_departments(db_session)
    assert "Sales" in departments
    assert "sales" not in departments

    sales_trend = get_trend(db_session, months=["2026-01"], department="Sales")
    assert sales_trend[0]["headcount"] == 3  # Alice, Bob, Dave
    assert sales_trend[0]["total_hr_cost"] == 1000 + 1200 + 500


def test_entity_default_and_explicit_values_resolve_consistently(db_session):
    _upload_and_confirm(db_session, "2026-01", build_month1_workbook())
    entities = list_entities(db_session)
    assert set(entities) == {"PalmPay", "Flexi"}


def test_summary_row_is_filtered_out_of_bonus_sheet(db_session):
    batch = stage_upload(db_session, month="2026-01", file_bytes=build_month1_workbook(), filename="x.xlsx", uploaded_by="t")
    payload = json.loads(batch.staged_data)
    bonus_ids = [b["staff_id"] for b in payload["bonuses"]]
    assert bonus_ids == ["E001"]  # the 'ITEM'/'TOTAL'/'Staff Number'/etc rows must not appear


def test_summary_row_markers_cover_2026_07_contract_flexi_wording():
    """Found in a real 2026-07 Contract-Flexi sheet: its trailing summary
    block spells these labels differently from every other month seen so
    far ("Gross Salary" instead of "Gross", "Total Amount" instead of
    "Total", "Net Pay" instead of "Net Amount", "Bonus & Arrears" not
    covered at all before) - all 4 slipped through as phantom zero-cost
    "employees" until SUMMARY_ROW_MARKERS picked up the exact wording."""
    from app.ingestion.parser import is_summary_row

    for label in ["Gross Salary", "Bonus & Arrears", "Net Pay", "Total Amount"]:
        assert is_summary_row(label), f"{label!r} should be recognized as a summary row"


def test_field_alias_and_sheet_name_drift_across_months(db_session):
    _upload_and_confirm(db_session, "2026-01", build_month1_workbook())
    batch2 = _upload_and_confirm(db_session, "2026-02", build_month2_workbook())
    payload2 = json.loads(batch2.staged_data)

    # Feb uses "Company/签约主体" instead of "Entity" and renames the PP
    # contract sheet to "PP-Contract" - Dave (E004) must still resolve to
    # entity=PalmPay via the alias map, not fall through as unmapped.
    dave = next(e for e in payload2["employees"] if e["staff_id"] == "E004")
    assert dave["entity"] == "PalmPay"

    # No exits sheet in Feb at all - must be flagged, not silently ignored.
    issue_types = [i["issue_type"] for i in payload2["issues"]]
    assert "missing_sheet" in issue_types


def test_attribution_reconciles_across_joiners_leavers_stayers(db_session):
    _upload_and_confirm(db_session, "2026-01", build_month1_workbook())
    _upload_and_confirm(db_session, "2026-02", build_month2_workbook())

    result = compute_attribution(db_session, "2026-01", "2026-02")

    assert result.joiners_count == 1  # Frank
    assert result.joiners_cost == 700
    assert result.leavers_count == 2  # Carol + Eve
    assert result.leavers_cost == 900 + 600
    assert result.stayers_count == 3  # Alice, Bob, Dave
    assert result.stayers_delta == 100 + 0 + 50
    assert result.net_change == 3550 - 4200
    assert result.reconciled is True
    assert abs(result.checksum - result.net_change) < 1e-6


def test_reupload_overwrites_prior_confirmed_month(db_session):
    _upload_and_confirm(db_session, "2026-01", build_month1_workbook())
    # Re-uploading the same month with identical content should not duplicate rows.
    _upload_and_confirm(db_session, "2026-01", build_month1_workbook())

    trend = get_trend(db_session, months=["2026-01"])
    assert trend[0]["headcount"] == 5


# ---------- match_base_sheet_role() / default_entity_for_suffix(): new-entity onboarding ----------


def test_match_base_sheet_role_recognizes_entity_suffix_in_either_order():
    """Regression test: a real user file had a third entity ("Blooms") with
    its own Formal/Contract sheets - the old sheet-role matching only knew
    about two hardcoded entities (PP/Flexi), so a bare "Contract" sheet and
    any "-Blooms" suffixed sheet ended up entirely unrecognized
    (unrecognized_sheet), not just missing a field or two."""
    assert match_base_sheet_role("Formal") == ("formal", None)
    assert match_base_sheet_role("contract") == ("contract", None)  # bare, lowercase - previously had no pattern at all
    assert match_base_sheet_role("Formal-Blooms") == ("formal", "Blooms")
    assert match_base_sheet_role("Contract-Blooms") == ("contract", "Blooms")
    assert match_base_sheet_role("Formal-Jupiter") == ("formal", "Jupiter")
    assert match_base_sheet_role("Contract-Jupiter") == ("contract", "Jupiter")
    assert match_base_sheet_role("Contract - PP") == ("contract", "PP")  # suffix after, spaced dash
    assert match_base_sheet_role("PP-Contract") == ("contract", "PP")  # suffix before
    assert match_base_sheet_role("Exit") is None
    assert match_base_sheet_role("PP-Dec bonus") is None


def test_default_entity_for_suffix_uses_alias_map_and_capitalizes():
    assert default_entity_for_suffix("PP") == "PalmPay"  # ENTITY_ALIASES
    assert default_entity_for_suffix("Blooms") == "Blooms"  # already capitalized, left alone
    assert default_entity_for_suffix("blooms") == "Blooms"  # all-lowercase sheet name -> title-cased


def test_entity_hint_from_sheet_name_only_matches_bare_known_entity_names():
    """Standalone 奖金批次 sheets can be named after their entity alone (no
    Formal/Contract role word to anchor a suffix on, unlike the base batch).
    "PP" resolves via ENTITY_ALIASES regardless of what's already known (it's
    a small, deliberately curated, stable list) - anything else needs to
    already be a known entity in the system (typically established by that
    entity's own Formal/Contract base-batch sheets already having been
    uploaded), otherwise ANY plain single-word sheet name ("Bonus",
    "Summary") would misfire as a made-up "entity". A descriptive real sheet
    name like "Feb Bonus-PP" (entity embedded with other words, not a bare
    token) is rejected outright regardless of known_entities - it still
    resolves entity purely from its own Entity column / the matched base
    employee, same as before this feature existed."""
    assert entity_hint_from_sheet_name("PP") == "PalmPay"
    assert entity_hint_from_sheet_name("Blooms") is None  # not a known entity yet
    assert entity_hint_from_sheet_name("Blooms", frozenset({"Blooms"})) == "Blooms"
    assert entity_hint_from_sheet_name("blooms", frozenset({"Blooms"})) == "Blooms"  # case-insensitive match
    assert entity_hint_from_sheet_name("Jupiter", frozenset({"Blooms"})) is None  # known set doesn't include it
    assert entity_hint_from_sheet_name("Bonus", frozenset({"Bonus"})) == "Bonus"  # deliberately still matches if it's genuinely a known entity name
    assert entity_hint_from_sheet_name("Feb Bonus-PP", frozenset({"PP"})) is None  # not a bare token, rejected regardless
    assert entity_hint_from_sheet_name("1月离职") is None


def test_stage_base_recognizes_new_entity_sheets_without_hardcoding(db_session):
    """End-to-end version: a workbook with a bare (lowercase) "contract"
    sheet and a brand-new entity's Formal/Contract sheets ("Formal-Blooms"/
    "Contract-Blooms", neither with their own Entity column) must all be
    recognized and staged - none of them should show up in unrecognized_sheet,
    and the Blooms rows must resolve to entity="Blooms" via the sheet-name
    suffix default, exactly like Contract-PP/-Flexi already did for PalmPay/
    Flexi."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Formal", ["Staff ID", "Staff Name", "Entity", "Department 1", "HR Cost"], [["E001", "Alice", "PalmPay", "Sales", 1000]])
    _sheet(wb, "contract", ["Staff ID", "Staff Name", "Entity", "Department 1", "HR Cost"], [["E002", "Bob", "PalmPay", "Sales", 500]])
    _sheet(wb, "Formal-Blooms", ["Staff ID", "Staff Name", "Department 1", "HR Cost"], [["E003", "Carol", "Ops", 800]])
    _sheet(wb, "Contract-Blooms", ["Staff ID", "Staff Name", "Department 1", "HR Cost"], [["E004", "Dave", "Ops", 300]])
    buf = io.BytesIO()
    wb.save(buf)

    batch = stage_upload(db_session, month="2026-01", file_bytes=buf.getvalue(), filename="x.xlsx", uploaded_by="t")
    payload = json.loads(batch.staged_data)

    issue_details = [i["issue_detail"] for i in payload["issues"] if i["issue_type"] == "unrecognized_sheet"]
    assert issue_details == []

    by_id = {e["staff_id"]: e for e in payload["employees"]}
    assert by_id["E001"]["employment_type"] == "Formal" and by_id["E001"]["entity"] == "PalmPay"
    assert by_id["E002"]["employment_type"] == "Contract" and by_id["E002"]["entity"] == "PalmPay"
    assert by_id["E003"]["employment_type"] == "Formal" and by_id["E003"]["entity"] == "Blooms"
    assert by_id["E004"]["employment_type"] == "Contract" and by_id["E004"]["entity"] == "Blooms"
    assert payload["summary"]["headcount_total"] == 4

    confirm_upload(db_session, batch, operator="tester")
    assert set(list_entities(db_session)) == {"PalmPay", "Blooms"}
