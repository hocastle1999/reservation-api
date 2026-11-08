from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 칸 하나의 길이(분). 예약 시각은 이 단위로만 받는다. (app/schemas/reservation.py)
SLOT_MINUTES = 30


class ReservationSlot(Base):
    """방법 B(시간 칸 + UNIQUE)용. 확정된 예약이 차지한 30분 칸 하나가 행 하나다.

    기본키 (resource_id, slot_start)가 "같은 자원의 같은 칸은 한 예약만"을 DB에서 보장한다.
    10:00~11:00 예약은 10:00, 10:30 두 행이 된다. 다른 요청이 이 중 하나라도 이미 넣었다면
    INSERT가 중복 키 오류(1062)로 실패한다. 락을 직접 잡지 않아도 DB가 막아 준다.
    """

    __tablename__ = "reservation_slots"
    __table_args__ = (
        # 취소할 때 "이 예약의 칸"을 지우기 위한 인덱스. 외래키 검사에도 쓰인다.
        Index("ix_reservation_slots_reservation_id", "reservation_id"),
    )

    resource_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resources.id", ondelete="RESTRICT"), primary_key=True
    )
    # 칸의 시작 시각 (UTC). 항상 SLOT_MINUTES 단위로 맞춰져 있다.
    slot_start: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    # 칸은 예약에 딸린 데이터라 예약 행이 지워지면 함께 지운다.
    # (예약은 평소에 지우지 않지만, 테스트 정리나 관리 작업에서 지울 때를 위해)
    reservation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ReservationSlot resource_id={self.resource_id} {self.slot_start}>"
