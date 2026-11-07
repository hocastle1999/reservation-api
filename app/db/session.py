from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# create_engine은 이 시점에 DB에 접속하지 않는다. 첫 쿼리 때 연결 풀에서 연결을 만든다.
# pool_pre_ping: MySQL이 오래 쉬던 연결을 끊어 버린 경우(wait_timeout)를 대비해
# 연결을 꺼내기 전에 살아 있는지 확인한다.
# init_command: 연결마다 세션 시간대를 UTC로 고정한다. 로컬 MySQL은 보통 PC 시간대(KST)를
# 따르기 때문에, 이걸 안 하면 CURRENT_TIMESTAMP 기본값이 한국 시간으로 저장된다.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"init_command": "SET time_zone = '+00:00'"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """요청 하나당 세션 하나를 열고, 요청이 끝나면 반드시 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
