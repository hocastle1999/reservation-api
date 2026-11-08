from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.time import to_utc_naive
from app.models import Reservation, ReservationStatus, Resource, User
from app.schemas.reservation import ReservationCreate

OVERLAP_MESSAGE = "이미 예약된 시간대와 겹칩니다."
INACTIVE_RESOURCE_MESSAGE = "비활성화된 자원은 예약할 수 없습니다."


def create_reservation(db: Session, user: User, data: ReservationCreate) -> Reservation:
    """겹치는 예약이 없을 때만 예약을 만든다. (비관적 락, docs/erd.md 참고)

    "겹치는 예약이 있는지 조회 → 없으면 INSERT"를 그냥 하면, 동시에 들어온 두 요청이
    둘 다 "없음"을 보고 둘 다 INSERT할 수 있다. 그래서 먼저 자원 행을 FOR UPDATE로
    잠근다. 같은 자원에 대한 예약 요청은 이 줄에서 한 줄로 서고, 앞 요청이 커밋(또는
    롤백)해 락을 풀어야 다음 요청이 겹침 검사를 시작한다.
    """
    start_at = to_utc_naive(data.start_at)
    end_at = to_utc_naive(data.end_at)

    # SELECT ... FROM resources WHERE id = ? FOR UPDATE
    # populate_existing: 같은 세션에 이미 읽어 둔 자원 객체가 있어도, 락을 잡으면서 읽은
    # 최신 값(is_active 등)으로 덮어쓴다.
    resource = db.scalar(
        select(Resource)
        .where(Resource.id == data.resource_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None:
        db.rollback()
        raise NotFoundError("자원을 찾을 수 없습니다.")
    if not resource.is_active:
        db.rollback()  # 락을 바로 풀어 준다.
        raise ConflictError(INACTIVE_RESOURCE_MESSAGE)

    # 두 구간이 겹치는 조건: A.start < B.end AND B.start < A.end
    # 끝 시각과 다음 예약의 시작 시각이 같으면(10~11시, 11~12시) 겹치지 않는다.
    # 인덱스 (resource_id, start_at)로 자원을 먼저 좁힌 뒤 시간 범위를 본다.
    overlapping_id = db.scalar(
        select(Reservation.id)
        .where(
            Reservation.resource_id == resource.id,
            Reservation.status == ReservationStatus.CONFIRMED,
            Reservation.start_at < end_at,
            Reservation.end_at > start_at,
        )
        .limit(1)
    )
    if overlapping_id is not None:
        db.rollback()
        raise ConflictError(OVERLAP_MESSAGE)

    reservation = Reservation(
        resource_id=resource.id,
        user_id=user.id,
        start_at=start_at,
        end_at=end_at,
        purpose=data.purpose,
    )
    db.add(reservation)
    # 커밋하는 순간 INSERT가 확정되고 자원 행의 락이 풀린다.
    db.commit()
    # status, created_at 같은 DB 기본값을 읽어 온다.
    db.refresh(reservation)
    return reservation
