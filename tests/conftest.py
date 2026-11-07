import os
from collections.abc import Iterator
from pathlib import Path

# 앱 모듈을 import하기 "전에" 테스트 DB를 가리키게 한다.
# 설정(get_settings)과 엔진은 import 시점에 한 번 만들어지기 때문이다.
# 환경 변수는 .env보다 우선하므로 .env의 DB_NAME(개발용 DB)을 덮어쓴다.
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "reservation_test")
# 테스트용 고정 서명 키. 실제 키(.env)와 무관하게 늘 같은 조건에서 돌게 한다.
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256-0123456789"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Connection  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserRole  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def db_connection() -> Iterator[Connection]:
    """테스트 세션 전체에서 한 번: 테스트 DB의 스키마를 마이그레이션으로 새로 만든다."""
    db_name = get_settings().db_name
    # 안전장치: 실수로 개발용 DB를 지우지 않도록 이름이 _test로 끝나는 DB만 허용한다.
    assert db_name.endswith("_test"), f"테스트는 *_test DB에서만 실행한다 (현재: {db_name})"

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    # 매번 base까지 내렸다가 head로 올린다. 마이그레이션의 왕복도 함께 검증된다.
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    with engine.connect() as connection:
        yield connection


@pytest.fixture
def db_session(db_connection: Connection) -> Iterator[Session]:
    """테스트 하나마다 트랜잭션을 열고, 끝나면 롤백해 데이터를 남기지 않는다.

    join_transaction_mode="create_savepoint": 코드 안의 commit()/rollback()은
    SAVEPOINT 단위로만 동작하고, 바깥 트랜잭션은 테스트가 끝날 때 통째로 롤백된다.
    그래서 서비스 코드를 고치지 않고도 테스트끼리 데이터가 섞이지 않는다.
    """
    transaction = db_connection.begin()
    session = Session(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


TEST_PASSWORD = "correct-horse-battery"


def make_user(db: Session, email: str, role: UserRole = UserRole.USER) -> User:
    user = User(email=email, password_hash=hash_password(TEST_PASSWORD), name="테스트", role=role)
    db.add(user)
    db.commit()
    return user


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def user(db_session: Session) -> User:
    return make_user(db_session, "user@example.com")


@pytest.fixture
def admin(db_session: Session) -> User:
    return make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
