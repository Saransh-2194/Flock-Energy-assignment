from contextlib import asynccontextmanager
from typing import Any
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Path, Query, Request, Depends, Response, Cookie
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.portal_client import PortalClient, PortalError
from app.config import settings


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


SESSION_COOKIE_NAME = "flock_session"
SESSION_SALT = "flock-meter-console-session-v1"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


def session_serializer() -> URLSafeTimedSerializer:
    if len(settings.session_secret) < 32:
        raise HTTPException(status_code=503, detail="Application authentication is not configured.")
    return URLSafeTimedSerializer(settings.session_secret, salt=SESSION_SALT)


def authenticated_session(flock_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> str:
    if not flock_session:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    try:
        payload = session_serializer().loads(
            flock_session, max_age=settings.session_max_age_seconds
        )
    except (BadSignature, SignatureExpired, HTTPException):
        raise HTTPException(status_code=401, detail="Your session is invalid or has expired.")
    if payload != {"sub": settings.app_username} or not settings.app_username:
        raise HTTPException(status_code=401, detail="Your session is invalid or has expired.")
    return settings.app_username


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
    # Return field locations only; omit submitted values and Pydantic internals.
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
    if exc.status_code in (401, 503) and isinstance(exc.detail, str):
        message = exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )


def normalize_meter_id(meter_id: str) -> str:
    """Normalize the first character to uppercase, preserving the rest."""
    if not meter_id:
        return meter_id
    return meter_id[0].upper() + meter_id[1:]


@app.post("/api/v1/auth/login", tags=["authentication"])
async def login(credentials: LoginRequest, response: Response) -> dict[str, str]:
    if not settings.app_username or not settings.app_password or len(settings.session_secret) < 32:
        raise HTTPException(status_code=503, detail="Application authentication is not configured.")
    username_ok = secrets.compare_digest(credentials.username, settings.app_username)
    password_ok = secrets.compare_digest(credentials.password, settings.app_password)
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = session_serializer().dumps({"sub": settings.app_username})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"status": "authenticated"}


@app.post("/api/v1/auth/logout", tags=["authentication"])
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return {"status": "logged_out"}


@app.get("/api/v1/auth/me", tags=["authentication"])
async def current_user(_: str = Depends(authenticated_session)) -> dict[str, str]:
    return {"status": "authenticated"}


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, str]:
    # Process health only; this does not test portal connectivity.
    return {"status": "ok"}


@app.get("/api/v1/meters", tags=["meters"])
async def search_meters(
    _: str = Depends(authenticated_session),
    q: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=10000),
) -> Any:
    try:
        return await get_portal().search_meters(q=q, page=page)
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/meters/{meter_id}/geo", tags=["meters"])
async def meter_geo(
    _: str = Depends(authenticated_session),
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
    _: str = Depends(authenticated_session),
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
async def transformers(
    page: int = Query(default=1, ge=1, le=10000),
    _: str = Depends(authenticated_session),
) -> Any:
    try:
        return await get_portal().list_transformers(page=page)
    except PortalError as exc:
        raise as_bad_gateway(exc) from exc


@app.get("/api/v1/export/meters", tags=["meters"])
async def export_meters(
    page: int = Query(default=1, ge=1, le=10000),
    _: str = Depends(authenticated_session),
) -> Any:
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

