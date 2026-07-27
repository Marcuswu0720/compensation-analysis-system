"""Field/sheet mapping rules, validated against 2026-01~06 real payroll workbooks.

Kept in one place because these are exactly the rules the PRD calls out as
"will keep changing between months" — new aliases/patterns should only ever
be added here, never hardcoded deeper in the parsing code.

PRD V1.8 §1: matching against these aliases is case/whitespace-normalized
(see header_match.py) before comparing, so this list only needs ONE entry
per genuinely different wording - "Job Grade" also matches "Job grade" or
"Job Grade " automatically now, so those used to need a second alias here
just for the casing/whitespace difference; they don't anymore.
"""

FIELD_ALIASES = {
    "staff_id": ["Staff ID", "ID", "Staff Number", "Staff ID No"],
    "entity": ["Entity", "Company/签约主体", "Company"],
    "employment_type": ["Employment Type", "Employee Type/员工类型"],
    "staff_name": ["Staff Name", "Name"],
    "department1": ["Department 1"],
    "job_grade": ["Job Grade"],
    "resign_date": ["Resign Date"],
    "exit_date": ["Exit Date"],
    "hr_cost": ["HR Cost"],
    "total_gross": ["Total Gross Salary", "Actual Gross Total Amount"],
    "reason_for_leaving": ["New Reason for Leaving", "Reason for Leaving"],
    "exit_type": ["Exit Type"],
    "attrition_type": ["Attrition"],
    "exit_date_record": ["Exit Date \n(YYYY/MM/DD)", "Exit Date"],
    "performance_bonus": ["Performance Bonus"],
    "commission": ["Commission"],
    "other_income": ["Other", "Other Income"],
    "deduction": ["Deduction"],
    "bonus_total": ["HR Cost", "Total"],
}

# When a sheet has no Entity column of its own, the sheet TYPE implies the entity.
SHEET_DEFAULT_ENTITY = {
    "contract_pp": "PalmPay",
    "contract_flexi": "Flexi",
    "bonus_pp": "PalmPay",
    "bonus_flexi": "Flexi",
}

# Known shorthand/typo forms for entity names that are NOT just a casing
# difference (so the generic case-insensitive dedup in normalize.py can't
# catch them on its own) - e.g. the Contract-PP sheet's own Entity column
# sometimes literally says "PP" rather than "PalmPay". Entities are a small,
# stable closed set (unlike departments), so a short seed list here is safe.
ENTITY_ALIASES = {
    "pp": "PalmPay",
}

# Regex patterns per sheet "role". Bonus patterns must be bidirectional: some
# months name it "PP-Jan bonus", others "April Bonus-PP" (label after entity).
SHEET_PATTERNS = {
    "formal": [r"^Formal$"],
    "contract_pp": [r"Contract.*PP", r"PP.*Contract"],
    "contract_flexi": [r"Contract.*Flexi", r"Flexi.*Contract"],
    "exits": [r"Exit", r"离职"],
    "bonus_pp": [r"PP.*[Bb]onus", r"[Bb]onus.*PP"],
    "bonus_flexi": [r"Flexi.*[Bb]onus", r"[Bb]onus.*Flexi"],
}

# Order matters: a sheet is claimed by the first role whose pattern matches it,
# so more specific bonus/contract patterns are checked before anything looser.
SHEET_ROLE_ORDER = ["formal", "contract_pp", "contract_flexi", "exits", "bonus_pp", "bonus_flexi"]

EMPLOYEE_SHEET_KEYS = ["formal", "contract_pp", "contract_flexi"]
BONUS_SHEET_KEYS = ["bonus_pp", "bonus_flexi"]

# Trailing summary/subtotal rows at the bottom of a sheet re-use the staff_id
# column to hold a row label ("TOTAL", "HR Cost", etc.) instead of a real
# staff ID - is_summary_row() checks the cell against this set (exact match,
# not substring) to skip them. A 2026-07 Contract-Flexi file's own summary
# block used "Gross Salary"/"Bonus & Arrears"/"Net Pay"/"Total Amount" -
# close to, but not exact matches for, "gross"/"total"/"net amount" already
# here - and slipped through as 4 phantom zero-cost "employees" (their other
# salary-component cells were blank, so no dollar total was affected, but
# headcount_total came out 4 too high). Added as their own exact entries
# rather than switching to substring matching, since a real staff ID could
# plausibly contain "total" as a substring in some future file.
SUMMARY_ROW_MARKERS = {
    "total",
    "total amount",
    "item",
    "staff number",
    "performance bonus",
    "commission",
    "other",
    "gross",
    "gross salary",
    "bonus & arrears",
    "paye",
    "hr cost",
    "net amount",
    "net pay",
    "deduction",
}

# Bonus sheet's month label ("Dec bonus") -> offset from the file's own month.
# Company rule: bonus sheet always carries the PREVIOUS natural month's
# performance bonus, paid out in the current month's payroll file.
BONUS_MONTH_OFFSET = -1
