from fastapi import HTTPException

from app.compute.export import get_employee_detail_rows, get_supplemental_detail_rows
from app.compute.scope import ScopeRule
from app.ingestion.commit import confirm_upload
from app.ingestion.loader import stage_upload
from app.models import DownloadLog, User, ViewerPermission
from app.routers.export import _build_workbook, export_detail
from app.schemas import ExportDetailRequest

from .xlsx_fixtures import build_component_workbook, build_month1_workbook, build_supplemental_workbook

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


def test_build_workbook_watermark_sheet_and_data_sheets():
    import io
    from datetime import datetime

    import openpyxl

    workbook_bytes = _build_workbook(
        [], [], ["base", "bonus", "backpay"], "marcus", datetime(2026, 7, 25, 9, 0, 0), "PalmPay", "Sales", "2026-01", "2026-01", []
    )
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    assert wb.sheetnames == ["说明", "正式工明细", "合同工明细", "奖金补发明细"]

    info_rows = list(wb["说明"].iter_rows(values_only=True))
    assert info_rows[0][0] == "本文件由 marcus 于 2026-07-25 09:00:00 导出"
    assert info_rows[1][0] == "数据范围：PalmPay-Sales，2026-01 至 2026-01"
    assert "底薪批次、奖金批次、补发批次" in info_rows[2][0]
    assert "保密" in info_rows[3][0]

    formal_header = next(wb["正式工明细"].iter_rows(values_only=True))
    assert formal_header[:5] == ("月份", "实体", "部门", "员工姓名", "员工工号")
    assert "用工类型" not in formal_header  # implied by the sheet name, not repeated as a column


def test_build_workbook_only_base_selected_omits_supplemental_sheet():
    import io
    from datetime import datetime

    import openpyxl

    workbook_bytes = _build_workbook([], [], ["base"], "marcus", datetime(2026, 7, 25, 9, 0, 0), "PalmPay", "全部部门", "2026-01", "2026-01", [])
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    assert wb.sheetnames == ["说明", "正式工明细", "合同工明细"]


def test_build_workbook_only_bonus_selected_omits_base_sheets():
    import io
    from datetime import datetime

    import openpyxl

    workbook_bytes = _build_workbook([], [], ["bonus"], "marcus", datetime(2026, 7, 25, 9, 0, 0), "PalmPay", "全部部门", "2026-01", "2026-01", [])
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    assert wb.sheetnames == ["说明", "奖金补发明细"]


def test_build_workbook_discloses_missing_month_type_combos():
    import io
    from datetime import datetime

    import openpyxl

    workbook_bytes = _build_workbook(
        [], [], ["base", "bonus"], "marcus", datetime(2026, 7, 25, 9, 0, 0), "全公司", "全部部门", "2026-01", "2026-02",
        [("2026-02", "bonus")],
    )
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    info_rows = list(wb["说明"].iter_rows(values_only=True))
    disclosure = [r[0] for r in info_rows if r[0] and "暂无数据" in r[0]]
    assert disclosure and "2026-02 奖金批次" in disclosure[0]


def test_formal_contract_split_uses_employment_type(db_session):
    employees = [
        {"staff_id": "E001", "name": "Alice", "role": "formal", "department": "Ops", "basic": 100000, "perf_bonus": 0, "commission": 0, "overtime": 0, "statutory": 0},
        {"staff_id": "E002", "name": "Bob", "role": "contract", "department": "Ops", "basic": 50000, "perf_bonus": 0, "commission": 0, "overtime": 0, "statutory": 0},
    ]
    batch = stage_upload(db_session, month="2026-01", file_bytes=build_component_workbook("2026-01", employees), filename="m.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db_session, batch, operator="tester")

    rows, _ = get_employee_detail_rows(db_session, months=["2026-01"], scope_rules=None, fold_supplemental=False)
    formal = [r for r in rows if r["employment_type"] == "Formal"]
    contract = [r for r in rows if r["employment_type"] != "Formal"]
    assert [r["staff_id"] for r in formal] == ["E001"]
    assert [r["staff_id"] for r in contract] == ["E002"]


def test_get_supplemental_detail_rows_reports_batch_type_and_match_status(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    _confirm(db_session, "2026-01", lambda: build_supplemental_workbook([("E001", "Alice", "Sales", 500), ("GHOST", "Nobody", "Sales", 200)]), salary_type="backpay")

    rows = get_supplemental_detail_rows(db_session, months=["2026-01"], pay_types=["backpay"], scope_rules=None)
    assert len(rows) == 2
    alice_row = next(r for r in rows if r["staff_id"] == "E001")
    assert alice_row["batch_type_label"] == "补发批次"
    assert alice_row["matched_label"] == "是"
    ghost_row = next(r for r in rows if r["staff_id"] == "GHOST")
    assert ghost_row["matched_label"] == "否"


def test_export_endpoint_rejects_when_requested_month_type_has_no_data(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    admin = _make_user(db_session, "marcus", "admin")

    try:
        export_detail(ExportDetailRequest(salary_types=["bonus"]), db_session, admin)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400
        assert "奖金批次" in e.detail
        assert "暂无数据" in e.detail


def test_export_endpoint_accepts_base_only_when_bonus_absent(db_session):
    from starlette.responses import StreamingResponse

    _confirm(db_session, "2026-01", build_month1_workbook)
    admin = _make_user(db_session, "marcus", "admin")

    response = export_detail(ExportDetailRequest(salary_types=["base"]), db_session, admin)
    assert isinstance(response, StreamingResponse)

    log = db_session.query(DownloadLog).one()
    assert log.salary_types == "base"
    assert log.row_count == 5


def test_export_endpoint_rejects_unknown_salary_type(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    admin = _make_user(db_session, "marcus", "admin")

    try:
        export_detail(ExportDetailRequest(salary_types=["bogus"]), db_session, admin)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400
