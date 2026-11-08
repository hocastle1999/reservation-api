import logging
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.core.time import kst_day_range, to_utc_naive, utc_now
from app.db.errors import is_deadlock, is_duplicate_entry
from app.models import (
    MAX_DURATION,
    SLOT_MINUTES,
    Reservation,
    ReservationSlot,
    ReservationStatus,
    Resource,
    User,
    UserRole,
)
from app.schemas.reservation import ReservationCreate
from app.services import resource_service

logger = logging.getLogger(__name__)

OVERLAP_MESSAGE = "이미 예약된 시간대와 겹칩니다."
INACTIVE_RESOURCE_MESSAGE = "비활성화된 자원은 예약할 수 없습니다."
NOT_FOUND_MESSAGE = "예약을 찾을 수 없습니다."
ALREADY_CANCELLED_MESSAGE = "이미 취소된 예약입니다."
ALREADY_STARTED_MESSAGE = "이미 시작된 예약은 취소할 수 없습니다."
BUSY_MESSAGE = "요청이 몰려 예약을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."

# 데드락이 났을 때 처음 시도를 포함해 몇 번까지 해 볼지.
DEADLOCK_RETRIES = 3


def create_reservation(db: Session, user: User, data: ReservationCreate) -> Reservation:
    """겹치는 예약이 없을 때만 예약을 만든다.

    "겹치는 예약이 있는지 조회 → 없으면 INSERT"를 그냥 하면, 동시에 들어온 두 요청이
    둘 다 "없음"을 보고 둘 다 INSERT할 수 있다. 이를 막는 방식을 두 가지 구현했고,
    설정(RESERVATION_STRATEGY)으로 고른다. 비교는 docs/erd.md에 있다.
    """
    create = (
        _create_with_slots if get_settings().reservation_strategy == "slot" else _create_with_lock
    )
    # 데드락(MySQL 1213)이 나면 트랜잭션을 처음부터 다시 시도한다.
    # 부하 측정에서 방법 B가 실제로 데드락을 냈다(docs/troubleshooting.md). InnoDB는 데드락이
    # 나면 한쪽 트랜잭션을 통째로 롤백할 뿐이고, 그 요청이 틀린 것은 아니다. 그래서 409로
    # 거절하지 않고 다시 시도한다. MySQL 문서도 "데드락으로 실패한 트랜잭션은 다시 실행할
    # 준비를 하라"고 권한다. 롤백된 트랜잭션은 아무것도 남기지 않으므로 다시 해도 안전하다.
    for attempt in range(1, DEADLOCK_RETRIES + 1):
        try:
            return create(db, user, data)
        except OperationalError as exc:
            db.rollback()
            if not is_deadlock(exc):
                raise
            # 재시도로 사용자에게 안 보이는 데드락도 로그로 남겨 발생 빈도를 알 수 있게 한다.
            logger.warning(
                "예약 생성 중 데드락 (%d/%d회째, resource_id=%s)",
                attempt,
                DEADLOCK_RETRIES,
                data.resource_id,
            )
            if attempt == DEADLOCK_RETRIES:
                raise ServiceUnavailableError(BUSY_MESSAGE) from exc
    raise AssertionError("unreachable")


def _create_with_lock(db: Session, user: User, data: ReservationCreate) -> Reservation:
    """방법 A: 자원 행을 FOR UPDATE로 잠근 뒤 겹침 검사.

    같은 자원에 대한 예약 요청은 락을 잡는 줄에서 한 줄로 서고, 앞 요청이 커밋(또는
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
    _ensure_reservable(db, resource)

    # 두 구간이 겹치는 조건: A.start < B.end AND B.start < A.end
    # 끝 시각과 다음 예약의 시작 시각이 같으면(10~11시, 11~12시) 겹치지 않는다.
    overlapping_id = db.scalar(
        select(Reservation.id)
        .where(
            Reservation.resource_id == resource.id,
            Reservation.status == ReservationStatus.CONFIRMED,
            *_overlap_conditions(start_at, end_at),
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


def _create_with_slots(db: Session, user: User, data: ReservationCreate) -> Reservation:
    """방법 B: 예약이 차지하는 30분 칸을 reservation_slots에 함께 INSERT한다.

    겹침 검사 SELECT도, 락도 없다. 기본키 (resource_id, slot_start)가 있어서 다른 확정
    예약이 이미 차지한 칸이 하나라도 있으면 INSERT가 중복 키 오류(1062)로 실패한다.
    그러면 예약 행까지 통째로 롤백하고 409로 바꾼다. (자원 이름 중복과 같은 방식)
    """
    start_at = to_utc_naive(data.start_at)
    end_at = to_utc_naive(data.end_at)

    resource = db.get(Resource, data.resource_id, populate_existing=True)
    _ensure_reservable(db, resource)

    reservation = Reservation(
        resource_id=resource.id,
        user_id=user.id,
        start_at=start_at,
        end_at=end_at,
        purpose=data.purpose,
    )
    db.add(reservation)
    try:
        db.flush()  # 칸 행에 넣을 reservation.id를 얻는다.
        # 칸은 항상 시간순으로 넣는다. 트랜잭션들이 같은 순서로 행 락을 잡게 해서
        # "서로가 가진 칸을 기다리는" 순환 대기를 줄이기 위해서다.
        db.add_all(
            ReservationSlot(resource_id=resource.id, slot_start=slot, reservation_id=reservation.id)
            for slot in _slot_starts(start_at, end_at)
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if is_duplicate_entry(exc):
            raise ConflictError(OVERLAP_MESSAGE) from exc
        raise
    db.refresh(reservation)
    return reservation


def _slot_starts(start_at: datetime, end_at: datetime) -> list[datetime]:
    """[start_at, end_at) 구간을 덮는 칸의 시작 시각들. 10:00~11:00 → [10:00, 10:30]"""
    step = timedelta(minutes=SLOT_MINUTES)
    slots = []
    slot = start_at
    while slot < end_at:
        slots.append(slot)
        slot += step
    return slots


def _overlap_conditions(start_at: datetime, end_at: datetime) -> list[ColumnElement[bool]]:
    """[start_at, end_at)와 겹치는 예약을 찾는 조건. 인덱스 (resource_id, start_at)를 쓴다.

    겹침 조건만으로는 start_at의 아래쪽 범위가 열려 있다(start_at < end_at). 그러면 인덱스가
    그 자원의 과거 예약을 전부 훑는다. 과거 예약 2만 건이 있을 때 검사 한 번이 2만 행을 읽었고,
    방법 A의 처리량이 233건/초에서 14건/초로 떨어졌다(docs/troubleshooting.md).

    예약은 최대 MAX_DURATION(8시간)이므로, 겹치는 예약은 반드시
    start_at > (찾는 구간의 시작 - 8시간)이다. 이 하한을 넣어 읽는 범위를 8시간 안으로 줄인다.
    상한은 입력 검증과 DB CHECK 제약(ck_reservations_duration)이 함께 보장한다.
    """
    return [
        Reservation.start_at > start_at - MAX_DURATION,
        Reservation.start_at < end_at,
        Reservation.end_at > start_at,
    ]


def _ensure_reservable(db: Session, resource: Resource | None) -> None:
    if resource is None:
        db.rollback()
        raise NotFoundError("자원을 찾을 수 없습니다.")
    if not resource.is_active:
        db.rollback()  # 락을 잡았다면 바로 풀어 준다.
        raise ConflictError(INACTIVE_RESOURCE_MESSAGE)


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
                *_overlap_conditions(day_start, day_end),
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
    # 방법 B의 칸을 비워 그 시간대를 다시 예약할 수 있게 한다. 상태 변경과 같은 트랜잭션이라
    # 둘 중 하나만 반영되는 일은 없다. 방법 A로 만든 예약은 칸이 없으므로 0행이 지워진다.
    db.execute(delete(ReservationSlot).where(ReservationSlot.reservation_id == reservation.id))
    db.commit()
    db.refresh(reservation)
    return reservation
