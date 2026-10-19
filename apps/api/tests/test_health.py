from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from talent_api.db import get_db
from talent_api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_database_failure_returns_safe_503():
    class BrokenSession:
        def execute(self, statement):
            raise OperationalError("private connection details", {}, Exception())

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
    finally:
        app.dependency_overrides.clear()
