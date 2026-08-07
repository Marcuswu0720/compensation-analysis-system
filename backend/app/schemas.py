from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class ChatRequest(BaseModel):
    question: str


class TrendRequest(BaseModel):
    department: str | None = None
    entity: str | None = None
    start_month: str | None = None
    end_month: str | None = None
    employment_type: str | None = None  # None (全部) | "Formal" | "Contract"


class AttributionRequest(BaseModel):
    department: str | None = None
    entity: str | None = None
    prev_month: str
    cur_month: str
    employment_type: str | None = None  # None (全部) | "Formal" | "Contract"


class ReassignMonthRequest(BaseModel):
    new_month: str


class CategoryTrendRequest(BaseModel):
    categories: list[str]
    department: str | None = None
    entity: str | None = None
    start_month: str | None = None
    end_month: str | None = None
    employment_type: str | None = None  # None (全部) | "Formal" | "Contract" - PRD V1.9
    per_capita: bool = False  # PRD V1.9 §2: also returns per_capita + median alongside categories


class CategoryCompareRequest(BaseModel):
    category: str
    month: str
    entity: str | None = None


class CompositionRequest(BaseModel):
    month: str
    department: str | None = None
    entity: str | None = None


class GrantPermissionRequest(BaseModel):
    scope_type: str  # 'entity' | 'entity_department'
    entity: str
    department1: str | None = None  # required iff scope_type == 'entity_department'


class SetUserActiveRequest(BaseModel):
    is_active: bool


class ResetPasswordRequest(BaseModel):
    new_password: str


class ExportDetailRequest(BaseModel):
    department: str | None = None
    entity: str | None = None
    start_month: str | None = None
    end_month: str | None = None
    salary_types: list[str] | None = None  # subset of base/bonus/backpay; None/[] = all three
