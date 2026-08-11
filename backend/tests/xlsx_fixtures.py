"""Builds small synthetic payroll workbooks (no real employee data) that
exercise the same edge cases the PRD documents from real files: sheet-name
drift, field-alias drift, casing variants, summary rows, an exit-sheet that
sometimes doesn't exist. Used only by tests/test_ingestion.py.
"""

import io

import openpyxl


def _sheet(wb, name, headers, rows):
    ws = wb.create_sheet(name)
    ws.append(headers)
    for row in rows:
        ws.append(row)
    return ws


def build_month1_workbook() -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    _sheet(
        wb,
        "Formal",
        ["Staff ID", "Staff Name", "Entity", "Department 1", "Job Grade", "HR Cost", "Resign Date"],
        [
            ["E001", "Alice", "PalmPay", "Sales", "P1", 1000, None],
            ["E002", "Bob", "PalmPay", "sales", "P2", 1200, None],
            ["E003", "Carol", "PalmPay", "Ops", "P1", 900, "2026-01-20"],
        ],
    )
    _sheet(
        wb,
        "Contract - PP",
        ["Staff ID", "Staff Name", "Department 1", "Job Grade", "HR Cost", "Exit Date"],
        [["E004", "Dave", "Sales", "C1", 500, "Active"]],
    )
    _sheet(
        wb,
        "Contract - Flexi",
        ["Staff ID", "Staff Name", "Entity", "Department 1", "Job Grade", "HR Cost", "Exit Date"],
        [["E005", "Eve", "Flexi", "Ops", "C1", 600, "Active"]],
    )
    _sheet(
        wb,
        "PP-Dec bonus",
        ["Staff ID No", "Staff name", "Department 1", "Performance Bonus", "Commission", "Other", "Deduction", "HR Cost"],
        [
            ["E001", "Alice", "Sales", 100, 0, 0, 0, 100],
            [None, "ITEM", "TOTAL", None, None, None, None, None],
            [None, "Staff Number", 1, None, None, None, None, None],
            [None, "Performance bonus", 100, None, None, None, None, None],
            [None, "HR cost", 100, None, None, None, None, None],
        ],
    )
    _sheet(
        wb,
        "1月离职",
        [
            "Staff Number",
            "Staff Name",
            "Entity",
            "Department 1",
            "New Reason for Leaving",
            "Exit Type",
            "Attrition",
            "Exit Date \n(YYYY/MM/DD)",
        ],
        [["E003", "Carol", "PalmPay", "Ops", "Career change", "Resignation", "Voluntary", "2026-01-20"]],
    )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_month2_workbook() -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    _sheet(
        wb,
        "Formal",
        ["Staff ID", "Staff Name", "Entity", "Department 1", "Job Grade", "HR Cost", "Resign Date"],
        [
            ["E001", "Alice", "PalmPay", "Sales", "P1", 1100, None],
            ["E002", "Bob", "PalmPay", "Sales", "P2", 1200, None],
            ["E006", "Frank", "PalmPay", "Sales", "P3", 700, None],
        ],
    )
    # Field-alias drift: Entity column renamed to Company/签约主体 this month.
    _sheet(
        wb,
        "PP-Contract",
        ["Staff ID", "Staff Name", "Company/签约主体", "Department 1", "Job Grade", "HR Cost", "Exit Date"],
        [["E004", "Dave", "PalmPay", "Sales", "C1", 550, "Active"]],
    )
    # E005 (Eve) is gone this month -> leaver. No Flexi sheet at all this month.
    # No exits sheet this month either, mirroring the real Apr-Jun gap found in the real data.

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_component_workbook(month: str, employees: list[dict]) -> bytes:
    """A Formal/Contract workbook carrying the PRD V1.1 salary-component
    columns (real names, verified against actual data - see
    ingestion/salary_components.py), for testing category breakdowns and the
    attribution component decomposition. `employees` is a list of dicts with
    keys: staff_id, name, role ('formal'|'contract'), department, basic,
    perf_bonus, commission, overtime, statutory, resigned (optional bool),
    department2 (optional, defaults to blank - for testing the department2
    drill-down filter).
    gross/hr_cost are computed here so the identities always hold exactly -
    the mismatch case is tested separately in test_salary_components.py.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    formal_rows = []
    contract_rows = []
    for e in employees:
        gross = e["basic"] + e["perf_bonus"] + e["commission"] + e["overtime"]
        hr_cost = gross + e["statutory"]
        if e["role"] == "formal":
            formal_rows.append(
                [
                    e["staff_id"],
                    e["name"],
                    "PalmPay",
                    e["department"],
                    e.get("department2"),
                    "P1",
                    hr_cost,
                    "2026-01-15" if e.get("resigned") else None,
                    e["basic"],
                    e["perf_bonus"],
                    e["commission"],
                    e["overtime"],
                    gross,
                    e["statutory"],
                ]
            )
        else:
            contract_rows.append(
                [
                    e["staff_id"],
                    e["name"],
                    "PalmPay",
                    e["department"],
                    e.get("department2"),
                    "C1",
                    hr_cost,
                    "Active",
                    e["basic"],
                    e["perf_bonus"],
                    e["commission"],
                    e["overtime"],
                    gross,
                    e["statutory"],
                    0,
                    0,
                    0,
                ]
            )

    if formal_rows:
        _sheet(
            wb,
            "Formal",
            [
                "Staff ID",
                "Staff Name",
                "Entity",
                "Department 1",
                "Department 2",
                "Job Grade",
                "HR Cost",
                "Resign Date",
                "Actual Monthly Basic Salary",
                "Performance Bonus",
                "Commission/Bonus",
                "Overtime Amount",
                "Total Gross Salary",
                "Statutory payments",
            ],
            formal_rows,
        )
    if contract_rows:
        _sheet(
            wb,
            "Contract - PP",
            [
                "Staff ID",
                "Staff Name",
                "Entity",
                "Department 1",
                "Department 2",
                "Job Grade",
                "HR Cost",
                "Exit Date",
                "Actual Monthly Basic Salary",
                "Perfomance bonus",
                "Commission/Bonus",
                "Overtime income",
                "Actual Gross Total Amount",
                "NSITF",
                "Pension ER",
                "ITF",
                "HMO",
            ],
            contract_rows,
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_supplemental_workbook(rows: list[tuple[str, str, str, float]], sheet_name: str = "Backpay") -> bytes:
    """rows: list of (staff_id, staff_name, department1, amount) - a standalone
    bonus/backpay file, deliberately much simpler/looser than the main workbook
    since these don't follow the fixed Formal/Contract shape."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(wb, sheet_name, ["Staff ID", "Staff Name", "Department 1", "HR Cost"], [list(r) for r in rows])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
