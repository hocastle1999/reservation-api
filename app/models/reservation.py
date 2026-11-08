from __future__ import annotations

import enum
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.resource import Resource
    from app.models.user import User


class ReservationStatus(enum.StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# 예약 하나의 최대 길이. 입력 검증(app/schemas/reservation.py)과 아래 CHECK 제약이 함께 쓴다.
# 겹침 검사와 일정 조회 쿼리도 이 상한을 전제로 검색 범위를 줄인다
# (reservation_service). 값을 바꾸면 CHECK 제약 마이그레이션도 새로 만들어야 한다.
MAX_DURATION_HOURS = 8
MAX_DURATION = timedelta(hours=MAX_DURATION_HOURS)


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="time"),
        # 앱 검증만 믿지 않고 DB에서도 막는다. SQL로 직접 넣은 행이 상한을 넘으면
        # 겹침 검사의 검색 범위 축소가 틀린 결과를 낸다(겹치는 예약을 못 찾음).
        CheckConstraint(
            f"TIMESTAMPDIFF(MINUTE, start_at, end_at) <= {MAX_DURATION_HOURS * 60}",
            name="duration",
        ),
        # 겹침 검사("이 자원의 이 시간대")와 자원별 예약 목록 조회용.
        # 자원으로 먼저 좁힌 뒤 시간 범위를 보므로 resource_id가 앞에 온다.
        Index("ix_reservations_resource_start", "resource_id", "start_at"),
        # 내 예약 목록(시간순) 조회용.
        Index("ix_reservations_user_start", "user_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 외래키 컬럼에 index=True를 따로 주지 않는 이유: 위 복합 인덱스가 이 컬럼으로
    # 시작하므로 MySQL이 외래키 검사에 그 인덱스를 그대로 쓴다.
    resource_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # 시각은 모두 UTC로 저장한다. (docs/erd.md 참고)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus),
        nullable=False,
        server_default=ReservationStatus.CONFIRMED.value,
    )
    purpose: Mapped[str | None] = mapped_column(String(200))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)

    resource: Mapped[Resource] = relationship(back_populates="reservations")
    user: Mapped[User] = relationship(back_populates="reservations")

    def __repr__(self) -> str:
        return (
            f"<Reservation id={self.id} resource_id={self.resource_id} "
            f"{self.start_at}~{self.end_at} {self.status}>"
        )
