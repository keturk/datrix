"""Exception handlers that map exceptions to RFC 7807 Problem Details."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from library_book_service.errors.problem_details import FieldError, ProblemDetails
from library_book_service.services._base import (
    CascadeRestrictionError,
    EntityNotFoundError,
)
from library_book_service.services._base import (
    ValidationError as ServiceValidationError,
)

logger = logging.getLogger(__name__)

_PROBLEM_JSON = "application/problem+json"


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
                field=".".join(str(loc) for loc in e["loc"]),
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
