import datetime as dt
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
from app.models import MAX_DURATION, MAX_DURATION_HOURS, SLOT_MINUTES, ReservationStatus

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
    def require_slot_boundary(cls, value: datetime) -> datetime:
        # 30분 단위(:00, :30)만 받는다. 방법 B(시간 칸)가 30분 칸으로만 막을 수 있어서,
        # 두 방식을 같은 입력으로 비교하려고 방법 A에도 같은 규칙을 둔다.
        # 초와 소수 초도 0이어야 한다. 컬럼이 DATETIME(소수 초 없음)이라 MySQL이 소수 초를
        # 반올림해 저장하므로, 앱이 검사한 값과 저장된 값이 달라질 수 있다.
        # UTC로 바꾼 뒤 검사한다. 칸은 UTC 기준으로 나뉘는데, +05:45 같은 시간대에서는
        # 입력값의 :00이 UTC로는 :15가 되기 때문이다.
        utc = to_utc_naive(value)
        if utc.minute % SLOT_MINUTES or utc.second or utc.microsecond:
            raise ValueError(f"시각은 {SLOT_MINUTES}분 단위로 입력해야 합니다. (예: 10:00, 10:30)")
        return value

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        if self.start_at >= self.end_at:
            raise ValueError("end_at은 start_at보다 늦어야 합니다.")
        # 상한이 없으면 1년짜리 예약 하나가 자원을 독점하고, 방법 B에서는 칸이 17,520개 생긴다.
        if self.end_at - self.start_at > MAX_DURATION:
            raise ValueError(f"한 번에 최대 {MAX_DURATION_HOURS}시간까지 예약할 수 있습니다.")
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


class ReservationList(BaseModel):
    items: list[ReservationRead]
    total: int = Field(description="필터 조건에 맞는 전체 개수 (페이지와 무관)")


class ReservationSlot(BaseModel):
    """자원 일정표용. 누가 왜 예약했는지(user_id, purpose)는 내보내지 않고 시간대만 보여 준다."""

    model_config = ConfigDict(from_attributes=True)

    start_at: KstDatetime
    end_at: KstDatetime


class ResourceSchedule(BaseModel):
    resource_id: int
    # 필드 이름과 타입 이름이 같으면(date: date) 파이썬이 이름을 헷갈릴 수 있어 dt.date로 쓴다.
    date: dt.date = Field(description="조회한 날짜 (한국 시간 기준)")
    items: list[ReservationSlot]
