from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app.portal_client import PortalClient, PortalError


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.portal = PortalClient()
    yield
    await app.state.portal.close()


app = FastAPI(
    title="Flock Meter API",
    description=(
        "Read-only API facade over Urja Meter Ops. Upstream response JSON is "
        "passed through until real response schemas are confirmed."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def get_portal() -> PortalClient:
    return app.state.portal


def as_bad_gateway(exc: PortalError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


def normalize_meter_id(meter_id: str) -> str:
    """Normalize the first character to uppercase, preserving the rest."""
    if not meter_id:
        return meter_id
    return meter_id[0].upper() + meter_id[1:]



@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, str]:
    # Process health only; this does not test portal connectivity.
    return {"status": "ok"}


@app.get("/api/v1/meters", tags=["meters"])
async def search_meters(
    q: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1),
) -> Any:
    try:
        return await get_portal().search_meters(q=q, page=page)
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/meters/{meter_id}/geo", tags=["meters"])
async def meter_geo(meter_id: str) -> Any:
    try:
        return await get_portal().get_meter_geo(normalize_meter_id(meter_id))
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/meters/{meter_id}/energy", tags=["meters"])
async def meter_energy(meter_id: str) -> Any:
    try:
        return await get_portal().get_meter_energy(normalize_meter_id(meter_id))
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/transformers", tags=["transformers"])
async def transformers(page: int = Query(default=1, ge=1)) -> Any:
    try:
        return await get_portal().list_transformers(page=page)
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.exception_handler(Exception)
async def unexpected_error_handler(request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
