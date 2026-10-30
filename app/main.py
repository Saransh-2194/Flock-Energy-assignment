from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.portal_client import PortalClient, PortalError


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.portal = PortalClient()
    yield
    await app.state.portal.close()


app = FastAPI(
    title="Flock Meter API",
    description=(
        "Read-only API buiult over Urja Meter Ops."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def get_portal() -> PortalClient:
    return app.state.portal


def as_bad_gateway(exc: PortalError) -> HTTPException:
    # Do not pass upstream details to API consumers; they may contain internal data.
    return HTTPException(status_code=502, detail="The upstream service could not complete the request.")


ERROR_MESSAGES = {
    400: ("BAD_REQUEST", "The request could not be processed."),
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You are not allowed to access this resource."),
    404: ("NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "This HTTP method is not supported for this resource."),
    422: ("VALIDATION_ERROR", "One or more request parameters are invalid."),
    429: ("RATE_LIMITED", "Too many requests. Please try again later."),
    502: ("UPSTREAM_ERROR", "The upstream service could not complete the request."),
    503: ("SERVICE_UNAVAILABLE", "The service is temporarily unavailable."),
    500: ("INTERNAL_ERROR", "An unexpected server error occurred."),
}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    fields = sorted(
        {".".join(str(part) for part in error.get("loc", ())[1:]) for error in exc.errors()}
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": ERROR_MESSAGES[422][1],
                "fields": fields,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    code, message = ERROR_MESSAGES.get(
        exc.status_code, ("REQUEST_ERROR", "The request could not be completed.")
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )


def normalize_meter_id(meter_id: str) -> str:
    """change the first character to uppercase, preserving the rest."""
    if not meter_id:
        return meter_id
    return meter_id[0].upper() + meter_id[1:]


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/meters", tags=["meters"])
async def search_meters(
    q: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=10000),
) -> Any:
    try:
        return await get_portal().search_meters(q=q, page=page)
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/meters/{meter_id}/geo", tags=["meters"])
async def meter_geo(
    meter_id: str = Path(
        ..., min_length=1, max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
) -> Any:
    try:
        return await get_portal().get_meter_geo(normalize_meter_id(meter_id))
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/meters/{meter_id}/energy", tags=["meters"])
async def meter_energy(
    meter_id: str = Path(
        ..., min_length=1, max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
) -> Any:
    try:
        return await get_portal().get_meter_energy(normalize_meter_id(meter_id))
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/transformers", tags=["transformers"])
async def transformers(page: int = Query(default=1, ge=1, le=10000)) -> Any:
    try:
        return await get_portal().list_transformers(page=page)
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/export/meters", tags=["meters"])
async def export_meters(page: int = Query(default=1, ge=1, le=10000)) -> Any:
    try:
        return await get_portal().export_meters(page=page)
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": ERROR_MESSAGES[500][1]}},
    )
