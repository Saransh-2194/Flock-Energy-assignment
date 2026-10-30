import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "testpassword"
            }
        )

        assert response.status_code == 200, response.text

        yield test_client