"""Shared query-scoping helpers used across compute/*.py.

`apply_scope_filter` lets every compute function accept either a single
department/entity name (the normal case - user picked one in the UI) or a
list of names, with the same parameter, instead of every call site needing
its own branch.

`apply_permission_scope` is the separate, security-relevant filter (PRD
V1.2 §1): a viewer's grants are a list of self-contained rules - either
"this whole entity" or "this exact (entity, department) pair" - and the
final permission is the UNION of those rules. It is applied independently
of (and in addition to) whatever single department/entity the caller
explicitly asked to view via apply_scope_filter, so a restricted viewer can
never construct a request that reads outside their granted rules.
"""

from dataclasses import dataclass

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Query


def apply_scope_filter(query: Query, column, value: str | list[str] | None) -> Query:
    if value is None:
        return query
    if isinstance(value, (list, set, tuple)):
        return query.filter(column.in_(value))
    return query.filter(column == value)


@dataclass(frozen=True)
class ScopeRule:
    entity: str
    department1: str | None  # None = every department under this entity


def apply_permission_scope(query: Query, entity_column, department_column, rules: list[ScopeRule] | None) -> Query:
    """rules=None means unrestricted (admin). rules=[] means zero grants -
    matches nothing, rather than everything."""
    if rules is None:
        return query
    if not rules:
        return query.filter(false())
    conditions = [
        (entity_column == r.entity) if r.department1 is None else and_(entity_column == r.entity, department_column == r.department1)
        for r in rules
    ]
    return query.filter(or_(*conditions))
