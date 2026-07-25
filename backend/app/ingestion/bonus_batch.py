"""Parses the standalone "奖金批次" upload (salary_type='bonus').

PRD V1.6 revealed this is NOT the loose staff_id+amount shape backpay uses -
it's a full structured template with 26 fields (department hierarchy,
position, KPI score, PAYE, training fund, bank charges, etc. - see
ingestion/full_fields.py's BONUS_FIELDS). None of these column names have
ever been checked against a real bonus batch file (every field here is
`verified=False` in full_fields.py, a first guess from the PRD's field-
template text alone) - if a real file's headers don't match, the returned
`missing_fields` set is what the caller surfaces as a validation issue,
rather than silently leaving those columns blank with no explanation.

补发批次 (backpay) is unaffected - it keeps using the older, deliberately
loose ingestion/supplemental.py parser, per the user's explicit confirmation
that backpay files really are a simple list, not a full payroll template.
"""

from dataclasses import dataclass, field

import openpyxl

from .constants import FIELD_ALIASES
from .full_fields import BONUS_EXCLUDE_KEYS, BONUS_FIELDS, BONUS_TOP_LEVEL_KEYS, extract_full_detail
from .parser import is_summary_row


@dataclass
class BonusBatchParseResult:
    rows: list[dict] = field(default_factory=list)
    sheet_names: list[str] = field(default_factory=list)
    skipped_sheets: list[str] = field(default_factory=list)
    missing_fields: set[str] = field(default_factory=set)


def parse_bonus_batch_workbook(file_obj) -> BonusBatchParseResult:
    wb = openpyxl.load_workbook(file_obj, data_only=True)
    result = BonusBatchParseResult(sheet_names=list(wb.sheetnames))
    staff_id_aliases = set(FIELD_ALIASES["staff_id"])

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        raw_headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        clean_headers = [str(h).strip() if h else None for h in raw_headers]

        sid_col_idx = next((i for i, h in enumerate(clean_headers) if h in staff_id_aliases), None)
        if sid_col_idx is None:
            result.skipped_sheets.append(f'sheet「{sheet_name}」找不到员工工号列，已跳过')
            continue

        for r in range(2, ws.max_row + 1):
            sid = ws.cell(row=r, column=sid_col_idx + 1).value
            if sid in (None, "") or is_summary_row(sid):
                continue
            row = {h: ws.cell(row=r, column=c).value for c, h in enumerate(clean_headers, start=1) if h}

            top_level, detail_json_fields, missing = extract_full_detail(
                row, BONUS_FIELDS, top_level_keys=BONUS_TOP_LEVEL_KEYS, exclude_keys=BONUS_EXCLUDE_KEYS
            )
            result.missing_fields.update(missing)

            hr_cost_raw = row.get("HR Cost")
            try:
                amount = float(hr_cost_raw) if hr_cost_raw not in (None, "") else 0.0
            except (TypeError, ValueError):
                amount = 0.0

            result.rows.append(
                {
                    "staff_id": str(sid).strip(),
                    "staff_name": row.get("Staff Name"),
                    "department1_raw": row.get("Department 1"),
                    "amount": amount,
                    "source_sheet": sheet_name,
                    "full_detail_json_fields": detail_json_fields,
                    **top_level,
                }
            )

    wb.close()
    return result
