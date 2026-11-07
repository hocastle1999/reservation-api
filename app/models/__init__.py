# 모든 모델을 여기서 import한다.
# Alembic이 Base.metadata에서 테이블 목록을 읽으려면 모델 모듈이 먼저 import되어 있어야 한다.
from app.models.reservation import Reservation, ReservationStatus
from app.models.resource import Resource
from app.models.user import User, UserRole

__all__ = ["Reservation", "ReservationStatus", "Resource", "User", "UserRole"]
