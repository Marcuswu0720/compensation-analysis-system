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
    __table_args__ = (UniqueConstraint("month", "staff_id", name="uq_month_staff"),)

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
    total_gross_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    resign_or_exit_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)


class MonthlyBonusSnapshot(Base):
    __tablename__ = "monthly_bonus_snapshot"
    __table_args__ = (UniqueConstraint("performance_month", "staff_id", name="uq_perf_month_staff"),)

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


class SupplementalPaySnapshot(Base):
    """Extra pay added on top of a month's base salary batch: a standalone
    bonus-correction file, or a one-off backpay file (e.g. overtime backpay
    sheets that don't fit the standard Formal/Contract shape). Kept separate
    from monthly_employee_snapshot so a 'base' re-upload never wipes these,
    and vice versa - see ingestion/commit.py."""

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


class DataQualityLog(Base):
    __tablename__ = "data_quality_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    upload_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    issue_type: Mapped[str] = mapped_column(String(64))
    issue_detail: Mapped[str] = mapped_column(Text)
    row_count_affected: Mapped[int] = mapped_column(Integer, default=0)
