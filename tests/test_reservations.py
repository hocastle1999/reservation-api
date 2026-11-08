from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import Reservation, ReservationStatus, Resource
from tests.conftest import auth_header

# 테스트 시각은 모두 먼 미래로 둔다. (과거 시각은 예약할 수 없으므로)
DAY = "2030-01-07"


def kst(hhmm: str, day: str = DAY) -> str:
    return f"{day}T{hhmm}:00+09:00"


@pytest.fixture
def resource(db_session) -> Resource:
    resource = Resource(name="회의실 A", capacity=6)
    db_session.add(resource)
    db_session.commit()
    return resource


@pytest.fixture
def client(client, user):
    """이 파일의 테스트는 일반 사용자로 로그인한 상태에서 실행한다."""
    client.headers.update(auth_header(user))
    return client


def reserve(client, resource_id: int, start: str, end: str, **overrides):
    body = {"resource_id": resource_id, "start_at": start, "end_at": end} | overrides
    return client.post("/reservations", json=body)


# --- 생성 -------------------------------------------------------------------


def test_create_reservation_returns_201_in_kst(client, resource, user):
    response = reserve(client, resource.id, kst("10:00"), kst("11:00"), purpose="주간 회의")

    assert response.status_code == 201
    body = response.json()
    assert body["resource_id"] == resource.id
    assert body["user_id"] == user.id
    assert body["start_at"] == "2030-01-07T10:00:00+09:00"
    assert body["end_at"] == "2030-01-07T11:00:00+09:00"
    assert body["status"] == "CONFIRMED"
    assert body["purpose"] == "주간 회의"
    assert body["cancelled_at"] is None


def test_reservation_is_stored_in_utc(client, resource, db_session):
    reservation_id = reserve(client, resource.id, kst("10:00"), kst("11:00")).json()["id"]

    stored = db_session.get(Reservation, reservation_id)

    # 한국 시간 10:00 = UTC 01:00
    assert stored.start_at == datetime(2030, 1, 7, 1, 0)
    assert stored.end_at == datetime(2030, 1, 7, 2, 0)


def test_create_accepts_any_utc_offset(client, resource):
    response = reserve(client, resource.id, "2030-01-07T01:00:00Z", "2030-01-07T02:00:00Z")

    assert response.status_code == 201
    assert response.json()["start_at"] == "2030-01-07T10:00:00+09:00"


def test_create_requires_login(client, resource):
    client.headers.pop("Authorization")

    response = reserve(client, resource.id, kst("10:00"), kst("11:00"))

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("start", "end", "overrides"),
    [
        ("2030-01-07T10:00:00", "2030-01-07T11:00:00", {}),
        (kst("11:00"), kst("10:00"), {}),
        (kst("10:00"), kst("10:00"), {}),
        ("2030-01-07T10:00:30+09:00", kst("11:00"), {}),
        ("2030-01-07T10:00:00.5+09:00", kst("11:00"), {}),
        (kst("10:00", "2020-01-01"), kst("11:00", "2020-01-01"), {}),
        (kst("10:00"), kst("11:00"), {"purpose": "가" * 201}),
        (kst("10:00"), kst("11:00"), {"unknown_field": "x"}),
    ],
    ids=[
        "naive-datetime",
        "end-before-start",
        "zero-length",
        "seconds",
        "fractional-seconds",
        "past",
        "purpose-too-long",
        "extra",
    ],
)
def test_create_with_invalid_body_returns_422(client, resource, start, end, overrides):
    assert reserve(client, resource.id, start, end, **overrides).status_code == 422


def test_create_for_unknown_resource_returns_404(client):
    response = reserve(client, 999999, kst("10:00"), kst("11:00"))

    assert response.status_code == 404


def test_create_for_inactive_resource_returns_409(client, resource, db_session):
    resource.is_active = False
    db_session.commit()

    response = reserve(client, resource.id, kst("10:00"), kst("11:00"))

    assert response.status_code == 409
    assert response.json() == {"detail": "비활성화된 자원은 예약할 수 없습니다."}


# --- 겹침 검사 ---------------------------------------------------------------
# 기존 예약: 10:00 ~ 12:00


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("10:00", "12:00"),
        ("09:00", "13:00"),
        ("10:30", "11:30"),
        ("09:00", "10:30"),
        ("11:30", "13:00"),
        ("11:59", "12:30"),
    ],
    ids=["same", "covers", "inside", "overlaps-start", "overlaps-end", "one-minute"],
)
def test_overlapping_reservation_returns_409(client, resource, start, end):
    assert reserve(client, resource.id, kst("10:00"), kst("12:00")).status_code == 201

    response = reserve(client, resource.id, kst(start), kst(end))

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 예약된 시간대와 겹칩니다."}


@pytest.mark.parametrize(
    ("start", "end"),
    [("09:00", "10:00"), ("12:00", "13:00")],
    ids=["ends-when-existing-starts", "starts-when-existing-ends"],
)
def test_adjacent_reservation_is_allowed(client, resource, start, end):
    assert reserve(client, resource.id, kst("10:00"), kst("12:00")).status_code == 201

    assert reserve(client, resource.id, kst(start), kst(end)).status_code == 201


def test_same_time_on_another_resource_is_allowed(client, resource, db_session):
    other = Resource(name="회의실 B", capacity=4)
    db_session.add(other)
    db_session.commit()
    assert reserve(client, resource.id, kst("10:00"), kst("12:00")).status_code == 201

    assert reserve(client, other.id, kst("10:00"), kst("12:00")).status_code == 201


def test_cancelled_reservation_does_not_block(client, resource, db_session, user):
    db_session.add(
        Reservation(
            resource_id=resource.id,
            user_id=user.id,
            start_at=datetime(2030, 1, 7, 1, 0),
            end_at=datetime(2030, 1, 7, 3, 0),
            status=ReservationStatus.CANCELLED,
            cancelled_at=datetime(2029, 12, 31, 0, 0),
        )
    )
    db_session.commit()

    response = reserve(client, resource.id, kst("10:00"), kst("12:00"))

    assert response.status_code == 201
    confirmed = db_session.scalars(
        select(Reservation).where(Reservation.status == ReservationStatus.CONFIRMED)
    ).all()
    assert len(confirmed) == 1
