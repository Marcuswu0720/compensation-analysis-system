"""Exercises the actual router functions for PRD V1.2's account-admin
features (account disable, password reset, permission grant/revoke audit
trail) rather than just the underlying models - these are simple enough
FastAPI endpoint functions to call directly without a TestClient."""

import pytest
from fastapi import HTTPException, Response

from app.models import User, ViewerPermission
from app.routers.auth import create_user, grant_permission, list_permissions, login, reset_password, revoke_permission, set_user_active
from app.schemas import CreateUserRequest, GrantPermissionRequest, LoginRequest, ResetPasswordRequest, SetUserActiveRequest
from app.security import hash_password, normalize_username, verify_password


def _make_user(db, username, role="viewer", password="pw12345"):
    u = User(username=username, password_hash=hash_password(password), role=role)
    db.add(u)
    db.commit()
    return u


def test_disabled_account_cannot_log_in(db_session):
    user = _make_user(db_session, "xiajie", password="pw12345")
    user.is_active = False
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username="xiajie", password="pw12345"), Response(), db_session)
    assert exc.value.status_code == 401
    assert "禁用" in exc.value.detail


def test_active_account_logs_in_fine(db_session):
    _make_user(db_session, "xiajie", password="pw12345")
    result = login(LoginRequest(username="xiajie", password="pw12345"), Response(), db_session)
    assert result["username"] == "xiajie"


def test_admin_cannot_disable_own_account(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    with pytest.raises(HTTPException) as exc:
        set_user_active(admin.id, SetUserActiveRequest(is_active=False), db_session, admin)
    assert exc.value.status_code == 400


def test_admin_can_disable_and_reenable_another_account(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    viewer = _make_user(db_session, "xiajie")

    result = set_user_active(viewer.id, SetUserActiveRequest(is_active=False), db_session, admin)
    assert result["is_active"] is False
    db_session.refresh(viewer)
    assert viewer.is_active is False

    set_user_active(viewer.id, SetUserActiveRequest(is_active=True), db_session, admin)
    db_session.refresh(viewer)
    assert viewer.is_active is True


def test_admin_reset_password_changes_hash_and_new_password_works(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    viewer = _make_user(db_session, "xiajie", password="old-password")

    reset_password(viewer.id, ResetPasswordRequest(new_password="new-password"), db_session, admin)
    db_session.refresh(viewer)
    assert verify_password("new-password", viewer.password_hash)
    assert not verify_password("old-password", viewer.password_hash)


def test_grant_permission_records_who_and_when(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    viewer = _make_user(db_session, "xiajie")

    result = grant_permission(
        viewer.id, GrantPermissionRequest(scope_type="entity_department", entity="Flexi", department1="Ops"), db_session, admin
    )
    assert result["entity"] == "Flexi" and result["department1"] == "Ops"

    grants = list_permissions(viewer.id, False, db_session, admin)
    assert len(grants) == 1
    assert grants[0]["granted_by"] == "marcus"
    assert grants[0]["is_active"] is True


def test_entity_department_grant_requires_department(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    viewer = _make_user(db_session, "xiajie")

    with pytest.raises(HTTPException) as exc:
        grant_permission(viewer.id, GrantPermissionRequest(scope_type="entity_department", entity="Flexi"), db_session, admin)
    assert exc.value.status_code == 400


def test_revoke_permission_is_soft_and_recorded(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    viewer = _make_user(db_session, "xiajie")
    granted = grant_permission(viewer.id, GrantPermissionRequest(scope_type="entity", entity="PalmPay"), db_session, admin)

    revoke_permission(viewer.id, granted["id"], db_session, admin)

    active_only = list_permissions(viewer.id, False, db_session, admin)
    assert active_only == []

    with_revoked = list_permissions(viewer.id, True, db_session, admin)
    assert len(with_revoked) == 1
    assert with_revoked[0]["is_active"] is False
    assert with_revoked[0]["revoked_by"] == "marcus"
    assert with_revoked[0]["revoked_time"] is not None

    # The row itself was never deleted.
    row = db_session.query(ViewerPermission).filter(ViewerPermission.id == granted["id"]).one()
    assert row.entity == "PalmPay"


def test_normalize_username_collapses_ime_full_width_space():
    # A full-width space (U+3000) - easy to type by accident while a Chinese
    # input method is active - looks near-identical to a normal space but is
    # a different character, so a naive `==` comparison would treat
    # "SME　Business" and "SME Business" as two different usernames.
    assert normalize_username("SME　Business") == "SME Business"
    assert normalize_username("  SME Business  ") == "SME Business"
    assert normalize_username("SME Business") == "SME Business"


def test_username_with_stray_whitespace_still_logs_in_correctly(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    create_user(CreateUserRequest(username="  SME　Business ", password="pw12345", role="viewer"), db_session, admin)

    # Whatever whitespace variant was typed at creation time, the stored
    # username is normalized - so logging in with the "clean" form works.
    result = login(LoginRequest(username="SME Business", password="pw12345"), Response(), db_session)
    assert result["username"] == "SME Business"


def test_reset_password_trims_accidental_trailing_space(db_session):
    admin = _make_user(db_session, "marcus", role="admin")
    viewer = _make_user(db_session, "xiajie", password="old-password")

    # Simulates an admin accidentally leaving a trailing space in the
    # browser prompt() dialog when resetting a password.
    reset_password(viewer.id, ResetPasswordRequest(new_password="new-password  "), db_session, admin)

    result = login(LoginRequest(username="xiajie", password="new-password"), Response(), db_session)
    assert result["username"] == "xiajie"
