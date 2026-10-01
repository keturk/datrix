#!/usr/bin/env python3
"""API-key identity round-trip gate: revocation, tenant scoping, exact concurrent
rate-limiting, bounded lastUsedAt writes, and cross-language parity against a
live backend.

Generates the key-bearing ecommerce fixture for every registered backend
language, boots each with real Postgres and Redis via docker compose, issues
real API keys through the generated issuance endpoint, and drives against the
live stack:

* **immediate revocation** -- a key that verifies is refused on its very next
  request once its stored row is deactivated;
* **exact concurrent rate-limit counting** -- N truly concurrent requests on a
  key whose stored limit is L admit exactly ``min(N, L)``;
* **bounded lastUsedAt writes** -- K verifications inside one resolution window
  write the key's row exactly once;
* **tenant from the key row** -- against a second, tenant-scoped fixture, a
  request tenant that differs from the key's stored tenant is refused 403 and a
  matching or absent one is admitted;
* **cross-language parity** -- every backend renders the same outcome vector
  for every probe above.

Lives here, as a repo-level script, for the same reason
``wire-shape-round-trip-gate.ps1`` does: it asserts on the COMBINED output of
several generator packages (each backend language package, the container
runtime that boots it, the SQL schema it migrates), which the repository's
boundary rules forbid inside any single package's test suite.

Backend targets are never hardcoded: they are enumerated from the
``datrix.languages`` entry-point group at run time, and the gate refuses to run
with fewer than two, because cross-language parity is vacuous with one. A
backend that cannot be generated or booted fails the gate -- every registered
backend must participate for parity to mean anything.

Every probe reads and writes the REAL booted stack: the HTTP outcomes come from
the stack's own gateway, and the key rows and rate-limit counters are read from
its own Postgres and Redis, reached with the connection facts and credentials
the generated project itself provisions. Nothing is mocked and nothing is
inferred from timing.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Final

import asyncpg
import httpx
import redis

_HERE = Path(__file__).resolve()
_LIBRARY_DIR = _HERE.parent.parent
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402
from shared.generated_stack import (  # noqa: E402
    COMPOSE_FILENAME,
    DOCKER_QUERY_TIMEOUT_SECONDS,
    EmittedArtifactDefect,
    analyze_fixture,
    assert_container_names_are_free,
    assert_fixed_host_ports_are_free,
    boot_stack,
    compose_bind_mounts,
    compose_document,
    compose_services,
    configure_logging,
    fixed_host_port_of,
    fixture_demanded_roles,
    generate_project,
    mint_bearer_token,
    plan_entry_point,
    plan_token_issuance,
    prepare_env_file,
    prepare_isolated_source,
    published_host_port,
    resolve_dialled_host,
    resolve_entry_base_url,
    run_command,
    run_diagnostic_durability_self_test,
    stop_stack,
)

# The fixture facts every probe needs are read from the analyzed application
# through the same model APIs the generators render from: which providers a
# route admits, where an API-key provider stores its keys, the store entity's
# table and column names, and the connection keys a service's blocks publish.
from datrix_codegen_common.algorithms.entity_model_context import entity_table_name  # noqa: E402
from datrix_common.config.datasource.identity_config import ApiKeyProviderConfig  # noqa: E402
from datrix_common.config.service_config.models import TenantIdentifierSource  # noqa: E402
from datrix_common.datrix_model.containers import Application, Service  # noqa: E402
from datrix_common.datrix_model.identity_admission import api_key_providers_of  # noqa: E402
from datrix_common.datrix_model.rest_route_paths import (  # noqa: E402
    resolved_rest_endpoint_path,
    route_endpoint_through_gateway,
)
from datrix_common.deployment.connection_surface import (  # noqa: E402
    CONNECTIONS_NAMESPACE,
    derive_connection_surface,
)
from datrix_common.deployment.runtime_bootstrap import FILE_CONFIG_STORE_NAME  # noqa: E402
from datrix_common.paths import ServicePaths  # noqa: E402
from datrix_common.utils.text import to_snake_case  # noqa: E402
from datrix_semantic.validators.identity_api_key_common import find_store_service  # noqa: E402

logger = logging.getLogger(__name__)

#: This file lives at <datrix>/scripts/library/test/api_key_identity_round_trip.py --
#: parents[3] is <datrix>.
DATRIX_DIR: Final[Path] = _HERE.parents[3]

#: The key-bearing product example: one API-key provider whose keys are stored
#: by one service and admitted by a route of another.
FIXTURE_SOURCE: Final[Path] = DATRIX_DIR / "examples" / "03-domains" / "ecommerce" / "system.dtrx"
FIXTURE_ROOT: Final[Path] = FIXTURE_SOURCE.parent
FIXTURE_PROFILE: Final[str] = "test"

#: Scratch space. Derived from DATRIX_DIR rather than written as an absolute
#: drive path: this file is committed and the workspace is cloned to different
#: roots on different machines. Never inside a package repository.
WORK_ROOT: Final[Path] = DATRIX_DIR.parent / ".tmp" / "api-key-identity-round-trip"

#: The tenant-scoped fixture's own sources, kept beside this gate. The product
#: example declares no tenant-scoped entity anywhere, so tenant-from-the-key-row
#: enforcement has nothing to run against there; this fixture exists only to
#: prove it and is never a product example.
TENANCY_FIXTURE_TEMPLATE: Final[Path] = _HERE.parent / "api_key_identity_fixture"

#: Where the tenant-scoped fixture is assembled for a run.
TENANCY_FIXTURE_ROOT: Final[Path] = WORK_ROOT / "tenancy-fixture"

#: Configuration the tenant-scoped fixture shares with the product example
#: rather than restating it: the compose deployment profile and the two
#: platform-managed identity providers (the signed-in caller who is issued a
#: key, and the machine identity that calls the key-verification route).
SHARED_FIXTURE_CONFIG: Final[tuple[Path, ...]] = (
    Path("config") / "system.dcfg",
    Path("config") / "identity" / "identity.dcfg",
    Path("config") / "identity" / "platform.dcfg",
)

#: The fixtures' issuance endpoint and the members of its request and response,
#: as the fixtures declare them (``issueApiKey`` taking ``IssueApiKeyRequest``
#: and answering ``IssueApiKeyResponse``) and as they travel on the wire.
ISSUANCE_ENDPOINT_NAME: Final[str] = "issueApiKey"
ISSUANCE_SCOPES_MEMBER: Final[str] = "scopes"
ISSUANCE_EXPIRY_MEMBER: Final[str] = "expiresAt"
ISSUED_KEY_MEMBER: Final[str] = "apiKey"
ISSUED_KEY_ID_MEMBER: Final[str] = "id"

#: The success statuses of the issuance POST: a backend answers a creating POST
#: with 200 or 201 by its own language's convention.
ISSUANCE_SUCCESS_STATUSES: Final[frozenset[int]] = frozenset({200, 201})

#: The gate named in the environment file it supplies missing compose values to.
_ENV_SUPPLIER: Final[str] = "API-key identity round-trip gate"

#: Every call to the stack goes through its own gateway, which declares one
#: address-keyed request zone shared by every route. Sequential probe calls are
#: paced under that zone's rate, and a concurrent burst is fired only after
#: waiting long enough for the zone's burst allowance to refill -- the emitted
#: limit is honoured, never routed around. A burst the gateway still throttles
#: is caught by the rate-limit counter corroboration below, never miscounted.
GATEWAY_PACING_SECONDS: Final[float] = 0.7
GATEWAY_BURST_REFILL_SECONDS: Final[float] = 9.0

#: The concurrent rate-limit probe: the key's stored limit is lowered to
#: RATE_LIMIT_PROBE_LIMIT and RATE_LIMIT_PROBE_CONCURRENCY requests are fired
#: at once. Concurrency exceeds the limit (so refusals must occur) and stays
#: within the gateway zone's burst allowance (so every request reaches the store).
RATE_LIMIT_PROBE_LIMIT: Final[int] = 3
RATE_LIMIT_PROBE_CONCURRENCY: Final[int] = 8

#: A burst starts only when at least this many seconds remain in the store's
#: current rate-limit window, so all of its requests are counted in one window.
RATE_LIMIT_WINDOW_MARGIN_SECONDS: Final[int] = 15

#: The store's rate-limit counter key for one key and one window. Read only to
#: corroborate the HTTP outcomes; the probe's verdict comes from the outcomes.
RATE_LIMIT_COUNTER_PATTERN: Final[str] = "apikey:rl:{provider}:{key_id}:*"

#: Verifications made inside one lastUsedAt resolution window.
LAST_USED_PROBE_CALLS: Final[int] = 5

#: Seconds an HTTP probe call may take before the stack is reported unresponsive.
HTTP_TIMEOUT_SECONDS: Final[float] = 60.0

#: A compose-published datastore port is bound on this machine's loopback.
LOOPBACK_HOST: Final[str] = "127.0.0.1"

#: Postgres identifiers this gate interpolates into SQL are names derived from
#: the fixture model (table and column names) and are additionally required to
#: match this shape before they are quoted -- values always travel as bound
#: parameters.
_SQL_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z_][a-z0-9_]*$")

#: The bearer scheme of the issuance call's Authorization header.
_BEARER_PREFIX: Final[str] = "Bearer "
_RETRY_AFTER_HEADER: Final[str] = "Retry-After"

#: Key-row roles this gate reads, beyond the provider's field map.
_ROLE_ID: Final[str] = "id"


class Outcome(StrEnum):
    """The outcome of one key-authenticated request, as the client observes it."""

    OK = "ok"
    INVALID = "invalid"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    UNAVAILABLE = "unavailable"
    UNEXPECTED = "unexpected"


class ProbeFailure(RuntimeError):
    """A probe observed the live stack violate the property it exists to prove."""


@dataclass(frozen=True)
class KeyRowState:
    """One read of an API key's stored row.

    Attributes:
        key_id: The row's primary key.
        version: The row version (Postgres ``xmin``): it changes on every
            write to the row and on nothing else, so two equal reads prove no
            write happened between them.
        key_hash: The stored hash of the raw key.
        active: Whether the key is active.
        expires_at: When the key expires, ``None`` for never.
        last_used_at: When the key was last recorded as used.
        rate_limit: Requests the key may make per rate-limit window.
        tenant_id: The key's tenant, ``None`` when the provider maps none.
    """

    key_id: str
    version: str
    key_hash: str
    active: bool
    expires_at: datetime.datetime | None
    last_used_at: datetime.datetime | None
    rate_limit: int
    tenant_id: str | None


@dataclass(frozen=True)
class Expectation:
    """The outcome the design's decision order prescribes for a key row, and why."""

    outcome: Outcome
    reason: str


@dataclass(frozen=True)
class ObservedResponse:
    """One HTTP answer, reduced to what outcome classification reads."""

    status: int
    retry_after: str | None


@dataclass(frozen=True)
class KeyProviderFacts:
    """Everything the probes need to know about one API-key provider, read from the model.

    Attributes:
        provider: The API-key provider's logical name.
        header: The request header carrying the key.
        scopes: The provider-local scope names a key is issued with.
        store_service: The service storing the keys.
        store_compose_service: That service's compose service name.
        store_block: The store service's RDBMS block holding the key entity.
        table: The key entity's table.
        columns: Column name per key-row role (``id`` plus the field map's roles).
        tenant_mapped: Whether the provider maps a tenant field.
        last_used_resolution_seconds: The lastUsedAt write resolution.
        rate_limit_window_seconds: The rate-limit window.
        rate_limit_cache: The store service's cache block holding the counters.
        issuance_path: Gateway path of the fixture's issuance endpoint.
        probe_path: Gateway path of a GET route admitting the provider.
        probe_service: The service owning the probe route.
    """

    provider: str
    header: str
    scopes: tuple[str, ...]
    store_service: Service
    store_compose_service: str
    store_block: str
    table: str
    columns: dict[str, str]
    tenant_mapped: bool
    last_used_resolution_seconds: int
    rate_limit_window_seconds: int
    rate_limit_cache: str
    issuance_path: str
    probe_path: str
    probe_service: Service


@dataclass(frozen=True)
class StoreConnection:
    """How to reach one compose-hosted datastore from this machine.

    Attributes:
        host: Loopback host the datastore's container port is published on.
        port: The published host port.
        database: The database (or Redis database index) the service uses.
        user: The login the service uses, empty when the store has none.
        password: The provisioned credential, held in memory only and never logged.
    """

    host: str
    port: int
    database: str
    user: str
    password: str

    def __repr__(self) -> str:
        """Never render the credential."""
        return f"StoreConnection(host={self.host!r}, port={self.port}, database={self.database!r})"


@dataclass(frozen=True)
class BackendStack:
    """Everything one booted stack needs to be driven.

    Attributes:
        backend: The ``datrix.languages`` entry-point name.
        project_dir: The generated project root.
        base_url: The gateway base URL.
        facts: The fixture's API-key provider facts.
        db: Connection to the key store's Postgres database.
        rate_limit_store: Connection to the key store's rate-limit Redis.
        bearer_token: A bearer credential the stack's own identity plumbing
            accepts; never logged.
        subject: The identity the bearer token speaks for.
    """

    backend: str
    project_dir: Path
    base_url: str
    facts: KeyProviderFacts
    db: StoreConnection
    rate_limit_store: StoreConnection
    bearer_token: str
    subject: str

    def __repr__(self) -> str:
        """Never render the bearer credential."""
        return f"BackendStack(backend={self.backend!r}, base_url={self.base_url!r})"


@dataclass(frozen=True)
class IssuedKey:
    """A key issued through the live issuance endpoint. ``raw_key`` is a credential."""

    key_id: str
    raw_key: str

    def __repr__(self) -> str:
        """Never render the raw key."""
        return f"IssuedKey(key_id={self.key_id!r})"


# --------------------------------------------------------------------------
# Outcome classification -- the functions the self-test proves sensitive
# --------------------------------------------------------------------------


def expected_outcome(
    row: KeyRowState | None, now: datetime.datetime, window_count: int
) -> Expectation:
    """The outcome the key-verification decision order prescribes for *row*.

    The order is: no row, inactive, and expired are each ``invalid``; a request
    counted beyond the row's limit in the current window is ``rate_limited``;
    anything else is ``ok``.

    Args:
        row: The key's stored row as read from the store, ``None`` for no row.
        now: The moment of the request.
        window_count: This request's position in the key's current rate-limit
            window, counting itself.
    """
    if row is None:
        return Expectation(Outcome.INVALID, "no stored row")
    if not row.active:
        return Expectation(Outcome.INVALID, "inactive")
    if row.expires_at is not None and row.expires_at <= now:
        return Expectation(Outcome.INVALID, "expired")
    if window_count > row.rate_limit:
        return Expectation(Outcome.RATE_LIMITED, f"request {window_count} over limit {row.rate_limit}")
    return Expectation(Outcome.OK, "active, unexpired, within its limit")


def classify_response(response: ObservedResponse) -> Outcome:
    """Reduce an HTTP answer to its key-verification outcome.

    A refusal for rate limiting is only recognised with an integer
    ``Retry-After``; a 429 without one is a malformed refusal, never counted as
    a limit being enforced.
    """
    if 200 <= response.status < 300:
        return Outcome.OK
    if response.status == 401:
        return Outcome.INVALID
    if response.status == 403:
        return Outcome.FORBIDDEN
    if response.status == 429:
        retry_after = response.retry_after
        return Outcome.RATE_LIMITED if retry_after is not None and retry_after.isdigit() else Outcome.UNEXPECTED
    if response.status == 503:
        return Outcome.UNAVAILABLE
    return Outcome.UNEXPECTED


def judge_against_row(observed: ObservedResponse, expectation: Expectation, step: str) -> str | None:
    """Compare one observed answer to the outcome its key row prescribes.

    Returns:
        ``None`` when they agree; a failure description naming the step, the
        row's reason, and both outcomes otherwise.
    """
    actual = classify_response(observed)
    if actual is expectation.outcome:
        return None
    return (
        f"{step}: the key row prescribes {expectation.outcome.value!r} ({expectation.reason}) but the "
        f"stack answered HTTP {observed.status} ({actual.value!r})"
    )


def tally_outcomes(outcomes: Sequence[Outcome]) -> dict[Outcome, int]:
    """Count each outcome in *outcomes*."""
    counts: dict[Outcome, int] = {}
    for outcome in outcomes:
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def judge_rate_limit(outcomes: Sequence[Outcome], limit: int) -> str | None:
    """Exactly ``min(N, limit)`` of N requests on one key admitted, the rest refused for the limit.

    Returns:
        ``None`` when the burst was counted exactly; a failure description with
        the observed counts otherwise.
    """
    expected_ok = min(len(outcomes), limit)
    expected_limited = len(outcomes) - expected_ok
    counts = tally_outcomes(outcomes)
    ok = counts.get(Outcome.OK, 0)
    limited = counts.get(Outcome.RATE_LIMITED, 0)
    if ok == expected_ok and limited == expected_limited:
        return None
    observed = {outcome.value: count for outcome, count in sorted(counts.items())}
    return (
        f"{len(outcomes)} concurrent requests on a key limited to {limit} per window: expected exactly "
        f"{expected_ok} 'ok' and {expected_limited} 'rate_limited', observed {observed}"
    )


def count_row_writes(snapshots: Sequence[KeyRowState]) -> int:
    """Count the writes between consecutive reads of one key row.

    Every write to a row changes its version, and reads are taken between
    sequential requests, so each changed version between two neighbouring
    reads is a write made by the request between them.
    """
    return sum(1 for before, after in zip(snapshots, snapshots[1:]) if before.version != after.version)


def judge_last_used_writes(snapshots: Sequence[KeyRowState]) -> str | None:
    """Exactly one write for every verification made inside one resolution window.

    *snapshots* holds a read before the first verification and one after each.

    Returns:
        ``None`` when the row was written exactly once and that write recorded
        a use; a failure description otherwise.
    """
    calls = len(snapshots) - 1
    writes = count_row_writes(snapshots)
    if writes != 1:
        return (
            f"{calls} verifications inside one lastUsedAt resolution window wrote the key row "
            f"{writes} time(s); expected exactly 1"
        )
    if snapshots[-1].last_used_at is None:
        return f"{calls} verifications wrote the key row once but recorded no lastUsedAt"
    return None


def compare_outcome_vectors(results_by_backend: dict[str, dict[str, tuple[str, ...]]]) -> list[str]:
    """Cross-language parity: every backend must answer identically for every probe.

    Returns:
        One description per probe whose outcome vector differs across backends;
        empty means parity holds.
    """
    probes = sorted({probe for vectors in results_by_backend.values() for probe in vectors})
    differences: list[str] = []
    for probe in probes:
        rendered = {backend: vectors.get(probe) for backend, vectors in sorted(results_by_backend.items())}
        if len({vector for vector in rendered.values()}) > 1:
            differences.append(f"{probe}: {rendered}")
    return differences


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def _synthetic_row(**overrides: object) -> KeyRowState:
    """An active, unexpired key row well within its limit; *overrides* replace fields."""
    row = KeyRowState(
        key_id=str(uuid.UUID(int=1)),
        version="100",
        key_hash=hashlib.sha256(b"self-test").hexdigest(),
        active=True,
        expires_at=None,
        last_used_at=None,
        rate_limit=100,
        tenant_id=None,
    )
    return replace(row, **overrides)  # type: ignore[arg-type]


def _self_test_row_classifier(now: datetime.datetime) -> list[str]:
    """The 'ok' classifier accepts a live key's answer and rejects a revoked or expired one."""
    problems: list[str] = []
    success = ObservedResponse(status=200, retry_after=None)
    live = _synthetic_row()
    if judge_against_row(success, expected_outcome(live, now, 1), "self-test live key") is not None:
        problems.append(
            "an active, unexpired, under-limit key row answered 200 was judged a failure -- the 'ok' "
            "classifier over-triggers"
        )
    logger.info("self-test: revoked-key leg -- a success answer for an inactive key row must be rejected")
    revoked = replace(live, active=False)
    verdict = judge_against_row(success, expected_outcome(revoked, now, 1), "self-test revoked key")
    if verdict is None:
        problems.append(
            "a success answer for a key whose row is inactive (revoked) was accepted as 'ok' -- a "
            "revocation that does not take effect would go undetected"
        )
    elif "inactive" not in verdict:
        problems.append(f"the revoked-key rejection does not name the inactive row: {verdict!r}")
    expired = replace(live, expires_at=now - datetime.timedelta(seconds=1))
    verdict = judge_against_row(success, expected_outcome(expired, now, 1), "self-test expired key")
    if verdict is None or "expired" not in verdict:
        problems.append(f"a success answer for an expired key row was not rejected as expired: {verdict!r}")
    if expected_outcome(None, now, 1).outcome is not Outcome.INVALID:
        problems.append("a key with no stored row was not prescribed 'invalid'")
    return problems


def _self_test_response_classifier() -> list[str]:
    """Statuses map to outcomes, and a 429 without an integer Retry-After is never a limit."""
    problems: list[str] = []
    cases = (
        (ObservedResponse(200, None), Outcome.OK),
        (ObservedResponse(201, None), Outcome.OK),
        (ObservedResponse(401, None), Outcome.INVALID),
        (ObservedResponse(403, None), Outcome.FORBIDDEN),
        (ObservedResponse(429, "12"), Outcome.RATE_LIMITED),
        (ObservedResponse(429, None), Outcome.UNEXPECTED),
        (ObservedResponse(429, "soon"), Outcome.UNEXPECTED),
        (ObservedResponse(503, None), Outcome.UNAVAILABLE),
        (ObservedResponse(500, None), Outcome.UNEXPECTED),
    )
    for response, outcome in cases:
        actual = classify_response(response)
        if actual is not outcome:
            problems.append(f"HTTP {response.status} (Retry-After {response.retry_after!r}) classified {actual.value!r}, expected {outcome.value!r}")
    return problems


def _self_test_rate_limit_counter(now: datetime.datetime) -> list[str]:
    """A burst over the limit admits exactly min(N, L); one over- or under-admission fails."""
    problems: list[str] = []
    limit, burst = RATE_LIMIT_PROBE_LIMIT, RATE_LIMIT_PROBE_CONCURRENCY
    row = _synthetic_row(rate_limit=limit)
    prescribed = [expected_outcome(row, now, position).outcome for position in range(1, burst + 1)]
    admitted = tally_outcomes(prescribed).get(Outcome.OK, 0)
    if admitted != min(burst, limit):
        problems.append(f"{burst} requests against limit {limit} were prescribed {admitted} admissions, expected {min(burst, limit)}")
    if judge_rate_limit(prescribed, limit) is not None:
        problems.append(f"an exactly-counted burst was judged a failure: {judge_rate_limit(prescribed, limit)}")
    over = [Outcome.OK] * (limit + 1) + [Outcome.RATE_LIMITED] * (burst - limit - 1)
    if judge_rate_limit(over, limit) is None:
        problems.append("a burst admitting one request over the limit was accepted -- a racy counter would go undetected")
    under = [Outcome.OK] * (limit - 1) + [Outcome.RATE_LIMITED] * (burst - limit + 1)
    if judge_rate_limit(under, limit) is None:
        problems.append("a burst admitting one request under the limit was accepted")
    return problems


def _self_test_last_used_counter() -> list[str]:
    """K verifications writing once pass; writing on every verification fails."""
    problems: list[str] = []
    calls = LAST_USED_PROBE_CALLS
    stamp = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    bounded = [_synthetic_row(version="1")] + [
        _synthetic_row(version="2", last_used_at=stamp) for _ in range(calls)
    ]
    if count_row_writes(bounded) != 1 or judge_last_used_writes(bounded) is not None:
        problems.append(f"{calls} verifications writing the row once were not counted as exactly one write")
    unbounded = [_synthetic_row(version="1")] + [
        _synthetic_row(version=str(2 + index), last_used_at=stamp) for index in range(calls)
    ]
    if judge_last_used_writes(unbounded) is None:
        problems.append(f"{calls} verifications each writing the row were accepted -- unbounded writes would go undetected")
    silent = [_synthetic_row(version="1")] * (calls + 1)
    if judge_last_used_writes(silent) is None:
        problems.append("verifications that never recorded a use were accepted")
    return problems


def _self_test_parity() -> list[str]:
    """Identical outcome vectors agree; one differing probe is reported by name."""
    problems: list[str] = []
    same = {"left": {"probe": ("ok", "invalid")}, "right": {"probe": ("ok", "invalid")}}
    if compare_outcome_vectors(same):
        problems.append("identical outcome vectors were reported as differing")
    differing = {"left": {"probe": ("ok", "invalid")}, "right": {"probe": ("ok", "ok")}}
    found = compare_outcome_vectors(differing)
    if len(found) != 1 or "probe" not in found[0]:
        problems.append(f"a differing outcome vector was not reported by probe name: {found}")
    return problems


def _self_test_fixed_port_parser() -> list[str]:
    """The pre-boot port census sees a host port fixed behind a bind address, and nothing else."""
    cases = (
        ("8080:80", "8080"),
        ("127.0.0.1:29092:29092", "29092"),
        ("127.0.0.1::8006", None),
        ("5432", None),
        ("${GATEWAY_PORT:-8080}:80", None),
        ("9000:9000/udp", "9000"),
    )
    return [
        f"port mapping {mapping!r} parsed as fixing host port {fixed_host_port_of(mapping)!r}, expected {expected!r}"
        for mapping, expected in cases
        if fixed_host_port_of(mapping) != expected
    ]


def run_self_test() -> list[str]:
    """Prove the gate's own outcome classifiers are sensitive before any real run.

    Drives the REAL classification and counting functions the probes use
    against synthetic inputs -- no Docker, no network:

    * a success answer for an active, unexpired, under-limit key row must be
      accepted as 'ok';
    * the SAME answer for that row with ``active`` false (a revoked key) must
      be rejected, naming the inactive row -- and an expired row likewise;
    * a burst of N requests against a limit L must be prescribed exactly
      ``min(N, L)`` admissions, and a burst admitting one more or one fewer
      must be rejected;
    * K verifications writing the row once must count as exactly one write,
      and K writes must be rejected;
    * identical outcome vectors must agree and a differing one must be named.

    Returns:
        Failure descriptions; empty means every classifier is sound.
    """
    now = datetime.datetime.now(datetime.UTC)
    problems: list[str] = []
    problems.extend(_self_test_row_classifier(now))
    problems.extend(_self_test_response_classifier())
    problems.extend(_self_test_rate_limit_counter(now))
    problems.extend(_self_test_last_used_counter())
    problems.extend(_self_test_parity())
    problems.extend(_self_test_fixed_port_parser())
    return problems


# --------------------------------------------------------------------------
# Fixture facts
# --------------------------------------------------------------------------


def registered_backends() -> tuple[str, ...]:
    """Return every registered ``datrix.languages`` backend, sorted.

    Raises:
        RuntimeError: If fewer than two are registered -- this gate exists to
            prove cross-language parity, which is vacuous with one target.
    """
    backends = tuple(sorted(registered_language_names()))
    if len(backends) < 2:
        raise RuntimeError(
            f"Only {len(backends)} 'datrix.languages' backend(s) are registered ({list(backends)}). "
            f"Expected at least two, because this gate proves the API-key outcomes are identical "
            f"across languages and that is vacuous with one. Fix: install a second "
            f"datrix-codegen-<language> package into the shared environment."
        )
    return backends


def write_tenancy_fixture(root: Path) -> Path:
    """Assemble the tenant-scoped fixture application in *root*, return its ``system.dtrx``.

    Two services: ``AccountService`` owns the identity block, including a
    ``customerKeys`` API-key provider whose store entity ``ApiKey`` is
    ``Tenantable`` (its ``tenantId`` mapped as the key's tenant), and issues
    keys; ``CatalogService`` declares one ``auth(required, providers:
    [customerKeys])`` route reading a ``Tenantable`` entity, so a request
    tenant that disagrees with the key's has somewhere to be refused. Both
    resolve the request tenant from a header under strict enforcement.

    The service sources are this gate's own fixture files; the compose
    deployment profile and the two platform-managed identity providers are the
    product example's, copied rather than restated. Never written under
    ``datrix/examples/``.
    """
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(TENANCY_FIXTURE_TEMPLATE, root)
    for relative in SHARED_FIXTURE_CONFIG:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_ROOT / relative, target)
    source = root / FIXTURE_SOURCE.name
    if not source.is_file():
        raise RuntimeError(
            f"Assembling the tenant-scoped fixture produced no {FIXTURE_SOURCE.name} at {source}. "
            f"Expected a copy of {TENANCY_FIXTURE_TEMPLATE}."
        )
    return source


def _single_api_key_admission(app: Application) -> tuple[str, Service, str]:
    """The one GET route through the gateway that admits an API-key provider.

    Returns:
        ``(provider, owning service, gateway path)``.

    Raises:
        EmittedArtifactDefect: If the fixture has no such route, or its routes
            admit more than one API-key provider.
    """
    identity = app.identity
    if identity is None:
        raise EmittedArtifactDefect("The fixture declares no identity block, so no API-key provider exists to probe.")
    candidates: list[tuple[str, Service, str]] = []
    routes = (
        (service, api, endpoint)
        for service in app.services.values()
        for api in service.rest_apis.values()
        for endpoint in api.endpoints.values()
    )
    for service, api, endpoint in routes:
        if endpoint.method != "get" or not route_endpoint_through_gateway(endpoint):
            continue
        path = resolved_rest_endpoint_path(endpoint, api.base_path)
        if ":" in path:
            continue
        for admission in api_key_providers_of(endpoint.auth_contract, identity):
            candidates.append((admission.provider, service, path))
    providers = sorted({provider for provider, _, _ in candidates})
    if len(providers) != 1:
        raise EmittedArtifactDefect(
            f"Expected the fixture's parameterless gateway GET routes to admit exactly one API-key "
            f"provider, found {providers}. Fix: point the gate at a fixture with one key-admitting "
            f"route it can call without arguments."
        )
    return sorted(candidates, key=lambda candidate: candidate[2])[0]


def _issuance_path(store: Service) -> str:
    """Gateway path of the store service's issuance endpoint.

    Raises:
        EmittedArtifactDefect: If the store declares no issuance endpoint.
    """
    for api in store.rest_apis.values():
        for endpoint in api.endpoints.values():
            if endpoint.name is not None and str(endpoint.name) == ISSUANCE_ENDPOINT_NAME:
                return resolved_rest_endpoint_path(endpoint, api.base_path)
    raise EmittedArtifactDefect(
        f"The key store {store.qualified_name} declares no {ISSUANCE_ENDPOINT_NAME!r} endpoint, so "
        f"no key can be issued through the live stack. Expected the fixture's issuance route."
    )


def _key_columns(store: Service, api_key: ApiKeyProviderConfig) -> tuple[str, dict[str, str]]:
    """The key entity's table and the column of each key-row role.

    Raises:
        EmittedArtifactDefect: If the mapped block, entity, or a mapped field is missing.
    """
    block = store.rdbms_blocks.get(api_key.store_block)
    entity = None if block is None else block.entities.get(api_key.entity)
    if entity is None:
        raise EmittedArtifactDefect(
            f"{store.qualified_name} has no entity {api_key.entity!r} in block {api_key.store_block!r}."
        )
    primary_key = entity.primary_key()
    if primary_key is None:
        raise EmittedArtifactDefect(f"The key entity {api_key.entity!r} declares no primary key.")
    mapped = {
        "hash": api_key.fields.hash,
        "owner": api_key.fields.owner,
        "active": api_key.fields.active,
        "expires_at": api_key.fields.expires_at,
        "last_used_at": api_key.fields.last_used_at,
        "rate_limit": api_key.fields.rate_limit,
        "tenant": api_key.fields.tenant,
    }
    columns = {_ROLE_ID: str(primary_key.name.snake)}
    for role, field_name in mapped.items():
        if field_name is None:
            continue
        if field_name not in entity.fields:
            raise EmittedArtifactDefect(f"The key entity {api_key.entity!r} has no field {field_name!r} for role {role!r}.")
        columns[role] = str(entity.fields[field_name].name.snake)
    for role, column in columns.items():
        if not _SQL_IDENTIFIER_RE.match(column):
            raise EmittedArtifactDefect(f"Column {column!r} for key-row role {role!r} is not a plain SQL identifier.")
    table = entity_table_name(entity)
    if not _SQL_IDENTIFIER_RE.match(table):
        raise EmittedArtifactDefect(f"The key table {table!r} is not a plain SQL identifier.")
    return table, columns


def resolve_key_provider_facts(source: Path, profile: str) -> KeyProviderFacts:
    """Read every fact the probes need from the fixture's analyzed application.

    Raises:
        EmittedArtifactDefect: If the fixture lacks a piece the probes depend on.
    """
    app = analyze_fixture(source, profile)
    provider, probe_service, probe_path = _single_api_key_admission(app)
    identity = app.identity
    if identity is None:
        raise EmittedArtifactDefect("The fixture declares no identity block.")
    config = identity.require_provider_configs()[provider]
    api_key = config.api_key
    if api_key is None or api_key.rate_limit_window_seconds is None or api_key.rate_limit_cache is None:
        raise EmittedArtifactDefect(
            f"API-key provider {provider!r} declares no per-key rate limit (fields.rateLimit, "
            f"rateLimitWindowSeconds, rateLimitCache), so the concurrent-counting probe has nothing "
            f"to count against. Fix: declare one in the fixture."
        )
    store = find_store_service(app, api_key.store)
    if store is None:
        raise EmittedArtifactDefect(f"API-key provider {provider!r} names store {api_key.store!r}, which no service is.")
    table, columns = _key_columns(store, api_key)
    scopes = tuple(
        mapping.provider_local_name for mapping in identity.require_provider(provider).group_mappings
    )
    return KeyProviderFacts(
        provider=provider,
        header=api_key.header,
        scopes=scopes,
        store_service=store,
        store_compose_service=ServicePaths(store.name).compose_service,
        store_block=api_key.store_block,
        table=table,
        columns=columns,
        tenant_mapped=api_key.fields.tenant is not None,
        last_used_resolution_seconds=api_key.last_used_resolution_seconds,
        rate_limit_window_seconds=api_key.rate_limit_window_seconds,
        rate_limit_cache=api_key.rate_limit_cache,
        issuance_path=_issuance_path(store),
        probe_path=probe_path,
        probe_service=probe_service,
    )


def tenant_header_of(service: Service) -> str:
    """The request header *service* resolves its tenant from.

    Raises:
        EmittedArtifactDefect: If the service is not tenant-scoped by a header.
    """
    tenancy = None if service.config is None else service.config.tenancy
    if tenancy is None or tenancy.identifier.source is not TenantIdentifierSource.HEADER:
        raise EmittedArtifactDefect(
            f"{service.qualified_name} is not tenant-scoped by a request header, so a request tenant "
            f"that disagrees with a key's has nowhere to be sent. Fix: declare tenancy with a header "
            f"identifier in the tenant-scoped fixture."
        )
    return tenancy.identifier.name


# --------------------------------------------------------------------------
# The booted stack's own datastores
# --------------------------------------------------------------------------


def _store_config(project_dir: Path, compose_service: str) -> dict[str, object]:
    """The connection values the store service's emitted file config store carries.

    Raises:
        EmittedArtifactDefect: If the store service mounts no file config store.
    """
    mounted = [
        host
        for service, host, target in compose_bind_mounts(project_dir)
        if service == compose_service and Path(target).name == FILE_CONFIG_STORE_NAME
    ]
    if not mounted or not mounted[0].is_file():
        raise EmittedArtifactDefect(
            f"Compose service {compose_service!r} in {project_dir} mounts no {FILE_CONFIG_STORE_NAME}, "
            f"so its datastore connection facts cannot be read. Expected the emitted file config store."
        )
    document = json.loads(mounted[0].read_text(encoding="utf-8"))
    connections = document.get(CONNECTIONS_NAMESPACE)
    if not isinstance(connections, dict):
        raise EmittedArtifactDefect(f"{mounted[0]} carries no {CONNECTIONS_NAMESPACE!r} namespace.")
    return connections


def _mounted_secret(project_dir: Path, compose_service: str, handle: str) -> str | None:
    """The value of the provisioned secret *handle* the compose service mounts, if it mounts one."""
    document = compose_document(project_dir / COMPOSE_FILENAME)
    service = compose_services(project_dir)[compose_service]
    sources = [
        str(entry["source"])
        for entry in service.get("secrets") or []
        if isinstance(entry, dict) and entry.get("target") == handle
    ]
    if not sources:
        return None
    declared = document.get("secrets")
    secret = declared.get(sources[0]) if isinstance(declared, dict) else None
    if not isinstance(secret, dict) or "file" not in secret:
        raise EmittedArtifactDefect(
            f"Compose service {compose_service!r} mounts secret {sources[0]!r} for {handle!r}, which "
            f"the compose file does not declare as a file-backed secret."
        )
    return (project_dir / str(secret["file"])).read_text(encoding="utf-8").strip()


def _connection_value(connections: dict[str, object], key: str, compose_service: str) -> str:
    """One required connection value of the store service.

    Raises:
        EmittedArtifactDefect: If the emitted config store does not carry it.
    """
    if key not in connections:
        raise EmittedArtifactDefect(
            f"The file config store of {compose_service!r} carries no {key!r} connection value. "
            f"Carried: {sorted(connections)}."
        )
    return str(connections[key])


def resolve_store_connection(
    project_dir: Path, facts: KeyProviderFacts, block: str, compose_env: dict[str, str]
) -> StoreConnection:
    """How to reach one of the store service's datastores from this machine.

    The key names are the store service's derived connection surface; the
    values are the ones the generated project emitted for its own service; the
    published port is asked of the running stack; the credential is the one
    the generated project provisioned for the service (never a literal here).

    Raises:
        EmittedArtifactDefect: If a connection fact the probes need is absent.
    """
    surface = derive_connection_surface(facts.store_service)
    block_keys = {key.key for key in surface.keys}
    prefix = to_snake_case(block)
    host_key, port_key, database_key, user_key = (
        f"{prefix}_host",
        f"{prefix}_port",
        f"{prefix}_database",
        f"{prefix}_user",
    )
    for required in (host_key, port_key):
        if required not in block_keys:
            raise EmittedArtifactDefect(
                f"{facts.store_service.qualified_name}'s connection surface derives no {required!r} for "
                f"block {block!r}. Derived: {sorted(block_keys)}."
            )
    connections = _store_config(project_dir, facts.store_compose_service)
    host_service = _connection_value(connections, host_key, facts.store_compose_service)
    container_port = _connection_value(connections, port_key, facts.store_compose_service)
    if host_service not in compose_services(project_dir):
        raise EmittedArtifactDefect(
            f"{facts.store_compose_service!r} reaches block {block!r} at host {host_service!r}, which is "
            f"not a compose service of {project_dir}, so it cannot be reached from this machine."
        )
    # A block's credential is the secret handle its connection surface derives
    # for it; a store that provisions none (an unauthenticated cache) mounts none.
    password = ""
    for handle in sorted(secret.handle for secret in surface.secrets if secret.handle.startswith(f"{prefix}_")):
        mounted = _mounted_secret(project_dir, facts.store_compose_service, handle)
        if mounted is not None:
            password = mounted
    database = (
        _connection_value(connections, database_key, facts.store_compose_service)
        if database_key in block_keys
        else ""
    )
    user = (
        _connection_value(connections, user_key, facts.store_compose_service)
        if user_key in block_keys
        else ""
    )
    return StoreConnection(
        host=LOOPBACK_HOST,
        port=published_host_port(project_dir, host_service, container_port, compose_env),
        database=database,
        user=user,
        password=password,
    )


def _quoted(identifier: str) -> str:
    """A model-derived SQL identifier, shape-checked and quoted.

    Raises:
        ValueError: If *identifier* is not a plain lower-case SQL identifier.
    """
    if not _SQL_IDENTIFIER_RE.match(identifier):
        raise ValueError(f"{identifier!r} is not a plain SQL identifier; refusing to interpolate it.")
    return f'"{identifier}"'


async def _db_session(db: StoreConnection) -> asyncpg.Connection:
    """Open one connection to the key store's database with the provisioned credential."""
    return await asyncpg.connect(
        host=db.host,
        port=db.port,
        user=db.user,
        password=db.password,
        database=db.database,
        timeout=HTTP_TIMEOUT_SECONDS,
    )


async def _fetch_row(db: StoreConnection, sql: str, *args: object) -> asyncpg.Record | None:
    """Run one parameterized query and return its single row, or ``None`` for no row."""
    connection = await _db_session(db)
    try:
        return await connection.fetchrow(sql, *args)
    finally:
        await connection.close()


async def _execute(db: StoreConnection, sql: str, *args: object) -> str:
    """Run one parameterized statement and return its command status (e.g. ``UPDATE 1``)."""
    connection = await _db_session(db)
    try:
        return await connection.execute(sql, *args)
    finally:
        await connection.close()


def read_key_row(stack: BackendStack, key_id: str) -> KeyRowState | None:
    """Read a key's stored row, version included, straight from the store's Postgres.

    Returns:
        The row, or ``None`` when no row has *key_id*.
    """
    columns = stack.facts.columns
    tenant = f"{_quoted(columns['tenant'])}::text" if "tenant" in columns else "NULL::text"
    sql = (
        f"SELECT {_quoted(columns[_ROLE_ID])}::text AS key_id, xmin::text AS version, "
        f"{_quoted(columns['hash'])}::text AS key_hash, {_quoted(columns['active'])} AS active, "
        f"{_quoted(columns['expires_at'])} AS expires_at, "
        f"{_quoted(columns['last_used_at'])} AS last_used_at, "
        f"{_quoted(columns['rate_limit'])} AS rate_limit, {tenant} AS tenant_id "
        f"FROM {_quoted(stack.facts.table)} WHERE {_quoted(columns[_ROLE_ID])}::text = $1"
    )
    record = asyncio.run(_fetch_row(stack.db, sql, key_id))
    if record is None:
        return None
    return KeyRowState(
        key_id=str(record["key_id"]),
        version=str(record["version"]),
        key_hash=str(record["key_hash"]),
        active=bool(record["active"]),
        expires_at=record["expires_at"],
        last_used_at=record["last_used_at"],
        rate_limit=int(record["rate_limit"]),
        tenant_id=None if record["tenant_id"] is None else str(record["tenant_id"]),
    )


def update_key_row(stack: BackendStack, key_id: str, role: str, value: object) -> None:
    """Write one column of a key's stored row directly, as an operator revoking or re-limiting it would.

    The fixture ships no revoke or re-limit endpoint, so the row is changed in
    the store itself -- which is exactly what such an endpoint would do.

    Raises:
        ProbeFailure: If the statement did not change exactly one row.
    """
    columns = stack.facts.columns
    sql = (
        f"UPDATE {_quoted(stack.facts.table)} SET {_quoted(columns[role])} = $2 "
        f"WHERE {_quoted(columns[_ROLE_ID])}::text = $1"
    )
    status = asyncio.run(_execute(stack.db, sql, key_id, value))
    if status != "UPDATE 1":
        raise ProbeFailure(f"Setting {role!r} on key {key_id} changed {status!r}; expected exactly one row.")


def rate_limit_counter_total(stack: BackendStack, key_id: str) -> int:
    """Sum every rate-limit window counter the store holds for one key, read from its own Redis.

    Raises:
        ProbeFailure: If a listed counter vanished before it could be read.
    """
    connection = stack.rate_limit_store
    client = redis.Redis(
        host=connection.host,
        port=connection.port,
        db=int(connection.database) if connection.database else 0,
        password=connection.password or None,
        socket_timeout=HTTP_TIMEOUT_SECONDS,
    )
    escaped_key_id = re.sub(r"([*?\[\]\\])", r"\\\1", key_id)
    pattern = RATE_LIMIT_COUNTER_PATTERN.format(provider=stack.facts.provider, key_id=escaped_key_id)
    total = 0
    try:
        for counter in client.scan_iter(match=pattern):
            value = client.get(counter)
            if value is None:
                raise ProbeFailure(f"Rate-limit counter {counter!r} vanished between listing and reading it.")
            total += int(value)
    finally:
        client.close()
    return total


# --------------------------------------------------------------------------
# HTTP against the booted stack
# --------------------------------------------------------------------------


class Pacer:
    """Spaces sequential calls under the gateway's per-address request rate."""

    def __init__(self) -> None:
        self._last_call = 0.0

    def wait(self) -> None:
        """Sleep until one pacing interval has passed since the previous call."""
        remaining = GATEWAY_PACING_SECONDS - (time.monotonic() - self._last_call)
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()

    def rest(self, seconds: float) -> None:
        """Sleep *seconds* so the gateway's burst allowance refills."""
        time.sleep(seconds)
        self._last_call = time.monotonic()


#: Drives one booted stack: returns each probe's outcome vector, keyed by probe.
DriveFunction = Callable[[httpx.Client, BackendStack, Pacer], dict[str, tuple[str, ...]]]


def _observe(response: httpx.Response) -> ObservedResponse:
    """Reduce an HTTP response to what outcome classification reads."""
    return ObservedResponse(status=response.status_code, retry_after=response.headers.get(_RETRY_AFTER_HEADER))


def call_with_key(
    client: httpx.Client, stack: BackendStack, raw_key: str, extra_headers: dict[str, str]
) -> ObservedResponse:
    """One fresh key-authenticated request to the probe route through the gateway -- never cached."""
    headers = {stack.facts.header: raw_key, **extra_headers}
    return _observe(client.get(f"{stack.base_url}{stack.facts.probe_path}", headers=headers))


def issue_api_key(
    client: httpx.Client, stack: BackendStack, pacer: Pacer, extra_headers: dict[str, str]
) -> IssuedKey:
    """Call the generated issuance endpoint with the stack's bearer credential; return the raw key.

    The one call that exercises the REAL issuance path end to end -- random key
    generation and hashing included. Every probe uses a key issued here, never
    a directly inserted row, and the stored row is checked to hold the SHA-256
    of the returned key and nothing else.

    Raises:
        ProbeFailure: If issuance fails or stores something other than the key's hash.
    """
    pacer.wait()
    body = {ISSUANCE_SCOPES_MEMBER: list(stack.facts.scopes), ISSUANCE_EXPIRY_MEMBER: None}
    headers = {"Authorization": f"{_BEARER_PREFIX}{stack.bearer_token}", **extra_headers}
    response = client.post(f"{stack.base_url}{stack.facts.issuance_path}", json=body, headers=headers)
    if response.status_code not in ISSUANCE_SUCCESS_STATUSES:
        raise ProbeFailure(
            f"POST {stack.facts.issuance_path} answered HTTP {response.status_code}; expected one of "
            f"{sorted(ISSUANCE_SUCCESS_STATUSES)}. Body: {response.text[:500]}"
        )
    payload = response.json()
    if (
        not isinstance(payload, dict)
        or not isinstance(payload[ISSUED_KEY_MEMBER] if ISSUED_KEY_MEMBER in payload else None, str)
        or not isinstance(payload[ISSUED_KEY_ID_MEMBER] if ISSUED_KEY_ID_MEMBER in payload else None, str)
    ):
        raise ProbeFailure(
            f"POST {stack.facts.issuance_path} answered without a {ISSUED_KEY_MEMBER!r} and "
            f"{ISSUED_KEY_ID_MEMBER!r} string; members present: "
            f"{sorted(payload) if isinstance(payload, dict) else type(payload).__name__}."
        )
    raw_key = str(payload[ISSUED_KEY_MEMBER])
    key_id = str(payload[ISSUED_KEY_ID_MEMBER])
    if not raw_key or not key_id:
        raise ProbeFailure(f"POST {stack.facts.issuance_path} answered an empty key or key id.")
    row = read_key_row(stack, key_id)
    if row is None:
        raise ProbeFailure(f"The issued key {key_id} has no stored row in {stack.facts.table}.")
    if row.key_hash != hashlib.sha256(raw_key.encode("utf-8")).hexdigest():
        raise ProbeFailure(f"The stored hash of issued key {key_id} is not the SHA-256 of the key returned once.")
    return IssuedKey(key_id=key_id, raw_key=raw_key)


# --------------------------------------------------------------------------
# Probes
# --------------------------------------------------------------------------


def _checked_call(
    client: httpx.Client,
    stack: BackendStack,
    pacer: Pacer,
    key: IssuedKey,
    window_count: int,
    step: str,
) -> tuple[Outcome, KeyRowState]:
    """A paced key call judged against the outcome the key's freshly read row prescribes.

    Raises:
        ProbeFailure: If the answer disagrees with the row.
    """
    row = read_key_row(stack, key.key_id)
    expectation = expected_outcome(row, datetime.datetime.now(datetime.UTC), window_count)
    pacer.wait()
    observed = call_with_key(client, stack, key.raw_key, {})
    failure = judge_against_row(observed, expectation, step)
    if failure is not None:
        raise ProbeFailure(failure)
    if row is None:
        raise ProbeFailure(f"{step}: key {key.key_id} has no stored row.")
    return classify_response(observed), row


def probe_revocation(client: httpx.Client, stack: BackendStack, pacer: Pacer) -> tuple[str, ...]:
    """Revocation is immediate: verify ok, deactivate the stored row, and the very next request is 401.

    Returns:
        The outcome vector: before revocation, then two requests after it.

    Raises:
        ProbeFailure: If any answer disagrees with the key row it was made against.
    """
    key = issue_api_key(client, stack, pacer, {})
    before, _ = _checked_call(client, stack, pacer, key, 1, "verify before revocation")
    if before is not Outcome.OK:
        raise ProbeFailure(f"A freshly issued key answered {before.value!r} before revocation; expected 'ok'.")
    update_key_row(stack, key.key_id, "active", False)
    first, row = _checked_call(client, stack, pacer, key, 2, "first request after revocation")
    second, _ = _checked_call(client, stack, pacer, key, 3, "second request after revocation")
    if row.active or first is not Outcome.INVALID or second is not Outcome.INVALID:
        raise ProbeFailure(
            f"After deactivating key {key.key_id} (stored active={row.active}) the stack answered "
            f"{first.value!r} then {second.value!r}; expected 'invalid' both times."
        )
    logger.info("backend=%s revocation: ok -> active=false -> invalid, invalid", stack.backend)
    return (before.value, first.value, second.value)


def probe_last_used_bound(client: httpx.Client, stack: BackendStack, pacer: Pacer) -> tuple[str, ...]:
    """Bounded writes: K verifications inside one resolution window write the key row exactly once.

    The row is read straight from Postgres before the first verification and
    after each one; every write changes the row's version, so the count of
    changed versions is the count of writes -- never inferred from responses.

    Returns:
        The outcome vector: each verification's outcome, then the write count.

    Raises:
        ProbeFailure: If a verification is refused, the window is exceeded, or
            the row is written other than exactly once.
    """
    key = issue_api_key(client, stack, pacer, {})
    started = time.monotonic()
    first = read_key_row(stack, key.key_id)
    if first is None or first.last_used_at is not None:
        raise ProbeFailure(f"Freshly issued key {key.key_id} already records a use, or has no row: {first!r}.")
    snapshots = [first]
    outcomes: list[str] = []
    for position in range(1, LAST_USED_PROBE_CALLS + 1):
        outcome, _ = _checked_call(client, stack, pacer, key, position, f"verification {position}")
        after = read_key_row(stack, key.key_id)
        if after is None:
            raise ProbeFailure(f"Key {key.key_id} lost its stored row during the bounded-write probe.")
        snapshots.append(after)
        outcomes.append(outcome.value)
    elapsed = time.monotonic() - started
    if elapsed >= stack.facts.last_used_resolution_seconds:
        raise ProbeFailure(
            f"The {LAST_USED_PROBE_CALLS} verifications took {elapsed:.1f}s, longer than one "
            f"{stack.facts.last_used_resolution_seconds}s lastUsedAt resolution window, so the write "
            f"bound cannot be judged. The stack answered too slowly."
        )
    verdict = judge_last_used_writes(snapshots)
    if verdict is not None:
        raise ProbeFailure(verdict)
    writes = count_row_writes(snapshots)
    logger.info(
        "backend=%s bounded lastUsedAt: %d verifications in %.1fs wrote the row %d time(s)",
        stack.backend,
        LAST_USED_PROBE_CALLS,
        elapsed,
        writes,
    )
    return (*outcomes, f"writes={writes}")


def _await_counting_window(stack: BackendStack, pacer: Pacer) -> None:
    """Let the gateway's burst allowance refill, then make sure the burst lands in one window."""
    pacer.rest(GATEWAY_BURST_REFILL_SECONDS)
    window = stack.facts.rate_limit_window_seconds
    remaining = window - (time.time() % window)
    if remaining < RATE_LIMIT_WINDOW_MARGIN_SECONDS:
        logger.info("backend=%s waiting %.1fs for a fresh rate-limit window", stack.backend, remaining + 1)
        pacer.rest(remaining + 1)


def _fire_concurrently(client: httpx.Client, stack: BackendStack, key: IssuedKey) -> list[ObservedResponse]:
    """Fire RATE_LIMIT_PROBE_CONCURRENCY requests released together from a barrier.

    Real concurrent calls against the live stack, each on its own thread and
    connection, so the store's counter is contended exactly as production
    traffic would contend it -- never a serial loop dressed up as concurrency.
    """
    barrier = threading.Barrier(RATE_LIMIT_PROBE_CONCURRENCY)

    def fire() -> ObservedResponse:
        barrier.wait()
        return call_with_key(client, stack, key.raw_key, {})

    with ThreadPoolExecutor(max_workers=RATE_LIMIT_PROBE_CONCURRENCY) as pool:
        futures = [pool.submit(fire) for _ in range(RATE_LIMIT_PROBE_CONCURRENCY)]
        return [future.result() for future in futures]


def probe_concurrent_rate_limit(client: httpx.Client, stack: BackendStack, pacer: Pacer) -> tuple[str, ...]:
    """Exact counting: N truly concurrent requests on a key limited to L admit exactly ``min(N, L)``.

    The verdict comes from the HTTP outcomes. The store's own Redis counters
    for the key are read afterwards to corroborate that every one of the N
    requests reached the store exactly once -- a request the gateway throttled
    before it reached the store would otherwise read as a limit enforced.

    Returns:
        The outcome vector: the count of each outcome.

    Raises:
        ProbeFailure: If the burst was miscounted or did not all reach the store.
    """
    key = issue_api_key(client, stack, pacer, {})
    update_key_row(stack, key.key_id, "rate_limit", RATE_LIMIT_PROBE_LIMIT)
    row = read_key_row(stack, key.key_id)
    if row is None or row.rate_limit != RATE_LIMIT_PROBE_LIMIT:
        raise ProbeFailure(f"Key {key.key_id} does not store the lowered limit {RATE_LIMIT_PROBE_LIMIT}: {row!r}.")
    _await_counting_window(stack, pacer)
    observed = _fire_concurrently(client, stack, key)
    pacer.rest(GATEWAY_PACING_SECONDS)
    outcomes = [classify_response(response) for response in observed]
    counted = rate_limit_counter_total(stack, key.key_id)
    if counted != RATE_LIMIT_PROBE_CONCURRENCY:
        statuses = sorted(response.status for response in observed)
        raise ProbeFailure(
            f"The store counted {counted} of {RATE_LIMIT_PROBE_CONCURRENCY} concurrent requests for key "
            f"{key.key_id} (statuses {statuses}); every request must reach the store's verification "
            f"exactly once for the burst to be judged. A lower count means the gateway refused some "
            f"before they were verified; a higher one means a request was verified twice."
        )
    verdict = judge_rate_limit(outcomes, RATE_LIMIT_PROBE_LIMIT)
    if verdict is not None:
        raise ProbeFailure(verdict)
    counts = tally_outcomes(outcomes)
    logger.info(
        "backend=%s concurrent rate limit: %d requests, limit %d -> %s (store counted %d)",
        stack.backend,
        RATE_LIMIT_PROBE_CONCURRENCY,
        RATE_LIMIT_PROBE_LIMIT,
        {outcome.value: count for outcome, count in sorted(counts.items())},
        counted,
    )
    return tuple(f"{outcome.value}={count}" for outcome, count in sorted(counts.items()))


def probe_tenant_from_key_row(
    client: httpx.Client, stack: BackendStack, pacer: Pacer, tenant_header: str
) -> tuple[str, ...]:
    """Tenant from the key row: a differing request tenant is 403; a matching or absent one is admitted.

    The key is issued in one tenant, its stored row is read to confirm that
    tenant is the one recorded, and the tenant-scoped route is then called with
    another tenant, the key's own, and none.

    Returns:
        The outcome vector: mismatching, matching, absent.

    Raises:
        ProbeFailure: If the key's tenant is not stored, or any answer is wrong.
    """
    tenant = str(uuid.uuid4())
    other_tenant = str(uuid.uuid4())
    key = issue_api_key(client, stack, pacer, {tenant_header: tenant})
    row = read_key_row(stack, key.key_id)
    if row is None or row.tenant_id != tenant:
        raise ProbeFailure(
            f"Key {key.key_id} issued in tenant {tenant} stores tenant "
            f"{None if row is None else row.tenant_id}; expected the request's tenant."
        )
    vector: list[str] = []
    for label, headers, expected in (
        ("a different request tenant", {tenant_header: other_tenant}, Outcome.FORBIDDEN),
        ("the key's own tenant", {tenant_header: tenant}, Outcome.OK),
        ("no request tenant", {}, Outcome.OK),
    ):
        pacer.wait()
        observed = call_with_key(client, stack, key.raw_key, headers)
        outcome = classify_response(observed)
        if outcome is not expected:
            raise ProbeFailure(
                f"A key stored in tenant {tenant} called with {label} answered HTTP {observed.status} "
                f"({outcome.value!r}); expected {expected.value!r}."
            )
        vector.append(outcome.value)
    logger.info("backend=%s tenant from key row: mismatch -> forbidden, match -> ok, absent -> ok", stack.backend)
    return tuple(vector)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FixturePlan:
    """One fixture this gate generates and boots per backend.

    Attributes:
        label: Short name used in scratch paths and reports.
        root: The fixture's source root.
        source: The fixture's entry ``.dtrx``.
        facts: The API-key provider facts read from it.
        dialled_host: The trusted host every one of its services accepts.
    """

    label: str
    root: Path
    source: Path
    facts: KeyProviderFacts
    dialled_host: str


def _project_dir(plan: FixturePlan, backend: str) -> Path:
    """Where *plan*'s fixture is generated for *backend*; its name is the compose project name."""
    return WORK_ROOT / "projects" / f"{plan.label}-{backend}"


def _generated_project(plan: FixturePlan, backend: str, reuse_generated: bool) -> Path:
    """Generate *plan*'s fixture for *backend*, or reuse the tree a previous run left.

    Raises:
        RuntimeError: If generation fails, or reuse finds no tree.
    """
    project_dir = _project_dir(plan, backend)
    if reuse_generated:
        if not (project_dir / COMPOSE_FILENAME).is_file():
            raise RuntimeError(
                f"Reuse of an already-generated tree was requested, but {project_dir} holds no "
                f"{COMPOSE_FILENAME}. Fix: run the gate once without the reuse switch to generate it."
            )
        logger.info("backend=%s fixture=%s reusing %s", backend, plan.label, project_dir)
        return project_dir
    source = prepare_isolated_source(plan.root, plan.source.name, WORK_ROOT / "sources" / f"{plan.label}-{backend}")
    logger.info("backend=%s fixture=%s generating into %s", backend, plan.label, project_dir)
    generate_project(source, project_dir, backend, FIXTURE_PROFILE)
    return project_dir


def drive_booted_stack(
    plan: FixturePlan,
    backend: str,
    project_dir: Path,
    drive: DriveFunction,
) -> dict[str, tuple[str, ...]]:
    """Boot one generated stack, drive it, and tear it down -- volumes included -- whatever happens.

    Raises:
        RuntimeError: If the stack cannot be planned or booted.
        ProbeFailure: If a probe fails.
    """
    entry = plan_entry_point(project_dir, plan.source, FIXTURE_PROFILE)
    issuance = plan_token_issuance(project_dir, fixture_demanded_roles(plan.source, FIXTURE_PROFILE))
    assert_container_names_are_free(project_dir)
    assert_fixed_host_ports_are_free(project_dir)
    supplied = prepare_env_file(project_dir, _ENV_SUPPLIER)
    logger.info(
        "backend=%s fixture=%s supplied %d compose variable(s) the emitted template leaves to the "
        "deployment: %s",
        backend,
        plan.label,
        len(supplied),
        supplied,
    )
    try:
        # Inside the try: a failed `up --wait` can still leave containers
        # behind, and the teardown below is what removes them.
        logger.info("backend=%s fixture=%s booting %s", backend, plan.label, project_dir)
        boot_stack(project_dir, entry.compose_env)
        subject = str(uuid.uuid4())
        stack = BackendStack(
            backend=backend,
            project_dir=project_dir,
            base_url=resolve_entry_base_url(project_dir, entry, plan.dialled_host),
            facts=plan.facts,
            db=resolve_store_connection(project_dir, plan.facts, plan.facts.store_block, entry.compose_env),
            rate_limit_store=resolve_store_connection(
                project_dir, plan.facts, plan.facts.rate_limit_cache, entry.compose_env
            ),
            bearer_token=mint_bearer_token(issuance, subject),
            subject=subject,
        )
        logger.info("backend=%s fixture=%s gateway at %s", backend, plan.label, stack.base_url)
        with httpx.Client(
            timeout=HTTP_TIMEOUT_SECONDS,
            limits=httpx.Limits(max_connections=RATE_LIMIT_PROBE_CONCURRENCY * 2),
        ) as client:
            return drive(client, stack, Pacer())
    finally:
        logger.info("backend=%s fixture=%s tearing down %s", backend, plan.label, project_dir)
        stop_stack(project_dir, entry.compose_env)


def _drive_product_fixture(client: httpx.Client, stack: BackendStack, pacer: Pacer) -> dict[str, tuple[str, ...]]:
    """Revocation, bounded lastUsedAt writes, and concurrent rate-limit counting."""
    return {
        "revocation": probe_revocation(client, stack, pacer),
        "last-used-bound": probe_last_used_bound(client, stack, pacer),
        "concurrent-rate-limit": probe_concurrent_rate_limit(client, stack, pacer),
    }


def _tenancy_driver(tenant_header: str) -> DriveFunction:
    """The tenant-scoped fixture's driver, bound to its request tenant header."""

    def drive(client: httpx.Client, stack: BackendStack, pacer: Pacer) -> dict[str, tuple[str, ...]]:
        return {"tenant-from-key-row": probe_tenant_from_key_row(client, stack, pacer, tenant_header)}

    return drive


def leaked_containers(project_dirs: Sequence[Path]) -> dict[str, list[str]]:
    """Every container a torn-down project still holds, keyed by project directory.

    Asked of the Docker daemon by compose project label -- compose names a
    project after its directory -- so the answer does not depend on the
    project's environment file still interpolating.
    """
    leaked: dict[str, list[str]] = {}
    for project_dir in project_dirs:
        listed = run_command(
            [
                "docker",
                "ps",
                "--all",
                "--filter",
                f"label=com.docker.compose.project={project_dir.name.lower()}",
                "--format",
                "{{.Names}}",
            ],
            cwd=WORK_ROOT,
            timeout_seconds=DOCKER_QUERY_TIMEOUT_SECONDS,
        )
        names = listed.stdout.split()
        if listed.returncode != 0 or names:
            leaked[str(project_dir)] = names or [f"'docker ps' exited {listed.returncode}: {listed.stderr.strip()}"]
    return leaked


def _plan_fixtures(reuse_generated: bool) -> tuple[list[FixturePlan], str]:
    """Plan both fixtures; return them and the tenant-scoped fixture's request tenant header."""
    tenancy_source = (
        TENANCY_FIXTURE_ROOT / FIXTURE_SOURCE.name if reuse_generated else write_tenancy_fixture(TENANCY_FIXTURE_ROOT)
    )
    product_facts = resolve_key_provider_facts(FIXTURE_SOURCE, FIXTURE_PROFILE)
    tenancy_facts = resolve_key_provider_facts(tenancy_source, FIXTURE_PROFILE)
    if not tenancy_facts.tenant_mapped:
        raise EmittedArtifactDefect(
            f"The tenant-scoped fixture's provider {tenancy_facts.provider!r} maps no tenant field."
        )
    tenant_header = tenant_header_of(tenancy_facts.probe_service)
    plans = [
        FixturePlan(
            label="ecommerce",
            root=FIXTURE_ROOT,
            source=FIXTURE_SOURCE,
            facts=product_facts,
            dialled_host=resolve_dialled_host(FIXTURE_ROOT, FIXTURE_PROFILE),
        ),
        FixturePlan(
            label="tenancy",
            root=TENANCY_FIXTURE_ROOT,
            source=tenancy_source,
            facts=tenancy_facts,
            dialled_host=resolve_dialled_host(TENANCY_FIXTURE_ROOT, FIXTURE_PROFILE),
        ),
    ]
    for plan in plans:
        logger.info(
            "fixture=%s provider=%s header=%s store=%s table=%s probe=GET %s issuance=POST %s",
            plan.label,
            plan.facts.provider,
            plan.facts.header,
            plan.facts.store_service.qualified_name,
            plan.facts.table,
            plan.facts.probe_path,
            plan.facts.issuance_path,
        )
    return plans, tenant_header


def _run_backend(
    backend: str, plans: Sequence[FixturePlan], tenant_header: str, reuse_generated: bool
) -> dict[str, tuple[str, ...]]:
    """Generate, boot, probe, and tear down every fixture for one backend."""
    vectors: dict[str, tuple[str, ...]] = {}
    for plan in plans:
        project_dir = _generated_project(plan, backend, reuse_generated)
        driver = _drive_product_fixture if plan.label == "ecommerce" else _tenancy_driver(tenant_header)
        vectors.update(drive_booted_stack(plan, backend, project_dir, driver))
    return vectors


def run_gate(reuse_generated: bool) -> int:
    """Run the real gate over every registered backend language.

    Returns:
        0 when every backend passes every probe and parity holds; 1 when a
        backend failed to generate or boot, a probe failed, parity broke, or a
        stack leaked containers; 2 when fewer than two backends are registered
        or the fixtures cannot be planned.
    """
    try:
        backends = registered_backends()
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        plans, tenant_header = _plan_fixtures(reuse_generated)
    except (RuntimeError, ValueError) as exc:
        logger.error("API-KEY IDENTITY GATE CANNOT RUN: %s", exc)
        return 2
    logger.info("backends: %s", list(backends))

    results: dict[str, dict[str, tuple[str, ...]]] = {}
    failures: dict[str, str] = {}
    for backend in backends:
        try:
            results[backend] = _run_backend(backend, plans, tenant_header, reuse_generated)
        except ProbeFailure as exc:
            failures[backend] = f"probe failed: {exc}"
        except (RuntimeError, subprocess.TimeoutExpired, httpx.HTTPError, OSError, asyncpg.PostgresError, redis.RedisError) as exc:
            failures[backend] = f"{type(exc).__name__}: {exc}"

    return _report(backends, results, failures, plans)


def _report(
    backends: Sequence[str],
    results: dict[str, dict[str, tuple[str, ...]]],
    failures: dict[str, str],
    plans: Sequence[FixturePlan],
) -> int:
    """Log every backend's outcome vectors, parity, and leaks; return the exit code."""
    holds = True
    for backend in backends:
        if backend in failures:
            logger.error("FAILED backend=%s: %s", backend, failures[backend])
            holds = False
            continue
        for probe, vector in sorted(results[backend].items()):
            logger.info("PASS backend=%s probe=%s outcomes=%s", backend, probe, list(vector))
    if failures:
        logger.error(
            "Cross-language parity cannot be judged: backend(s) %s did not complete every probe.",
            sorted(failures),
        )
    else:
        differences = compare_outcome_vectors(results)
        for difference in differences:
            logger.error("PARITY DIFFERENCE %s", difference)
        holds = holds and not differences
        logger.info(
            "cross-language parity over %s: %d probe(s) compared, %d difference(s)",
            list(backends),
            len({probe for vectors in results.values() for probe in vectors}),
            len(differences),
        )
    project_dirs = [_project_dir(plan, backend) for plan in plans for backend in backends]
    leaked = leaked_containers(project_dirs)
    for project, names in sorted(leaked.items()):
        logger.error("LEAKED CONTAINERS project=%s: %s", project, names)
    holds = holds and not leaked
    logger.info("leak check: %d project(s) inspected, %d with containers left", len(project_dirs), len(leaked))
    return 0 if holds else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: self-test, then (unless --self-test) generate, boot and probe every backend.

    Returns:
        Exit code: 0 = every registered backend passed every probe and parity
        holds; 1 = a backend failed, a probe failed, parity broke, or a stack
        leaked containers; 2 = a self-test failed, fewer than two languages are
        registered, or the fixtures cannot be planned.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate the API-key fixtures for every registered backend language, boot each, issue "
            "real keys, and prove revocation, tenant scoping, exact concurrent rate limiting, "
            "bounded lastUsedAt writes, and cross-language parity against the live stack."
        )
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test")
    parser.add_argument(
        "--reuse-generated",
        action="store_true",
        help="Boot and probe the trees a previous run generated instead of regenerating them",
    )
    args = parser.parse_args(argv)

    configure_logging(debug=args.debug)

    durability = run_diagnostic_durability_self_test()
    if durability:
        logger.error("Diagnostic-durability self-test FAILED:")
        for problem in durability:
            logger.error("  %s", problem)
        return 2

    problems = run_self_test()
    if problems:
        logger.error("Non-vacuity self-test FAILED:")
        for problem in problems:
            logger.error("  %s", problem)
        return 2
    logger.info(
        "Non-vacuity self-test passed (live key accepted; revoked and expired keys rejected naming "
        "the row; status classification with fail-closed 429; burst of %d against limit %d "
        "admits exactly %d and one over or under is rejected; %d verifications writing once "
        "accepted and writing every time rejected; parity differences named; fixed host ports "
        "read behind a bind address); "
        "diagnostic-durability self-test passed.",
        RATE_LIMIT_PROBE_CONCURRENCY,
        RATE_LIMIT_PROBE_LIMIT,
        min(RATE_LIMIT_PROBE_CONCURRENCY, RATE_LIMIT_PROBE_LIMIT),
        LAST_USED_PROBE_CALLS,
    )

    if args.self_test:
        return 0

    return run_gate(reuse_generated=args.reuse_generated)


if __name__ == "__main__":
    sys.exit(main())
