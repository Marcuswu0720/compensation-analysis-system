"""Parses one month's raw payroll workbook into per-sheet-role rows.

This is a direct, minimally-modified port of the validated parse_all_months.py
reference script (see PRD §8), adapted to parse a single in-memory workbook
instead of a fixed multi-month path list, and to surface unmatched sheets so
the upload flow can flag them instead of silently dropping data.
"""

import re
from dataclasses import dataclass, field

import openpyxl

from .constants import ENTITY_ALIASES, FIELD_ALIASES, SHEET_DEFAULT_ENTITY, SHEET_PATTERNS, SHEET_ROLE_ORDER, SUMMARY_ROW_MARKERS
from .header_match import build_header_index, find_alias


@dataclass
class SheetParseResult:
    rows: list[dict]
    header_map: dict[str, str]
    sheet_name: str | None


@dataclass
class WorkbookParseResult:
    by_role: dict[str, SheetParseResult]
    # Formal/Contract base-salary sheets - a list per role (not one
    # SheetParseResult like by_role's fixed roles) because a single workbook
    # can carry one such sheet per entity (Formal, Formal-Blooms,
    # Formal-Jupiter, ...) - see match_base_sheet_role().
    base_sheets: dict[str, list[SheetParseResult]] = field(default_factory=lambda: {"formal": [], "contract": []})
    unmatched_sheets: list[str] = field(default_factory=list)
    missing_field_issues: list[str] = field(default_factory=list)


def find_sheet(sheetnames: list[str], patterns: list[str]) -> str | None:
    for name in sheetnames:
        for p in patterns:
            if re.search(p, name, re.IGNORECASE):
                return name
    return None


# Formal/Contract base-salary sheets are entity-scoped by an optional suffix
# - "Formal", "Contract - PP", "Contract-Flexi", "PP-Contract",
# "Formal-Blooms", "Contract_Jupiter" - real files aren't consistent about
# whether the entity name comes before or after the role word, or what
# separates them (nothing, a space, a dash, an underscore). These three
# patterns replace what used to be a fixed, hardcoded list of per-entity role
# names (contract_pp/contract_flexi -> PalmPay/Flexi only) - a real file with
# a third entity had no role to match at all before this. Order matters:
# bare match first, since "Formal"/"Contract" alone would also technically
# satisfy the suffix patterns with an empty suffix.
_BARE_ROLE_RE = re.compile(r"^(formal|contract)$", re.IGNORECASE)
_ROLE_THEN_SUFFIX_RE = re.compile(r"^(formal|contract)[\s\-_]+(.+)$", re.IGNORECASE)
_SUFFIX_THEN_ROLE_RE = re.compile(r"^(.+?)[\s\-_]+(formal|contract)$", re.IGNORECASE)


def match_base_sheet_role(sheet_name: str) -> tuple[str, str | None] | None:
    """Returns (role, entity_suffix) for a Formal/Contract sheet name, role
    always lowercase 'formal'/'contract', entity_suffix None for a bare
    sheet name (that sheet must have its own Entity column - see
    default_entity_for_suffix()). Returns None if `sheet_name` isn't a
    Formal/Contract sheet at all (exits/bonus sheets, or anything else)."""
    name = sheet_name.strip()
    if _BARE_ROLE_RE.match(name):
        return name.lower(), None
    m = _ROLE_THEN_SUFFIX_RE.match(name)
    if m:
        return m.group(1).lower(), m.group(2).strip()
    m = _SUFFIX_THEN_ROLE_RE.match(name)
    if m:
        return m.group(2).lower(), m.group(1).strip()
    return None


def default_entity_for_suffix(suffix: str) -> str:
    """Canonicalizes a Formal/Contract sheet's entity suffix into a default
    Entity value for rows that have no Entity column of their own -
    ENTITY_ALIASES first (e.g. "PP" -> "PalmPay"), otherwise the suffix
    as-is if it's already got some capitalization (e.g. "Blooms"), or
    title-cased if it's all lowercase (e.g. a sheet literally named
    "formal-blooms")."""
    canonical = ENTITY_ALIASES.get(suffix.lower())
    if canonical:
        return canonical
    return suffix if any(c.isupper() for c in suffix) else suffix.title()


def is_summary_row(sid) -> bool:
    cleaned = str(sid).strip().lower().rstrip(".").strip()
    return cleaned in SUMMARY_ROW_MARKERS


def build_header_map(raw_headers: list) -> tuple[dict[str, str], list[str | None]]:
    """PRD V1.8 §1: matches FIELD_ALIASES against the sheet's actual headers
    with case/whitespace-normalized comparison (see header_match.py), not
    exact string equality - a header spelled "Staff name" or "Joining Date "
    (trailing space) is still recognized without needing a new alias for
    every casing/whitespace variant that shows up in a new month's file."""
    clean = [str(h).strip() if h else None for h in raw_headers]
    index = build_header_index(clean)
    result = {}
    for canonical, aliases in FIELD_ALIASES.items():
        raw = find_alias(index, aliases)
        if raw is not None:
            result[canonical] = raw
    return result, clean


def parse_sheet(ws) -> tuple[list[dict], dict[str, str]]:
    raw_headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    hmap, clean_headers = build_header_map(raw_headers)
    sid_col = hmap.get("staff_id")
    rows: list[dict] = []
    if not sid_col:
        return rows, hmap
    sid_idx = clean_headers.index(sid_col) + 1
    for r in range(2, ws.max_row + 1):
        sid = ws.cell(row=r, column=sid_idx).value
        if sid in (None, "") or is_summary_row(sid):
            continue
        row = {}
        for c, h in enumerate(clean_headers, start=1):
            if h:
                row[h] = ws.cell(row=r, column=c).value
        rows.append(row)
    return rows, hmap


def get(row: dict, hmap: dict, canonical: str, default=None):
    if canonical == "entity" and "entity" not in hmap and "__default_entity__" in row:
        return row["__default_entity__"]
    col = hmap.get(canonical)
    if not col:
        return default
    return row.get(col, default)


def parse_workbook(file_obj_or_path) -> WorkbookParseResult:
    wb = openpyxl.load_workbook(file_obj_or_path, data_only=True)
    sheetnames = wb.sheetnames
    by_role: dict[str, SheetParseResult] = {}
    base_sheets: dict[str, list[SheetParseResult]] = {"formal": [], "contract": []}
    matched_names: set[str] = set()
    missing_field_issues: list[str] = []

    # Formal/Contract base-salary sheets: any number of them, one per entity
    # (see match_base_sheet_role()'s docstring) - checked before the fixed
    # exits/bonus roles below since there's no overlap risk (those patterns
    # never contain the words "formal"/"contract").
    for sheet_name in sheetnames:
        matched = match_base_sheet_role(sheet_name)
        if matched is None:
            continue
        role, suffix = matched
        matched_names.add(sheet_name)
        ws = wb[sheet_name]
        rows, hmap = parse_sheet(ws)
        entity_hint = default_entity_for_suffix(suffix) if suffix else None
        if "entity" not in hmap and entity_hint:
            for row in rows:
                row["__default_entity__"] = entity_hint
        base_sheets[role].append(SheetParseResult(rows=rows, header_map=hmap, sheet_name=sheet_name))

        for must_have in ["staff_id", "department1", "hr_cost"]:
            if must_have not in hmap:
                missing_field_issues.append(f'sheet「{sheet_name}」缺少关键字段映射: {must_have}')
        if "entity" not in hmap and not entity_hint:
            missing_field_issues.append(f'sheet「{sheet_name}」缺少关键字段映射: entity')

    for role in SHEET_ROLE_ORDER:
        patterns = SHEET_PATTERNS[role]
        sheet_name = find_sheet(sheetnames, patterns)
        if not sheet_name:
            by_role[role] = SheetParseResult(rows=[], header_map={}, sheet_name=None)
            continue
        matched_names.add(sheet_name)
        ws = wb[sheet_name]
        rows, hmap = parse_sheet(ws)
        if "entity" not in hmap and role in SHEET_DEFAULT_ENTITY:
            for row in rows:
                row["__default_entity__"] = SHEET_DEFAULT_ENTITY[role]
        by_role[role] = SheetParseResult(rows=rows, header_map=hmap, sheet_name=sheet_name)

    unmatched_sheets = [s for s in sheetnames if s not in matched_names]
    wb.close()
    return WorkbookParseResult(by_role=by_role, base_sheets=base_sheets, unmatched_sheets=unmatched_sheets, missing_field_issues=missing_field_issues)
