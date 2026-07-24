import pytest
from fastapi import HTTPException

from app.compute.trends import get_trend, list_departments
from app.ingestion.commit import confirm_upload, delete_confirmed_batch
from app.ingestion.loader import stage_upload
from app.models import User, ViewerPermission
from app.security import (
    NO_ACCESS_SENTINEL,
    get_allowed_scope,
    resolve_department_axis,
    resolve_scope_filters,
)

from .xlsx_fixtures import build_month1_workbook, build_month2_workbook


def _confirm(db, month, builder):
    batch = stage_upload(db, month=month, file_bytes=builder(), filename=f"{month}.xlsx", uploaded_by="t", salary_type="base")
    confirm_upload(db, batch, operator="tester")
    return batch


def _grant(db, user, scope_type, value):
    db.add(ViewerPermission(user_id=user.id, scope_type=scope_type, scope_value=value))
    db.commit()


def _make_user(db, username, role):
    u = User(username=username, password_hash="x", role=role)
    db.add(u)
    db.commit()
    return u


def test_admin_scope_is_unrestricted(db_session):
    admin = _make_user(db_session, "marcus", "admin")
    scope = get_allowed_scope(db_session, admin)
    assert scope.departments is None
    assert scope.entities is None
    dept, entity = resolve_scope_filters(scope, "Anything", "Anything")
    assert dept == "Anything" and entity == "Anything"


def test_viewer_with_no_grants_is_locked_out(db_session):
    viewer = _make_user(db_session, "xiajie", "viewer")
    scope = get_allowed_scope(db_session, viewer)
    dept, entity = resolve_scope_filters(scope, None, None)
    assert dept == NO_ACCESS_SENTINEL
    assert resolve_department_axis(scope) == NO_ACCESS_SENTINEL


def test_viewer_department_grant_allows_that_department_and_blocks_others(db_session):
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "department", "Sales")
    scope = get_allowed_scope(db_session, viewer)

    dept, entity = resolve_scope_filters(scope, "Sales", None)
    assert dept == "Sales"
    assert entity is None  # no entity grants at all -> unrestricted on that axis

    with pytest.raises(HTTPException) as exc:
        resolve_scope_filters(scope, "Marketing", None)
    assert exc.value.status_code == 403


def test_viewer_with_only_department_grant_sees_all_entities_within_it(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "department", "Sales")
    scope = get_allowed_scope(db_session, viewer)

    department, entity = resolve_scope_filters(scope, None, None)
    assert department == ["Sales"]
    assert entity is None

    rows = get_trend(db_session, months=["2026-01"], department=department, entity=entity)
    # Sales spans both PalmPay (Alice/Bob) and contract (Dave) - all three
    # should count since the entity axis is unrestricted for this viewer.
    assert rows[0]["headcount"] == 3


def test_department_and_entity_grants_combine_as_intersection(db_session):
    """Documented simplification vs the PRD's literal OR wording: when a
    viewer has grants on BOTH axes, both axes must match (AND), not either
    (OR) - see security.py's AllowedScope docstring. Two separate viewer
    accounts is the workaround if true OR access is ever needed."""
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "department", "Sales")
    _grant(db_session, viewer, "entity", "Flexi")
    scope = get_allowed_scope(db_session, viewer)

    department, entity = resolve_scope_filters(scope, None, None)
    rows = get_trend(db_session, months=["2026-01"], department=department, entity=entity)
    # Only Dave (Sales + PalmPay contract... wait Dave has no explicit entity
    # column, defaults to PalmPay) matches neither Sales+Flexi combo, so this
    # scope should return nobody, proving the AND (not OR) semantics.
    assert rows == [] or rows[0]["headcount"] == 0


def test_allowed_departments_list_only_shows_granted_departments(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "department", "Sales")
    scope = get_allowed_scope(db_session, viewer)

    visible = list_departments(db_session, allowed=scope.departments)
    assert visible == ["Sales"]


def test_soft_deleted_batch_excluded_from_department_list(db_session):
    batch = _confirm(db_session, "2026-01", build_month1_workbook)
    assert "Sales" in list_departments(db_session)

    delete_confirmed_batch(db_session, batch, operator="tester")
    assert list_departments(db_session) == []
