from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.time import to_kst, to_utc_naive, utc_now
from app.models import ReservationStatus

Purpose = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]

# 응답용: DB의 UTC 값을 한국 시간(+09:00)으로 바꿔서 내보낸다.
KstDatetime = Annotated[datetime, AfterValidator(to_kst)]


class ReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: int
    # AwareDatetime: "2030-01-07T10:00:00+09:00"처럼 시간대가 있어야 한다.
    # 시간대 없는 값은 한국 시간인지 UTC인지 알 수 없으므로 추측하지 않고 422로 거절한다.
    start_at: AwareDatetime = Field(examples=["2030-01-07T10:00:00+09:00"])
    end_at: AwareDatetime = Field(examples=["2030-01-07T11:00:00+09:00"])
    purpose: Purpose | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def require_whole_minutes(cls, value: datetime) -> datetime:
        # 초와 마이크로초는 0이어야 한다. DB 컬럼은 DATETIME(소수 초 없음)이라
        # MySQL이 소수 초를 "반올림"해 저장한다. 10:59:59.6이 11:00:00이 되면
        # 앱이 검사한 값과 저장된 값이 달라지므로 처음부터 분 단위만 받는다.
        if value.second or value.microsecond:
            raise ValueError("시각은 분 단위로 입력해야 합니다. (초는 0)")
        return value

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        if self.start_at >= self.end_at:
            raise ValueError("end_at은 start_at보다 늦어야 합니다.")
        if to_utc_naive(self.start_at) <= utc_now():
            raise ValueError("이미 지난 시각은 예약할 수 없습니다.")
        return self


class ReservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    user_id: int
    start_at: KstDatetime
    end_at: KstDatetime
    status: ReservationStatus
    purpose: str | None
    cancelled_at: KstDatetime | None
    created_at: KstDatetime
