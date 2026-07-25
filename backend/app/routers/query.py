from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..compute.attribution import compute_attribution, flatten_attribution
from ..compute.categories import CATEGORY_FIELDS, compare_departments_by_category, get_categories_trend, get_cost_composition
from ..compute.trends import get_trend, list_available_months, list_departments, list_entities
from ..database import get_db
from ..models import User
from ..schemas import AttributionRequest, CategoryCompareRequest, CategoryTrendRequest, CompositionRequest, TrendRequest
from ..security import get_allowed_scope, get_current_user, resolve_requested_filters

router = APIRouter(prefix="/api", tags=["query"])


@router.get("/meta")
def meta(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = get_allowed_scope(db, user)
    return {
        "departments": list_departments(db, scope_rules=scope.rules),
        "entities": list_entities(db, scope_rules=scope.rules),
        "months": list_available_months(db),
        "categories": [{"value": k, "label": v} for k, v in CATEGORY_FIELDS.items()],
    }


@router.post("/trend")
def trend(payload: TrendRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = get_allowed_scope(db, user)
    department, entity = resolve_requested_filters(scope, payload.department, payload.entity)
    months = None
    if payload.start_month and payload.end_month:
        available = list_available_months(db)
        months = [m for m in available if payload.start_month <= m <= payload.end_month]
    return get_trend(db, months=months, department=department, entity=entity, scope_rules=scope.rules)


@router.post("/attribution")
def attribution(payload: AttributionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = get_allowed_scope(db, user)
    department, entity = resolve_requested_filters(scope, payload.department, payload.entity)
    result = compute_attribution(
        db,
        prev_month=payload.prev_month,
        cur_month=payload.cur_month,
        department=department,
        entity=entity,
        scope_rules=scope.rules,
    )
    result_dict = asdict(result)
    result_dict["flat_items"] = [asdict(i) for i in flatten_attribution(result)]
    if user.role != "admin":
        for key in ("top_increases", "top_decreases"):
            for item in result_dict.get(key, []):
                item["name"] = "[无权限查看，仅管理员可见]"
                item["staff_id"] = "[隐藏]"
    return result_dict


@router.post("/category-trend")
def category_trend(payload: CategoryTrendRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.categories:
        raise HTTPException(status_code=400, detail="请至少选择一个薪资类目")
    if payload.employment_type not in (None, "Formal", "Contract"):
        raise HTTPException(status_code=400, detail="employment_type 只能是 Formal、Contract 或不填（表示全部）")
    scope = get_allowed_scope(db, user)
    department, entity = resolve_requested_filters(scope, payload.department, payload.entity)
    months = None
    if payload.start_month and payload.end_month:
        available = list_available_months(db)
        months = [m for m in available if payload.start_month <= m <= payload.end_month]
    try:
        return get_categories_trend(
            db,
            categories=payload.categories,
            months=months,
            department=department,
            entity=entity,
            scope_rules=scope.rules,
            employment_type=payload.employment_type,
            per_capita=payload.per_capita,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/category-compare")
def category_compare(payload: CategoryCompareRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = get_allowed_scope(db, user)
    _, entity = resolve_requested_filters(scope, None, payload.entity)
    try:
        return compare_departments_by_category(
            db, category=payload.category, month=payload.month, entity=entity, scope_rules=scope.rules
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/composition")
def composition(payload: CompositionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = get_allowed_scope(db, user)
    department, entity = resolve_requested_filters(scope, payload.department, payload.entity)
    return get_cost_composition(db, month=payload.month, department=department, entity=entity, scope_rules=scope.rules)
