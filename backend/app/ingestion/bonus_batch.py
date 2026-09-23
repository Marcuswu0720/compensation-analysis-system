"""Parses the standalone "奖金批次" upload (salary_type='bonus').

PRD V1.6 revealed this is NOT the loose staff_id+amount shape backpay uses -
it's a full structured template (see ingestion/full_fields.py's
BONUS_FIELDS). PRD V1.8 rebuilt the field list from an authoritative
mapping file the user provided, correcting several V1.6 guesses that had
never been checked against a real bonus batch file - notably, the template
DOES have its own Entity and Employment Type columns (V1.6 assumed neither
existed).

补发批次 (backpay) is unaffected - it keeps using the older, deliberately
loose ingestion/supplemental.py parser, per the user's explicit confirmation
that backpay files really are a simple list, not a full payroll template.

Every sheet in the workbook is tried (no sheet-name pattern gates which ones
count, unlike parser.py's base-batch role matching) - a sheet is only
skipped for lacking a recognizable staff_id column. A sheet named after a
bare entity (e.g. "PP", "Blooms", "Flexi", "Jupiter") gets that entity as
the default for any row with no Entity value of its own, via
ingestion/parser.py's entity_hint_from_sheet_name() (same idea as
match_base_sheet_role()/default_entity_for_suffix() for Formal/Contract
sheets, but bare-name-only since there's no role word for a bonus sheet to
anchor a suffix on).
"""

from dataclasses import dataclass, field

import openpyxl

from .full_fields import BONUS_EXCLUDE_KEYS, BONUS_FIELDS, BONUS_TOP_LEVEL_KEYS, check_field_mapping, extract_full_detail
from .header_match import build_header_index, find_alias
from .parser import entity_hint_from_sheet_name, is_summary_row

_SPEC_BY_KEY = {s.key: s for s in BONUS_FIELDS}


@dataclass
class FieldMappingReport:
    sheet_name: str
    total: int
    matched: int
    missing: list[dict]


@dataclass
class BonusBatchParseResult:
    rows: list[dict] = field(default_factory=list)
    sheet_names: list[str] = field(default_factory=list)
    skipped_sheets: list[str] = field(default_factory=list)
    field_mapping_reports: list[FieldMappingReport] = field(default_factory=list)


def parse_bonus_batch_workbook(file_obj, known_entities: frozenset[str] = frozenset()) -> BonusBatchParseResult:
    """`known_entities`: every entity name already on record in the system
    (see ingestion/parser.py's entity_hint_from_sheet_name()) - the caller
    (loader.py) supplies this from the DB, keeping this function itself
    free of any DB dependency, same as every other pure workbook parser in
    this package."""
    wb = openpyxl.load_workbook(file_obj, data_only=True)
    result = BonusBatchParseResult(sheet_names=list(wb.sheetnames))

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        raw_headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        clean_headers = [str(h).strip() if h else None for h in raw_headers]
        header_index = build_header_index(clean_headers)

        staff_id_col = find_alias(header_index, _SPEC_BY_KEY["staff_id"].source_aliases)
        if staff_id_col is None:
            result.skipped_sheets.append(f'sheet「{sheet_name}」找不到员工工号列，已跳过')
            continue
        sid_col_idx = clean_headers.index(staff_id_col)

        staff_name_col = find_alias(header_index, _SPEC_BY_KEY["staff_name"].source_aliases)
        department1_col = find_alias(header_index, _SPEC_BY_KEY["department1"].source_aliases)
        entity_col = find_alias(header_index, _SPEC_BY_KEY["entity"].source_aliases)
        employment_type_col = find_alias(header_index, _SPEC_BY_KEY["employment_type"].source_aliases)
        hr_cost_col = find_alias(header_index, _SPEC_BY_KEY["hr_cost"].source_aliases)

        # A sheet named after a bare entity (e.g. "Blooms", "PP") doesn't need
        # its own Entity column - the sheet name supplies the default for any
        # row whose own Entity cell is blank (see loader.py's
        # _stage_bonus_batch()). Only kicks in when there's genuinely no
        # Entity column at all; a descriptively-named sheet like "Feb
        # Bonus-PP" still relies purely on its own Entity column / the
        # matched base employee, same as before.
        sheet_entity_hint = entity_hint_from_sheet_name(sheet_name, known_entities) if entity_col is None else None
        satisfied_elsewhere = frozenset({"entity"}) if sheet_entity_hint else frozenset()
        total, matched, missing = check_field_mapping(header_index, BONUS_FIELDS, satisfied_elsewhere)
        result.field_mapping_reports.append(FieldMappingReport(sheet_name=sheet_name, total=total, matched=matched, missing=missing))

        for r in range(2, ws.max_row + 1):
            sid = ws.cell(row=r, column=sid_col_idx + 1).value
            if sid in (None, "") or is_summary_row(sid):
                continue
            row = {h: ws.cell(row=r, column=c).value for c, h in enumerate(clean_headers, start=1) if h}

            top_level, detail_json_fields, _ = extract_full_detail(
                row, BONUS_FIELDS, top_level_keys=BONUS_TOP_LEVEL_KEYS, exclude_keys=BONUS_EXCLUDE_KEYS, header_index=header_index
            )

            hr_cost_raw = row.get(hr_cost_col) if hr_cost_col else None
            try:
                amount = float(hr_cost_raw) if hr_cost_raw not in (None, "") else 0.0
            except (TypeError, ValueError):
                amount = 0.0

            result.rows.append(
                {
                    "staff_id": str(sid).strip(),
                    "staff_name": row.get(staff_name_col) if staff_name_col else None,
                    "department1_raw": row.get(department1_col) if department1_col else None,
                    "entity_raw": (row.get(entity_col) if entity_col else None) or sheet_entity_hint,
                    "employment_type": row.get(employment_type_col) if employment_type_col else None,
                    "amount": amount,
                    "source_sheet": sheet_name,
                    "full_detail_json_fields": detail_json_fields,
                    **top_level,
                }
            )

    wb.close()
    return result
