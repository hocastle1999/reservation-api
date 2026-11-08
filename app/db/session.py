from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


# create_engine은 이 시점에 DB에 접속하지 않는다. 첫 쿼리 때 연결 풀에서 연결을 만든다.
# pool_pre_ping: MySQL이 오래 쉬던 연결을 끊어 버린 경우(wait_timeout)를 대비해
# 연결을 꺼내기 전에 살아 있는지 확인한다.
# connect_args: 연결마다 세션 시간대를 UTC로 고정하고, 설정에 따라 SSL로 접속한다.
# 로컬 MySQL은 보통 PC 시간대(KST)를 따르기 때문에, 시간대를 고정하지 않으면
# CURRENT_TIMESTAMP 기본값이 한국 시간으로 저장된다. (Settings.database_connect_args)
# isolation_level: MySQL 기본값(REPEATABLE READ) 대신 READ COMMITTED를 쓴다.
# REPEATABLE READ는 트랜잭션의 첫 일반 SELECT 시점에 스냅샷을 고정한다. 예약 요청은
# 인증 단계에서 사용자를 먼저 읽기 때문에, 자원 락을 기다렸다가 받은 뒤에도 겹침 검사가
# "락을 기다리기 전" 스냅샷을 보고 앞 요청이 커밋한 예약을 못 본다. (중복 예약 발생)
# READ COMMITTED는 문장마다 최신 커밋을 읽으므로 락을 받은 뒤의 겹침 검사가 정확하다.
# (docs/troubleshooting.md, docs/erd.md 참고)
def create_app_engine(**pool_options: Any) -> Engine:
    """앱과 같은 연결 설정(시간대, 격리 수준)의 엔진을 만든다.

    pool_options: 연결 풀 크기 등. 부하 측정 스크립트(scripts/benchmark_reservations.py)가
    스레드 수만큼 연결을 쓰려고 넘긴다. 설정을 복사하지 않고 이 함수를 같이 써야
    측정 환경이 실제 앱과 어긋나지 않는다.
    """
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        isolation_level="READ COMMITTED",
        connect_args=get_settings().database_connect_args,
        **pool_options,
    )


engine = create_app_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """요청 하나당 세션 하나를 열고, 요청이 끝나면 반드시 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
