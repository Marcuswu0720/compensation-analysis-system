"""Tiny, hand-rolled schema upgrade for existing SQLite databases.

Base.metadata.create_all() only creates tables that don't exist yet - it
never ALTERs a table that's already there to add a new column. This project
has no Alembic set up (overkill for a single-admin internal tool), so when a
model gains a column, add a matching "if missing, ALTER TABLE" check here.
Runs once at startup, after create_all() has had a chance to create any
brand-new tables.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def run_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    if "upload_batches" not in inspector.get_table_names():
        return  # fresh DB, create_all() already built it with every column

    columns = {c["name"] for c in inspector.get_columns("upload_batches")}
    if "salary_type" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE upload_batches ADD COLUMN salary_type VARCHAR(16) NOT NULL DEFAULT 'base'"))
