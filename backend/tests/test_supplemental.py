from app.compute.attribution import compute_attribution
from app.compute.categories import get_categories_trend
from app.compute.trends import get_trend, list_available_months
from app.ingestion.commit import confirm_upload, delete_confirmed_batch, reassign_month
from app.ingestion.loader import stage_upload
from app.models import UploadBatch

from .xlsx_fixtures import build_month1_workbook, build_month2_workbook, build_supplemental_workbook


def _confirm_base(db, month, builder):
    batch = stage_upload(db, month=month, file_bytes=builder(), filename=f"{month}.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db, batch, operator="tester")
    return batch


def test_backpay_adds_on_top_of_base_without_touching_headcount(db_session):
    _confirm_base(db_session, "2026-01", build_month1_workbook)

    backpay = build_supplemental_workbook([("E001", "Alice", "Sales", 500)])
    batch = stage_upload(db_session, month="2026-01", file_bytes=backpay, filename="bp.xlsx", uploaded_by="t", salary_type="backpay")
    confirm_upload(db_session, batch, operator="tester")

    trend = get_trend(db_session, months=["2026-01"])
    assert trend[0]["headcount"] == 5  # unchanged - backpay doesn't create headcount
    assert trend[0]["total_hr_cost"] == 4200 + 500


def test_unmatched_supplemental_staff_is_unattributed_but_still_counted(db_session):
    _confirm_base(db_session, "2026-01", build_month1_workbook)
    _confirm_base(db_session, "2026-02", build_month2_workbook)

    backpay = build_supplemental_workbook([("E001", "Alice", "Sales", 500), ("GHOST", "Nobody", "Sales", 200)])
    batch = stage_upload(db_session, month="2026-01", file_bytes=backpay, filename="bp.xlsx", uploaded_by="t", salary_type="backpay")
    payload_summary = None
    import json

    payload_summary = json.loads(batch.staged_data)["summary"]
    assert payload_summary["matched_count"] == 1
    assert payload_summary["unmatched_count"] == 1
    confirm_upload(db_session, batch, operator="tester")

    result = compute_attribution(db_session, "2026-01", "2026-02")
    assert result.unattributed_prev == 200
    assert result.unattributed_cur == 0
    # checksum must still reconcile even with an unattributed adjustment folded in
    assert result.reconciled is True
    assert abs(result.checksum - result.net_change) < 1e-6


def test_reuploading_same_type_supersedes_only_that_type(db_session):
    _confirm_base(db_session, "2026-01", build_month1_workbook)

    bp1 = stage_upload(
        db_session,
        month="2026-01",
        file_bytes=build_supplemental_workbook([("E001", "Alice", "Sales", 500)]),
        filename="bp1.xlsx",
        uploaded_by="t",
        salary_type="backpay",
    )
    confirm_upload(db_session, bp1, operator="tester")

    bp2 = stage_upload(
        db_session,
        month="2026-01",
        file_bytes=build_supplemental_workbook([("E001", "Alice", "Sales", 999)]),
        filename="bp2.xlsx",
        uploaded_by="t",
        salary_type="backpay",
    )
    confirm_upload(db_session, bp2, operator="tester")

    trend = get_trend(db_session, months=["2026-01"])
    # must be replaced (4200+999), not stacked (4200+500+999)
    assert trend[0]["total_hr_cost"] == 4200 + 999

    db_session.refresh(bp1)
    assert bp1.status == "superseded"

    # base data for the month must be untouched by the backpay supersede
    base_trend = get_trend(db_session, months=["2026-01"])
    assert base_trend[0]["headcount"] == 5


def test_delete_confirmed_batch_removes_its_data(db_session):
    batch = _confirm_base(db_session, "2026-01", build_month1_workbook)
    assert get_trend(db_session, months=["2026-01"])[0]["headcount"] == 5

    delete_confirmed_batch(db_session, batch, operator="tester")
    assert get_trend(db_session, months=["2026-01"]) == []
    assert "2026-01" not in list_available_months(db_session)


def test_reassign_month_moves_all_data_and_detects_conflict(db_session):
    b1 = _confirm_base(db_session, "2026-01", build_month1_workbook)
    b2 = _confirm_base(db_session, "2026-02", build_month2_workbook)

    # Conflict: 2026-02 already has a confirmed base batch.
    import pytest

    with pytest.raises(ValueError):
        reassign_month(db_session, b1, "2026-02", operator="tester")

    reassign_month(db_session, b1, "2026-03", operator="tester")
    assert get_trend(db_session, months=["2026-01"]) == []
    trend = get_trend(db_session, months=["2026-03"])
    assert trend[0]["headcount"] == 5
    assert trend[0]["total_hr_cost"] == 4200


def test_supplemental_only_month_still_shows_in_trend_not_dropped(db_session):
    _confirm_base(db_session, "2026-01", build_month1_workbook)
    batch = stage_upload(
        db_session,
        month="2026-05",
        file_bytes=build_supplemental_workbook([("E001", "Alice", "Sales", 300)]),
        filename="bonus.xlsx",
        uploaded_by="t",
        salary_type="bonus",
    )
    confirm_upload(db_session, batch, operator="tester")

    trend = get_trend(db_session)
    months_seen = {r["month"] for r in trend}
    assert "2026-05" in months_seen
    row = next(r for r in trend if r["month"] == "2026-05")
    assert row["total_hr_cost"] == 300
    assert row["headcount"] == 0
    assert "2026-05" in list_available_months(db_session)


def test_backpay_category_tag_folds_into_that_category_not_generic_bucket(db_session):
    _confirm_base(db_session, "2026-05", build_month1_workbook)

    batch = stage_upload(
        db_session,
        month="2026-05",
        file_bytes=build_supplemental_workbook([("E001", "Alice", "Sales", 300)]),
        filename="customer_service_overtime_backpay.xlsx",
        uploaded_by="t",
        salary_type="backpay",
        category="overtime_amount",
    )
    assert batch.category == "overtime_amount"
    confirm_upload(db_session, batch, operator="tester")

    rows = get_categories_trend(db_session, categories=["overtime_amount", "supplemental_backpay", "hr_cost"], months=["2026-05"])
    cats = rows[0]["categories"]
    assert cats["overtime_amount"] == 300  # month1 workbook's base overtime is 0 for every employee
    assert cats["supplemental_backpay"] == 0  # nothing uncategorized this month
    assert cats["hr_cost"] == 4200 + 300


def test_uncategorized_backpay_still_falls_into_generic_bucket(db_session):
    _confirm_base(db_session, "2026-05", build_month1_workbook)

    batch = stage_upload(
        db_session,
        month="2026-05",
        file_bytes=build_supplemental_workbook([("E001", "Alice", "Sales", 500)]),
        filename="bp.xlsx",
        uploaded_by="t",
        salary_type="backpay",
    )
    assert batch.category is None
    confirm_upload(db_session, batch, operator="tester")

    rows = get_categories_trend(db_session, categories=["overtime_amount", "supplemental_backpay"], months=["2026-05"])
    cats = rows[0]["categories"]
    assert cats["overtime_amount"] == 0
    assert cats["supplemental_backpay"] == 500
