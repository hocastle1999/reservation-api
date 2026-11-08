"""동시에 들어온 예약 요청에서도 겹치는 예약이 하나만 만들어지는지 확인한다.

다른 테스트와 달리 여기서는 트랜잭션 롤백 픽스처(db_session)를 쓰지 않는다.
락은 서로 다른 DB 연결(트랜잭션) 사이에서만 의미가 있기 때문이다. 스레드마다
자기 세션을 열어 실제로 커밋하고, 테스트가 끝나면 만든 데이터를 직접 지운다.
"""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.exceptions import ConflictError
from app.core.time import KST
from app.db.session import SessionLocal
from app.models import Reservation, Resource, User
from app.schemas.reservation import ReservationCreate
from app.services import reservation_service

THREADS = 10


@pytest.fixture
def committed(db_connection):
    """실제로 커밋된 사용자와 자원. (db_connection: 마이그레이션이 먼저 적용되게 한다)"""
    with SessionLocal() as db:
        user = User(email="concurrency@example.com", password_hash="unused", name="동시성")
        resource = Resource(name="동시성 테스트 회의실", capacity=4)
        db.add_all([user, resource])
        db.commit()
        user_id, resource_id = user.id, resource.id

    yield user_id, resource_id

    with SessionLocal() as db:
        db.execute(delete(Reservation).where(Reservation.resource_id == resource_id))
        db.execute(delete(Resource).where(Resource.id == resource_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()


def run_concurrently(user_id: int, requests: list[ReservationCreate]) -> Counter:
    barrier = threading.Barrier(len(requests))

    def attempt(data: ReservationCreate) -> str:
        with SessionLocal() as db:
            # 실제 요청에서도 인증 의존성(get_current_user)이 예약 전에 사용자를 먼저 읽는다.
            # 이 첫 SELECT에서 트랜잭션이 시작된다.
            user = db.get(User, user_id)
            # 모든 스레드가 여기까지 온 뒤 동시에 예약을 시도한다.
            barrier.wait()
            try:
                reservation_service.create_reservation(db, user, data)
                return "created"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return Counter(pool.map(attempt, requests))


def count_reservations(resource_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(Reservation.resource_id == resource_id)
        )


def test_only_one_of_concurrent_overlapping_requests_succeeds(committed):
    user_id, resource_id = committed
    start = datetime(2030, 1, 7, 10, 0, tzinfo=KST)
    same_slot = ReservationCreate(
        resource_id=resource_id, start_at=start, end_at=start + timedelta(hours=1)
    )

    results = run_concurrently(user_id, [same_slot] * THREADS)

    assert results == Counter(created=1, conflict=THREADS - 1)
    assert count_reservations(resource_id) == 1


def test_concurrent_non_overlapping_requests_all_succeed(committed):
    # 락은 "같은 자원의 요청을 한 줄로 세울" 뿐, 겹치지 않는 예약까지 막으면 안 된다.
    user_id, resource_id = committed
    base = datetime(2030, 1, 7, 9, 0, tzinfo=KST)
    slots = [
        ReservationCreate(
            resource_id=resource_id,
            start_at=base + timedelta(hours=i),
            end_at=base + timedelta(hours=i + 1),
        )
        for i in range(THREADS)
    ]

    results = run_concurrently(user_id, slots)

    assert results == Counter(created=THREADS)
    assert count_reservations(resource_id) == THREADS
