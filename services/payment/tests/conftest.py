import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db

TEST_DATABASE_URL = "postgresql+asyncpg://docfliq:changeme@localhost:5432/payment_db"


@pytest.fixture
def client() -> TestClient:
    init_db(TEST_DATABASE_URL)
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "payment"
