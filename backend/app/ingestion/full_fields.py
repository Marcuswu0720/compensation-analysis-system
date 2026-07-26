"""PRD V1.8 §2: the complete field templates for the three structured batch
types (正式工底薪&补发批次 = 40 fields, 合同工底薪&补发批次 = 33 fields,
奖金批次 = 24 fields), rebuilt from the authoritative field-mapping file the
user provided ("数据导出展示字段-映射.xlsx") - this supersedes every guess
V1.5/V1.6 made from the PRD text alone. Every field here is `verified=True`:
the mapping file names the exact raw column per batch type, no more
first-guess aliases.

Two corrections from this file worth calling out:
  - Entity and Employment Type are real target fields the V1.5/V1.6 field
    lists omitted entirely.
  - 奖金批次's template changed: State+Work Station merged into a single
    Location field, and PAYE/Bank Charges/Cost Center/Work Country - all
    guesses from V1.6 that were never checked against a real file - are
    gone; ITF (ER) now maps to a plain "ITF" column, not several guessed
    variants.

Why this file exists at all (unchanged since V1.6): the original data model
only ever captured the fields the cost-analysis dashboard needs (basic
salary, performance bonus, overtime, etc.) - Department 2/3, Position,
State, attendance/deduction detail, and everything else in the original
Excel were dropped at parse time and never reached the database. This
module is the single source of truth for "what the complete field list
actually is" so parsing and export can't drift apart from each other.

PRD V1.8 §1: matching a field's `source_aliases` against a sheet's real
headers is case/whitespace-normalized (see header_match.py), not exact
string equality - so a header spelled "Staff name" or "Joining Date "
(trailing space) is still recognized. `source_aliases` only needs a second
entry when the wording is genuinely different (not just casing/whitespace).
"""

from dataclasses import dataclass

from .date_utils import format_date_value
from .header_match import build_header_index, find_alias


@dataclass(frozen=True)
class FieldSpec:
    key: str  # canonical snake_case key - dict key in full_detail_json (or an existing top-level column name)
    target_label: str  # PRD's target English field name - used verbatim as the export column header
    chinese_gloss: str
    source_aliases: tuple[str, ...]  # candidate raw column names, checked in order (normalized comparison)
    verified: bool  # confirmed against the authoritative field-mapping file (PRD V1.8) or real data


def export_header(spec: FieldSpec) -> str:
    return f"{spec.target_label}（{spec.chinese_gloss}）"


FORMAL_FIELDS: list[FieldSpec] = [
    FieldSpec("entity", "Entity", "公司实体", ("Entity",), True),
    FieldSpec("staff_id", "Staff ID", "工号", ("Staff ID",), True),
    FieldSpec("employment_type", "Employment Type", "员工类别", ("Employment Type",), True),
    FieldSpec("staff_name", "Staff Name", "姓名", ("Staff Name",), True),
    FieldSpec("department1", "Department 1", "一级部门", ("Department 1",), True),
    FieldSpec("department2", "Department 2", "二级部门", ("Department 2",), True),
    FieldSpec("department3", "Department 3", "三级部门", ("Department 3",), True),
    FieldSpec("position", "Position", "岗位", ("Position",), True),
    FieldSpec("reporting_line", "Reporting Line", "汇报对象", ("Reporting Line",), True),
    FieldSpec("job_grade", "Job Grade", "职级", ("Job Grade",), True),
    FieldSpec("state", "State", "工作地点-州", ("State",), True),
    FieldSpec("work_station", "Work Station", "工作地点-办公室", ("Work Station",), True),
    FieldSpec("joining_date", "Joining Date", "入职时间", ("Joining Date",), True),
    FieldSpec("resign_date", "Resign Date", "离职时间", ("Resign Date",), True),
    FieldSpec("should_work_days", "Should Work Days", "应出勤日", ("Should Work Days",), True),
    FieldSpec("monthly_basic_salary", "Monthly Basic Salary", "底薪标准", ("Monthly Basic Salary",), True),
    FieldSpec("call_allowance", "Call Allowance", "话补", ("Call Allowance",), True),
    FieldSpec("internet_allowance", "Internet Allowance", "网补", ("Internet Allowance",), True),
    FieldSpec("traffic_allowance", "Traffic Allowance", "交补", ("Traffic Allowance",), True),
    FieldSpec("transportation_subsidy", "Transportation Subsidy", "油补", ("Transportation Subsidy",), True),
    FieldSpec("performance_std", "Performance STD", "绩效标准薪酬", ("Performance STD",), True),
    FieldSpec("hourly_late", "Hourly Late", "迟到小时数", ("Hourly Late",), True),
    # A real production export showed this column blank for every row despite
    # the sheet having the data - "Late Ded." (the abbreviated form the
    # mapping file used) doesn't match the real header, which spells the
    # word out in full like every sibling attendance/deduction column above
    # and below it (Hourly Late, Porated Days, Absent Days). Kept as a
    # fallback alias in case some file really does use the abbreviation.
    FieldSpec("late_deduction", "Late Deduction", "迟到扣款", ("Late Deduction", "Late Ded."), True),
    FieldSpec("porated_days", "Porated Days", "未满月天数", ("Porated Days",), True),
    FieldSpec(
        "porated_days_deduction", "Porated Days Deduction", "未满月扣款", ("Porated Days Deduction", "Porated Days Ded."), True
    ),
    FieldSpec("absent_days", "Absent Days", "无故缺勤天数", ("Absent Days",), True),
    FieldSpec("absent_deduction", "Absent Deduction", "缺勤扣款", ("Absent Deduction", "Absent Ded."), True),
    FieldSpec("attendance_rate", "Attendance Rate", "出勤率", ("Attendance Rate",), True),
    FieldSpec("basic_salary_actual", "Actual Monthly Basic", "当月应发底薪", ("Actual Monthly Basic Salary",), True),
    FieldSpec("performance_coefficient", "KPI Coefficient", "绩效系数", ("Coefficient",), True),
    FieldSpec("performance_bonus", "Performance Bonus", "绩效薪资实发", ("Performance Bonus",), True),
    FieldSpec("commission_bonus", "Commission / Bonus", "奖金", ("Commission/Bonus",), True),
    FieldSpec("overtime_hours", "Overtime Hours", "加班小时", ("Overtime Hours",), True),
    FieldSpec("overtime_amount", "Overtime Amount", "加班收入", ("Overtime Amount",), True),
    FieldSpec("other_income_raw", "Other Income", "其他收入", ("Other Income",), True),
    FieldSpec("gross_salary", "Total Gross Salary", "税前总薪资", ("Total Gross Salary",), True),
    FieldSpec("employer_statutory_cost", "Statutory payments", "雇主侧社保", ("Statutory payments",), True),
    FieldSpec("net_pay", "Total Net Pay", "税后实发", ("Total Net Pay",), True),
    FieldSpec("hr_cost", "HR Cost", "总人力成本", ("HR Cost",), True),
    FieldSpec("remark", "Remark", "备注", ("Remark",), True),
]

CONTRACT_FIELDS: list[FieldSpec] = [
    FieldSpec("entity", "Entity", "公司实体", ("Entity",), True),
    # Contract-Flexi's real sheet uses a bare "ID" column, not "Staff ID" -
    # the actual staff_id VALUE was always correct regardless (it comes from
    # the ingestion/constants.py alias list, not this diagnostic-only spec),
    # but without this alias the upload-time field-mapping check wrongly
    # reported "Staff ID" as missing for every Contract-Flexi sheet.
    FieldSpec("staff_id", "Staff ID", "工号", ("Staff ID", "ID"), True),
    FieldSpec("employment_type", "Employment Type", "员工类别", ("Employment Type",), True),
    FieldSpec("staff_name", "Staff Name", "姓名", ("Name",), True),
    FieldSpec("department1", "Department 1", "一级部门", ("Department 1",), True),
    FieldSpec("department2", "Department 2", "二级部门", ("Department 2",), True),
    FieldSpec("department3", "Department 3", "三级部门", ("Department 3",), True),
    # Contract-PP calls this column "Job Title"; Contract-Flexi calls the
    # same column "Position" - verified against a real January file where
    # relying on "Job Title" alone left every Flexi row's position blank.
    FieldSpec("position", "Position", "岗位", ("Job Title", "Position"), True),
    # Same story for reporting line: Contract-Flexi's real header is
    # "Chinese Reporting line", not "Reporting Line".
    FieldSpec("reporting_line", "Reporting Line", "汇报对象", ("Reporting Line", "Chinese Reporting line"), True),
    FieldSpec("job_grade", "Job Grade", "职级", ("Job Grade",), True),
    FieldSpec("state", "State", "工作地点-州", ("State",), True),
    # Contract-Flexi's real header is "Work Location", not "Work Station".
    FieldSpec("work_station", "Work Station", "工作地点-办公室", ("Work Station", "Work Location"), True),
    FieldSpec("joining_date", "Joining Date", "入职时间", ("Joining Date",), True),
    FieldSpec("resign_date", "Resign Date", "离职时间", ("Exit Date",), True),
    # Contract-Flexi's real header is "Should Working Days", not "Working Days".
    FieldSpec("should_work_days", "Should Work Days", "应出勤日", ("Working Days", "Should Working Days"), True),
    # This FieldSpec only feeds the upload-time diagnostic (does a raw column
    # exist for the PRD's "Basic Salary" target field) - the exported value
    # itself always comes from salary_components.py's already-validated
    # analysis-layer number (see ANALYSIS_KEYS below), never a fresh
    # extraction from this alias. The diagnostic used to check for a
    # "Monthly Basic Salary" column per the mapping file, but real Contract
    # files (confirmed against a real January upload) don't have a column by
    # that exact name - only "Actual Monthly Basic Salary", which is also
    # what the analysis layer actually reads. Matching the same column here
    # makes the diagnostic agree with reality instead of falsely reporting
    # "Basic Salary missing" on every upload despite the number being
    # correct; "Monthly Basic Salary" is kept as a fallback alias in case
    # some other entity's file genuinely has a separate column by that name.
    FieldSpec("basic_salary_actual", "Basic Salary", "底薪标准", ("Actual Monthly Basic Salary", "Monthly Basic Salary"), True),
    # Contract-Flexi's real header has extra trailing wording ("... / POS
    # Storage Subcidy") that isn't just casing/whitespace drift.
    FieldSpec(
        "airtime_data_allowance",
        "Airtime/Data Allowance",
        "话补",
        ("Airtime / Data Allowance", "Airtime / Data Allowance / POS Storage Subcidy"),
        True,
    ),
    FieldSpec("transport_allowance", "Transport Allowance", "交通补贴", ("Transport Allowance",), True),
    FieldSpec("performance_std", "Performance Standard", "绩效标准", ("Performance Standard",), True),
    FieldSpec("attendance_days", "Attendance Days", "实际出勤日", ("Attendance Days",), True),
    FieldSpec("attendance_rate", "Attendance Rate", "出勤率", ("Attendance rate",), True),
    FieldSpec("performance_coefficient", "KPI Coefficient", "绩效系数", ("KPI Coeff.",), True),
    FieldSpec("performance_bonus", "Performance Bonus", "绩效薪资", ("Perfomance bonus",), True),  # sic - real column misspelled
    FieldSpec("hourly_late", "Hourly Late", "迟到小时数", ("Hourly Late",), True),
    # Same real-file mismatch as FORMAL_FIELDS' late_deduction: a real
    # production export showed this blank for every Contract row too.
    # "Lateness deduction" is kept as a fallback in case some file really
    # uses that wording.
    FieldSpec("late_deduction", "Late Deduction", "迟到扣款", ("Late Deduction", "Lateness deduction"), True),
    FieldSpec("commission_bonus", "Commission / Bonus", "奖金", ("Commission/Bonus",), True),
    FieldSpec("overtime_hours", "Overtime Hours", "加班小时", ("Overtime Hour",), True),
    FieldSpec("overtime_amount", "Overtime Amount", "加班收入", ("Overtime income",), True),
    FieldSpec("other_income_raw", "Other Income", "其他收入", ("Arrears/Other Income",), True),
    FieldSpec("gross_salary", "Actual Gross", "税前总薪资", ("Actual Gross Total Amount",), True),
    # PRD V1.8 correction: Contract has its own ready-made "ER COST" column -
    # V1.1/V1.5 wrongly assumed it needed summing from NSITF+Pension ER+ITF+
    # HMO (see ingestion/salary_components.py's module docstring).
    FieldSpec("employer_statutory_cost", "Statutory payments", "雇主侧社保", ("ER COST",), True),
    FieldSpec("net_pay", "Net Amount Due", "税后实发", ("Net Amount Due",), True),
    FieldSpec("hr_cost", "HR Cost", "总人力成本", ("HR Cost",), True),
]

BONUS_FIELDS: list[FieldSpec] = [
    FieldSpec("entity", "Entity", "公司实体", ("Entity",), True),
    # PRD V1.8 §1.1 documents "Staff ID No" as an actually-observed variant
    # for this batch type specifically (not just a casing/whitespace issue,
    # a genuinely different wording) - kept as a second alias even though
    # the mapping file's own row says "Staff ID".
    FieldSpec("staff_id", "Staff ID", "工号", ("Staff ID", "Staff ID No"), True),
    # A real January bonus file uses "Staff Type" for this column, not
    # "Employment Type" - genuinely different wording, not casing drift.
    FieldSpec("employment_type", "Employment Type", "员工类别", ("Employment Type", "Staff Type"), True),
    # Same story: PRD V1.8 §1.1 documents "Staff name" as an observed
    # variant alongside the mapping file's stated "Name".
    FieldSpec("staff_name", "Staff Name", "姓名", ("Name", "Staff Name"), True),
    FieldSpec("department1", "Department 1", "一级部门", ("Department 1",), True),
    FieldSpec("department2", "Department 2", "二级部门", ("Department 2",), True),
    FieldSpec("department3", "Department 3", "三级部门", ("Department 3",), True),
    # The bonus template's real header is "Position", not "Job Title" (unlike
    # Contract, which really does use "Job Title").
    FieldSpec("position", "Position", "岗位", ("Job Title", "Position"), True),
    # The bonus template's real header is "Line Manager", not "Reporting Line".
    FieldSpec("reporting_line", "Reporting Line", "汇报对象", ("Reporting Line", "Line Manager"), True),
    FieldSpec("job_grade", "Job Grade", "职级", ("Job Grade",), True),
    # V1.8 correction: the bonus template merges State+Work Station into one
    # Location field - unlike Formal/Contract, which keep the two separate.
    FieldSpec("location", "Location", "工作地点", ("Location",), True),
    FieldSpec("joining_date", "Joining Date", "入职时间", ("Joining Date",), True),
    FieldSpec("resign_date", "Resign Date", "离职时间", ("Leaving date",), True),
    FieldSpec("performance_std", "Performance Standard", "奖金标准", ("Performance Standard",), True),
    FieldSpec("kpi_score", "KPI Score", "KPI评分", ("KPI Score",), True),
    FieldSpec("performance_bonus", "Performance Bonus", "绩效奖金", ("Performance Bonus",), True),
    FieldSpec("commission", "Commission", "销售佣金", ("Commission",), True),
    FieldSpec("other", "Other", "其他收入", ("Other",), True),
    FieldSpec("deduction", "Deduction", "扣款", ("Deduction",), True),
    FieldSpec("gross_total_amount", "Gross Total Amount", "税前总奖金", ("Gross Total Amount",), True),
    # V1.8 correction: PAYE/Bank Charges/Cost Center/Work Country (all
    # guesses in V1.6) are gone from the real template; ITF (ER) maps to a
    # plain "ITF" column, not several guessed variants.
    FieldSpec("itf_er", "ITF (ER)", "雇主侧社保", ("ITF",), True),
    FieldSpec("net_amount", "Net Amount", "税后实发", ("Net Amount",), True),
    FieldSpec("hr_cost", "HR Cost", "人力成本", ("HR Cost",), True),
    FieldSpec("remark", "Remark", "备注", ("Remark",), True),
]

assert len(FORMAL_FIELDS) == 40, f"正式工底薪&补发批次 field spec has {len(FORMAL_FIELDS)} fields, PRD V1.8 §2.1 defines 40"
assert len(CONTRACT_FIELDS) == 33, f"合同工底薪&补发批次 field spec has {len(CONTRACT_FIELDS)} fields, PRD V1.8 §2.1 defines 33"
assert len(BONUS_FIELDS) == 24, f"奖金批次 field spec has {len(BONUS_FIELDS)} fields, PRD V1.8 §2.1 defines 24"

# Fields already extracted, verified, and stored by ingestion/salary_components.py
# (Formal/Contract) - re-extracting them here via source_aliases would just
# be a second, potentially-divergent code path for the same number. Skipped
# entirely when building full_detail_json; the exported value always comes
# from compute/export.py's _base_row_to_dict(), which reads the already-
# computed model column directly.
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
# Fields already extracted directly in ingestion/loader.py's per-role loop
# (entity/employment_type are resolved there too - entity through
# NameResolver, employment_type from which sheet/role matched - not by
# re-parsing a raw column here).
TOP_LEVEL_DESCRIPTIVE_KEYS = {"staff_id", "staff_name", "department1", "job_grade", "resign_date", "entity", "employment_type"}
# New descriptive fields promoted to real MonthlyEmployeeSnapshot columns
# (see models.py) rather than buried in full_detail_json - common/reusable
# enough to be worth a dedicated column.
NEW_DESCRIPTIVE_KEYS = {"department2", "department3", "position", "reporting_line", "state", "work_station", "joining_date"}

# SupplementalPaySnapshot's equivalent split for the standalone 奖金批次
# upload: "amount" is fed from hr_cost directly (matching backpay's existing
# amount concept), not duplicated into full_detail_json; staff_id/staff_name/
# department1/entity/employment_type are all extracted by dedicated lookups
# in ingestion/bonus_batch.py (entity additionally goes through NameResolver
# for canonicalization, employment_type is a plain pass-through) rather than
# this module's generic top_level/detail_json routing.
BONUS_TOP_LEVEL_KEYS = {"department2", "department3", "position", "reporting_line", "job_grade", "location", "joining_date", "resign_date"}
BONUS_EXCLUDE_KEYS = {"staff_id", "staff_name", "department1", "entity", "employment_type", "hr_cost"}


def _json_safe(value):
    return format_date_value(value)


def extract_full_detail(
    row: dict, specs: list[FieldSpec], top_level_keys: set[str], exclude_keys: set[str], header_index: dict[str, str] | None = None
) -> tuple[dict, dict, list[str]]:
    """Looks up every FieldSpec's source_aliases against `row` (a parsed
    sheet row dict keyed by raw header string - see parser.py's parse_sheet,
    which keeps every column, not just recognized ones), using the
    case/whitespace-normalized matching from header_match.py.

    `header_index` should be built once per sheet (via build_header_index)
    and passed in by the caller - it's the same for every row in a sheet, so
    rebuilding it per row would be wasted work. If omitted, it's built from
    this row's own keys (convenient for tests / one-off calls).

    Returns (top_level_values, detail_json_values, missing_keys):
      - top_level_values: entries for spec.key in `top_level_keys` - meant
        to become real model columns.
      - detail_json_values: everything else not in `exclude_keys` - meant
        for a full_detail_json blob.
      - missing_keys: specs whose alias(es) weren't found in this row at
        all, so the caller can surface a validation issue instead of
        silently leaving the export column blank with no explanation.
    """
    if header_index is None:
        header_index = build_header_index(row.keys())

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
        raw_col = find_alias(header_index, spec.source_aliases)
        found = raw_col is not None
        value = _json_safe(row[raw_col]) if found else None
        if not found:
            missing.append(spec.key)
        if spec.key in top_level_keys:
            top_level[spec.key] = value
        else:
            detail_json[spec.key] = value
    return top_level, detail_json, missing


def check_field_mapping(header_index: dict[str, str], specs: list[FieldSpec]) -> tuple[int, int, list[dict]]:
    """PRD V1.8 §4: the upload-time field-mapping diagnostic. Independent of
    exclude_keys/top_level_keys routing (unlike extract_full_detail) - this
    checks EVERY target field in `specs`, including the ones handled by a
    separate mechanism (staff_id, entity, the analysis-layer fields, etc.),
    because the point is "does a matching raw column exist in this sheet at
    all", not "does this function need to do anything about it".

    Returns (total_field_count, matched_count, missing_details) where each
    missing_details entry is {"key", "target_label", "tried_aliases"} - the
    admin needs to know which target field, described by its human-readable
    label, and which aliases were tried, not just an internal snake_case key.
    """
    missing: list[dict] = []
    matched = 0
    for spec in specs:
        if find_alias(header_index, spec.source_aliases) is not None:
            matched += 1
        else:
            missing.append({"key": spec.key, "target_label": spec.target_label, "tried_aliases": list(spec.source_aliases)})
    return len(specs), matched, missing
