"""app.bootstrap.seed_admin_from_env is what lets a PaaS deploy (Render,
etc.) get its first admin account without an interactive terminal - see
the module docstring. Tests monkeypatch its SessionLocal to the shared
db_session fixture so no real database file is touched."""

from app import bootstrap
from app.models import User
from app.security import verify_password


def _use_test_session(monkeypatch, db_session):
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db_session)


def test_noop_when_env_vars_unset(db_session, monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    _use_test_session(monkeypatch, db_session)

    bootstrap.seed_admin_from_env()
    assert db_session.query(User).count() == 0


def test_noop_when_only_username_set(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "marcus")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    _use_test_session(monkeypatch, db_session)

    bootstrap.seed_admin_from_env()
    assert db_session.query(User).count() == 0


def test_creates_admin_from_env_vars(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "marcus")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-pass")
    _use_test_session(monkeypatch, db_session)

    bootstrap.seed_admin_from_env()

    user = db_session.query(User).filter(User.username == "marcus").one()
    assert user.role == "admin"
    assert user.is_active is True
    assert verify_password("s3cret-pass", user.password_hash)


def test_is_idempotent_and_never_overwrites_existing_account(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "marcus")
    monkeypatch.setenv("ADMIN_PASSWORD", "first-password")
    _use_test_session(monkeypatch, db_session)
    bootstrap.seed_admin_from_env()

    # Re-running with a DIFFERENT password (e.g. a redeploy with the same
    # env vars still set) must not reset an account someone may have since
    # changed the password on manually.
    monkeypatch.setenv("ADMIN_PASSWORD", "second-password")
    bootstrap.seed_admin_from_env()

    assert db_session.query(User).filter(User.username == "marcus").count() == 1
    user = db_session.query(User).filter(User.username == "marcus").one()
    assert verify_password("first-password", user.password_hash)
    assert not verify_password("second-password", user.password_hash)


def test_normalizes_username_like_login_and_create_user_do(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "  marcus  ")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-pass")
    _use_test_session(monkeypatch, db_session)

    bootstrap.seed_admin_from_env()

    assert db_session.query(User).filter(User.username == "marcus").count() == 1
