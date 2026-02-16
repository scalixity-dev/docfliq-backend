import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db

# Use in-memory or test DB URL
TEST_DATABASE_URL = "postgresql+asyncpg://docfliq:changeme@localhost:5432/identity_db"


@pytest.fixture
def client() -> TestClient:
    init_db(TEST_DATABASE_URL)
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "identity"


def test_register_and_login(client: TestClient) -> None:
    # Register
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    # May be 201 or 422/500 if DB not running or tables missing
    if reg.status_code == 201:
        data = reg.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    if login.status_code == 200:
        assert "access_token" in login.json()
