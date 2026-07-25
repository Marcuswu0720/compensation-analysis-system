from fastapi import HTTPException

from app.compute.export import get_employee_detail_rows
from app.compute.scope import ScopeRule
from app.ingestion.commit import confirm_upload
from app.ingestion.loader import stage_upload
from app.models import DownloadLog, User, ViewerPermission
from app.routers.export import _build_workbook, export_detail
from app.schemas import ExportDetailRequest

from .xlsx_fixtures import build_month1_workbook, build_supplemental_workbook

# Same fixture geometry as test_permissions.py: Alice/Bob/Dave = PalmPay+Sales,
# Carol = PalmPay+Ops, Eve = Flexi+Ops - two differently-owned "Ops"
# departments, which is exactly the case V1.2/V1.3 must not conflate.


def _confirm(db, month, builder, salary_type="base"):
    batch = stage_upload(db, month=month, file_bytes=builder(), filename=f"{month}.xlsx", uploaded_by="t", salary_type=salary_type)
    confirm_upload(db, batch, operator="tester")
    return batch


def _grant(db, user, entity, department1=None):
    scope_type = "entity_department" if department1 else "entity"
    db.add(ViewerPermission(user_id=user.id, scope_type=scope_type, entity=entity, department1=department1, granted_by="tester"))
    db.commit()


def _make_user(db, username, role):
    u = User(username=username, password_hash="x", role=role)
    db.add(u)
    db.commit()
    return u


def test_admin_export_sees_every_department_including_both_ops(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    rows, unattributed = get_employee_detail_rows(db_session, months=["2026-01"], scope_rules=None)
    staff_ids = {r["staff_id"] for r in rows}
    assert staff_ids == {"E001", "E002", "E003", "E004", "E005"}
    assert unattributed == {}


def test_entity_department_rule_excludes_same_named_department_in_other_entity(db_session):
    """The core V1.3 requirement: download must reuse the V1.2 rule engine,
    not a bare department-name filter - granting Flexi+Ops must never also
    export PalmPay's own Ops department (Carol)."""
    _confirm(db_session, "2026-01", build_month1_workbook)
    rules = [ScopeRule(entity="Flexi", department1="Ops")]

    rows, _ = get_employee_detail_rows(db_session, months=["2026-01"], scope_rules=rules)
    assert [r["staff_id"] for r in rows] == ["E005"]
    assert rows[0]["staff_name"] == "Eve"
    assert rows[0]["entity"] == "Flexi"
    assert rows[0]["department1"] == "Ops"


def test_zero_rules_exports_nothing(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    rows, _ = get_employee_detail_rows(db_session, months=["2026-01"], scope_rules=[])
    assert rows == []


def test_matched_supplemental_pay_folds_into_hr_cost(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    _confirm(db_session, "2026-01", lambda: build_supplemental_workbook([("E001", "Alice", "Sales", 500)]), salary_type="backpay")

    rows, unattributed = get_employee_detail_rows(db_session, months=["2026-01"], scope_rules=None)
    alice = next(r for r in rows if r["staff_id"] == "E001")
    assert alice["hr_cost"] == 1000 + 500  # Alice's base hr_cost (1000) + backpay
    assert unattributed == {}


def test_unattributed_supplemental_reported_not_dropped(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    _confirm(
        db_session,
        "2026-01",
        lambda: build_supplemental_workbook([("GHOST", "Nobody", "Sales", 777)]),
        salary_type="backpay",
    )

    rows, unattributed = get_employee_detail_rows(db_session, months=["2026-01"], scope_rules=None)
    assert all(r["hr_cost"] not in (777,) for r in rows)  # not attached to any real employee
    assert unattributed == {"2026-01": 777}


def test_resigned_employee_status_label_includes_date(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    rows, _ = get_employee_detail_rows(db_session, months=["2026-01"], scope_rules=None)
    carol = next(r for r in rows if r["staff_id"] == "E003")
    assert carol["status_label"] == "已离职（2026-01-20）"
    alice = next(r for r in rows if r["staff_id"] == "E001")
    assert alice["status_label"] == "在职"


def test_export_endpoint_rejects_viewer_with_no_grants(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")

    try:
        export_detail(ExportDetailRequest(), db_session, viewer)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_export_endpoint_rejects_out_of_scope_request(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "Flexi", "Ops")

    try:
        export_detail(ExportDetailRequest(entity="PalmPay"), db_session, viewer)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_export_endpoint_logs_download_and_returns_valid_workbook(db_session):
    from starlette.responses import StreamingResponse

    _confirm(db_session, "2026-01", build_month1_workbook)
    admin = _make_user(db_session, "marcus", "admin")

    response = export_detail(ExportDetailRequest(), db_session, admin)
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert ".xlsx" in response.headers["content-disposition"]

    log = db_session.query(DownloadLog).one()
    assert log.username == "marcus"
    assert log.row_count == 5
    assert log.month_range_start == "2026-01"
    assert log.month_range_end == "2026-01"
    assert log.entity_scope == "全公司"
    assert log.department_scope == "全部部门"


def test_build_workbook_content_and_watermark():
    import io
    from datetime import datetime

    import openpyxl

    rows_bytes = _build_workbook([], "marcus", datetime(2026, 7, 25, 9, 0, 0), "PalmPay", "Sales", "2026-01", "2026-01", {})
    wb = openpyxl.load_workbook(io.BytesIO(rows_bytes))
    ws = wb.active
    out_rows = list(ws.iter_rows(values_only=True))
    assert out_rows[0][0] == "本文件由 marcus 于 2026-07-25 09:00:00 导出"
    assert out_rows[1][0] == "数据范围：PalmPay-Sales，2026-01 至 2026-01"
    assert "保密" in out_rows[2][0]
    assert all(v is None for v in out_rows[3])
    assert out_rows[4][:5] == ("月份", "实体", "部门", "员工姓名", "员工工号")


def test_build_workbook_discloses_unattributed_amount_in_watermark():
    from datetime import datetime

    rows_bytes = _build_workbook(
        [], "marcus", datetime(2026, 7, 25, 9, 0, 0), "全公司", "全部部门", "2026-01", "2026-01", {"2026-01": 777.0}
    )
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(rows_bytes))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert "无法关联到具体在职员工" in rows[3][0]
    assert "777" in rows[3][0]
