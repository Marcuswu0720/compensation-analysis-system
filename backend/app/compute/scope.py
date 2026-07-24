"""Shared query-scoping helpers used across compute/*.py.

`apply_scope_filter` lets every compute function accept either a single
department/entity name (the normal case - user picked one in the UI) or a
list of names (a restricted viewer's allowlist - see security.py) with the
same parameter, instead of every call site needing its own branch.
"""

from sqlalchemy.orm import Query


def apply_scope_filter(query: Query, column, value: str | list[str] | None) -> Query:
    if value is None:
        return query
    if isinstance(value, (list, set, tuple)):
        return query.filter(column.in_(value))
    return query.filter(column == value)
