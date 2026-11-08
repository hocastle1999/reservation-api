"""시각 변환 도우미.

규칙: DB에는 UTC를 시간대 정보 없는(naive) datetime으로 저장한다.
API로 들어오는 시각은 시간대 정보가 있어야 하고, 응답은 한국 시간(+09:00)으로 돌려준다.
변환은 API 경계(스키마, 서비스 입구)에서만 한다.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

# 한국은 서머타임이 없어서 고정 오프셋(+09:00)으로 충분하다.
# zoneinfo("Asia/Seoul")를 쓰지 않는 이유: Windows에는 시간대 DB가 없어서
# tzdata 패키지를 따로 설치해야 한다. 고정 오프셋이면 의존성이 필요 없다.
KST = timezone(timedelta(hours=9), "KST")


def utc_now() -> datetime:
    """DB에 저장된 값과 바로 비교할 수 있는 현재 시각 (UTC, naive)."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    """시간대가 있는 시각을 DB 저장용(UTC, naive)으로 바꾼다."""
    if value.tzinfo is None:
        raise ValueError("시간대 정보가 없는 시각은 변환할 수 없습니다.")
    return value.astimezone(UTC).replace(tzinfo=None)


def to_kst(value: datetime) -> datetime:
    """DB에서 읽은 시각(UTC, naive)을 한국 시간으로 바꾼다."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(KST)


def kst_day_range(day: date) -> tuple[datetime, datetime]:
    """한국 날짜 하루(00:00 ~ 다음 날 00:00)를 DB 비교용 UTC 구간으로 바꾼다.

    예: 2030-01-07 → (2030-01-06 15:00, 2030-01-07 15:00) UTC
    """
    start = datetime.combine(day, time(0, 0), tzinfo=KST)
    return to_utc_naive(start), to_utc_naive(start + timedelta(days=1))
