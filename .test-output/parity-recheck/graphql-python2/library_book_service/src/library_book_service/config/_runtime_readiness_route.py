"""Internal readiness route. Auto-generated. Do not edit.

Exposes ``GET /internal/readiness``. It uses the SAME ``RemoteConfigClient``
instance the lifespan built (``app.state.config_client``) and the SAME
``_secrets_resolver`` module the app uses, then returns the value-free readiness
report: HTTP 200 when every required item resolves, HTTP 503 otherwise. The JSON
body carries identities and statuses only -- never a resolved value.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, FastAPI, Request, Response

from library_book_service.config._runtime_readiness import check_runtime_readiness
from library_book_service.config.remote_config import RemoteConfigClient

logger = logging.getLogger(__name__)

_readiness_router = APIRouter(tags=["internal"])

_HTTP_OK = 200
_HTTP_SERVICE_UNAVAILABLE = 503


@_readiness_router.get("/internal/readiness", include_in_schema=False)
async def readiness(request: Request) -> Response:
    """Run the strict runtime readiness check and return a value-free report.

    Resolves every required config key and secret handle through the SAME
    ``RemoteConfigClient`` the application built at startup, returning 200 when
    all resolve and 503 with the failing items (names + statuses only) otherwise.
    """
    config_client = request.app.state.config_client
    if not isinstance(config_client, RemoteConfigClient):
        raise RuntimeError(
            "Runtime readiness route requires app.state.config_client to be a "
            "RemoteConfigClient built during the lifespan startup. It was not set "
            "or has the wrong type. Ensure the readiness route is registered after "
            "the lifespan builds and stores the config client on app.state."
        )
    report = await check_runtime_readiness(config_client)
    body: dict[str, object] = {
        "ok": report.ok,
        "items": [
            {
                "kind": item.kind,
                "name": item.logical_name,
                "rendered": item.rendered_name,
                "status": item.status.value,
                "detail": item.detail,
            }
            for item in report.items
        ],
    }
    status_code = _HTTP_OK if report.ok else _HTTP_SERVICE_UNAVAILABLE
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        status_code=status_code,
    )


def setup_runtime_readiness(app: FastAPI) -> None:
    """Register the ``/internal/readiness`` endpoint on the FastAPI app."""
    app.include_router(_readiness_router)
