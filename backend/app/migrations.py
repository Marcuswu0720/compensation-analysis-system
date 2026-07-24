"""Tiny, hand-rolled schema upgrade for existing SQLite databases.

Base.metadata.create_all() only creates tables that don't exist yet - it
never ALTERs a table that's already there to add a new column. This project
has no Alembic set up (overkill for a single-admin internal tool), so when a
model gains a column, add a matching "if missing, ALTER TABLE" check here.
Runs once at startup, after create_all() has had a chance to create any
brand-new tables.
"""

from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.engine import Engine

from .models import MonthlyBonusSnapshot, MonthlyEmployeeSnapshot


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


def run_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    if "upload_batches" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("upload_batches")}
        if "salary_type" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE upload_batches ADD COLUMN salary_type VARCHAR(16) NOT NULL DEFAULT 'base'"))

    if "monthly_employee_snapshot" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("monthly_employee_snapshot")}
        with engine.begin() as conn:
            for col in SALARY_COMPONENT_COLUMNS:
                if col not in columns:
                    conn.execute(text(f"ALTER TABLE monthly_employee_snapshot ADD COLUMN {col} FLOAT"))

    for table in ["monthly_employee_snapshot", "monthly_bonus_snapshot", "supplemental_pay_snapshot", "exit_records"]:
        if table not in inspector.get_table_names():
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "is_deleted" not in columns:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))

    # A soft-deleted row (is_deleted=True) has to be able to coexist with the
    # active row that superseded it for the same (month, staff_id) /
    # (performance_month, staff_id) key. Older databases created before this
    # was a soft-delete system still have that inline UNIQUE constraint baked
    # into the table, which SQLite can't ALTER away - the table has to be
    # rebuilt (this is the standard SQLite pattern for dropping a constraint).
    inspector = inspect(engine)
    _drop_unique_constraint_via_rebuild(engine, inspector, "monthly_employee_snapshot", MonthlyEmployeeSnapshot)
    _drop_unique_constraint_via_rebuild(engine, inspector, "monthly_bonus_snapshot", MonthlyBonusSnapshot)


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
