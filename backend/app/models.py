from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")  # admin | viewer
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Account-level disable (PRD V1.2 §3.1): a disabled account can't log in and
    # loses access mid-session, but the row (and its operation-log history) is
    # kept forever - never physically deleted.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # '2026-01'
    salary_type: Mapped[str] = mapped_column(String(16), nullable=False, default="base")  # base | bonus | backpay
    original_filename: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # pending_review | confirmed | rejected | superseded (replaced by a later confirmed
    # upload for the same month+salary_type) | deleted
    status: Mapped[str] = mapped_column(String(16), default="pending_review")
    staged_data: Mapped[str] = mapped_column(Text)  # JSON blob: parsed rows + summary, shape depends on salary_type
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CanonicalName(Base):
    """Resolves raw label variants (department / entity names) to one display form."""

    __tablename__ = "canonical_names"
    __table_args__ = (UniqueConstraint("category", "raw_lower", name="uq_category_raw"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(16))  # 'department' | 'entity'
    raw_lower: Mapped[str] = mapped_column(String(255))
    canonical_display: Mapped[str] = mapped_column(String(255))
    first_seen_month: Mapped[str] = mapped_column(String(7))
    seen_raw_forms_json: Mapped[str] = mapped_column(Text, default="[]")


class MonthlyEmployeeSnapshot(Base):
    __tablename__ = "monthly_employee_snapshot"
    # No DB-level unique constraint on (month, staff_id): a soft-deleted row
    # (is_deleted=True) has to be able to coexist with the active replacement
    # that superseded it, for the same key. Uniqueness among *active* rows is
    # guaranteed by ingestion/commit.py always soft-deleting the prior batch
    # before inserting a new one for the same (month, salary_type) slot.

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    staff_id: Mapped[str] = mapped_column(String(64), nullable=False)
    staff_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    department1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department1_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hr_cost: Mapped[float] = mapped_column(Float, default=0.0)
    # Salary component breakdown (PRD V1.1 §2) - see ingestion/salary_components.py
    # for the Formal-vs-Contract column mapping these are extracted from.
    basic_salary_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    performance_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    performance_coefficient: Mapped[float | None] = mapped_column(Float, nullable=True)
    performance_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    overtime_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    other_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    employer_statutory_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    deduction_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_pay: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    resign_or_exit_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    # Soft-delete flag (PRD V1.1 §3.3): a deleted/superseded batch's rows stay
    # in the table for audit purposes but are excluded from every query - see
    # compute/scope.py and ingestion/commit.py.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # PRD V1.6: the original data model above only ever captured the fields
    # the cost-analysis dashboard needs - Department 2/3, Position, State,
    # attendance/deduction detail, etc. were dropped at parse time and never
    # reached the database at all, which is why V1.5's "full detail export"
    # came out ~20 columns short (see ingestion/full_fields.py). These
    # descriptive fields are common/reusable enough to be real columns;
    # everything else new (allowance breakdowns, attendance/deduction
    # figures) goes into full_detail_json instead of ~15 more single-purpose
    # nullable columns, since nothing in compute/*.py ever needs them - only
    # the full-detail export does.
    department2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reporting_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_station: Mapped[str | None] = mapped_column(String(255), nullable=True)
    joining_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MonthlyBonusSnapshot(Base):
    __tablename__ = "monthly_bonus_snapshot"
    # See MonthlyEmployeeSnapshot's comment above - no DB-level unique
    # constraint, for the same soft-delete-coexistence reason.

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    performance_month: Mapped[str] = mapped_column(String(7), nullable=False)
    payment_month: Mapped[str] = mapped_column(String(7), nullable=False)
    staff_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performance_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    other_income: Mapped[float] = mapped_column(Float, default=0.0)
    deduction: Mapped[float] = mapped_column(Float, default=0.0)
    bonus_total: Mapped[float] = mapped_column(Float, default=0.0)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class SupplementalPaySnapshot(Base):
    """Extra pay added on top of a month's base salary batch: a standalone
    bonus file, or a one-off backpay file (e.g. overtime backpay sheets that
    don't fit the standard Formal/Contract shape). Kept separate from
    monthly_employee_snapshot so a 'base' re-upload never wipes these, and
    vice versa - see ingestion/commit.py.

    pay_type='backpay' rows stay the original loose staff_id+amount shape
    (confirmed with the user - V1.5 §0.2/PRD V1.6 background: backpay files
    really are just a simple list, not a full payroll template). pay_type=
    'bonus' rows are the standalone "奖金批次" upload, which PRD V1.6
    revealed is actually a full 26-field structured template (see
    ingestion/full_fields.py's BONUS_FIELDS) - the extra descriptive columns
    below and full_detail_json are only ever populated for those, left NULL
    for backpay rows."""

    __tablename__ = "supplemental_pay_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    pay_type: Mapped[str] = mapped_column(String(16), nullable=False)  # bonus | backpay
    staff_id: Mapped[str] = mapped_column(String(64), nullable=False)
    staff_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    source_sheet: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matched_base_employee: Mapped[bool] = mapped_column(Boolean, default=False)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # PRD V1.6 §2.1 - only populated for pay_type='bonus' rows.
    department2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reporting_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_station: Mapped[str | None] = mapped_column(String(255), nullable=True)
    joining_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resign_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExitRecord(Base):
    __tablename__ = "exit_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exit_month: Mapped[str] = mapped_column(String(7), nullable=False)
    staff_id: Mapped[str] = mapped_column(String(64), nullable=False)
    staff_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason_for_leaving: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exit_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attrition_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class DataQualityLog(Base):
    __tablename__ = "data_quality_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    upload_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    issue_type: Mapped[str] = mapped_column(String(64))
    issue_detail: Mapped[str] = mapped_column(Text)
    row_count_affected: Mapped[int] = mapped_column(Integer, default=0)


class ViewerPermission(Base):
    """A viewer's visible-data allowlist (PRD V1.2 §1 - supersedes the V1.1
    department/entity-as-independent-axes design). Each row is a
    self-contained, already-AND'd rule:
      - scope_type='entity': the WHOLE entity is visible (every department
        under it), `department1` is NULL.
      - scope_type='entity_department': only that one (entity, department1)
        pair is visible.
    A viewer's visible data is the UNION of all their is_active=true rules -
    see security.get_allowed_scope / compute/scope.py's apply_permission_scope.
    This closes the V1.1 bug where granting entity=Flexi + department=Credit
    Business independently (two separate axis-filters ANDed/ORed at query
    time) could also expose a same-named department in a different entity;
    here department1 only ever gets compared to rows that also match that
    exact rule's entity, never in isolation.
    A viewer with zero active rows sees nothing until an admin grants them
    something, rather than defaulting to full access.
    Revoking a rule sets is_active=False (+ revoked_by/revoked_time) instead
    of deleting the row, so "what could this account see, and when" stays
    fully reconstructable for compliance/audit purposes (PRD V1.2 §3.2)."""

    __tablename__ = "viewer_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(24), nullable=False)  # 'entity' | 'entity_department'
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    department1: Mapped[str | None] = mapped_column(String(255), nullable=True)  # set iff scope_type='entity_department'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    granted_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DownloadLog(Base):
    """Audit trail for salary-detail Excel exports (PRD V1.3 §4) - more
    important than logging a web page view, because once a file is
    downloaded it's completely outside the system's access control forever
    (can be forwarded/saved/screenshotted); if the data ever leaks, this is
    what lets someone reconstruct which download it came from. Append-only,
    like DataOperationLog - nothing here is ever edited or deleted."""

    __tablename__ = "download_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    download_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    entity_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    month_range_start: Mapped[str | None] = mapped_column(String(7), nullable=True)
    month_range_end: Mapped[str | None] = mapped_column(String(7), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    # Comma-joined subset of base/bonus/backpay actually included (PRD V1.5
    # §2.1's batch-type filter) - nullable so old rows from before this
    # column existed don't need backfilling.
    salary_types: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DataOperationLog(Base):
    """Audit trail for anything that changes official data (PRD V1.1 §3.3),
    kept even after the batch it refers to is deleted/superseded - this table
    is append-only, nothing here is ever deleted or edited."""

    __tablename__ = "data_operation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'upload' | 'delete' | 'correct'
    target_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    operation_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
