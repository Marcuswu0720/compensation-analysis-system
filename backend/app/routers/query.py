from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..compute.attribution import compute_attribution
from ..compute.trends import get_trend, list_available_months, list_departments, list_entities
from ..database import get_db
from ..models import User
from ..schemas import AttributionRequest, TrendRequest
from ..security import get_current_user

router = APIRouter(prefix="/api", tags=["query"])


@router.get("/meta")
def meta(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {
        "departments": list_departments(db),
        "entities": list_entities(db),
        "months": list_available_months(db),
    }


@router.post("/trend")
def trend(payload: TrendRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    months = None
    if payload.start_month and payload.end_month:
        available = list_available_months(db)
        months = [m for m in available if payload.start_month <= m <= payload.end_month]
    return get_trend(db, months=months, department=payload.department, entity=payload.entity)


@router.post("/attribution")
def attribution(payload: AttributionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    result = compute_attribution(
        db,
        prev_month=payload.prev_month,
        cur_month=payload.cur_month,
        department=payload.department,
        entity=payload.entity,
    )
    result_dict = asdict(result)
    if user.role != "admin":
        for key in ("top_increases", "top_decreases"):
            for item in result_dict.get(key, []):
                item["name"] = "[无权限查看，仅管理员可见]"
                item["staff_id"] = "[隐藏]"
    return result_dict
