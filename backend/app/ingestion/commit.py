"""Materializes a reviewed & confirmed UploadBatch into the real snapshot tables."""

import json

from sqlalchemy.orm import Session

from ..models import DataQualityLog, ExitRecord, MonthlyBonusSnapshot, MonthlyEmployeeSnapshot, UploadBatch


def confirm_upload(db: Session, batch: UploadBatch) -> None:
    if batch.status == "confirmed":
        raise ValueError("该批次已确认，不能重复确认")

    payload = json.loads(batch.staged_data)

    # Re-uploading the same month replaces its prior data outright (a corrected
    # file supersedes the previous one; we don't try to merge two versions).
    db.query(MonthlyEmployeeSnapshot).filter(MonthlyEmployeeSnapshot.month == batch.month).delete()
    db.query(ExitRecord).filter(ExitRecord.exit_month == batch.month).delete()
    db.query(MonthlyBonusSnapshot).filter(MonthlyBonusSnapshot.payment_month == batch.month).delete()

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

    from datetime import datetime

    batch.status = "confirmed"
    batch.confirmed_at = datetime.utcnow()
    db.commit()
