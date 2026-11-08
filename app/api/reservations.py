from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.reservation import ReservationCreate, ReservationList, ReservationRead
from app.services import reservation_service

router = APIRouter(prefix="/reservations", tags=["reservations"])

UNAUTHORIZED = {status.HTTP_401_UNAUTHORIZED: {"description": "로그인하지 않음"}}
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "예약이 없거나 내 예약이 아님"}}


@router.post(
    "",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        **UNAUTHORIZED,
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


# /me는 /{reservation_id}보다 먼저 등록해야 한다. 경로는 등록 순서대로 비교되는데,
# 뒤에 두면 "me"가 {reservation_id}에 먼저 걸려 정수 변환 오류(422)가 난다.
@router.get(
    "/me",
    response_model=ReservationList,
    responses=UNAUTHORIZED,
    summary="내 예약 목록",
    description="시작 시각 순서로 돌려준다. 기본값은 끝나지 않은 확정 예약만이다.",
)
def list_my_reservations(
    db: DbSession,
    user: CurrentUser,
    include_past: Annotated[bool, Query(description="이미 끝난 예약도 포함")] = False,
    include_cancelled: Annotated[bool, Query(description="취소한 예약도 포함")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = reservation_service.list_my_reservations(
        db,
        user,
        include_past=include_past,
        include_cancelled=include_cancelled,
        limit=limit,
        offset=offset,
    )
    return ReservationList(items=items, total=total)


@router.get(
    "/{reservation_id}",
    response_model=ReservationRead,
    responses={**UNAUTHORIZED, **NOT_FOUND},
    summary="예약 상세",
    description="본인의 예약만 볼 수 있다. 관리자는 모든 예약을 볼 수 있다.",
)
def get_reservation(reservation_id: int, db: DbSession, user: CurrentUser):
    return reservation_service.get_reservation(db, user, reservation_id)


@router.post(
    "/{reservation_id}/cancel",
    response_model=ReservationRead,
    responses={
        **UNAUTHORIZED,
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": "이미 취소했거나 이미 시작된 예약"},
    },
    summary="예약 취소",
    description=(
        "본인의 예약만 취소할 수 있다. 관리자는 모든 예약을 취소할 수 있다. "
        "예약은 지우지 않고 상태를 CANCELLED로 바꾼다. 이미 시작된 예약은 취소할 수 없다."
    ),
)
def cancel_reservation(reservation_id: int, db: DbSession, user: CurrentUser):
    return reservation_service.cancel_reservation(db, user, reservation_id)
