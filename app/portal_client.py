from typing import Any

import httpx

from app.config import settings


class PortalError(RuntimeError):
    """Safe-to-return upstream integration error."""


class PortalClient:
    MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MiB cap for upstream JSON payloads
    # Login route and field names are provisional; verify against DevTools.
    # This client deliberately does not call /portal/keys or use signingSecret.

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.portal_base_url.rstrip("/"),
            timeout=settings.portal_timeout_seconds,
            # Do not follow upstream redirects: redirects could send requests to an
            # unexpected host. Login cookies are still retained from the response.
            follow_redirects=False,
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
                },)
        except httpx.HTTPError as exc:
            raise PortalError("The upstream login service could not be reached.") from exc

        if response.is_error:
            raise PortalError("Portal login failed.")

        # A 200/redirect does not prove login succeeded. A protected request below
        # is the practical check; refine this if the portal has a clear login signal.
        self._login_attempted = True

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self.login()
        try:
            # Stream the response so oversized upstream bodies can be rejected
            # before buffering the entire payload in memory.
            async with self._client.stream("GET", path, params=params) as response:
                if response.status_code in (401, 403):
                    self._login_attempted = False
                    raise PortalError("Portal authentication failed or the session expired.")
                if response.is_error:
                    raise PortalError("Portal request was rejected by the upstream service.")

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > self.MAX_RESPONSE_BYTES:
                        raise PortalError("The upstream response exceeded the allowed size limit.")
                    body.extend(chunk)
                try:
                    import json
                    return json.loads(body)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise PortalError("The upstream service returned an invalid response format.") from exc
        except httpx.TimeoutException as exc:
            raise PortalError("Portal request timed out.") from exc
        except httpx.HTTPError as exc:
            raise PortalError("The upstream service could not be reached.") from exc

    async def search_meters(self, q: str = "", page: int = 1) -> Any:
        return await self.get_json("/portal/meters/search", {"q": q, "page": page})

    async def get_meter_geo(self, meter_id: str) -> Any:
        return await self.get_json(f"/portal/meters/{meter_id}/geo")

    async def get_meter_energy(self, meter_id: str) -> Any:
        return await self.get_json(f"/portal/meters/{meter_id}/energy")

    async def list_transformers(self, page: int = 1) -> Any:
        return await self.get_json("/portal/dts", {"page": page})

    async def export_meters(self, page: int = 1) -> Any:
        # page=1 was observed to return all data; other page behavior is unknown.
        return await self.get_json("/portal/export", {"page": page})
