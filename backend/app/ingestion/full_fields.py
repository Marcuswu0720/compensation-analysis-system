"""PRD V1.6: the complete field templates for the three structured batch
types (正式工底薪&补发批次 = 37 fields, 合同工底薪&补发批次 = 29 fields,
奖金批次 = 26 fields).

Why this file exists: V1.1's data model only ever captured the ~10 fields
needed for the cost-analysis dashboard (basic salary, performance bonus,
overtime, etc.) - Department 2/3, Position, State, attendance/deduction
detail, and everything else in the original Excel were dropped at parse
time and never reached the database. V1.5's "full detail export" then had
nothing to export beyond those ~10 fields, no matter how the export code
was written - the gap was in what gets *parsed and stored*, not in the
export logic. This module is the single source of truth for "what the
complete field list actually is" so parsing and export can never drift
apart from each other again the way they did before.

`verified` marks whether a field's `source_aliases` have been confirmed
against real Jan-Jun payroll data in earlier work. Fields with
verified=False are a first guess from the PRD's field-template text alone
- ingestion reports (not silently ignores) any of these it can't find a
matching column for, and the admin/Marcus needs to check a real file to
confirm or correct the alias before fully trusting the exported values -
see README's "已知限制" section.
"""

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    key: str  # canonical snake_case key - dict key in full_detail_json (or an existing top-level column name)
    target_label: str  # PRD's target English field name - used verbatim as the export column header
    chinese_gloss: str
    source_aliases: tuple[str, ...]  # candidate raw column names, checked in order
    verified: bool


def export_header(spec: FieldSpec) -> str:
    return f"{spec.target_label}（{spec.chinese_gloss}）"


# Fields shared by both Formal and Contract templates - identical target
# label/gloss, but each role may need different source_aliases so these are
# NOT deduplicated into one shared list; see FORMAL_FIELDS/CONTRACT_FIELDS.
_COMMON_DESCRIPTIVE = [
    ("staff_id", "Staff ID", "员工工号"),
    ("staff_name", "Staff Name", "员工姓名"),
    ("department1", "Department 1", "一级部门"),
    ("department2", "Department 2", "二级部门"),
    ("department3", "Department 3", "三级部门"),
    ("position", "Position", "职位"),
    ("reporting_line", "Reporting Line", "汇报线"),
    ("job_grade", "Job Grade", "职级"),
    ("state", "State", "所在州"),
    ("work_station", "Work Station", "工作站点"),
    ("joining_date", "Joining Date", "入职日期"),
    ("resign_date", "Resign Date", "离职日期"),
]

FORMAL_FIELDS: list[FieldSpec] = [
    *[FieldSpec(k, label, gloss, (label,), k in ("staff_id", "staff_name", "department1", "job_grade", "resign_date")) for k, label, gloss in _COMMON_DESCRIPTIVE],
    FieldSpec("should_work_days", "Should Work Days", "应出勤日", ("Should Work Days",), False),
    FieldSpec("monthly_basic_salary", "Monthly Basic Salary", "合同底薪", ("Monthly Basic Salary",), False),
    FieldSpec("call_allowance", "Call Allowance", "话补", ("Call Allowance",), True),
    FieldSpec("internet_allowance", "Internet Allowance", "网补", ("Internet Allowance",), True),
    FieldSpec("traffic_allowance", "Traffic Allowance", "交补", ("Traffic Allowance",), True),
    FieldSpec("transportation_subsidy", "Transportation Subsidy", "油补", ("Transportation Subsidy",), True),
    FieldSpec("performance_std", "Performance STD", "绩效标准薪酬", ("Performance STD",), True),
    FieldSpec("hourly_late", "Hourly Late", "迟到小时数", ("Hourly Late",), False),
    FieldSpec("late_deduction", "Late Deduction", "迟到扣款", ("Late Deduction",), False),
    FieldSpec("porated_days", "Porated Days", "未满月天数", ("Porated Days", "Prorated Days"), False),
    FieldSpec("porated_days_deduction", "Porated Days Deduction", "未满月扣款", ("Porated Days Deduction", "Prorated Days Deduction"), False),
    FieldSpec("absent_days", "Absent Days", "无故缺勤天数", ("Absent Days",), False),
    FieldSpec("absent_deduction", "Absent Deduction", "缺勤扣款", ("Absent Deduction",), False),
    FieldSpec("attendance_rate", "Attendance Rate", "出勤率", ("Attendance Rate",), False),
    FieldSpec("basic_salary_actual", "Actual Monthly Basic", "当月应发底薪", ("Actual Monthly Basic Salary",), True),
    FieldSpec("performance_coefficient", "KPI Coefficient", "绩效系数", ("Coefficient",), True),
    FieldSpec("performance_bonus", "Performance Bonus", "绩效薪资实发", ("Performance Bonus",), True),
    FieldSpec("commission_bonus", "Commission/Bonus", "奖金", ("Commission/Bonus",), True),
    FieldSpec("overtime_hours", "Overtime Hours", "加班小时", ("Overtime Hours",), False),
    FieldSpec("overtime_amount", "Overtime Amount", "加班收入", ("Overtime Amount",), True),
    FieldSpec("other_income_raw", "Other Income", "其他收入", ("Other Income",), True),
    FieldSpec("gross_salary", "Total Gross Salary", "税前总薪资", ("Total Gross Salary",), True),
    FieldSpec("net_pay", "Total Net Pay", "税后实发", ("Total Net Pay",), True),
    FieldSpec("hr_cost", "HR Cost", "总人力成本", ("HR Cost",), True),
    FieldSpec("remark", "Remark", "备注", ("Remark",), False),
]

CONTRACT_FIELDS: list[FieldSpec] = [
    *[FieldSpec(k, label, gloss, (label,), k in ("staff_id", "staff_name", "department1", "job_grade", "resign_date")) for k, label, gloss in _COMMON_DESCRIPTIVE],
    FieldSpec("working_days", "Working Days", "应工作日", ("Working Days",), False),
    # NOTE: the PRD's 29-field list only lists one basic-salary concept for
    # Contract ("Basic Salary（合同底薪）"), unlike Formal which has both a
    # contracted-rate AND an actual-paid column. We only have one previously
    # -verified basic-salary column for Contract ("Actual Monthly Basic
    # Salary") - mapping it to this field is a judgment call, not a
    # certainty; confirm against a real Contract file.
    FieldSpec("basic_salary_actual", "Basic Salary", "合同底薪", ("Actual Monthly Basic Salary",), False),
    FieldSpec("airtime_data_allowance", "Airtime/Data Allowance", "话补", ("Airtime/Data Allowance",), False),
    FieldSpec("transport_allowance", "Transport Allowance", "交通补贴", ("Transport Allowance",), False),
    FieldSpec("performance_std", "Performance Standard", "绩效标准", ("Performance Standard",), True),
    FieldSpec("attendance_days", "Attendance Days", "实际出勤日", ("Attendance Days",), False),
    FieldSpec("attendance_rate", "Attendance Rate", "出勤率", ("Attendance Rate",), False),
    FieldSpec("performance_coefficient", "KPI Coefficient", "绩效系数", ("KPI Coeff.",), True),
    FieldSpec("performance_bonus", "Performance Bonus", "绩效薪资", ("Perfomance bonus",), True),  # sic - real column misspelled, see salary_components.py
    FieldSpec("hourly_late", "Hourly Late", "迟到小时数", ("Hourly Late",), False),
    FieldSpec("late_deduction", "Late Deduction", "迟到扣款", ("Late Deduction",), False),
    FieldSpec("commission_bonus", "Commission/Bonus", "奖金", ("Commission/Bonus",), True),
    FieldSpec("overtime_hours", "Overtime Hours", "加班小时", ("Overtime Hours",), False),
    FieldSpec("overtime_amount", "Overtime Amount", "加班收入", ("Overtime income",), True),
    FieldSpec("gross_salary", "Actual Gross", "税前总薪资", ("Actual Gross Total Amount",), True),
    FieldSpec("net_pay", "Net Amount Due", "税后实发", ("Net Amount Due",), True),
    FieldSpec("hr_cost", "HR Cost", "总人力成本", ("HR Cost",), True),
]

BONUS_FIELDS: list[FieldSpec] = [
    *[FieldSpec(k, label, gloss, (label,), k in ("staff_id", "staff_name", "department1")) for k, label, gloss in _COMMON_DESCRIPTIVE],
    FieldSpec("cost_center", "Cost Center", "成本中心", ("Cost Center",), False),
    FieldSpec("work_country", "Work Country", "工作国家", ("Work Country",), False),
    FieldSpec("performance_std", "Performance Standard", "奖金标准", ("Performance Standard",), False),
    FieldSpec("kpi_score", "KPI Score", "KPI评分", ("KPI Score",), False),
    FieldSpec("performance_bonus", "Performance Bonus", "绩效奖金", ("Performance Bonus",), True),
    FieldSpec("commission", "Commission", "销售佣金", ("Commission",), True),
    FieldSpec("other_income_raw", "Other", "其他收入", ("Other",), True),
    FieldSpec("deduction", "Deduction", "扣款", ("Deduction",), True),
    FieldSpec("gross_total_amount", "Gross Total Amount", "税前总奖金", ("Gross Total Amount",), False),
    FieldSpec("paye", "PAYE", "个人所得税", ("PAYE",), False),
    FieldSpec("itf_er", "ITF (ER)", "培训基金", ("ITF (ER)", "ITF(ER)", "ITF"), False),
    FieldSpec("bank_charges", "Bank Charges", "银行手续费", ("Bank Charges",), False),
    FieldSpec("hr_cost", "HR Cost", "人力成本", ("HR Cost",), True),
    FieldSpec("net_amount", "Net Amount", "税后实发", ("Net Amount",), False),
]

assert len(FORMAL_FIELDS) == 37, f"正式工底薪&补发批次 field spec has {len(FORMAL_FIELDS)} fields, PRD V1.6 §2.1 defines 37"
assert len(CONTRACT_FIELDS) == 29, f"合同工底薪&补发批次 field spec has {len(CONTRACT_FIELDS)} fields, PRD V1.6 §2.1 defines 29"
assert len(BONUS_FIELDS) == 26, f"奖金批次 field spec has {len(BONUS_FIELDS)} fields, PRD V1.6 §2.1 defines 26"

# Fields already extracted, verified, and stored by ingestion/salary_components.py
# (Formal/Contract) - re-extracting them here via source_aliases would just
# be a second, potentially-divergent code path for the same number. Skipped
# entirely when building full_detail_json.
ANALYSIS_KEYS = {
    "basic_salary_actual",
    "performance_std",
    "performance_coefficient",
    "performance_bonus",
    "commission_bonus",
    "overtime_amount",
    "other_income",
    "gross_salary",
    "employer_statutory_cost",
    "deduction_total",
    "net_pay",
    "hr_cost",
}
# Fields already extracted directly in ingestion/loader.py's per-role loop.
TOP_LEVEL_DESCRIPTIVE_KEYS = {"staff_id", "staff_name", "department1", "job_grade", "resign_date"}
# New descriptive fields promoted to real MonthlyEmployeeSnapshot columns
# (see models.py) rather than buried in full_detail_json - common/reusable
# enough to be worth a dedicated column.
NEW_DESCRIPTIVE_KEYS = {"department2", "department3", "position", "reporting_line", "state", "work_station", "joining_date"}

# SupplementalPaySnapshot's equivalent split for the standalone 奖金批次
# upload (see models.py's SupplementalPaySnapshot docstring): "amount" is
# fed from hr_cost directly (matching backpay's existing amount concept),
# not duplicated into full_detail_json; the rest of NEW_DESCRIPTIVE_KEYS'
# fields plus job_grade/cost_center/work_country/resign_date become real
# columns since they're the same kind of reusable descriptive data.
BONUS_TOP_LEVEL_KEYS = NEW_DESCRIPTIVE_KEYS | {"job_grade", "cost_center", "work_country", "resign_date"}
BONUS_EXCLUDE_KEYS = {"staff_id", "staff_name", "department1", "hr_cost"}


def _json_safe(value):
    """openpyxl hands back a real `datetime.datetime`/`datetime.date` object
    for any date-formatted cell (Joining Date, Resign Date, etc.) - unlike
    the handful of pre-V1.6 date fields (resign_or_exit_date), which were
    always explicitly str()'d at the point of extraction, these ~50 new
    fields are generic pass-throughs with no per-field special-casing. Doing
    the conversion once, here, means no future field needs its own
    stringification code, and the staged payload's `json.dumps()` call
    (loader.py's stage_upload) never crashes on a raw datetime again."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def extract_full_detail(
    row: dict, specs: list[FieldSpec], top_level_keys: set[str], exclude_keys: set[str]
) -> tuple[dict, dict, list[str]]:
    """Looks up every FieldSpec's source_aliases directly against `row` (a
    parsed sheet row dict keyed by raw header string - see parser.py's
    parse_sheet, which keeps every column, not just recognized ones).

    Returns (top_level_values, detail_json_values, missing_keys):
      - top_level_values: entries for spec.key in `top_level_keys` - meant
        to become real model columns.
      - detail_json_values: everything else not in `exclude_keys` - meant
        for a full_detail_json blob.
      - missing_keys: specs whose alias(es) weren't found in this row at
        all, so the caller can surface a validation issue instead of
        silently leaving the export column blank with no explanation.
    """
    top_level: dict = {}
    detail_json: dict = {}
    missing: list[str] = []
    for spec in specs:
        if spec.key in exclude_keys:
            # Handled by a separate, already-working mechanism (e.g.
            # extract_salary_components, or loader.py's direct get() calls)
            # - not this function's concern, so don't report it as missing
            # even if this particular alias list doesn't happen to match.
            continue
        value = None
        found = False
        for alias in spec.source_aliases:
            if alias in row:
                value = _json_safe(row[alias])
                found = True
                break
        if not found:
            missing.append(spec.key)
        if spec.key in top_level_keys:
            top_level[spec.key] = value
        else:
            detail_json[spec.key] = value
    return top_level, detail_json, missing
