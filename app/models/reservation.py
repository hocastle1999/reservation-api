from __future__ import annotations

import enum
from datetime import datetime
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


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="time"),
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
