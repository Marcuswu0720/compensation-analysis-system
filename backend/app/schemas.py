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


class AttributionRequest(BaseModel):
    department: str | None = None
    entity: str | None = None
    prev_month: str
    cur_month: str


class ReassignMonthRequest(BaseModel):
    new_month: str
