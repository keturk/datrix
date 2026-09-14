"""Microservice helper functions for generated Python code.

Uses httpx for HTTP calls, tenacity for retry/backoff, pybreaker for circuit breakers.
Service URLs are resolved from the config store peer-URL namespace (no env reads).
"""

from __future__ import annotations

import asyncio
import datetime
import decimal
import enum
import inspect
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

import httpx
import pybreaker
import tenacity

logger = logging.getLogger(__name__)

from ._service_credential import acquire_service_credential


async def _inter_service_auth_headers() -> dict[str, str]:
    """Bearer credential for raw HTTP calls to peer services (managed machine identity).

    The credential's audience is the machine identity provider's own resource,
    resolved inside ``acquire_service_credential`` — never the callee's network
    address. Fails closed: a token-acquisition failure raises rather than returning
    empty headers — an unauthenticated peer call is never emitted (design principle 15).
    """
    token = await acquire_service_credential()
    return {"Authorization": f"Bearer {token}"}


# ── Service URL resolution ──


def _datrix_str(value: object) -> str:
    """String conversion matching Datrix DSL interpolation semantics."""
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, decimal.Decimal):
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    return str(value)


def _json_default(value: object) -> object:
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", by_alias=True)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_serialize(value: object) -> str:
    return json.dumps(value, default=_json_default)


def _json_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(headers or {})
    merged.setdefault("Content-Type", "application/json")
    return merged


def _ms_join_base_path(base_path: str, endpoint: object) -> str:
    path = str(endpoint)
    base = base_path.rstrip("/")
    if not base:
        return path if path.startswith("/") else f"/{path}"
    if path == base or path.startswith(f"{base}/"):
        return path
    return f"{base}/{path.lstrip('/')}"


_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_microservice_http_timeout: ContextVar[float | None] = ContextVar(
    "microservice_http_timeout", default=None
)


_MS_DEFAULT_TIMEOUT: float = 300.0


def _http_client(**kwargs: object) -> httpx.AsyncClient:
    timeout = _microservice_http_timeout.get()
    if timeout is not None and "timeout" not in kwargs:
        kwargs["timeout"] = timeout
    elif "timeout" not in kwargs:
        kwargs["timeout"] = _MS_DEFAULT_TIMEOUT
    return httpx.AsyncClient(**kwargs)


def _raise_for_status_with_body(response: httpx.Response, url: str) -> None:
    if response.status_code >= 400:
        logger.error(
            "inter_service_http_failed url=%s status=%s body=%s",
            url,
            response.status_code,
            response.text[:500],
        )
    response.raise_for_status()


async def _await_if_needed(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


# In-process registry populated by the lifespan startup from the config store.
# Key: service kebab name (e.g. "ecommerce-user-service").
# Value: base URL (e.g. "http://ecommerce-user-service:8000").
_SERVICE_URLS: dict[str, str] = {}


def _register_service_url(service: str, url: str) -> None:
    """Register a peer service URL at lifespan startup.

    Called by the generated lifespan init (populated from the config store
    peer-URL namespace). Must be called before any inter-service call.

    Args:
        service: Service kebab name (e.g. ``"ecommerce-user-service"``).
        url: Base URL for the service (e.g. ``"http://ecommerce-user-service:8000"``).
    """
    _SERVICE_URLS[service] = url


def _resolve_service_url(service: str) -> str:
    """Resolve a peer service base URL from the in-process registry.

    URLs are populated at lifespan startup from the config store peer-URL
    namespace. No environment reads are performed.

    Args:
        service: Service kebab name (e.g. ``"ecommerce-user-service"``).

    Returns:
        The base URL for the service.

    Raises:
        RuntimeError: When the service URL is not registered (startup missed it).
    """
    url = _SERVICE_URLS.get(service)
    if url is not None:
        return url
    raise RuntimeError(
        f"Peer service URL not registered for '{service}'. "
        "Ensure the lifespan init populates service URLs from the config store "
        "before making inter-service calls. Available: "
        + (", ".join(sorted(_SERVICE_URLS)) or "(none)")
    )


# ── HTTP call methods ──


async def _service_json_get(
    service: str, path: str, params: dict[str, object] | None = None
) -> object:
    """GET request to service path; returns JSON (distinct from _json_helpers._json_get for dict paths).

    Args:
        service: Service name for URL resolution
        path: Request path
        params: Optional query parameters
    """
    url = f"{_resolve_service_url(service)}{path}"
    headers = await _inter_service_auth_headers()
    async with _http_client() as client:
        response = await client.get(url, headers=headers, params=params)
        _raise_for_status_with_body(response, url)
        return response.json()


async def _ms_call(service: str, method: str, params: dict | None = None) -> object:
    """Call service method via HTTP POST."""
    url = f"{_resolve_service_url(service)}/{method}"
    headers = _json_headers(await _inter_service_auth_headers())
    async with _http_client() as client:
        response = await client.post(
            url, content=_json_serialize(params or {}), headers=headers
        )
        _raise_for_status_with_body(response, url)
        return response.json()


async def _ms_call_async(service: str, method: str, params: dict | None = None) -> None:
    """Fire-and-forget service call."""
    asyncio.create_task(_ms_call(service, method, params))


# Word-boundary split mirroring datrix_common.utils.text.to_snake_case: a camelCase
# boundary (aB), an acronym boundary (ABc), or any run of . - _ whitespace separators.
_MS_KEY_WORD_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|[.\-_\s]+"
)


def _ms_snake_key(key: str) -> str:
    """Snake_case one object key to the snake_case Python wire contract.

    Identical output to the build-time ``to_snake_case`` used for the receiving service's
    pydantic field names, so e.g. ``registrationNumber`` -> ``registration_number``.
    """
    words = [part.lower() for part in _MS_KEY_WORD_BOUNDARY.split(key) if part]
    return "_".join(words)


def _ms_snake_keys(value: object) -> object:
    """Recursively snake_case every object key in an inter-service request body.

    Applied only when the target endpoint's body is fully structurally typed (no free-form
    ``JSON``/``Map``), so every key is a declared struct/entity field name rather than
    data. Fixes camelCase JSON-literal keys (including array-built/nested object literals)
    that a typed ``Array<Struct>`` consumer would otherwise reject with HTTP 422.
    """
    if isinstance(value, dict):
        return {_ms_snake_key(str(k)): _ms_snake_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_ms_snake_keys(item) for item in value]
    return value


async def _ms_post(service: str, endpoint: str, data: object) -> object:
    url = f"{_resolve_service_url(service)}{endpoint}"
    headers = _json_headers(await _inter_service_auth_headers())
    async with _http_client() as client:
        response = await client.post(
            url, content=_json_serialize(data), headers=headers
        )
        _raise_for_status_with_body(response, url)
        return response.json()


async def _ms_put(service: str, endpoint: str, data: object) -> object:
    url = f"{_resolve_service_url(service)}{endpoint}"
    headers = _json_headers(await _inter_service_auth_headers())
    async with _http_client() as client:
        response = await client.put(url, content=_json_serialize(data), headers=headers)
        _raise_for_status_with_body(response, url)
        return response.json()


async def _ms_patch(service: str, endpoint: str, data: object) -> object:
    url = f"{_resolve_service_url(service)}{endpoint}"
    headers = _json_headers(await _inter_service_auth_headers())
    async with _http_client() as client:
        response = await client.patch(
            url, content=_json_serialize(data), headers=headers
        )
        _raise_for_status_with_body(response, url)
        return response.json()


async def _ms_delete(service: str, endpoint: str) -> object:
    url = f"{_resolve_service_url(service)}{endpoint}"
    headers = await _inter_service_auth_headers()
    async with _http_client() as client:
        response = await client.delete(url, headers=headers)
        _raise_for_status_with_body(response, url)
        return response.json()


async def _http_post_with_headers(
    url: str, body: str, headers: dict[str, str]
) -> dict[str, object]:
    """POST a UTF-8 string body with explicit headers (e.g. webhooks with HMAC).

    Returns a dict with ``statusCode`` (HTTP status) and ``body`` (parsed JSON or
    ``None`` if the response is not valid JSON). Does not raise on 4xx/5xx.
    """
    async with _http_client() as client:
        response = await client.post(url, content=body.encode("utf-8"), headers=headers)
    try:
        parsed: object = response.json()
    except Exception:
        parsed = None
    return {"statusCode": response.status_code, "body": parsed}


async def _http_post_webhook(
    url: str, body: str, signature: str, delivery_id: str
) -> dict[str, object]:
    """POST JSON webhook with standard HMAC and tracing headers."""
    headers = {
        "X-Webhook-Signature": signature,
        "X-Webhook-Id": delivery_id,
        "Content-Type": "application/json",
    }
    return await _http_post_with_headers(url, body, headers)


async def _ms_call_with_options(service: str, endpoint: str, options: dict) -> object:
    url = f"{_resolve_service_url(service)}{endpoint}"
    opts = dict(options)
    timeout = opts.pop("timeout", None)
    extra_headers = opts.pop("headers", None)
    method = opts.pop("method", "GET")
    merged_headers: dict[str, str] = dict(await _inter_service_auth_headers())
    if extra_headers:
        merged_headers.update(extra_headers)
    client_kwargs: dict[str, object] = {"headers": merged_headers}
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    async with _http_client(**client_kwargs) as client:
        response = await client.request(method, url)
        response.raise_for_status()
        return response.json()


# ── Service discovery ──


async def _ms_discover(service: str) -> dict[str, object]:
    return {"name": service, "url": _resolve_service_url(service)}


async def _ms_health(service: str) -> dict[str, object]:
    url = f"{_resolve_service_url(service)}/health"
    async with _http_client() as client:
        response = await client.get(url)
        return response.json()


async def _ms_register(service: str, endpoint: str) -> None:
    """Register a peer service URL in the in-process registry."""
    _register_service_url(service, endpoint)


async def _ms_deregister(service: str) -> None:
    """Remove a peer service URL from the in-process registry."""
    _SERVICE_URLS.pop(service, None)


def _ms_get_url(service: str) -> str:
    return _resolve_service_url(service)


async def _ms_is_available(service: str) -> bool:
    try:
        await _ms_health(service)
        return True
    except Exception:
        return False


def _ms_list_services() -> list[str]:
    """Return kebab names of all registered peer services."""
    return list(_SERVICE_URLS.keys())


async def _ms_health_check_all() -> dict[str, object]:
    services = _ms_list_services()
    results: dict[str, object] = {}
    for svc in services:
        try:
            results[svc] = await _ms_health(svc)
        except Exception as e:
            results[svc] = {"status": "unhealthy", "error": str(e)}
    return results


# ── Resilience patterns ──

_circuit_breakers: dict[str, pybreaker.CircuitBreaker] = {}


def _get_circuit_breaker(service: str) -> pybreaker.CircuitBreaker:
    if service not in _circuit_breakers:
        _circuit_breakers[service] = pybreaker.CircuitBreaker(
            fail_max=5, reset_timeout=30, name=service
        )
    return _circuit_breakers[service]


async def _ms_with_circuit_breaker(
    service: str, callback: Callable[..., object]
) -> object:
    """Execute *callback* inside a circuit breaker.

    ``pybreaker``'s ``call_async`` relies on ``tornado.gen.coroutine`` which was
    removed in Python 3.14.  This wrapper replicates the state-machine logic
    (open guard, half-open transition, listener hooks, failure/success counting)
    using native ``async``/``await`` so no Tornado dependency is needed.
    """
    cb = _get_circuit_breaker(service)

    with cb._lock:
        # Pre-call: open-state guard raises CircuitBreakerError when the
        # reset timeout has not elapsed.  When the timeout *has* elapsed the
        # open state transitions to half-open and attempts a synchronous
        # ``self._breaker.call(func)``; we pass a no-op so that call
        # completes harmlessly — the real execution happens below.
        cb.state.before_call(lambda: None)
        for listener in cb.listeners:
            listener.before_call(cb, callback)

    try:
        result = await _await_if_needed(callback())
    except BaseException as exc:
        with cb._lock:
            cb.state._handle_error(exc)
        raise  # pragma: no cover — _handle_error(reraise=True) always re-raises
    else:
        with cb._lock:
            cb.state._handle_success()
        return result


def _ms_get_circuit_state(service: str) -> str:
    cb = _get_circuit_breaker(service)
    return cb.current_state


def _ms_reset_circuit(service: str) -> None:
    if service in _circuit_breakers:
        del _circuit_breakers[service]


async def _ms_with_retry(callback: Callable[..., object], max_retries: int) -> object:
    retrying = tenacity.AsyncRetrying(
        stop=tenacity.stop_after_attempt(max_retries),
        wait=tenacity.wait_fixed(1),
        reraise=True,
    )

    async def _call() -> object:
        return await _await_if_needed(callback())

    return await retrying(_call)


async def _ms_with_exponential_backoff(
    callback: Callable[..., object], max_retries: int, backoff_ms: int
) -> object:
    retrying = tenacity.AsyncRetrying(
        stop=tenacity.stop_after_attempt(max_retries),
        wait=tenacity.wait_exponential(multiplier=backoff_ms / 1000),
        reraise=True,
    )

    async def _call() -> object:
        return await _await_if_needed(callback())

    return await retrying(_call)


async def _ms_with_timeout(callback: Callable[..., object], timeout_ms: int) -> object:
    timeout_seconds = timeout_ms / 1000
    token = _microservice_http_timeout.set(timeout_seconds)
    try:
        return await asyncio.wait_for(
            _await_if_needed(callback()),
            timeout=timeout_seconds,
        )
    finally:
        _microservice_http_timeout.reset(token)


_bulkhead_semaphores: dict[str, asyncio.Semaphore] = {}


async def _ms_with_bulkhead(service: str, callback: Callable[..., object]) -> object:
    if service not in _bulkhead_semaphores:
        _bulkhead_semaphores[service] = asyncio.Semaphore(10)
    async with _bulkhead_semaphores[service]:
        return await _await_if_needed(callback())


# ── In-process config store (key/value pairs populated at startup) ──

_MS_CONFIG: dict[str, str] = {}


def _register_ms_config(key: str, value: str) -> None:
    """Register a runtime config value at lifespan startup.

    Called by the generated lifespan init for values loaded from the config store.
    """
    _MS_CONFIG[key] = value


# ── Config ──


async def _ms_get_config(key: str) -> object:
    """Get a config value from the in-process config store (no env reads)."""
    if key not in _MS_CONFIG:
        raise KeyError(
            f"Config key '{key}' not found in the in-process config store. "
            "Ensure the lifespan init populates all required config keys from the "
            "config store before accessing them."
        )
    return _MS_CONFIG[key]


async def _ms_set_config(key: str, value: object) -> None:
    """Set a config value in the in-process config store."""
    _MS_CONFIG[key] = str(value)


# ── Tracing ──


def _ms_propagate_context(headers: dict) -> dict:
    tid = _trace_id.get()
    if not tid:
        tid = str(uuid.uuid4())
        _trace_id.set(tid)
    headers["X-Trace-Id"] = tid
    return headers


def _ms_get_trace_id() -> str:
    tid = _trace_id.get()
    if not tid:
        tid = str(uuid.uuid4())
        _trace_id.set(tid)
    return tid


def _ms_set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


# ── Events ──


async def _ms_broadcast(event: str, data: object) -> list[tuple[str, bool, str]]:
    """Broadcast event to all registered services.

    Delivery is not silently swallowed: every peer's outcome is recorded and
    returned so the caller can act on partial failure (retry, alert, dead-letter)
    instead of only observing a log line (design decision 11 — resilience is
    declared policy, never a silent generator-invented degrade).

    Returns:
        One ``(service, ok, error_summary)`` tuple per registered service.
        ``error_summary`` is ``""`` when ``ok`` is ``True``.
    """
    outcomes: list[tuple[str, bool, str]] = []
    for service in _ms_list_services():
        try:
            await _ms_post(service, f"/events/{event}", data)
        except Exception as exc:
            logger.warning(
                "broadcast_failed service=%s event=%s",
                service,
                event,
                exc_info=True,
            )
            outcomes.append((service, False, str(exc)))
        else:
            outcomes.append((service, True, ""))
    return outcomes


async def _ms_subscribe(event: str, handler: Callable[..., object]) -> None:
    """Subscribe to a Kafka event topic and dispatch payloads to ``handler``.

    Broker connection info is resolved from the in-process config store
    (populated at lifespan startup from AppSettings). No environment reads.
    """
    import json as _json

    from aiokafka import AIOKafkaConsumer

    brokers_raw = _MS_CONFIG.get("bootstrap_servers")
    if not brokers_raw:
        raise RuntimeError(
            "Kafka broker address not found in the in-process config store. "
            "Ensure AppSettings includes 'bootstrap_servers' and "
            "the lifespan init registers it via _register_ms_config() before "
            "calling Microservice.subscribe."
        )
    topic_key = "event_topic_" + event.lower().replace("-", "_").replace(".", "_")
    topic = _MS_CONFIG.get(topic_key, event)
    group_id = _MS_CONFIG.get(
        "event_group_id",
        "datrix-" + event.lower().replace(".", "-").replace("_", "-") + "-subscriber",
    )
    auto_offset_reset = _MS_CONFIG.get("event_auto_offset_reset", "latest")
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=[b.strip() for b in brokers_raw.split(",") if b.strip()],
        group_id=group_id,
        enable_auto_commit=True,
        auto_offset_reset=auto_offset_reset,
    )
    await consumer.start()
    logger.info(
        "event_subscription_started event=%s topic=%s group=%s", event, topic, group_id
    )
    try:
        async for message in consumer:
            raw = message.value
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            envelope = _json.loads(raw)
            payload = (
                envelope.get("payload", envelope)
                if isinstance(envelope, dict)
                else envelope
            )
            result = handler(payload)
            if hasattr(result, "__await__"):
                await result
    finally:
        await consumer.stop()


async def _ms_publish(event_name: str, payload: object) -> list[tuple[str, bool, str]]:
    """Publish event (same as broadcast); returns the same per-target outcomes."""
    return await _ms_broadcast(event_name, payload)


# ── Load balancing ──


def _ms_get_next_instance(service: str) -> str:
    """Round-robin instance selection."""
    return _resolve_service_url(service)


def _ms_get_all_instances(service: str) -> list[str]:
    """Get all instances (single instance per env-based discovery)."""
    return [_resolve_service_url(service)]


# ── Rate limiting ──

_rate_limit_counters: dict[str, list[float]] = {}


async def _ms_check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Check if request is within rate limit (in-memory)."""
    now = time.time()
    if key not in _rate_limit_counters:
        _rate_limit_counters[key] = []
    _rate_limit_counters[key] = [
        t for t in _rate_limit_counters[key] if now - t < window_seconds
    ]
    if len(_rate_limit_counters[key]) >= limit:
        return False
    _rate_limit_counters[key].append(now)
    return True


async def _ms_get_rate_limit_status(key: str) -> dict[str, object]:
    """Get rate limit status."""
    timestamps = _rate_limit_counters.get(key, [])
    return {
        "key": key,
        "count": len(timestamps),
        "oldest": min(timestamps) if timestamps else None,
    }
