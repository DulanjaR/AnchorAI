"""One error shape for the whole C1 API (docs/API.md §1):

    { "error": { "code": "...", "message": "..." } }

so the Flutter app can handle errors in one place. The handlers are installed on
the C1 app only; shared/ is not touched.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from components.c1_disruption.engine.errors import EngineError

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def bad_request(message: str, code: str = "INVALID_INPUT") -> ApiError:
    return ApiError(400, code, message)


def not_found(what: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} not found")


def conflict(message: str, code: str = "WRONG_STATE") -> ApiError:
    return ApiError(409, code, message)


def unprocessable(message: str, code: str = "CANNOT_PLAN") -> ApiError:
    return ApiError(422, code, message)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


# Codes for errors raised by FastAPI/Starlette itself or by shared.auth.
_HTTP_CODES = {401: "INVALID_API_KEY", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def validation_message(exc: RequestValidationError) -> tuple[str, str]:
    """(code, message) for a request that failed Pydantic validation.

    The C1 request models (validation.py) raise errors whose message is already
    written like the Node API's ("'title' is required (...)"); anything else
    gets a generic message naming the field.
    """
    errors = exc.errors()
    if any(e["type"] == "json_invalid" for e in errors):
        return "INVALID_JSON", "Request body is not valid JSON"
    first = errors[0]
    ctx = first.get("ctx") or {}
    if first["type"].startswith("c1_"):
        return ctx.get("code", "INVALID_INPUT"), first["msg"]
    loc = [str(part) for part in first["loc"] if part != "body"]
    if not loc:
        # No body, or a body that is not an object.
        return "INVALID_INPUT", "Request body must be a JSON object"
    return "INVALID_INPUT", f"'{'.'.join(loc)}': {first['msg']}"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(EngineError)
    async def engine_error(request: Request, exc: EngineError) -> JSONResponse:
        # Input was validated already, so an engine error is a planning problem the
        # user must know about, e.g. a None EF value (open research decision).
        return _error(422, "CANNOT_PLAN", str(exc))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        code, message = validation_message(exc)
        return _error(400, code, message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            message = f"No route {request.method} {request.url.path}"
        else:
            message = str(exc.detail)
        return _error(exc.status_code, _HTTP_CODES.get(exc.status_code, "HTTP_ERROR"), message)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unexpected error in C1 API")
        return _error(500, "INTERNAL", "Unexpected server error")
