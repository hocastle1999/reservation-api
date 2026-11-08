from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models import Reservation, ReservationSlot, ReservationStatus, Resource
from tests.conftest import auth_header, make_user

# 이 파일의 모든 테스트를 방법 A(lock)와 방법 B(slot)로 한 번씩 실행한다.
pytestmark = pytest.mark.usefixtures("reservation_strategy")

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


def test_slot_boundary_is_checked_in_utc(client, resource):
    # +05:45(네팔)의 10:15는 UTC 04:30이라 30분 경계에 맞는다.
    response = reserve(
        client, resource.id, "2030-01-07T10:15:00+05:45", "2030-01-07T11:15:00+05:45"
    )

    assert response.status_code == 201
    assert response.json()["start_at"] == "2030-01-07T13:30:00+09:00"


def test_create_allows_max_duration(client, resource):
    assert reserve(client, resource.id, kst("09:00"), kst("17:00")).status_code == 201


def test_slots_are_stored_only_by_slot_strategy(client, resource, db_session, reservation_strategy):
    reservation_id = reserve(client, resource.id, kst("10:00"), kst("11:30")).json()["id"]

    slots = db_session.scalars(
        select(ReservationSlot.slot_start)
        .where(ReservationSlot.reservation_id == reservation_id)
        .order_by(ReservationSlot.slot_start)
    ).all()

    if reservation_strategy == "slot":
        # 한국 10:00 ~ 11:30 = UTC 01:00 ~ 02:30 → 칸 3개
        assert slots == [
            datetime(2030, 1, 7, 1, 0),
            datetime(2030, 1, 7, 1, 30),
            datetime(2030, 1, 7, 2, 0),
        ]
    else:
        assert slots == []


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
        (kst("10:15"), kst("11:00"), {}),
        (kst("10:00"), kst("10:45"), {}),
        # +05:45의 10:00은 UTC 04:15라 30분 경계가 아니다.
        ("2030-01-07T10:00:00+05:45", "2030-01-07T11:00:00+05:45", {}),
        (kst("09:00"), kst("17:30"), {}),
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
        "start-not-on-slot",
        "end-not-on-slot",
        "not-on-slot-in-utc",
        "longer-than-8-hours",
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
        ("11:30", "12:00"),
    ],
    ids=["same", "covers", "inside", "overlaps-start", "overlaps-end", "last-slot"],
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


# --- 조회 -------------------------------------------------------------------


def add_reservation(db, resource, user, start_utc, end_utc, status=ReservationStatus.CONFIRMED):
    """API를 거치지 않고 DB에 바로 넣는다. (과거 예약처럼 API로 만들 수 없는 데이터용)"""
    reservation = Reservation(
        resource_id=resource.id,
        user_id=user.id,
        start_at=start_utc,
        end_at=end_utc,
        status=status,
        purpose="비공개 목적",
    )
    db.add(reservation)
    db.commit()
    return reservation


@pytest.fixture
def other_user(db_session):
    return make_user(db_session, "other@example.com")


def test_get_own_reservation(client, resource):
    reservation_id = reserve(client, resource.id, kst("10:00"), kst("11:00")).json()["id"]

    response = client.get(f"/reservations/{reservation_id}")

    assert response.status_code == 200
    assert response.json()["id"] == reservation_id


def test_get_other_users_reservation_returns_404(client, resource, db_session, other_user):
    # 403이 아니라 404: 남의 예약이 "있다"는 사실도 알려 주지 않는다.
    others = add_reservation(
        db_session, resource, other_user, datetime(2030, 1, 7, 1), datetime(2030, 1, 7, 2)
    )

    response = client.get(f"/reservations/{others.id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "예약을 찾을 수 없습니다."}


def test_admin_can_get_any_reservation(client, resource, db_session, other_user, admin):
    others = add_reservation(
        db_session, resource, other_user, datetime(2030, 1, 7, 1), datetime(2030, 1, 7, 2)
    )

    response = client.get(f"/reservations/{others.id}", headers=auth_header(admin))

    assert response.status_code == 200


def test_get_unknown_reservation_returns_404(client):
    assert client.get("/reservations/999999").status_code == 404


def test_my_reservations_default_to_upcoming_confirmed(
    client, resource, db_session, user, other_user
):
    later = reserve(client, resource.id, kst("14:00"), kst("15:00")).json()["id"]
    sooner = reserve(client, resource.id, kst("10:00"), kst("11:00")).json()["id"]
    past = add_reservation(
        db_session, resource, user, datetime(2020, 1, 1, 1), datetime(2020, 1, 1, 2)
    )
    cancelled = add_reservation(
        db_session,
        resource,
        user,
        datetime(2030, 1, 8, 1),
        datetime(2030, 1, 8, 2),
        status=ReservationStatus.CANCELLED,
    )
    add_reservation(  # 남의 예약은 어떤 옵션으로도 나오지 않는다.
        db_session, resource, other_user, datetime(2030, 1, 9, 1), datetime(2030, 1, 9, 2)
    )

    default = client.get("/reservations/me").json()
    everything = client.get(
        "/reservations/me", params={"include_past": True, "include_cancelled": True}
    ).json()

    # 시작 시각 순서
    assert [r["id"] for r in default["items"]] == [sooner, later]
    assert default["total"] == 2
    assert [r["id"] for r in everything["items"]] == [past.id, sooner, later, cancelled.id]
    assert everything["total"] == 4


def test_my_reservations_paginates(client, resource):
    ids = [
        reserve(client, resource.id, kst(f"{hour:02d}:00"), kst(f"{hour + 1:02d}:00")).json()["id"]
        for hour in range(9, 14)
    ]

    page = client.get("/reservations/me", params={"limit": 2, "offset": 2}).json()

    assert [r["id"] for r in page["items"]] == ids[2:4]
    assert page["total"] == 5


def test_my_reservations_requires_login(client):
    client.headers.pop("Authorization")

    assert client.get("/reservations/me").status_code == 401


def test_resource_schedule_lists_slots_overlapping_the_kst_day(
    client, resource, db_session, user, other_user
):
    other_resource = Resource(name="회의실 B", capacity=4)
    db_session.add(other_resource)
    db_session.commit()
    # 시각은 UTC. 한국 날짜 2030-01-07 = UTC 2030-01-06 15:00 ~ 2030-01-07 15:00
    add_reservation(  # 전날 23:00 ~ 당일 01:00 (KST): 자정을 넘는 예약도 포함
        db_session, resource, user, datetime(2030, 1, 6, 14), datetime(2030, 1, 6, 16)
    )
    add_reservation(  # 당일 10:00 ~ 11:00, 다른 사용자
        db_session, resource, other_user, datetime(2030, 1, 7, 1), datetime(2030, 1, 7, 2)
    )
    add_reservation(  # 취소된 예약: 제외
        db_session,
        resource,
        user,
        datetime(2030, 1, 7, 3),
        datetime(2030, 1, 7, 4),
        status=ReservationStatus.CANCELLED,
    )
    add_reservation(  # 전날 22:00 ~ 23:00 (KST): 제외
        db_session, resource, user, datetime(2030, 1, 6, 13), datetime(2030, 1, 6, 14)
    )
    add_reservation(  # 다음 날 00:00 ~ 01:00 (KST): 제외
        db_session, resource, user, datetime(2030, 1, 7, 15), datetime(2030, 1, 7, 16)
    )
    add_reservation(  # 다른 자원: 제외
        db_session, other_resource, user, datetime(2030, 1, 7, 5), datetime(2030, 1, 7, 6)
    )
    client.headers.pop("Authorization")  # 로그인 없이도 볼 수 있다.

    response = client.get(f"/resources/{resource.id}/reservations", params={"date": DAY})

    assert response.status_code == 200
    assert response.json() == {
        "resource_id": resource.id,
        "date": DAY,
        "items": [
            # 누가, 왜 예약했는지는 내보내지 않는다.
            {"start_at": "2030-01-06T23:00:00+09:00", "end_at": "2030-01-07T01:00:00+09:00"},
            {"start_at": "2030-01-07T10:00:00+09:00", "end_at": "2030-01-07T11:00:00+09:00"},
        ],
    }


def test_resource_schedule_for_unknown_resource_returns_404(client):
    response = client.get("/resources/999999/reservations", params={"date": DAY})

    assert response.status_code == 404


@pytest.mark.parametrize("params", [{}, {"date": "2030-13-01"}], ids=["missing", "invalid"])
def test_resource_schedule_requires_valid_date(client, resource, params):
    assert client.get(f"/resources/{resource.id}/reservations", params=params).status_code == 422


# --- 취소 -------------------------------------------------------------------


def test_cancel_own_reservation(client, resource, db_session):
    reservation_id = reserve(client, resource.id, kst("10:00"), kst("11:00")).json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED"
    assert body["cancelled_at"] is not None
    # 행은 지워지지 않고 남는다. (소프트 삭제)
    stored = db_session.get(Reservation, reservation_id)
    assert stored.status is ReservationStatus.CANCELLED
    # 방법 B의 칸은 비워진다.
    slot_count = db_session.scalar(
        select(func.count())
        .select_from(ReservationSlot)
        .where(ReservationSlot.reservation_id == reservation_id)
    )
    assert slot_count == 0


def test_cancel_twice_returns_409(client, resource):
    reservation_id = reserve(client, resource.id, kst("10:00"), kst("11:00")).json()["id"]
    assert client.post(f"/reservations/{reservation_id}/cancel").status_code == 200

    response = client.post(f"/reservations/{reservation_id}/cancel")

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 취소된 예약입니다."}


def test_cancel_started_reservation_returns_409(client, resource, db_session, user):
    past = add_reservation(
        db_session, resource, user, datetime(2020, 1, 1, 1), datetime(2020, 1, 1, 2)
    )

    response = client.post(f"/reservations/{past.id}/cancel")

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 시작된 예약은 취소할 수 없습니다."}


def test_cancel_other_users_reservation_returns_404(client, resource, db_session, other_user):
    others = add_reservation(
        db_session, resource, other_user, datetime(2030, 1, 7, 1), datetime(2030, 1, 7, 2)
    )

    response = client.post(f"/reservations/{others.id}/cancel")

    assert response.status_code == 404
    assert db_session.get(Reservation, others.id).status is ReservationStatus.CONFIRMED


def test_admin_can_cancel_any_reservation(client, resource, db_session, other_user, admin):
    others = add_reservation(
        db_session, resource, other_user, datetime(2030, 1, 7, 1), datetime(2030, 1, 7, 2)
    )

    response = client.post(f"/reservations/{others.id}/cancel", headers=auth_header(admin))

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancelled_slot_can_be_reserved_again(client, resource):
    reservation_id = reserve(client, resource.id, kst("10:00"), kst("11:00")).json()["id"]
    client.post(f"/reservations/{reservation_id}/cancel")

    assert reserve(client, resource.id, kst("10:00"), kst("11:00")).status_code == 201
