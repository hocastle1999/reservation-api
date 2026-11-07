from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict[str, str]:
    """서버 프로세스가 살아 있는지만 확인한다. (배포 서비스의 헬스 체크용)"""
    return {"status": "ok"}


@router.get("/db")
def health_db(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """DB까지 연결되는지 확인한다."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ok", "database": "ok"}
