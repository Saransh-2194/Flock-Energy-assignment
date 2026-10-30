"""PortalClient integration-boundary tests using httpx.MockTransport (no network)."""
import asyncio
import httpx
import pytest

from app.config import settings
from app.portal_client import PortalClient, PortalError


def make_client(handler):
    """Build a PortalClient whose HTTP requests are handled by a local mock."""
    portal = PortalClient()
    assert portal._client.follow_redirects is False
    # Close the real, unused client before swapping in a deterministic mock.
    asyncio.run(portal._client.aclose())
    portal._client = httpx.AsyncClient(
        base_url=settings.portal_base_url.rstrip("/"),
        timeout=settings.portal_timeout_seconds,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        headers={"Accept": "application/json, text/html;q=0.9"},
    )
    # Most tests focus on an already-authenticated upstream session.
    portal._login_attempted = True
    return portal


def run(coro):
    return asyncio.run(coro)


def test_successful_json_response_is_returned():
    def handler(request):
        assert request.url.path == "/portal/meters/search"
        assert request.url.params["q"] == "J100"
        assert request.url.params["page"] == "2"
        return httpx.Response(200, json={"data": [{"meterId": "J100"}]})

    portal = make_client(handler)
    try:
        result = run(portal.get_json("/portal/meters/search", {"q": "J100", "page": 2}))
        assert result == {"data": [{"meterId": "J100"}]}
    finally:
        run(portal.close())


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_failure_reports_expired_session_and_resets_login(status_code):
    def handler(request):
        return httpx.Response(status_code, json={"error": "unauthorized"})

    portal = make_client(handler)
    try:
        with pytest.raises(PortalError, match="authentication failed or the session expired"):
            run(portal.get_json("/portal/meters/search"))
        assert portal._login_attempted is False
    finally:
        run(portal.close())


@pytest.mark.parametrize("status_code", [400, 404, 429, 500, 503])
def test_other_upstream_http_errors_are_safely_reported(status_code):
    def handler(request):
        return httpx.Response(status_code, text="upstream details that should not leak")

    portal = make_client(handler)
    try:
        with pytest.raises(PortalError, match="rejected by the upstream service") as error:
            run(portal.get_json("/portal/meters/search"))
        assert "upstream details" not in str(error.value)
    finally:
        run(portal.close())


def test_timeout_is_reported_without_leaking_transport_details():
    def handler(request):
        raise httpx.ReadTimeout("sensitive transport detail", request=request)

    portal = make_client(handler)
    try:
        with pytest.raises(PortalError, match="Portal request timed out") as error:
            run(portal.get_json("/portal/meters/search"))
        assert "sensitive transport detail" not in str(error.value)
    finally:
        run(portal.close())


def test_other_transport_error_is_reported_safely():
    def handler(request):
        raise httpx.ConnectError("private host details", request=request)

    portal = make_client(handler)
    try:
        with pytest.raises(PortalError, match="upstream service could not be reached") as error:
            run(portal.get_json("/portal/meters/search"))
        assert "private host details" not in str(error.value)
    finally:
        run(portal.close())


@pytest.mark.parametrize("body,content_type", [
    ("not json", "text/html"),
    ("{broken", "application/json"),
])
def test_non_json_or_malformed_json_is_reported(body, content_type):
    def handler(request):
        return httpx.Response(200, text=body, headers={"content-type": content_type})

    portal = make_client(handler)
    try:
        with pytest.raises(PortalError, match="invalid response format"):
            run(portal.get_json("/portal/meters/search"))
    finally:
        run(portal.close())


def test_login_http_error_is_reported_safely(monkeypatch):
    monkeypatch.setattr(settings, "portal_username", "test-user")
    monkeypatch.setattr(settings, "portal_password", "test-password")

    def handler(request):
        assert request.method == "POST"
        return httpx.Response(403, text="Cross-site POST form submissions are forbidden")

    portal = make_client(handler)
    portal._login_attempted = False
    try:
        with pytest.raises(PortalError, match="Portal login failed") as error:
            run(portal.login())
        assert "Cross-site POST" not in str(error.value)
    finally:
        run(portal.close())


def test_missing_credentials_fail_before_network_request(monkeypatch):
    monkeypatch.setattr(settings, "portal_username", "")
    monkeypatch.setattr(settings, "portal_password", "")
    portal = make_client(lambda request: pytest.fail("network should not be called"))
    portal._login_attempted = False
    try:
        with pytest.raises(PortalError, match="credentials are not configured"):
            run(portal.login())
    finally:
        run(portal.close())


def test_login_submits_configured_form_field_names(monkeypatch):
    monkeypatch.setattr(settings, "portal_username", "test-user")
    monkeypatch.setattr(settings, "portal_password", "test-password")
    monkeypatch.setattr(settings, "portal_username_field", "email")
    monkeypatch.setattr(settings, "portal_password_field", "password")
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(200, json={"ok": True})

    portal = make_client(handler)
    portal._login_attempted = False
    try:
        run(portal.login())
        assert seen["method"] == "POST"
        assert seen["form"] == {"email": "test-user", "password": "test-password"}
        assert portal._login_attempted is True
    finally:
        run(portal.close())


def test_upstream_redirect_is_not_followed_to_another_host():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://attacker.example/collect"})

    portal = make_client(handler)
    try:
        with pytest.raises(PortalError, match="invalid response format"):
            run(portal.get_json("/portal/meters/search"))
        assert len(requests) == 1
        assert "attacker.example" not in requests[0]
    finally:
        run(portal.close())


def test_login_error_does_not_leak_credentials_or_response_body(monkeypatch):
    monkeypatch.setattr(settings, "portal_username", "private-user")
    monkeypatch.setattr(settings, "portal_password", "private-password")

    def handler(request):
        return httpx.Response(401, text="private-password leaked by upstream")

    portal = make_client(handler)
    portal._login_attempted = False
    try:
        with pytest.raises(PortalError, match="Portal login failed") as error:
            run(portal.login())
        assert "private-password" not in str(error.value)
        assert "private-user" not in str(error.value)
    finally:
        run(portal.close())


def test_oversized_upstream_response_is_rejected():
    def handler(request):
        return httpx.Response(200, content=b"x" * (PortalClient.MAX_RESPONSE_BYTES + 1))

    portal = make_client(handler)
    try:
        with pytest.raises(PortalError, match="exceeded the allowed size limit"):
            run(portal.get_json("/portal/meters/search"))
    finally:
        run(portal.close())
