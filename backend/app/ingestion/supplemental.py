"""Parses a standalone "奖金" or "补发薪资" file: unlike the main monthly
workbook, these don't follow the fixed Formal/Contract/Exits sheet shape -
could be one sheet or several (e.g. one per entity), with whatever columns
happen to be in the source file. So this reads every sheet generically:
any sheet with a recognizable staff-id column and an amount-ish column
counts; sheets without a staff-id column are skipped and reported, not
guessed at.
"""

from dataclasses import dataclass, field

import openpyxl

from .constants import FIELD_ALIASES
from .parser import build_header_map, get, is_summary_row

AMOUNT_ALIASES = ["hr_cost", "bonus_total", "total_gross"]


@dataclass
class SupplementalParseResult:
    rows: list[dict] = field(default_factory=list)  # aggregated per staff_id
    skipped_sheets: list[str] = field(default_factory=list)  # no staff_id or amount column found
    sheet_names: list[str] = field(default_factory=list)


def _find_amount(row: dict, hmap: dict) -> float | None:
    for canonical in AMOUNT_ALIASES:
        val = get(row, hmap, canonical)
        if val not in (None, ""):
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def parse_supplemental_workbook(file_obj) -> SupplementalParseResult:
    wb = openpyxl.load_workbook(file_obj, data_only=True)
    result = SupplementalParseResult(sheet_names=list(wb.sheetnames))
    aggregated: dict[str, dict] = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        raw_headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        hmap, clean_headers = build_header_map(raw_headers)
        sid_col = hmap.get("staff_id")
        if not sid_col:
            result.skipped_sheets.append(f'sheet「{sheet_name}」找不到员工工号列，已跳过')
            continue
        sid_idx = clean_headers.index(sid_col) + 1

        has_amount_col = any(hmap.get(c) for c in AMOUNT_ALIASES)
        if not has_amount_col:
            result.skipped_sheets.append(f'sheet「{sheet_name}」找不到金额列（HR Cost/Total），已跳过')
            continue

        for r in range(2, ws.max_row + 1):
            sid = ws.cell(row=r, column=sid_idx).value
            if sid in (None, "") or is_summary_row(sid):
                continue
            row = {h: ws.cell(row=r, column=c).value for c, h in enumerate(clean_headers, start=1) if h}
            amount = _find_amount(row, hmap)
            if amount is None:
                continue
            sid = str(sid).strip()
            entry = aggregated.setdefault(
                sid,
                {
                    "staff_id": sid,
                    "staff_name": get(row, hmap, "staff_name"),
                    "department1_raw": get(row, hmap, "department1"),
                    "entity_raw": get(row, hmap, "entity"),
                    "amount": 0.0,
                    "source_sheet": sheet_name,
                },
            )
            entry["amount"] += amount

    result.rows = list(aggregated.values())
    wb.close()
    return result
