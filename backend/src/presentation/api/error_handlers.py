"""FastAPI exception handlers — maps domain errors to HTTP status codes.

Registered once in app.py. No try/except blocks needed in route handlers.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from src.domain.errors.domain_errors import (
    AuthenticationError,
    AuthorizationError,
    DomainError,
    DuplicateJobError,
    InvalidAudioFormatError,
    JobNotFoundError,
    ProviderRateLimitError,
    SourceNotFoundError,
    TokenExpiredError,
    TranscriptNotFoundError,
    UserNotFoundError,
    AnalysisNotFoundError,
    ReportNotFoundError,
)


def _error_body(code: str, message: str) -> dict:  # type: ignore[type-arg]
    return {"success": False, "data": None, "error": {"code": code, "message": message}}


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Generic domain error → 400."""
    return JSONResponse(status_code=400, content=_error_body(exc.code, exc.message))


async def not_found_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=404, content=_error_body(exc.code, exc.message))


async def duplicate_handler(request: Request, exc: DuplicateJobError) -> JSONResponse:
    return JSONResponse(status_code=409, content=_error_body(exc.code, exc.message))


async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=_error_body(exc.code, exc.message),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def authz_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(status_code=403, content=_error_body(exc.code, exc.message))


async def rate_limit_handler(request: Request, exc: ProviderRateLimitError) -> JSONResponse:
    return JSONResponse(status_code=429, content=_error_body(exc.code, exc.message))


async def validation_error_handler(request: Request, exc: InvalidAudioFormatError) -> JSONResponse:
    return JSONResponse(status_code=422, content=_error_body(exc.code, exc.message))


def register_handlers(app: "FastAPI") -> None:  # type: ignore[name-defined]
    """Register all domain exception handlers on the FastAPI app."""
    _not_found = (
        JobNotFoundError,
        SourceNotFoundError,
        UserNotFoundError,
        TranscriptNotFoundError,
        AnalysisNotFoundError,
        ReportNotFoundError,
    )
    for exc_cls in _not_found:
        app.add_exception_handler(exc_cls, not_found_handler)  # type: ignore[arg-type]

    app.add_exception_handler(DuplicateJobError, duplicate_handler)  # type: ignore[arg-type]
    app.add_exception_handler(TokenExpiredError, auth_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AuthenticationError, auth_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AuthorizationError, authz_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ProviderRateLimitError, rate_limit_handler)  # type: ignore[arg-type]
    app.add_exception_handler(InvalidAudioFormatError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]


from fastapi import FastAPI  # noqa: E402
