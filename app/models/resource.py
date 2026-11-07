from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.reservation import Reservation


class Resource(TimestampMixin, Base):
    """예약 대상 자원 (회의실 등)."""

    __tablename__ = "resources"
    __table_args__ = (CheckConstraint("capacity >= 1", name="capacity"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str | None] = mapped_column(String(100))
    # 예약 기록이 있는 자원은 지우지 않고(외래키 RESTRICT) 비활성화한다.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())

    reservations: Mapped[list[Reservation]] = relationship(back_populates="resource")

    def __repr__(self) -> str:
        return f"<Resource id={self.id} name={self.name!r}>"
