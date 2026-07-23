from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..qa.answer import answer_question
from ..schemas import ChatRequest
from ..security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
def chat(payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return answer_question(db, user, payload.question)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
