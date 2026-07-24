import json

from app.compute.attribution import compute_attribution
from app.compute.trends import get_trend, list_departments, list_entities
from app.ingestion.commit import confirm_upload
from app.ingestion.loader import stage_upload

from .xlsx_fixtures import build_month1_workbook, build_month2_workbook


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
