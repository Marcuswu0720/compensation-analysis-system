from datetime import datetime

import pytest
from fastapi import HTTPException

from app.compute.scope import ScopeRule
from app.compute.trends import get_trend, list_departments
from app.ingestion.commit import confirm_upload, delete_confirmed_batch
from app.ingestion.loader import stage_upload
from app.models import User, ViewerPermission
from app.security import get_allowed_scope, resolve_requested_filters

from .xlsx_fixtures import build_month1_workbook

# build_month1_workbook resolves to: Alice/Bob/Carol = PalmPay+Sales (Carol is
# PalmPay+Ops), Dave = PalmPay+Sales (Contract-PP, entity defaults to
# PalmPay), Eve = Flexi+Ops (Contract-Flexi, entity defaults to Flexi).
# Two departments named "Ops" exist, one under each of two different
# entities - this is the exact scenario PRD V1.2 §1.1 is about.


def _confirm(db, month, builder):
    batch = stage_upload(db, month=month, file_bytes=builder(), filename=f"{month}.xlsx", uploaded_by="t", salary_type="base")
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


def test_admin_scope_is_unrestricted(db_session):
    admin = _make_user(db_session, "marcus", "admin")
    scope = get_allowed_scope(db_session, admin)
    assert scope.rules is None
    dept, entity = resolve_requested_filters(scope, "Anything", "Anything")
    assert dept == "Anything" and entity == "Anything"


def test_viewer_with_no_grants_is_locked_out(db_session):
    viewer = _make_user(db_session, "xiajie", "viewer")
    scope = get_allowed_scope(db_session, viewer)
    assert scope.rules == []
    rows = get_trend(db_session, months=["2026-01"], scope_rules=scope.rules)
    assert rows == []


def test_entity_wide_grant_sees_every_department_under_it(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "PalmPay")
    scope = get_allowed_scope(db_session, viewer)
    assert scope.rules == [ScopeRule(entity="PalmPay", department1=None)]

    rows = get_trend(db_session, months=["2026-01"], scope_rules=scope.rules)
    # PalmPay: Alice, Bob, Carol (Formal) + Dave (Contract-PP) = 4. Eve (Flexi) excluded.
    assert rows[0]["headcount"] == 4


def test_entity_department_rule_does_not_leak_same_named_department_in_other_entity(db_session):
    """The exact V1.2 bug fix: a rule for entity=Flexi + department=Ops must
    never also expose PalmPay's own Ops department, even though both
    entities have a department literally named 'Ops'."""
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "Flexi", "Ops")
    scope = get_allowed_scope(db_session, viewer)

    departments = list_departments(db_session, scope_rules=scope.rules)
    assert departments == ["Ops"]

    rows = get_trend(db_session, months=["2026-01"], scope_rules=scope.rules)
    # Only Eve (Flexi, Ops) should count - NOT Carol (PalmPay, Ops).
    assert rows[0]["headcount"] == 1


def test_multiple_rules_combine_as_union(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "Flexi", "Ops")  # Eve
    _grant(db_session, viewer, "PalmPay", "Sales")  # Alice, Bob, Dave
    scope = get_allowed_scope(db_session, viewer)
    assert len(scope.rules) == 2

    rows = get_trend(db_session, months=["2026-01"], scope_rules=scope.rules)
    assert rows[0]["headcount"] == 4  # union of both rules


def test_requested_department_outside_every_rule_is_rejected(db_session):
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "PalmPay", "Sales")
    scope = get_allowed_scope(db_session, viewer)

    dept, entity = resolve_requested_filters(scope, "Sales", None)
    assert dept == "Sales"

    with pytest.raises(HTTPException) as exc:
        resolve_requested_filters(scope, "Marketing", None)
    assert exc.value.status_code == 403


def test_requested_entity_outside_every_rule_is_rejected(db_session):
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "PalmPay")
    scope = get_allowed_scope(db_session, viewer)

    with pytest.raises(HTTPException) as exc:
        resolve_requested_filters(scope, None, "Flexi")
    assert exc.value.status_code == 403


def test_revoked_rule_stops_granting_access_but_row_is_kept(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "PalmPay")
    grant = db_session.query(ViewerPermission).filter(ViewerPermission.user_id == viewer.id).one()

    grant.is_active = False
    grant.revoked_by = "admin"
    grant.revoked_time = datetime.utcnow()
    db_session.commit()

    scope = get_allowed_scope(db_session, viewer)
    assert scope.rules == []  # revoked rule no longer counted

    # The row itself, and who/when revoked it, is still in the table.
    still_there = db_session.query(ViewerPermission).filter(ViewerPermission.user_id == viewer.id).one()
    assert still_there.is_active is False
    assert still_there.revoked_by == "admin"


def test_allowed_departments_list_only_shows_granted_departments(db_session):
    _confirm(db_session, "2026-01", build_month1_workbook)
    viewer = _make_user(db_session, "xiajie", "viewer")
    _grant(db_session, viewer, "PalmPay", "Sales")
    scope = get_allowed_scope(db_session, viewer)

    visible = list_departments(db_session, scope_rules=scope.rules)
    assert visible == ["Sales"]


def test_soft_deleted_batch_excluded_from_department_list(db_session):
    batch = _confirm(db_session, "2026-01", build_month1_workbook)
    assert "Sales" in list_departments(db_session)

    delete_confirmed_batch(db_session, batch, operator="tester")
    assert list_departments(db_session) == []
