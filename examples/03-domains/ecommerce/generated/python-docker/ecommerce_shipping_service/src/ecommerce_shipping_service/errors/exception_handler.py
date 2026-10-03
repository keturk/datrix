"""Exception handlers that map exceptions to RFC 7807 Problem Details."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ecommerce_shipping_service.auth import AuthorizationDenied
from ecommerce_shipping_service.errors.problem_details import FieldError, ProblemDetails
from ecommerce_shipping_service.services._base import (
    CascadeRestrictionError,
    EntityNotFoundError,
)
from ecommerce_shipping_service.services._base import (
    ValidationError as ServiceValidationError,
)

logger = logging.getLogger(__name__)

_PROBLEM_JSON = "application/problem+json"

# RFC 7807 type + title for a bare HTTP status raised as an HTTPException
# (auth guards, rate limiting, dependency clients). The URNs are the
# framework problem-type registry's, spelled identically by every language
# target, so a client keyed on `type` sees one vocabulary.
_HTTP_STATUS_PROBLEM_TYPES: dict[int, tuple[str, str]] = {
    400: ("urn:datrix:error:bad-request", "Bad Request"),
    401: ("urn:datrix:error:unauthorized", "Unauthorized"),
    403: ("urn:datrix:error:forbidden", "Forbidden"),
    404: ("urn:datrix:error:not-found", "Not Found"),
    409: ("urn:datrix:error:conflict", "Conflict"),
    422: ("urn:datrix:error:validation", "Validation Error"),
    429: ("urn:datrix:error:rate-limit-exceeded", "Too Many Requests"),
    500: ("urn:datrix:error:internal", "Internal Server Error"),
}
_PROBLEM_TYPE_PREFIX = "urn:datrix:error:"
_HTTP_FORBIDDEN = 403
# The one client-visible detail of every authorization denial -- identical to
# the auth dependencies' own 403, so a denial never discloses why.
_FORBIDDEN_DETAIL = "Insufficient permissions"


def _problem_type_for_status(status: int) -> tuple[str, str]:
    """Registered (type, title) for *status*; a generic pair for any other."""
    if status in _HTTP_STATUS_PROBLEM_TYPES:
        return _HTTP_STATUS_PROBLEM_TYPES[status]
    return (f"{_PROBLEM_TYPE_PREFIX}http-{status}", f"HTTP {status}")


# Inlined from datrix_codegen_python/runtime/field_error_path.py. Maps a
# pydantic-style loc tuple to the one wire field-error path every realized
# request-validation problem's errors[].field follows -- unit tested by
# calling it directly, never by executing this rendered module.
_BODY_ROOT_SEGMENT = "body"


def format_field_error_path(loc: Sequence[str | int]) -> str:
    """Map a pydantic-style ``loc`` tuple to the one wire field-error path.

    Args:
        loc: E.g. ``("body", "shippingAddress", "postalCode")`` or
            ``("body", "items", 0, "sku")``. A ``loc`` not starting with
            ``"body"`` is passed through unchanged from its first element --
            a query/path-param validation error carries no body prefix.

    Returns:
        ``"shippingAddress.postalCode"`` / ``"items[0].sku"``.

    Raises:
        ValueError: ``loc`` is empty, or its only element is the body-root
            segment itself (no field to name).
    """
    segments = list(loc)
    if segments and segments[0] == _BODY_ROOT_SEGMENT:
        segments = segments[1:]
    if not segments:
        raise ValueError(
            f"format_field_error_path() received an empty field path "
            f"(loc={list(loc)!r}). Expected: at least one segment naming a "
            f"field beyond the body root."
        )
    parts: list[str] = []
    for segment in segments:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        elif parts:
            parts.append(f".{segment}")
        else:
            parts.append(str(segment))
    return "".join(parts)


def register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI application."""

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(
        request: Request,
        exc: EntityNotFoundError,
    ) -> JSONResponse:
        error = ProblemDetails(
            type="urn:datrix:error:entity-not-found",
            title="Entity Not Found",
            status=404,
            detail=str(exc),
            instance=str(request.url.path),
        )
        logger.warning(
            "entity_not_found path=%s detail=%s",
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=404,
            content=error.model_dump(),
            media_type=_PROBLEM_JSON,
        )

    @app.exception_handler(CascadeRestrictionError)
    async def cascade_restriction_handler(
        request: Request,
        exc: CascadeRestrictionError,
    ) -> JSONResponse:
        error = ProblemDetails(
            type="urn:datrix:error:cascade-restriction",
            title="Conflict",
            status=409,
            detail=str(exc),
            instance=str(request.url.path),
        )
        logger.warning(
            "cascade_restriction path=%s detail=%s",
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=409,
            content=error.model_dump(),
            media_type=_PROBLEM_JSON,
        )

    @app.exception_handler(ServiceValidationError)
    async def service_validation_handler(
        request: Request,
        exc: ServiceValidationError,
    ) -> JSONResponse:
        field_errors = [
            FieldError(field=f"body[{i}]", message=msg, code="validation")
            for i, msg in enumerate(exc.errors)
        ]
        error = ProblemDetails(
            type="urn:datrix:error:validation",
            title="Validation Error",
            status=422,
            detail="Request validation failed.",
            instance=str(request.url.path),
            errors=field_errors,
        )
        return JSONResponse(
            status_code=422,
            content=error.model_dump(),
            media_type=_PROBLEM_JSON,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        field_errors = [
            FieldError(
                field=format_field_error_path(e["loc"]),
                message=str(e["msg"]),
                code=str(e["type"]),
            )
            for e in exc.errors()
        ]
        error = ProblemDetails(
            type="urn:datrix:error:request-validation",
            title="Validation Error",
            status=422,
            detail="Request validation failed.",
            instance=str(request.url.path),
            errors=field_errors,
        )
        return JSONResponse(
            status_code=422,
            content=error.model_dump(),
            media_type=_PROBLEM_JSON,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """A bare-status HTTPException (auth guards, rate limiting, clients)
        answers as Problem Details too, keeping any headers the raiser set
        (Retry-After, WWW-Authenticate)."""
        problem_type, title = _problem_type_for_status(exc.status_code)
        error = ProblemDetails(
            type=problem_type,
            title=title,
            status=exc.status_code,
            detail=str(exc.detail),
            instance=str(request.url.path),
        )
        logger.warning(
            "http_exception status=%s path=%s detail=%s",
            exc.status_code,
            request.url.path,
            exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error.model_dump(),
            media_type=_PROBLEM_JSON,
            headers=exc.headers,
        )

    @app.exception_handler(AuthorizationDenied)
    async def authorization_denied_handler(
        request: Request,
        exc: AuthorizationDenied,
    ) -> JSONResponse:
        """A verified principal the contract refuses, raised from handler code
        (e.g. Auth.token() on a principal holding no bearer token) rather than
        from the auth dependencies, which answer their own denials. The body is
        the same opaque 403 every authorization denial answers with; the reason
        code is logged, never returned."""
        logger.warning(
            "authorization_denied reason_code=%s path=%s",
            exc.reason_code,
            request.url.path,
        )
        problem_type, title = _problem_type_for_status(_HTTP_FORBIDDEN)
        error = ProblemDetails(
            type=problem_type,
            title=title,
            status=_HTTP_FORBIDDEN,
            detail=_FORBIDDEN_DETAIL,
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=_HTTP_FORBIDDEN,
            content=error.model_dump(),
            media_type=_PROBLEM_JSON,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("unhandled_error path=%s", request.url.path)
        error = ProblemDetails(
            type="urn:datrix:error:internal",
            title="Internal Server Error",
            status=500,
            detail="An unexpected error occurred.",
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=500,
            content=error.model_dump(),
            media_type=_PROBLEM_JSON,
        )
