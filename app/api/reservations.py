from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.reservation import ReservationCreate, ReservationRead
from app.services import reservation_service

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post(
    "",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "로그인하지 않음"},
        status.HTTP_404_NOT_FOUND: {"description": "자원이 없음"},
        status.HTTP_409_CONFLICT: {"description": "겹치는 예약이 있거나 비활성 자원"},
    },
    summary="예약 생성",
    description=(
        "시각은 시간대를 포함해 보낸다 (예: `2030-01-07T10:00:00+09:00`). "
        "분 단위만 받고, 응답은 한국 시간으로 돌려준다. "
        "같은 자원의 확정된 예약과 시간이 겹치면 409를 돌려준다. "
        "끝 시각과 다음 예약의 시작 시각이 같은 것은 겹치지 않는 것으로 본다."
    ),
)
def create_reservation(data: ReservationCreate, db: DbSession, user: CurrentUser):
    return reservation_service.create_reservation(db, user, data)
