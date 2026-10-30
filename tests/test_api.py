"""API route tests; all portal calls are faked so tests never need credentials/network."""
import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app import main
from app.portal_client import PortalError


class FakePortal:
    def __init__(self):
        self.calls = []
        self.error = None

    async def _respond(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.error:
            raise self.error
        return {"ok": True, "endpoint": name, "args": list(args), "kwargs": kwargs}

    async def search_meters(self, q="", page=1):
        return await self._respond("search_meters", q=q, page=page)

    async def get_meter_geo(self, meter_id):
        return await self._respond("get_meter_geo", meter_id=meter_id)

    async def get_meter_energy(self, meter_id):
        return await self._respond("get_meter_energy", meter_id=meter_id)

    async def list_transformers(self, page=1):
        return await self._respond("list_transformers", page=page)

    async def export_meters(self, page=1):
        return await self._respond("export_meters", page=page)


@pytest.fixture
def fake_portal():
    return FakePortal()


@pytest.fixture
def client(monkeypatch, fake_portal):
    monkeypatch.setattr(main, "get_portal", lambda: fake_portal)

    test_client = TestClient(main.app)

    response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.app_username,
            "password": settings.app_password,
        },
    )

    assert response.status_code == 200, response.text

    yield test_client
    test_client.close()


def test_health_returns_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meter_search_defaults(client, fake_portal):
    response = client.get("/api/v1/meters")
    assert response.status_code == 200
    assert fake_portal.calls[-1] == ("search_meters", (), {"q": "", "page": 1})


def test_meter_search_passes_query_and_page(client, fake_portal):
    response = client.get("/api/v1/meters", params={"q": "J100", "page": 2})
    assert response.status_code == 200
    assert fake_portal.calls[-1] == ("search_meters", (), {"q": "J100", "page": 2})


@pytest.mark.parametrize("page", ["0", "-1"])
def test_meter_search_rejects_page_below_one(client, page):
    response = client.get("/api/v1/meters", params={"page": page})
    assert response.status_code == 422


def test_meter_search_rejects_non_integer_page(client):
    response = client.get("/api/v1/meters", params={"page": "abc"})
    assert response.status_code == 422


def test_meter_search_rejects_query_over_200_characters(client):
    response = client.get("/api/v1/meters", params={"q": "x" * 201})
    assert response.status_code == 422


@pytest.mark.parametrize("meter_id,expected", [("j100000", "J100000"), ("J100000", "J100000"), ("aBc-12", "ABc-12")])
def test_geo_normalizes_only_first_character(client, fake_portal, meter_id, expected):
    response = client.get(f"/api/v1/meters/{meter_id}/geo")
    assert response.status_code == 200
    assert fake_portal.calls[-1] == ("get_meter_geo", (), {"meter_id": expected})


@pytest.mark.parametrize("meter_id,expected", [("j100000", "J100000"), ("J100000", "J100000")])
def test_energy_normalizes_first_character(client, fake_portal, meter_id, expected):
    response = client.get(f"/api/v1/meters/{meter_id}/energy")
    assert response.status_code == 200
    assert fake_portal.calls[-1] == ("get_meter_energy", (), {"meter_id": expected})


def test_transformer_page_defaults_to_one(client, fake_portal):
    response = client.get("/api/v1/transformers")
    assert response.status_code == 200
    assert fake_portal.calls[-1] == ("list_transformers", (), {"page": 1})


def test_transformer_page_validation(client):
    assert client.get("/api/v1/transformers?page=0").status_code == 422
    assert client.get("/api/v1/transformers?page=nope").status_code == 422


def test_portal_errors_are_returned_as_502(client, fake_portal):
    fake_portal.error = PortalError("Portal returned HTTP 503.")
    response = client.get("/api/v1/meters")
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "UPSTREAM_ERROR",
            "message": "The upstream service could not complete the request.",
        }
    }
    assert "Portal returned HTTP 503" not in response.text


def test_openapi_json_is_available(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "Flock Meter API"
    assert "/api/v1/meters/{meter_id}/geo" in spec["paths"]
    assert "/api/v1/meters/{meter_id}/energy" in spec["paths"]


@pytest.mark.parametrize("path", [
    "/api/v1/meters/../../etc/passwd/geo",
    "/api/v1/meters/" + ("A" * 129) + "/geo",
    "/api/v1/meters/bad%2Fid/energy",
])
def test_meter_id_rejects_path_injection_or_excessive_length(client, fake_portal, path):
    response = client.get(path)
    assert response.status_code in (400, 404, 422)
    assert not fake_portal.calls


def test_validation_errors_use_custom_message_and_hide_submitted_value(client):
    secretish_input = "SENSITIVE-" + ("x" * 201)
    response = client.get("/api/v1/meters", params={"q": secretish_input})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["message"] == "One or more request parameters are invalid."
    assert secretish_input not in response.text
    assert "detail" not in response.json()


def test_oversized_page_is_rejected(client, fake_portal):
    response = client.get("/api/v1/meters", params={"page": "10001"})
    assert response.status_code == 422
    assert not fake_portal.calls


def test_upstream_error_message_does_not_leak_secret(client, fake_portal):
    fake_portal.error = PortalError("password=very-secret-value; cookie=private-cookie")
    response = client.get("/api/v1/meters")
    assert response.status_code == 502
    assert "very-secret-value" not in response.text
    assert "private-cookie" not in response.text


def test_unknown_route_uses_custom_not_found_message(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested resource was not found.",
        }
    }
