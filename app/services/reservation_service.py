from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.time import kst_day_range, to_utc_naive, utc_now
from app.models import Reservation, ReservationStatus, Resource, User, UserRole
from app.schemas.reservation import ReservationCreate
from app.services import resource_service

OVERLAP_MESSAGE = "이미 예약된 시간대와 겹칩니다."
INACTIVE_RESOURCE_MESSAGE = "비활성화된 자원은 예약할 수 없습니다."
NOT_FOUND_MESSAGE = "예약을 찾을 수 없습니다."
ALREADY_CANCELLED_MESSAGE = "이미 취소된 예약입니다."
ALREADY_STARTED_MESSAGE = "이미 시작된 예약은 취소할 수 없습니다."


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


def get_reservation(db: Session, user: User, reservation_id: int) -> Reservation:
    """본인의 예약만 볼 수 있다. 관리자는 모든 예약을 볼 수 있다.

    남의 예약이면 403이 아니라 404를 돌려준다. 403이면 "그 번호의 예약이 있다"는
    사실이 드러나기 때문이다. (예약 번호를 하나씩 넣어 보며 정보를 캐는 것을 막는다)
    """
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    if user.role is not UserRole.ADMIN and reservation.user_id != user.id:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    return reservation


def list_my_reservations(
    db: Session,
    user: User,
    *,
    include_past: bool,
    include_cancelled: bool,
    limit: int,
    offset: int,
) -> tuple[list[Reservation], int]:
    conditions = [Reservation.user_id == user.id]
    if not include_past:
        # 아직 끝나지 않은 예약 (진행 중인 예약도 포함)
        conditions.append(Reservation.end_at > utc_now())
    if not include_cancelled:
        conditions.append(Reservation.status == ReservationStatus.CONFIRMED)

    total = db.scalar(select(func.count()).select_from(Reservation).where(*conditions)) or 0
    # 정렬 순서가 인덱스 (user_id, start_at) 순서와 같다. InnoDB 보조 인덱스에는 기본키(id)가
    # 뒤에 붙어 있으므로 (start_at, id) 정렬도 인덱스 순서 그대로다.
    items = db.scalars(
        select(Reservation)
        .where(*conditions)
        .order_by(Reservation.start_at, Reservation.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def list_resource_schedule(db: Session, resource_id: int, day: date) -> list[Reservation]:
    """자원의 하루(한국 날짜) 일정. 확정된 예약 중 그날과 겹치는 것을 시간순으로 돌려준다.

    "그날 시작한 예약"이 아니라 "그날과 겹치는 예약"이다. 전날 23시~다음 날 01시 예약도
    포함해야 일정표에 빈 시간이 잘못 보이지 않는다.
    """
    resource_service.get_resource(db, resource_id)  # 없는 자원이면 404
    day_start, day_end = kst_day_range(day)
    return list(
        db.scalars(
            select(Reservation)
            .where(
                Reservation.resource_id == resource_id,
                Reservation.status == ReservationStatus.CONFIRMED,
                Reservation.start_at < day_end,
                Reservation.end_at > day_start,
            )
            .order_by(Reservation.start_at)
        ).all()
    )


def cancel_reservation(db: Session, user: User, reservation_id: int) -> Reservation:
    """예약을 취소한다. 행을 지우지 않고 status를 CANCELLED로 바꾼다. (소프트 삭제)

    상태 변경은 조건부 UPDATE 한 문장으로 한다.

        UPDATE reservations SET status = 'CANCELLED', cancelled_at = NOW()
        WHERE id = ? AND status = 'CONFIRMED'

    "읽어서 CONFIRMED인지 확인 → 객체 값을 바꿔 저장"으로 하면 같은 예약에 대한 취소
    요청 두 개가 동시에 둘 다 CONFIRMED를 보고 둘 다 성공한다(cancelled_at도 덮어씀).
    조건부 UPDATE는 DB가 행을 잠그고 조건을 다시 확인하므로, 먼저 바꾼 쪽만 1행이
    바뀌고 나중 쪽은 0행이 된다. 바뀐 행 수(rowcount)로 성공 여부를 판단한다.
    별도 락(FOR UPDATE)이 필요 없다.
    """
    reservation = get_reservation(db, user, reservation_id)
    if reservation.status is ReservationStatus.CANCELLED:
        raise ConflictError(ALREADY_CANCELLED_MESSAGE)
    # start_at은 바뀌지 않는 값이라, 이 검사는 UPDATE 조건에 넣지 않아도 안전하다.
    if reservation.start_at <= utc_now():
        raise ConflictError(ALREADY_STARTED_MESSAGE)

    result = db.execute(
        update(Reservation)
        .where(
            Reservation.id == reservation.id,
            Reservation.status == ReservationStatus.CONFIRMED,
        )
        .values(status=ReservationStatus.CANCELLED, cancelled_at=func.current_timestamp())
        # 세션의 객체는 아래 refresh로 다시 읽으므로 SQLAlchemy가 따로 맞추지 않게 한다.
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        # 위에서 확인한 뒤 그 사이에 다른 요청이 먼저 취소했다.
        db.rollback()
        raise ConflictError(ALREADY_CANCELLED_MESSAGE)
    db.commit()
    db.refresh(reservation)
    return reservation
