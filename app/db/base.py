from datetime import datetime

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 제약 조건 이름 규칙. 이름을 직접 정하지 않으면 MySQL이 임의의 이름을 붙이는데,
# 그러면 나중에 마이그레이션에서 제약을 지우거나 바꿀 때 이름을 알 수 없어 곤란해진다.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """created_at, updated_at을 DB가 직접 채우도록 한다.

    앱에서 datetime.now()로 넣지 않고 DB 기본값을 쓰는 이유:
    SQL로 직접 넣거나 고친 행에도 시각이 빠짐없이 기록된다.
    CURRENT_TIMESTAMP는 DB 세션의 시간대를 따르므로, 앱의 연결은 세션 시간대를
    UTC로 고정한다. (app/db/session.py, docs/erd.md 참고)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
