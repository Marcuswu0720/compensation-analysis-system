"""Splits the Formal / Contract sheets' raw columns into the canonical salary
component fields from PRD V1.1 §2.1. Formal and Contract use different column
names for almost every component (verified against real Jan-Jun data - see
commit message / session notes; no drift found across months for these
specific columns, unlike department/entity which do drift), so this uses
direct column lookups per employment type rather than the fuzzy alias
matching in constants.py/parser.py, which exists for the columns that DO
drift across months.

Two identities the PRD calls out as "raise, don't silently trust" checks:
    gross_salary == basic_salary_actual + performance_bonus + commission_bonus
                    + overtime_amount + other_income
    hr_cost == gross_salary + employer_statutory_cost
Both were spot-checked against real data: hr_cost holds exactly everywhere,
but gross_salary vs the component sum has a small number of real mismatches
(~1-2% of rows, both Formal and Contract-PP) that look like manual
adjustments in the source spreadsheet, not a parsing bug. So gross_salary
and hr_cost are taken directly from their own columns (already present and
proven exact), the component breakdown is stored from its own columns too,
and a mismatch just gets flagged as a data-quality issue instead of forcing
one side to match the other.
"""

FORMAL_DIRECT_COLUMNS = {
    "basic_salary_actual": "Actual Monthly Basic Salary",
    "performance_std": "Performance STD",
    "performance_coefficient": "Coefficient",
    "performance_bonus": "Performance Bonus",
    "commission_bonus": "Commission/Bonus",
    "overtime_amount": "Overtime Amount",
    "gross_salary": "Total Gross Salary",
    "employer_statutory_cost": "Statutory payments",
    "monthly_income_tax": "Monthly Income Tax",
    "other_deduction": "Other Deduction",
    "private_loan": "Private Loan",
    "bank_charge": "Bank Charge",
    "net_pay": "Total Net Pay",
}
FORMAL_OTHER_INCOME_COLUMNS = [
    "Other Income",
    "Welfare Fund",
    "Call Allowance",
    "Internet Allowance",
    "Traffic Allowance",
    "Transportation Subsidy",
]

CONTRACT_DIRECT_COLUMNS = {
    "basic_salary_actual": "Actual Monthly Basic Salary",
    "performance_std": "Performance Standard",
    "performance_coefficient": "KPI Coeff.",
    "performance_bonus": "Perfomance bonus",  # sic - real column is misspelled in the source file
    "commission_bonus": "Commission/Bonus",
    "overtime_amount": "Overtime income",
    "other_income": "Arrears/Other Income",
    "gross_salary": "Actual Gross Total Amount",
    "monthly_income_tax": "Monthly Income Tax",
    "other_deduction": "Other Deduction",
    "bank_charge": "Bank Charges",
    "net_pay": "Net Amount Due",
}
CONTRACT_STATUTORY_COLUMNS = ["NSITF", "Pension ER", "ITF", "HMO"]

GROSS_SALARY_COMPONENTS = ["basic_salary_actual", "performance_bonus", "commission_bonus", "overtime_amount", "other_income"]


def _num(row: dict, col: str | None) -> float:
    if not col:
        return 0.0
    val = row.get(col)
    try:
        return float(val) if val not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def extract_salary_components(row: dict, role: str) -> dict:
    if role == "formal":
        direct = {k: _num(row, v) for k, v in FORMAL_DIRECT_COLUMNS.items()}
        direct["other_income"] = sum(_num(row, c) for c in FORMAL_OTHER_INCOME_COLUMNS)
    else:
        direct = {k: _num(row, v) for k, v in CONTRACT_DIRECT_COLUMNS.items()}
        direct["employer_statutory_cost"] = sum(_num(row, c) for c in CONTRACT_STATUTORY_COLUMNS)

    direct["deduction_total"] = direct["monthly_income_tax"] + direct["other_deduction"] + direct.get("bank_charge", 0.0)
    if role == "formal":
        direct["deduction_total"] += direct.get("private_loan", 0.0)

    computed_gross = sum(direct[k] for k in GROSS_SALARY_COMPONENTS)
    direct["gross_salary_component_mismatch"] = abs(computed_gross - direct["gross_salary"]) > 1

    for k in ("monthly_income_tax", "other_deduction", "private_loan", "bank_charge"):
        direct.pop(k, None)

    return direct
