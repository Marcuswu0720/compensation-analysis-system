"""Materializes a reviewed & confirmed UploadBatch into the real snapshot tables.

Each (month, salary_type) slot can have at most one *confirmed* batch at a
time. Confirming a new batch for a slot that already has one supersedes the
old one: its rows are deleted (scoped precisely by upload_batch_id, so this
never touches a different salary_type's data for the same month) and its
status flips to 'superseded' rather than being silently overwritten.
"""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (
    DataQualityLog,
    ExitRecord,
    MonthlyBonusSnapshot,
    MonthlyEmployeeSnapshot,
    SupplementalPaySnapshot,
    UploadBatch,
)
from .constants import BONUS_MONTH_OFFSET
from .loader import shift_month


def delete_batch_data(db: Session, batch_id: int) -> None:
    """Removes every row tied to a batch, across all tables it could have written to."""
    db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.upload_batch_id == batch_id).delete()
    db.query(MonthlyBonusSnapshot).filter(MonthlyBonusSnapshot.upload_batch_id == batch_id).delete()
    db.query(ExitRecord).filter(ExitRecord.upload_batch_id == batch_id).delete()
    db.query(SupplementalPaySnapshot).filter(SupplementalPaySnapshot.upload_batch_id == batch_id).delete()
    db.query(DataQualityLog).filter(DataQualityLog.upload_batch_id == batch_id).delete()


def confirm_upload(db: Session, batch: UploadBatch) -> None:
    if batch.status == "confirmed":
        raise ValueError("该批次已确认，不能重复确认")

    payload = json.loads(batch.staged_data)

    prior_batches = (
        db.query(UploadBatch)
        .filter(
            UploadBatch.month == batch.month,
            UploadBatch.salary_type == batch.salary_type,
            UploadBatch.status == "confirmed",
            UploadBatch.id != batch.id,
        )
        .all()
    )
    for prior in prior_batches:
        delete_batch_data(db, prior.id)
        prior.status = "superseded"

    if batch.salary_type == "base":
        _insert_base(db, batch, payload)
    else:
        _insert_supplemental(db, batch, payload)

    for issue in payload["issues"]:
        db.add(
            DataQualityLog(
                month=batch.month,
                upload_batch_id=batch.id,
                issue_type=issue["issue_type"],
                issue_detail=issue["issue_detail"],
                row_count_affected=issue["row_count_affected"],
            )
        )

    batch.status = "confirmed"
    batch.confirmed_at = datetime.utcnow()
    db.commit()


def _insert_base(db: Session, batch: UploadBatch, payload: dict) -> None:
    for e in payload["employees"]:
        db.add(
            MonthlyEmployeeSnapshot(
                month=batch.month,
                staff_id=e["staff_id"],
                staff_name=e["staff_name"],
                entity=e["entity"],
                employment_type=e["employment_type"],
                department1=e["department1"],
                department1_raw=e["department1_raw"],
                job_grade=e["job_grade"],
                hr_cost=e["hr_cost"],
                total_gross_salary=e["total_gross_salary"],
                is_active=e["is_active"],
                resign_or_exit_date=e["resign_or_exit_date"],
                source_sheet=e["source_sheet"],
                upload_batch_id=batch.id,
            )
        )

    for b in payload["bonuses"]:
        db.add(
            MonthlyBonusSnapshot(
                performance_month=b["performance_month"],
                payment_month=b["payment_month"],
                staff_id=b["staff_id"],
                entity=b["entity"],
                department1=b["department1"],
                performance_bonus=b["performance_bonus"],
                commission=b["commission"],
                other_income=b["other_income"],
                deduction=b["deduction"],
                bonus_total=b["bonus_total"],
                upload_batch_id=batch.id,
            )
        )

    for x in payload["exits"]:
        db.add(
            ExitRecord(
                exit_month=batch.month,
                staff_id=x["staff_id"],
                staff_name=x["staff_name"],
                entity=x["entity"],
                department1=x["department1"],
                reason_for_leaving=x["reason_for_leaving"],
                exit_type=x["exit_type"],
                attrition_type=x["attrition_type"],
                exit_date=x["exit_date"],
                upload_batch_id=batch.id,
            )
        )


def _insert_supplemental(db: Session, batch: UploadBatch, payload: dict) -> None:
    for e in payload["entries"]:
        db.add(
            SupplementalPaySnapshot(
                month=batch.month,
                pay_type=batch.salary_type,
                staff_id=e["staff_id"],
                staff_name=e["staff_name"],
                entity=e["entity"],
                department1=e["department1"],
                amount=e["amount"],
                source_sheet=e["source_sheet"],
                matched_base_employee=e["matched_base_employee"],
                upload_batch_id=batch.id,
            )
        )


def delete_confirmed_batch(db: Session, batch: UploadBatch) -> None:
    """Hard-deletes a confirmed batch and all the data it wrote."""
    if batch.status != "confirmed":
        raise ValueError("只能删除已确认入库的批次")
    delete_batch_data(db, batch.id)
    db.delete(batch)
    db.commit()


def reassign_month(db: Session, batch: UploadBatch, new_month: str) -> None:
    """Moves every row a confirmed batch wrote over to a different month.

    Refuses if the target (new_month, salary_type) slot is already occupied
    by a different confirmed batch - the caller must delete or move that one
    first, rather than this silently superseding it (a month reassignment is
    a correction, not a new upload, so it shouldn't have re-upload's
    supersede-on-confirm behavior).
    """
    if batch.status != "confirmed":
        raise ValueError("只能修改已确认入库的批次的月份")
    if new_month == batch.month:
        return

    conflict = (
        db.query(UploadBatch)
        .filter(
            UploadBatch.month == new_month,
            UploadBatch.salary_type == batch.salary_type,
            UploadBatch.status == "confirmed",
            UploadBatch.id != batch.id,
        )
        .first()
    )
    if conflict:
        raise ValueError(f"{new_month} 已经有一个确认过的「{batch.salary_type}」批次（#{conflict.id}），请先删除或改掉那个批次的月份")

    db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.upload_batch_id == batch.id).update(
        {"month": new_month}
    )
    db.query(ExitRecord).filter(ExitRecord.upload_batch_id == batch.id).update({"exit_month": new_month})
    db.query(SupplementalPaySnapshot).filter(SupplementalPaySnapshot.upload_batch_id == batch.id).update(
        {"month": new_month}
    )
    db.query(MonthlyBonusSnapshot).filter(MonthlyBonusSnapshot.upload_batch_id == batch.id).update(
        {"payment_month": new_month, "performance_month": shift_month(new_month, BONUS_MONTH_OFFSET)}
    )
    db.query(DataQualityLog).filter(DataQualityLog.upload_batch_id == batch.id).update({"month": new_month})

    batch.month = new_month
    db.commit()
