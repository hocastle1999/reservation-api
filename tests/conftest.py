from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    # 테스트마다 바꾼 의존성(get_db 등)을 원래대로 돌려 놓는다.
    app.dependency_overrides.clear()
