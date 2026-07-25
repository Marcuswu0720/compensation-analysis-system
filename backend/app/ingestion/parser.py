"""Parses one month's raw payroll workbook into per-sheet-role rows.

This is a direct, minimally-modified port of the validated parse_all_months.py
reference script (see PRD §8), adapted to parse a single in-memory workbook
instead of a fixed multi-month path list, and to surface unmatched sheets so
the upload flow can flag them instead of silently dropping data.
"""

import re
from dataclasses import dataclass, field

import openpyxl

from .constants import FIELD_ALIASES, SHEET_DEFAULT_ENTITY, SHEET_PATTERNS, SHEET_ROLE_ORDER, SUMMARY_ROW_MARKERS
from .header_match import build_header_index, find_alias


@dataclass
class SheetParseResult:
    rows: list[dict]
    header_map: dict[str, str]
    sheet_name: str | None


@dataclass
class WorkbookParseResult:
    by_role: dict[str, SheetParseResult]
    unmatched_sheets: list[str] = field(default_factory=list)
    missing_field_issues: list[str] = field(default_factory=list)


def find_sheet(sheetnames: list[str], patterns: list[str]) -> str | None:
    for name in sheetnames:
        for p in patterns:
            if re.search(p, name, re.IGNORECASE):
                return name
    return None


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
    matched_names: set[str] = set()
    missing_field_issues: list[str] = []

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

        if role in ("formal", "contract_pp", "contract_flexi"):
            for must_have in ["staff_id", "department1", "hr_cost"]:
                if must_have not in hmap:
                    missing_field_issues.append(f'sheet「{sheet_name}」缺少关键字段映射: {must_have}')
            if "entity" not in hmap and role not in SHEET_DEFAULT_ENTITY:
                missing_field_issues.append(f'sheet「{sheet_name}」缺少关键字段映射: entity')

    unmatched_sheets = [s for s in sheetnames if s not in matched_names]
    wb.close()
    return WorkbookParseResult(by_role=by_role, unmatched_sheets=unmatched_sheets, missing_field_issues=missing_field_issues)
