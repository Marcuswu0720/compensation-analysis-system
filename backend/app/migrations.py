"""Tiny, hand-rolled schema upgrade for existing SQLite databases.

Base.metadata.create_all() only creates tables that don't exist yet - it
never ALTERs a table that's already there to add a new column. This project
has no Alembic set up (overkill for a single-admin internal tool), so when a
model gains a column, add a matching "if missing, ALTER TABLE" check here.
Runs once at startup, after create_all() has had a chance to create any
brand-new tables.
"""

from datetime import datetime

from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.engine import Engine

from .models import MonthlyBonusSnapshot, MonthlyEmployeeSnapshot, ViewerPermission
from .security import normalize_username


SALARY_COMPONENT_COLUMNS = [
    "basic_salary_actual",
    "performance_std",
    "performance_coefficient",
    "performance_bonus",
    "commission_bonus",
    "overtime_amount",
    "other_income",
    "gross_salary",
    "employer_statutory_cost",
    "deduction_total",
    "net_pay",
]

# PRD V1.6 §2.1: descriptive fields the original model never captured.
FULL_DETAIL_DESCRIPTIVE_COLUMNS = {
    "department2": "VARCHAR(255)",
    "department3": "VARCHAR(255)",
    "position": "VARCHAR(255)",
    "reporting_line": "VARCHAR(255)",
    "state": "VARCHAR(64)",
    "work_station": "VARCHAR(255)",
    "joining_date": "VARCHAR(32)",
    "full_detail_json": "TEXT",
}

# Same idea, but supplemental_pay_snapshot also needs job_grade/cost_center/
# work_country/resign_date on top of the columns above (see models.py's
# SupplementalPaySnapshot docstring - only populated for pay_type='bonus').
SUPPLEMENTAL_FULL_DETAIL_COLUMNS = {
    **FULL_DETAIL_DESCRIPTIVE_COLUMNS,
    "job_grade": "VARCHAR(32)",
    "cost_center": "VARCHAR(255)",
    "work_country": "VARCHAR(64)",
    "resign_date": "VARCHAR(32)",
}


def run_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    if "upload_batches" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("upload_batches")}
        if "salary_type" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE upload_batches ADD COLUMN salary_type VARCHAR(16) NOT NULL DEFAULT 'base'"))

    if "users" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("users")}
        if "is_active" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        _normalize_existing_usernames(engine)

    if "monthly_employee_snapshot" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("monthly_employee_snapshot")}
        with engine.begin() as conn:
            for col in SALARY_COMPONENT_COLUMNS:
                if col not in columns:
                    conn.execute(text(f"ALTER TABLE monthly_employee_snapshot ADD COLUMN {col} FLOAT"))
            for col, sql_type in FULL_DETAIL_DESCRIPTIVE_COLUMNS.items():
                if col not in columns:
                    conn.execute(text(f"ALTER TABLE monthly_employee_snapshot ADD COLUMN {col} {sql_type}"))

    if "supplemental_pay_snapshot" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("supplemental_pay_snapshot")}
        with engine.begin() as conn:
            for col, sql_type in SUPPLEMENTAL_FULL_DETAIL_COLUMNS.items():
                if col not in columns:
                    conn.execute(text(f"ALTER TABLE supplemental_pay_snapshot ADD COLUMN {col} {sql_type}"))

    for table in ["monthly_employee_snapshot", "monthly_bonus_snapshot", "supplemental_pay_snapshot", "exit_records"]:
        if table not in inspector.get_table_names():
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "is_deleted" not in columns:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))

    if "download_log" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("download_log")}
        if "salary_types" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE download_log ADD COLUMN salary_types VARCHAR(64)"))

    # A soft-deleted row (is_deleted=True) has to be able to coexist with the
    # active row that superseded it for the same (month, staff_id) /
    # (performance_month, staff_id) key. Older databases created before this
    # was a soft-delete system still have that inline UNIQUE constraint baked
    # into the table, which SQLite can't ALTER away - the table has to be
    # rebuilt (this is the standard SQLite pattern for dropping a constraint).
    inspector = inspect(engine)
    _drop_unique_constraint_via_rebuild(engine, inspector, "monthly_employee_snapshot", MonthlyEmployeeSnapshot)
    _drop_unique_constraint_via_rebuild(engine, inspector, "monthly_bonus_snapshot", MonthlyBonusSnapshot)

    _migrate_viewer_permissions_to_entity_rules(engine, inspector)


def _normalize_existing_usernames(engine: Engine) -> None:
    """Retroactively fixes usernames created before login/create_user started
    calling normalize_username() - most importantly a stray full-width IME
    space (visually near-identical to a normal space, but a different
    character), which made a correctly-typed login permanently fail with
    "用户名或密码错误" for an account whose name looks fine at a glance.
    Skips a rename if it would collide with another existing username -
    that case needs a human to pick a name, not a silent auto-merge."""
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, username FROM users")).fetchall()
        existing = {r.username for r in rows}
        for row in rows:
            normalized = normalize_username(row.username)
            if normalized != row.username and normalized not in existing:
                conn.execute(text("UPDATE users SET username = :new WHERE id = :id"), {"new": normalized, "id": row.id})
                existing.add(normalized)


def _drop_unique_constraint_via_rebuild(engine: Engine, inspector, table_name: str, model) -> None:
    if table_name not in inspector.get_table_names():
        return
    if not inspector.get_unique_constraints(table_name):
        return  # already migrated, or never had one

    temp_name = f"{table_name}__rebuild_tmp"
    columns = []
    for c in model.__table__.columns:
        copy = c.copy()
        if not copy.primary_key:
            # This rebuild only exists to drop the old UNIQUE constraint - it
            # must not fail because a pre-existing row has a NULL in a column
            # the current model happens to mark NOT NULL (e.g. a nullable
            # column that later gained a Python-side default and is no
            # longer typed Optional).
            copy.nullable = True
        columns.append(copy)
    temp_table = Table(temp_name, MetaData(), *columns)
    col_names = ", ".join(c.name for c in model.__table__.columns)

    with engine.begin() as conn:
        temp_table.create(conn)
        conn.execute(text(f"INSERT INTO {temp_name} ({col_names}) SELECT {col_names} FROM {table_name}"))
        conn.execute(text(f"DROP TABLE {table_name}"))
        conn.execute(text(f"ALTER TABLE {temp_name} RENAME TO {table_name}"))


def _migrate_viewer_permissions_to_entity_rules(engine: Engine, inspector) -> None:
    """PRD V1.2 §1: viewer_permissions moves from independent department/entity
    axes (scope_type + scope_value) to self-contained rules (scope_type +
    entity [+ department1]) - see models.ViewerPermission's docstring for why
    the old shape was a leak risk. create_all() already gives a brand-new
    database the new schema directly, so this only fires for a database that
    still has the old columns.

    Old scope_type='entity' rows map 1:1 onto the new shape (entity=
    scope_value, department1=NULL) and are carried over. Old scope_type=
    'department' rows have no entity attached at all, so there is no safe way
    to re-express them as an (entity[, department]) rule - that ambiguity is
    exactly the gap V1.2 closes - so those grants are dropped rather than
    guessed at; an admin needs to re-grant them under the new, more precise
    model via the 用户权限 page.
    """
    if "viewer_permissions" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("viewer_permissions")}
    if "entity" in columns and "granted_time" in columns:
        return  # already on the new schema

    with engine.begin() as conn:
        old_rows = conn.execute(text("SELECT user_id, scope_type, scope_value FROM viewer_permissions")).fetchall()
        conn.execute(text("DROP TABLE viewer_permissions"))

    ViewerPermission.__table__.create(engine)

    carried_over = [r for r in old_rows if r.scope_type == "entity"]
    if carried_over:
        now = datetime.utcnow().isoformat(sep=" ")
        with engine.begin() as conn:
            for row in carried_over:
                conn.execute(
                    text(
                        "INSERT INTO viewer_permissions "
                        "(user_id, scope_type, entity, department1, is_active, granted_by, granted_time) "
                        "VALUES (:user_id, 'entity', :entity, NULL, 1, :granted_by, :granted_time)"
                    ),
                    {"user_id": row.user_id, "entity": row.scope_value, "granted_by": "migration_v1.2", "granted_time": now},
                )
