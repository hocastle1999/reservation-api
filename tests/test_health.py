from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_returns_ok_when_database_responds(client):
    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_db_returns_503_when_database_fails(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_db] = lambda: BrokenSession()

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
