from typing import Any

import httpx

from app.config import settings


class PortalError(RuntimeError):
    """Safe-to-return upstream integration error."""


class PortalClient:
    # Login route and field names are provisional; verify against DevTools.
    # This client deliberately does not call /portal/keys or use signingSecret.

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.portal_base_url.rstrip("/"),
            timeout=settings.portal_timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/json, text/html;q=0.9"},
        )
        self._login_attempted = False

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self) -> None:
        if self._login_attempted:
            return
        if not settings.portal_username or not settings.portal_password:
            raise PortalError("Portal credentials are not configured in .env.")

        payload = {
            settings.portal_username_field: settings.portal_username,
            settings.portal_password_field: settings.portal_password,
        }
        try:
            response = await self._client.post(
                settings.portal_login_path,
                data=payload,
                headers={
                    "Origin": "https://urja-ops.flockenergy.tech",
                    "Referer": "https://urja-ops.flockenergy.tech/",
                },
            )
            print("Login status:", response.status_code)
            print("Login URL:", response.url)
            print("Redirect history:", [
                r.status_code for r in response.history
            ])
            print("Response type:", response.headers.get("content-type"))
            print("Redirect target:", response.headers.get("location"))
            print("Response preview:", response.text[:300])
        except httpx.HTTPError as exc:
            raise PortalError(f"Could not reach portal login endpoint ({type(exc).__name__}).") from exc

        if response.is_error:
            raise PortalError(f"Portal login returned HTTP {response.status_code}.")

        # A 200/redirect does not prove login succeeded. A protected request below
        # is the practical check; refine this if the portal has a clear login signal.
        self._login_attempted = True

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self.login()
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise PortalError("Portal request timed out.") from exc
        except httpx.HTTPError as exc:
            raise PortalError(f"Portal request failed ({type(exc).__name__}).") from exc

        if response.status_code in (401, 403):
            self._login_attempted = False
            raise PortalError(
                f"Portal returned HTTP {response.status_code}; session may have expired."
            )
        if response.is_error:
            raise PortalError(f"Portal returned HTTP {response.status_code}.")
        try:
            return response.json()
        except ValueError as exc:
            raise PortalError(
                f"Expected JSON from {path}; received "
                f"{response.headers.get('content-type', 'unknown content type')}."
            ) from exc

    async def search_meters(self, q: str = "", page: int = 1) -> Any:
        return await self.get_json("/portal/meters/search", {"q": q, "page": page})

    async def get_meter_geo(self, meter_id: str) -> Any:
        return await self.get_json(f"/portal/meters/{meter_id}/geo")

    async def get_meter_energy(self, meter_id: str) -> Any:
        return await self.get_json(f"/portal/meters/{meter_id}/energy")

    async def list_transformers(self, page: int = 1) -> Any:
        return await self.get_json("/portal/dts", {"page": page})
