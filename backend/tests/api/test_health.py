from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.dependencies import get_repository
from app.api.health import router


def make_client(repository):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app, raise_server_exceptions=False)


def test_health_reports_ok_after_querying_database():
    repository = MagicMock()

    response = make_client(repository).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    repository.session.execute.assert_called_once()


def test_health_fails_when_database_is_unavailable():
    repository = MagicMock()
    repository.session.execute.side_effect = OperationalError("select", {}, Exception("down"))

    response = make_client(repository).get("/api/health")

    assert response.status_code == 500
