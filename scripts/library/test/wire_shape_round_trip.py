#!/usr/bin/env python3
"""Wire-shape round-trip gate: the emitted client, run against a live backend.

For the adopted ecommerce fixture application this gate generates BOTH a
backend service and a browser client, boots the backend, invokes every
generated client method against it, and compares every response body against
the interface the client generator emitted for it.

It is the only check in the frontend-client program that exercises the emitted
client against a RUNNING backend instead of reasoning about either artifact in
isolation, which is what makes it the one that catches a response field
transcribed in the wrong case, or a query parameter cased against the wrong
rule, at the source.

**It lives here, as a repo-level script, and must stay here.** It asserts on
the COMBINED output of two generator packages -- a backend language package's
service and the browser-client renderer's tree -- which the repository's
boundary rules forbid inside any single package ("a unit test that imports two
generator packages, or asserts on the combined output of several, does not
belong in any package"). Moving its logic into a renderer's own pytest suite
would reintroduce exactly that violation. Only its home differs from the
design that asked for it; its content does not.

Backend targets are never hardcoded: they are enumerated from the
``datrix.languages`` entry-point group at run time via
``registered_targets.registered_language_names()``, so a future language
package is covered with no edit here. A backend that cannot be generated or
booted is reported as SKIPPED, by name and with its reason -- the target set
is never narrowed in silence.

The response-shape comparator itself lives in the Node harness
(``wire_shape_harness/shape_comparator.mjs``) because the declared side of the
comparison is TypeScript and only the TypeScript compiler can read it
faithfully. The non-vacuity self-test below drives that exact function through
its own command-line entry point, so a severed comparator turns the self-test
red rather than passing an empty check.

The gate makes a SECOND comparison, across languages: for every route, what
each booted backend answered is compared against what every OTHER booted
backend answered -- status, media type, body shape and the casing of every
field -- because two languages must answer the same route identically on the
wire, and a disagreement is invisible to a check that compares each backend only
against its own client interface. No second request is made for it: the
harness's one call per (backend, route) also records what arrived on the wire
(status, content type and the value-free SHAPE of the body), and the shapes are
compared pairwise in memory, so the comparison costs O(backends x routes) calls
and no more. A response VALUE never leaves the harness: a body is reduced to its
shape the moment it is captured, so no report, log line or results file can
carry a token, an identifier or a personal datum a backend returned. A mismatch
names the JSON path and the two kinds, spellings, statuses or media types, and
nothing else.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import itertools
import json
import logging
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

_HERE = Path(__file__).resolve()
_LIBRARY_DIR = _HERE.parent.parent
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

# Generation, the compose/environment and trusted-host seam closers, bearer
# token minting, and the stack's boot and teardown are shared with every other
# gate that drives a generated application against a running backend.
from shared.generated_stack import (  # noqa: E402
    COMPOSE_FILENAME,
    EmittedArtifactDefect,
    assert_container_names_are_free,
    assert_fixed_host_ports_are_free,
    boot_stack,
    configure_logging,
    fixture_demanded_roles,
    generate_project,
    mint_bearer_token,
    plan_entry_point,
    plan_token_issuance,
    prepare_env_file,
    prepare_isolated_source,
    resolve_dialled_host,
    resolve_entry_base_url,
    run_command,
    run_diagnostic_durability_self_test,
    stop_stack,
)
from datrix_common.directory_constants import CLIENTS_DIR  # noqa: E402
from datrix_codegen_kernel.generation.client_output import client_target_subtree  # noqa: E402

logger = logging.getLogger(__name__)

#: This file lives at <datrix>/scripts/library/test/wire_shape_round_trip.py --
#: parents[3] is <datrix>.
DATRIX_DIR: Path = _HERE.parents[3]

#: The one real, already-adopted fixture application this gate exercises. It
#: declares a browser client target in its own system config, which is what
#: activates the client renderer during generation.
FIXTURE_SOURCE: Path = DATRIX_DIR / "examples" / "03-domains" / "ecommerce" / "system.dtrx"
FIXTURE_PROFILE: Final[str] = "test"

#: The fixture application's own root, which is also the project root every one
#: of its ``.dcfg`` files resolves relative paths against.
FIXTURE_ROOT: Path = FIXTURE_SOURCE.parent

#: Scratch space. Derived from DATRIX_DIR rather than written as an absolute
#: drive path: this file is committed and the workspace is cloned to different
#: roots on different machines. Never inside a package repository.
WORK_ROOT: Path = DATRIX_DIR.parent / ".tmp" / "wire-shape-round-trip"
NODE_DIR: Path = WORK_ROOT / "harness-node"
SELF_TEST_DIR: Path = WORK_ROOT / "self-test"

HARNESS_DIR: Path = _HERE.parent / "wire_shape_harness"
COMPARATOR_SCRIPT: Path = HARNESS_DIR / "shape_comparator.mjs"
CAPTURE_SELF_TEST_SCRIPT: Path = HARNESS_DIR / "wire_capture_self_test.mjs"

#: Scratch directory the live cross-language comparison writes its job into.
CROSS_LANGUAGE_DIR: Path = WORK_ROOT / "cross-language"

#: The jobs the Node comparator accepts. Every job names its mode; the
#: comparator refuses one that does not, so no job can silently default into a
#: comparison it did not ask for.
COMPARATOR_MODE_DECLARED_TYPE: Final[str] = "declared-type"
COMPARATOR_MODE_WIRE_COMPARE: Final[str] = "wire-compare"
COMPARATOR_MODE_WIRE_DESCRIBE: Final[str] = "wire-describe"

#: Mismatch kind the Python side itself reports when two backends' manifests
#: disagree about which verb and path a route key names. Every other kind comes
#: from the Node comparator.
MISMATCH_KIND_ROUTE: Final[str] = "route"

#: A cross-language comparison needs at least two backends that answered. With
#: fewer it compares nothing, and a comparison that compared nothing never
#: passes.
MIN_BACKENDS_FOR_CROSS_LANGUAGE: Final[int] = 2

#: Client targets this gate can drive, and the harness that drives each. A
#: harness knows one frontend framework's runtime, so there is one per target;
#: an emitted client target absent from this table is reported as SKIPPED by
#: name, never dropped in silence.
CLIENT_TARGET_HARNESSES: Final[dict[str, Path]] = {"angular": HARNESS_DIR / "run.mjs"}

#: The gate named in the environment file it supplies missing compose values to.
_ENV_SUPPLIER: Final[str] = "wire-shape round-trip gate"

#: Synthetic identifiers used only by the non-vacuity self-test. They are
#: deliberately unlike any real DSL name so a self-test artifact can never be
#: mistaken for a generated one.
SELF_TEST_ROUTE: Final[str] = "GET /self-test/wire-shape-probe"
SELF_TEST_FIELD: Final[str] = "selfTestField"
SELF_TEST_NESTED_FIELD: Final[str] = "selfTestInner"
SELF_TEST_TYPE: Final[str] = "WireShapeSelfTestProbe"

_COMPARATOR_TIMEOUT_SECONDS: Final[int] = 900
_HARNESS_TIMEOUT_SECONDS: Final[int] = 1800

#: Outcomes the harness reports that make the gate fail. Everything reported
#: outside this set is still printed, and the counts are always published, but
#: only these are defects in the emitted artifacts.
FAILING_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "mismatch",
        "no-reachable-method",
        "argument-not-constructible",
        "response-type-unresolved",
        "comparator-missing-result",
        "pending-shape-check",
    }
)


@dataclass(frozen=True)
class RouteResponse:
    """One backend's actual HTTP response to one route call.

    Captured once per (backend, route) -- by the very request the harness
    already issues for the per-backend comparison -- so it can be compared
    against every OTHER backend's response to the SAME route without issuing
    another request.

    It holds no response value. ``shape`` is the value-free description the
    harness reduced the body to at capture (the kind at every position and the
    name of every property, nothing else), so a token, an identifier or a
    personal datum in a body cannot reach a report, a log line or a results
    file through this record.

    Attributes:
        backend: The backend language target that answered.
        client_target: The client target whose method issued the request.
        route_key: The route key the generated route manifest declares.
        route: ``"<http verb> <path>"`` the manifest declares for that key.
        status: The HTTP status the backend answered with.
        content_type: Its ``Content-Type`` header, empty when absent.
        shape: The value-free shape of the response body.
    """

    backend: str
    client_target: str
    route_key: str
    route: str
    status: int
    content_type: str
    shape: dict[str, object]

    @property
    def route_id(self) -> str:
        """The identity every backend's response to this route shares."""
        return f"{self.client_target}:{self.route_key}"


@dataclass(frozen=True)
class CrossLanguageMismatch:
    """One (route, position) disagreement between two backends' responses.

    Never carries a response value: only the JSON path (or the envelope fact)
    and the two kinds, spellings, statuses or media types observed.

    Attributes:
        route_id: The route both backends were asked.
        route: ``"<http verb> <path>"`` of that route, as the left backend's
            manifest declares it.
        backend_a: The first backend of the pair (sorted by name).
        backend_b: The second backend of the pair.
        kind: What disagreed -- ``status``, ``content-type``, ``value-kind``,
            ``property-casing``, ``missing-property``, ``unrecognized-shape``
            or ``route``.
        json_path: Where the two responses disagree: a JSON path into the body,
            or ``<status>`` / ``<content-type>`` for the envelope.
        detail: A sentence naming the path and the two sides' observations.
    """

    route_id: str
    route: str
    backend_a: str
    backend_b: str
    kind: str
    json_path: str
    detail: str


@dataclass(frozen=True)
class RouteCallResult:
    """One generated client method's invocation result against the booted backend.

    Attributes:
        backend: The backend language target this run generated.
        client_target: The client target whose emitted method was invoked.
        route_key: The route key the generated route manifest declares.
        route: ``"<http verb> <path>"`` for the invoked route.
        method_name: The generated client method that was called, empty when
            no reachable method serves the route.
        invoked: Whether a request actually reached the booted backend.
        outcome: What happened -- ``parsed``, ``mismatch``, ``unexercised``,
            ``untyped``, ``no-reachable-method``, or
            ``argument-not-constructible``.
        http_status: The status the backend answered with, ``0`` when the
            request never completed and ``200`` for any success body.
        parsed_ok: Whether the response parsed against the generated interface.
        detail: What went wrong, naming the property and its path.
        response: What the backend put on the wire for this call, for the
            cross-language comparison. ``None`` when nothing comparable
            arrived: no request was made, the request never completed, or the
            shared gateway rate-limited it (a throttle is not an answer the
            backend's language produced).
    """

    backend: str
    client_target: str
    route_key: str
    route: str
    method_name: str
    invoked: bool
    outcome: str
    http_status: int
    parsed_ok: bool
    detail: str
    response: RouteResponse | None


@dataclass(frozen=True)
class BackendRun:
    """Everything one backend target's run produced.

    Attributes:
        backend: The backend language target.
        results: One entry per declared route of every emitted client target.
        emitted_method_count: Client methods the renderer emitted.
        manifest_route_count: Routes the generated route manifest declares.
        compile_diagnostics: Compiler diagnostics from the emitted client tree.
        unrouted_methods: Emitted methods issuing a route the manifest does not
            declare.
        introspection_failures: Emitted methods whose shape the harness could
            not read at all.
        skipped_client_targets: Emitted client targets this gate cannot drive.
    """

    backend: str
    results: list[RouteCallResult]
    emitted_method_count: int
    manifest_route_count: int
    compile_diagnostics: list[str]
    unrouted_methods: list[str]
    introspection_failures: list[str]
    skipped_client_targets: dict[str, str]


def _resolve_node() -> str:
    """Return the Node executable, raising with a fix suggestion when absent.

    Raises:
        RuntimeError: If no ``node`` executable is on PATH.
    """
    node = shutil.which("node")
    if node is None:
        raise RuntimeError(
            "No 'node' executable is on PATH. Expected a Node.js installation, which the "
            "wire-shape harness needs to compile and execute the emitted client. Fix: install "
            "Node.js (>= 20) and make sure 'node' and 'npm' resolve on PATH."
        )
    return node


def compare_shapes(work_dir: Path, cases: list[dict[str, object]]) -> list[dict[str, object]]:
    """Run the shared response-shape comparator over *cases*.

    The single entry point into the comparator from Python. The gate's
    self-test and any future caller reach the comparator through here, so
    there is exactly one implementation of "does this payload match this
    generated interface" in the whole gate.

    Args:
        work_dir: Scratch directory the comparator writes its probes into.
        cases: One ``{caseId, typeFile, typeName, value}`` mapping per payload.

    Returns:
        One ``{caseId, parsedOk, detail}`` mapping per case, in input order.

    Raises:
        RuntimeError: If the comparator process itself fails, which is
            distinct from a case reporting ``parsedOk: false``.
    """
    return _run_comparator_job(
        work_dir,
        {
            "mode": COMPARATOR_MODE_DECLARED_TYPE,
            "workDir": str(work_dir),
            "nodeDir": str(NODE_DIR),
            "cases": cases,
        },
    )


def _run_comparator_job(work_dir: Path, job: dict[str, object]) -> list[dict[str, object]]:
    """Run one job through the Node comparator's command-line entry point.

    Every comparison this gate makes -- a payload against a generated
    interface, one backend's wire response against another's, a planted body
    reduced to its shape -- reaches the one comparator module through here.

    Args:
        work_dir: Scratch directory the job and its results are written into.
        job: The job, carrying its ``mode`` and that mode's ``cases``.

    Returns:
        The job's ``results`` list, one mapping per submitted case in order.

    Raises:
        RuntimeError: If the comparator process itself fails.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    job_path = work_dir / "job.json"
    out_path = work_dir / "results.json"
    out_path.unlink(missing_ok=True)
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    result = run_command(
        [_resolve_node(), str(COMPARATOR_SCRIPT), "--job", str(job_path), "--out", str(out_path)],
        cwd=work_dir,
        timeout_seconds=_COMPARATOR_TIMEOUT_SECONDS,
    )
    if result.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"The response-shape comparator failed to run (exit {result.returncode}). Expected "
            f"it to write {out_path}. Fix: read the output below -- a missing Node toolchain or "
            f"an unreachable npm registry is the usual cause.\n{result.stdout}\n{result.stderr}"
        )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    results = payload["results"]
    if not isinstance(results, list):
        raise RuntimeError(
            f"The response-shape comparator wrote {out_path} without a 'results' list. "
            f"Expected one result mapping per submitted case."
        )
    return results


def describe_wire_bodies(
    work_dir: Path, bodies: Mapping[str, dict[str, object]]
) -> dict[str, dict[str, object]]:
    """Reduce bodies to their value-free shapes through the comparator's own function.

    The live path never serialises a body: the harness describes it in-process
    the moment it arrives. This entry point exists so the self-test can feed
    planted bodies -- carrying a planted secret -- through that exact function
    and then prove the secret does not survive it.

    Args:
        work_dir: Scratch directory for the job.
        bodies: ``{case id: body spec}`` where a spec is
            ``{"encoding": "json", "value": ...}`` or
            ``{"encoding": "binary", "binaryType": ..., "base64": ...}``.

    Returns:
        ``{case id: shape}`` for every submitted body.

    Raises:
        RuntimeError: If the comparator fails or answers for the wrong cases.
    """
    results = _run_comparator_job(
        work_dir,
        {
            "mode": COMPARATOR_MODE_WIRE_DESCRIBE,
            "cases": [{"caseId": case_id, "body": spec} for case_id, spec in bodies.items()],
        },
    )
    shapes = {str(entry["caseId"]): entry["shape"] for entry in results}
    if set(shapes) != set(bodies):
        raise RuntimeError(
            f"The comparator described {sorted(shapes)} but {sorted(bodies)} were submitted. "
            f"Expected exactly one shape per submitted body."
        )
    return {case_id: _shape_mapping(shape) for case_id, shape in shapes.items()}


def _shape_mapping(shape: object) -> dict[str, object]:
    """Return *shape* as a mapping, raising if the comparator wrote anything else."""
    if not isinstance(shape, dict):
        raise RuntimeError(
            f"The comparator wrote a wire shape of type {type(shape).__name__}. "
            f"Expected a mapping with a 'kind'."
        )
    return shape


def _self_test_contract_source(field_name: str, inner_type: str) -> str:
    """Return a synthetic contract interface for the self-test.

    Args:
        field_name: Name of the top-level property. The self-test re-spells
            this in a different case to plant a mismatch.
        inner_type: Declared type of the nested property. The self-test
            changes this to plant a value-kind mismatch.
    """
    return (
        "// Synthetic self-test contract for the wire-shape round-trip gate.\n"
        f"export interface {SELF_TEST_TYPE} {{\n"
        f"  {field_name}: string;\n"
        f"  selfTestNested: {{ {SELF_TEST_NESTED_FIELD}: {inner_type} }};\n"
        "}\n"
    )


def _compare_one(leg: str, contract_file: Path, type_expr: str, value: object) -> dict[str, object]:
    """Run the real comparator over one synthetic (declared type, payload) pair."""
    results = compare_shapes(
        SELF_TEST_DIR / f"shape-{leg}",
        [
            {
                "caseId": SELF_TEST_ROUTE,
                "typeExpression": type_expr,
                "typeFiles": [str(contract_file)],
                "value": value,
            }
        ],
    )
    if len(results) != 1:
        raise RuntimeError(
            f"The comparator returned {len(results)} results for one self-test case. "
            f"Expected exactly one."
        )
    return results[0]


def _run_untyped_field_self_test(contract_file: Path) -> list[str]:
    """Prove a field the generator typed ``unknown`` constrains nothing.

    ``unknown`` is the generator's own marker for a DSL ``JSON`` value: the
    caller is expected to narrow it, and the wire may legitimately carry any
    shape underneath. A comparator that descends into it and demands its keys
    be declared reports a defect in every correct client that has one -- which
    is what happened to a real ``pagination: unknown`` field, whose six inner
    keys were all reported undeclared.

    Both directions are checked, so neither a comparator that re-breaks the
    descent nor one that stops comparing altogether can pass:

    * an object under an ``unknown`` field parses;
    * a mis-cased field BESIDE it still fails, proving the leg above is not
      passing because comparison was switched off.

    Returns:
        Failure descriptions; empty means ``unknown`` is honoured.
    """
    problems: list[str] = []
    type_name = f"{SELF_TEST_TYPE}Untyped"
    source = (
        "// Synthetic self-test contract for the wire-shape round-trip gate.\n"
        f"export interface {type_name} {{\n"
        f"  {SELF_TEST_FIELD}: string;\n"
        "  selfTestUntyped: unknown;\n"
        "}\n"
    )
    contract_file.write_text(source, encoding="utf-8")
    payload = {
        SELF_TEST_FIELD: "probe",
        "selfTestUntyped": {"anyKey": 1, "anotherKey": {"deeper": "value"}},
    }
    permitted = _compare_one(
        "untyped-permitted", contract_file, f"@{{0}}.{type_name}", payload
    )
    if not permitted["parsedOk"]:
        problems.append(
            f"the comparator reported an object under a field declared 'unknown' as "
            f"unparsed: {permitted['detail']}. 'unknown' is the generator's marker for a "
            f"DSL JSON value and constrains nothing, so descending into it reports a "
            f"defect in every correct client that has one."
        )

    mis_cased = {SELF_TEST_FIELD.lower(): "probe", "selfTestUntyped": {"anyKey": 1}}
    still_strict = _compare_one(
        "untyped-nonvacuous", contract_file, f"@{{0}}.{type_name}", mis_cased
    )
    if still_strict["parsedOk"]:
        problems.append(
            "a payload whose declared sibling field was mis-cased parsed against a "
            "contract carrying an 'unknown' field -- the leg above is passing because "
            "comparison stopped, not because 'unknown' is honoured."
        )
    return problems


def _run_void_response_self_test(contract_file: Path) -> list[str]:
    """Prove a ``void`` declaration accepts a JSON ``null`` body, and only that.

    ``void`` is what the generator emits for a DSL ``-> Void`` endpoint -- the
    declaration that there is no body to read -- and a backend answering such a
    route with ``null`` is saying the same thing on the wire. Reporting that as
    a mismatch failed two correct routes and could never be fixed generator-side,
    because ``void`` is the only honest TypeScript type for "no value".

    The negative leg keeps it honest: a NON-void declared type must still reject
    ``null``, so this is not a blanket "null always passes".

    Returns:
        Failure descriptions; empty means ``void`` is handled precisely.
    """
    problems: list[str] = []
    type_name = f"{SELF_TEST_TYPE}Void"
    source = (
        "// Synthetic self-test contract for the wire-shape round-trip gate.\n"
        f"export type {type_name} = void;\n"
        f"export interface {type_name}Body {{ {SELF_TEST_FIELD}: string }}\n"
    )
    contract_file.write_text(source, encoding="utf-8")

    accepted = _compare_one("void-null", contract_file, f"@{{0}}.{type_name}", None)
    if not accepted["parsedOk"]:
        problems.append(
            f"the comparator rejected a JSON null body against a 'void' declaration: "
            f"{accepted['detail']}. That is the shape a DSL '-> Void' endpoint emits, and "
            f"no generator change could satisfy the check."
        )

    rejected = _compare_one(
        "void-nonvacuous", contract_file, f"@{{0}}.{type_name}Body", None
    )
    if rejected["parsedOk"]:
        problems.append(
            "the comparator accepted a JSON null body against an interface declaring a "
            "required property -- null is now allowed everywhere, not only for 'void'."
        )
    return problems


#: A synthetic secret-shaped string the self-test plants in response bodies. It
#: stands for a bearer token, an identifier or any other value a backend might
#: return, and is deliberately unlike any real credential. The cross-language
#: comparison must never let it reach a mismatch, a log line or a results file.
PLANTED_SECRET: Final[str] = "Bearer wire-shape-self-test-planted-credential-7f3a9c21e5"

#: Synthetic backend and client-target names for the cross-language self-test.
#: Deliberately not registered language names: the comparison is target-agnostic.
SELF_TEST_BACKENDS: Final[tuple[str, str, str]] = ("backend-a", "backend-b", "backend-c")
SELF_TEST_CLIENT_TARGET: Final[str] = "self-test-client"

_JSON_MEDIA_TYPE: Final[str] = "application/json"

#: What each planted route must produce, as the sorted ``(kind, JSON path)`` of
#: every mismatch -- one entry per mismatch, so a route that must produce two
#: lists two. A route must produce exactly this: "detects it" is not enough, it
#: must detect only it.
_EXPECTED_CROSS_LANGUAGE: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "agree": (),
    "charset": (),
    "casing": (("property-casing", "$.orderId"),),
    "kinds": (("value-kind", "$.accessToken"), ("value-kind", "$.total")),
    "missing": (("missing-property", "$.internalNote"),),
    "nested": (("property-casing", "$.items[0].sku"),),
    "status": (("status", "<status>"),),
    "content-type": (("content-type", "<content-type>"),),
    "bytes-vs-string": (("value-kind", "$"),),
    "route": (("route", "<route>"),),
    "unrecognized-both": (("unrecognized-shape", "$"),),
    "unrecognized-vs-string": (("value-kind", "$"),),
    "one-sided": (),
    # Two disagreeing pairs (a-c, b-c) and one agreeing pair (a-b).
    "three-backends": (("property-casing", "$.orderId"), ("property-casing", "$.orderId")),
}

#: Fragments each route's mismatch details must name: the two sides' spellings,
#: kinds, statuses or media types. These are what a human needs to act on a
#: mismatch, and the only content a detail may carry besides the path.
_EXPECTED_DETAIL_FRAGMENTS: Final[dict[str, tuple[str, ...]]] = {
    "casing": ("'orderId'", "'order_id'", "'backend-a'", "'backend-b'"),
    "kinds": ("number", "string"),
    "missing": ("internalNote", "present on 'backend-a'", "absent on 'backend-b'"),
    "nested": ("'sku'", "'SKU'"),
    "status": ("200", "404"),
    "content-type": ("'application/json'", "'application/octet-stream'"),
    "bytes-vs-string": ("bytes", "string"),
    "route": ("route differs", "'get /self-test/route'", "'post /self-test/elsewhere'"),
}


def _json_body(value: object) -> dict[str, object]:
    """A planted JSON body, spelled the way the comparator's describe job takes it."""
    return {"encoding": "json", "value": value}


def _binary_body(binary_type: str, content: bytes) -> dict[str, object]:
    """A planted binary body of one runtime type, bytes carried as base64."""
    return {
        "encoding": "binary",
        "binaryType": binary_type,
        "base64": base64.b64encode(content).decode("ascii"),
    }


def _self_test_response(
    backend: str,
    route_key: str,
    shape: dict[str, object],
    *,
    status: int = 200,
    content_type: str = _JSON_MEDIA_TYPE,
    route: str | None = None,
) -> RouteResponse:
    return RouteResponse(
        backend=backend,
        client_target=SELF_TEST_CLIENT_TARGET,
        route_key=route_key,
        route=f"get /self-test/{route_key}" if route is None else route,
        status=status,
        content_type=content_type,
        shape=shape,
    )


def _self_test_pair(
    route_key: str,
    left: dict[str, object],
    right: dict[str, object],
    *,
    left_status: int = 200,
    right_status: int = 200,
    left_type: str = _JSON_MEDIA_TYPE,
    right_type: str = _JSON_MEDIA_TYPE,
    right_route: str | None = None,
) -> list[RouteResponse]:
    """Two backends' planted responses to one route."""
    first, second = SELF_TEST_BACKENDS[0], SELF_TEST_BACKENDS[1]
    return [
        _self_test_response(first, route_key, left, status=left_status, content_type=left_type),
        _self_test_response(
            second,
            route_key,
            right,
            status=right_status,
            content_type=right_type,
            route=right_route,
        ),
    ]


class _RecordingHandler(logging.Handler):
    """Collects every formatted record, so the self-test can search what was logged."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


@contextlib.contextmanager
def _captured_log_records() -> Iterator[_RecordingHandler]:
    """Capture this module's log records instead of printing them.

    The self-test's planted mismatches are logged at ERROR exactly as a real one
    would be; propagation is switched off for the duration so a planted failure
    does not print to the console as if the gate had found it.
    """
    recorder = _RecordingHandler()
    propagated = logger.propagate
    logger.propagate = False
    logger.addHandler(recorder)
    try:
        yield recorder
    finally:
        logger.removeHandler(recorder)
        logger.propagate = propagated


def _texts_containing(secret: str, texts: Sequence[str]) -> list[str]:
    """The entries of *texts* that contain *secret* -- the leak detector."""
    return [text for text in texts if secret in text]


def _planted_cross_language_responses(
    shapes: Mapping[str, dict[str, object]],
) -> dict[str, list[RouteResponse]]:
    """Every planted route, each answered the way its leg of the self-test needs."""
    agree_left, agree_right = shapes["agree-left"], shapes["agree-right"]
    casing_left, casing_right = shapes["casing-left"], shapes["casing-right"]
    first, second, third = SELF_TEST_BACKENDS
    one_sided = _self_test_response(first, "one-sided", agree_left)
    three_backends = [
        _self_test_response(first, "three-backends", casing_left),
        _self_test_response(second, "three-backends", casing_left),
        _self_test_response(third, "three-backends", casing_right),
    ]
    routes: dict[str, list[RouteResponse]] = {
        "agree": _self_test_pair("agree", agree_left, agree_right),
        "charset": _self_test_pair(
            "charset", agree_left, agree_right, left_type="application/json; charset=utf-8"
        ),
        "casing": _self_test_pair("casing", casing_left, casing_right),
        "kinds": _self_test_pair("kinds", shapes["kind-left"], shapes["kind-right"]),
        "missing": _self_test_pair("missing", shapes["missing-left"], shapes["missing-right"]),
        "nested": _self_test_pair("nested", shapes["nested-left"], shapes["nested-right"]),
        "status": _self_test_pair(
            "status", shapes["casing-left"], agree_right, right_status=404
        ),
        "content-type": _self_test_pair(
            "content-type", agree_left, agree_right, right_type="application/octet-stream"
        ),
        "bytes-vs-string": _self_test_pair(
            "bytes-vs-string", shapes["bytes-left"], shapes["string-right"]
        ),
        "route": _self_test_pair(
            "route",
            agree_left,
            agree_right,
            right_route="post /self-test/elsewhere",
        ),
        "unrecognized-both": _self_test_pair(
            "unrecognized-both", {"kind": "mystery"}, {"kind": "mystery"}
        ),
        "unrecognized-vs-string": _self_test_pair(
            "unrecognized-vs-string", {"kind": "mystery"}, {"kind": "string"}
        ),
        "one-sided": [one_sided],
        "three-backends": three_backends,
    }
    return {responses[0].route_id: responses for responses in routes.values()}


def _planted_bodies() -> dict[str, dict[str, object]]:
    """Bodies the self-test reduces to shapes; the secret sits in every mismatched field."""
    secret_bytes = PLANTED_SECRET.encode("utf-8")
    return {
        "agree-left": _json_body(
            {"orderId": "order-1", "total": 3.5, "items": [{"sku": "sku-a", "quantity": 1}], "note": None}
        ),
        "agree-right": _json_body(
            {
                "orderId": "order-2",
                "total": 9,
                "items": [{"sku": "sku-b", "quantity": 7}, {"sku": "sku-c", "quantity": 8}],
                "note": None,
            }
        ),
        "casing-left": _json_body({"orderId": PLANTED_SECRET, "total": 1}),
        "casing-right": _json_body({"order_id": PLANTED_SECRET, "total": 1}),
        "kind-left": _json_body({"total": 1, "accessToken": PLANTED_SECRET}),
        "kind-right": _json_body({"total": "1", "accessToken": 4096}),
        "missing-left": _json_body({"orderId": "order-1", "internalNote": PLANTED_SECRET}),
        "missing-right": _json_body({"orderId": "order-2"}),
        "nested-left": _json_body({"items": [{"sku": PLANTED_SECRET}]}),
        "nested-right": _json_body({"items": [{"SKU": PLANTED_SECRET}]}),
        "bytes-left": _binary_body("uint8array", secret_bytes),
        "bytes-arraybuffer": _binary_body("arraybuffer", secret_bytes),
        "bytes-blob": _binary_body("blob", secret_bytes),
        "string-right": _json_body(PLANTED_SECRET),
    }


def _check_cross_language_verdicts(
    by_route: Mapping[str, Sequence[CrossLanguageMismatch]], problems: list[str]
) -> None:
    """Each planted route must produce exactly the mismatches its leg plants, naming what a human needs."""
    for route_key, expected in _EXPECTED_CROSS_LANGUAGE.items():
        found = by_route.get(f"{SELF_TEST_CLIENT_TARGET}:{route_key}", [])
        observed = sorted((mismatch.kind, mismatch.json_path) for mismatch in found)
        if observed != sorted(expected):
            problems.append(
                f"route {route_key!r}: expected exactly {sorted(expected)} but the comparison "
                f"reported {observed} -- "
                f"{'a planted difference went undetected' if expected else 'it over-triggered on agreeing responses'}."
            )
            continue
        text = " | ".join(mismatch.detail for mismatch in found)
        missing = [
            fragment for fragment in _EXPECTED_DETAIL_FRAGMENTS.get(route_key, ()) if fragment not in text
        ]
        if missing:
            problems.append(
                f"route {route_key!r}: detected the planted difference but its detail did not "
                f"name {missing} (got {text!r})."
            )
            continue
        logger.info(
            "[OK] cross-language self-test route=%s reported %s",
            route_key,
            observed if observed else "no mismatch (agreeing or one-sided)",
        )
    for route_key, found in by_route.items():
        if route_key.split(":", 1)[1] not in _EXPECTED_CROSS_LANGUAGE and found:
            problems.append(f"unplanted route {route_key!r} produced {len(found)} mismatch(es).")
    pairs = {
        (mismatch.backend_a, mismatch.backend_b)
        for mismatch in by_route.get(f"{SELF_TEST_CLIENT_TARGET}:three-backends", [])
    }
    expected_pairs = {
        (SELF_TEST_BACKENDS[0], SELF_TEST_BACKENDS[2]),
        (SELF_TEST_BACKENDS[1], SELF_TEST_BACKENDS[2]),
    }
    if pairs != expected_pairs:
        problems.append(
            f"three backends where only {SELF_TEST_BACKENDS[2]!r} re-spelled a field reported the "
            f"pair(s) {sorted(pairs)}; expected exactly {sorted(expected_pairs)} -- the agreeing "
            f"pair must stay silent and each disagreeing pair must be named."
        )
    else:
        logger.info(
            "[OK] cross-language self-test three backends: only the disagreeing pair(s) %s were named",
            sorted(pairs),
        )


def _check_no_value_disclosure(
    bodies: Mapping[str, dict[str, object]],
    shapes: Mapping[str, dict[str, object]],
    responses_by_route: Mapping[str, Sequence[RouteResponse]],
    mismatches: Sequence[CrossLanguageMismatch],
    problems: list[str],
) -> None:
    """Prove the planted secret appears nowhere a report, log line or file could carry it.

    The negative assertion is only worth something if the detector can fire and
    the secret really was in the input, so both are checked first.
    """
    if not _texts_containing(PLANTED_SECRET, [json.dumps(bodies)]):
        problems.append("the planted secret is not in the planted bodies; the disclosure leg is vacuous.")
    if not _texts_containing(PLANTED_SECRET, [f"leaked: {PLANTED_SECRET}"]):
        problems.append("the leak detector did not flag a string that contains the planted secret.")
    if not mismatches:
        problems.append("no mismatch was produced, so the disclosure leg checked nothing.")

    with _captured_log_records() as recorder:
        _log_cross_language_mismatches(mismatches)
    if len(recorder.messages) != len(mismatches):
        problems.append(
            f"logging {len(mismatches)} mismatch(es) produced {len(recorder.messages)} record(s); "
            f"the log path was not exercised once per mismatch."
        )

    carriers: list[str] = []
    for mismatch in mismatches:
        carriers.extend(str(value) for value in asdict(mismatch).values())
    carriers.extend(recorder.messages)
    carriers.extend(json.dumps(shape) for shape in shapes.values())
    carriers.extend(
        repr(response) for responses in responses_by_route.values() for response in responses
    )
    leaked = _texts_containing(PLANTED_SECRET, carriers)
    if leaked:
        problems.append(
            f"the planted secret appeared in {len(leaked)} place(s) a mismatch report, log line "
            f"or captured shape must never carry a response value. First: {leaked[0][:160]!r}."
        )
        return
    logger.info(
        "[OK] no-value-disclosure self-test: the planted secret is absent from all %d searched "
        "text(s) (%d mismatch record(s) field by field, %d log record(s), %d captured shape(s), "
        "%d response record(s)); the detector fired on a known leak and the secret was present "
        "in the input",
        len(carriers),
        len(mismatches),
        len(recorder.messages),
        len(shapes),
        sum(len(responses) for responses in responses_by_route.values()),
    )


def _self_test_call_result(backend: str, route_key: str, response: RouteResponse | None) -> RouteCallResult:
    return RouteCallResult(
        backend=backend,
        client_target=SELF_TEST_CLIENT_TARGET,
        route_key=route_key,
        route=f"get /self-test/{route_key}",
        method_name=route_key,
        invoked=True,
        outcome="parsed" if response is not None else "unexercised",
        http_status=200 if response is not None else 429,
        parsed_ok=response is not None,
        detail="",
        response=response,
    )


def _self_test_backend_run(backend: str, results: list[RouteCallResult]) -> BackendRun:
    return BackendRun(
        backend=backend,
        results=results,
        emitted_method_count=len(results),
        manifest_route_count=len(results),
        compile_diagnostics=[],
        unrouted_methods=[],
        introspection_failures=[],
        skipped_client_targets={},
    )


def _run_call_count_self_test() -> list[str]:
    """Prove the cross-language comparison costs one captured call per (backend, route).

    Four backends and two routes make the difference visible: eight captured
    responses, twelve backend pairs. A collector that re-called per pair would
    report twelve; one that dropped a backend would report fewer than eight. A
    throttled route (no wire response) must not count as a captured call, and a
    backend captured twice for one route must be refused.
    """
    problems: list[str] = []
    backends = (*SELF_TEST_BACKENDS, "backend-d")
    route_keys = ("selfTest.list", "selfTest.create")
    shape: dict[str, object] = {"kind": "null"}
    runs = [
        _self_test_backend_run(
            backend,
            [
                _self_test_call_result(
                    backend, route_key, _self_test_response(backend, route_key, shape)
                )
                for route_key in route_keys
            ]
            + [_self_test_call_result(backend, "selfTest.throttled", None)],
        )
        for backend in backends
    ]
    collected = collect_route_responses(runs)
    captured = sum(len(responses) for responses in collected.values())
    if captured != len(backends) * len(route_keys):
        problems.append(
            f"{len(backends)} backends x {len(route_keys)} routes captured {captured} responses; "
            f"expected exactly {len(backends) * len(route_keys)} (one per backend and route; the "
            f"throttled route carries no wire response and must not count)."
        )
    expected_pairs = len(route_keys) * len(backends) * (len(backends) - 1) // 2
    compared = len(_response_pairs(collected))
    if compared != expected_pairs:
        problems.append(
            f"{len(backends)} backends over {len(route_keys)} routes compared {compared} backend "
            f"pair(s); expected {expected_pairs}."
        )
    if not captured < compared:
        problems.append(
            f"captured calls ({captured}) are not fewer than compared pairs ({compared}): the "
            f"self-test cannot tell O(backends x routes) calls from O(backends^2 x routes)."
        )

    doubled = [
        *runs,
        _self_test_backend_run(
            backends[0],
            [
                _self_test_call_result(
                    backends[0],
                    route_keys[0],
                    _self_test_response(backends[0], route_keys[0], shape),
                )
            ],
        ),
    ]
    try:
        collect_route_responses(doubled)
    except ValueError as exc:
        if backends[0] not in str(exc):
            problems.append(f"a doubled capture was refused without naming the backend: {exc}")
    else:
        problems.append(
            "a backend captured twice for one route was accepted; the one-call-per-(backend, route) "
            "guarantee is not enforced."
        )
    if not problems:
        logger.info(
            "[OK] call-count self-test: %d backends x %d routes = %d captured call(s), compared as "
            "%d backend pair(s) in memory; a throttled route is not a captured call; a repeated "
            "(backend, route) is refused",
            len(backends),
            len(route_keys),
            captured,
            compared,
        )
    return problems


def _run_report_self_test(work_dir: Path) -> list[str]:
    """Prove the cross-language report fails closed and passes only on real agreement.

    Drives :func:`_report_cross_language` itself -- the function the live gate
    calls -- over synthetic backend runs:

    * one booted backend: nothing to compare against, so it must fail;
    * two backends that agree: it must pass;
    * two backends that disagree on a field's casing: it must fail and log the
      mismatch under the ``CROSS-LANGUAGE`` label;
    * two backends that answered disjoint routes: no route was compared, so it
      must fail as vacuous rather than pass.

    Returns:
        Failure descriptions; empty means the report is sound.
    """
    problems: list[str] = []
    first, second = SELF_TEST_BACKENDS[0], SELF_TEST_BACKENDS[1]
    camel: dict[str, object] = _expected_object_shape({"orderId": {"kind": "string"}})
    snake: dict[str, object] = _expected_object_shape({"order_id": {"kind": "string"}})

    def runs_for(left: dict[str, object], right: dict[str, object], right_route: str) -> list[BackendRun]:
        left_route = "selfTest.read"
        return [
            _self_test_backend_run(
                first,
                [_self_test_call_result(first, left_route, _self_test_response(first, left_route, left))],
            ),
            _self_test_backend_run(
                second,
                [
                    _self_test_call_result(
                        second, right_route, _self_test_response(second, right_route, right)
                    )
                ],
            ),
        ]

    both = [first, second]
    scenarios: list[tuple[str, list[BackendRun], list[str], bool, str]] = [
        ("one backend booted", runs_for(camel, camel, "selfTest.read")[:1], [first], False, "CANNOT BE JUDGED"),
        ("two backends agree", runs_for(camel, camel, "selfTest.read"), both, True, "mismatches=0"),
        (
            "two backends disagree on a field's casing",
            runs_for(camel, snake, "selfTest.read"),
            both,
            False,
            "CROSS-LANGUAGE MISMATCH",
        ),
        (
            "two backends answered disjoint routes",
            runs_for(camel, camel, "selfTest.other"),
            both,
            False,
            "VACUOUS",
        ),
    ]
    for name, runs, booted, expected_holds, expected_text in scenarios:
        with _captured_log_records() as recorder:
            holds = _report_cross_language(runs, booted, {}, work_dir)
        if holds != expected_holds:
            problems.append(
                f"cross-language report scenario {name!r} returned {holds}; expected {expected_holds}."
            )
        elif not any(expected_text in message for message in recorder.messages):
            problems.append(
                f"cross-language report scenario {name!r} did not log {expected_text!r} "
                f"(logged {recorder.messages})."
            )
        else:
            logger.info(
                "[OK] cross-language report self-test %r: %s, logged %r",
                name,
                "passes" if holds else "fails",
                expected_text,
            )
    return problems


def _run_cross_language_self_test() -> list[str]:
    """Prove the cross-language comparison detects what it must, and only that.

    Planted bodies are reduced to shapes by the comparator's own function --
    the one the live harness calls in-process -- and every planted pair is then
    compared by the comparator's own pairwise function:

    * agreeing responses (different VALUES, different list lengths, a charset
      parameter on one media type) must report nothing;
    * a field re-spelled in another casing, at the top level and inside an
      array element, must report exactly that path and both spellings;
    * a field of a different value kind, a property one side lacks, a different
      status, a different media type, a binary body against a string body, a
      different route, and a shape the comparator cannot classify must each
      report exactly one thing and name what differs;
    * a route only one backend answered must report nothing;
    * with three backends, only the pairs that actually disagree are named.

    The secret planted in every mismatched field must appear in no mismatch, no
    log line, no captured shape and no response record, and the collector must
    cost one captured call per (backend, route).

    Returns:
        Failure descriptions; empty means the comparison is sound.
    """
    problems: list[str] = []
    work_dir = SELF_TEST_DIR / "cross-language"
    bodies = _planted_bodies()
    shapes = describe_wire_bodies(work_dir / "describe", bodies)

    bytes_shape = {"kind": "bytes"}
    for name in ("bytes-left", "bytes-arraybuffer", "bytes-blob"):
        if shapes[name] != bytes_shape:
            problems.append(f"a {name!r} body was described as {shapes[name]!r}; expected {bytes_shape!r}.")
    if shapes["string-right"] != {"kind": "string"}:
        problems.append(f"a string body was described as {shapes['string-right']!r}.")

    responses_by_route = _planted_cross_language_responses(shapes)
    mismatches = compare_across_languages(responses_by_route, work_dir / "compare")
    by_route: dict[str, list[CrossLanguageMismatch]] = {}
    for mismatch in mismatches:
        by_route.setdefault(mismatch.route_id, []).append(mismatch)
    _check_cross_language_verdicts(by_route, problems)
    _check_no_value_disclosure(bodies, shapes, responses_by_route, mismatches, problems)
    problems.extend(_run_call_count_self_test())
    problems.extend(_run_report_self_test(work_dir / "report"))
    return problems


def _expected_object_shape(properties: Mapping[str, dict[str, object]]) -> dict[str, object]:
    """The shape the comparator describes a record with these property shapes as."""
    return {
        "kind": "object",
        "properties": [
            {"name": name, "shape": properties[name]} for name in sorted(properties)
        ],
    }


def _check_row_reader(name: str, captured: dict[str, object]) -> list[str]:
    """Hand a capture the harness produced to the reader the live gate uses.

    The harness writes it into a results row as ``wire``; this is the seam
    between that JSON and :class:`RouteResponse`, so a field renamed on either
    side is caught here rather than in a live run.
    """
    row = {"routeKey": name, "route": f"get /self-test/{name}", "wire": captured}
    parsed = _route_response_of_row("capture-self-test", SELF_TEST_CLIENT_TARGET, row)
    if parsed is None:
        return [f"capture case {name!r}: the row reader returned no response for a real capture."]
    if (parsed.status, parsed.content_type, parsed.shape) != (
        captured["status"],
        captured["contentType"],
        captured["shape"],
    ):
        return [f"capture case {name!r}: the row reader changed what the harness captured."]
    return []


def _check_row_reader_rejects_malformed() -> list[str]:
    """A row with no capture reads as none; a capture of the wrong shape is refused, not skipped."""
    problems: list[str] = []
    base = {"routeKey": "selfTest.row", "route": "get /self-test/row"}
    if _route_response_of_row("capture-self-test", SELF_TEST_CLIENT_TARGET, {**base, "wire": None}) is not None:
        problems.append("a row carrying `wire: null` was read as a response.")
    malformed: list[object] = [
        {"status": "200", "contentType": "", "shape": {"kind": "null"}},
        {"status": 200, "contentType": None, "shape": {"kind": "null"}},
        {"status": 200, "contentType": "", "shape": "null"},
        ["not", "a", "mapping"],
    ]
    for wire in malformed:
        try:
            _route_response_of_row("capture-self-test", SELF_TEST_CLIENT_TARGET, {**base, "wire": wire})
        except RuntimeError:
            continue
        problems.append(f"a malformed capture {wire!r} was accepted by the row reader.")
    return problems


def _run_wire_capture_self_test() -> list[str]:
    """Prove the harness's capture records status, media type and shape -- and no value.

    Runs the harness's REAL capture path: a real Angular ``HttpClient`` over
    ``fetch``, provisioned by the same function the live harness uses, with the
    same recorder interceptor, against a throwaway server bound to the loopback
    interface that answers with planted responses carrying the planted secret.
    No generated backend is involved, so it needs no Docker.

    Covers a JSON success with a charset parameter, an error status, an empty
    204, a binary body, and two requests in flight at once, each of which must
    capture into the attempt that issued it.

    Returns:
        Failure descriptions; empty means the capture is sound.

    Raises:
        RuntimeError: If the capture script itself fails to run.
    """
    out_path = SELF_TEST_DIR / "wire-capture" / "results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)
    result = run_command(
        [
            _resolve_node(),
            str(CAPTURE_SELF_TEST_SCRIPT),
            "--node-dir",
            str(NODE_DIR),
            "--out",
            str(out_path),
            "--planted-secret",
            PLANTED_SECRET,
        ],
        cwd=out_path.parent,
        timeout_seconds=_COMPARATOR_TIMEOUT_SECONDS,
    )
    if result.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"The wire-capture self-test failed to run (exit {result.returncode}). Expected it to "
            f"write {out_path}. Fix: read the output below -- a missing Node toolchain or an "
            f"unreachable npm registry is the usual cause.\n{result.stdout}\n{result.stderr}"
        )
    text = out_path.read_text(encoding="utf-8")
    observed = {entry["name"]: entry for entry in json.loads(text)["cases"]}
    string_shape: dict[str, object] = {"kind": "string"}
    expected: dict[str, tuple[str, dict[str, object]]] = {
        "answered-json": (
            "resolved",
            {
                "status": 200,
                "contentType": "application/json; charset=utf-8",
                "shape": _expected_object_shape(
                    {
                        "orderId": string_shape,
                        "lineItems": {
                            "kind": "array",
                            "elements": [
                                _expected_object_shape(
                                    {"sku": string_shape, "quantity": {"kind": "number"}}
                                )
                            ],
                        },
                        "total": {"kind": "number"},
                        "note": {"kind": "null"},
                    }
                ),
            },
        ),
        "refused-json": (
            "rejected",
            {
                "status": 404,
                "contentType": _JSON_MEDIA_TYPE,
                "shape": _expected_object_shape({"detail": string_shape}),
            },
        ),
        "empty-204": (
            "resolved",
            {"status": 204, "contentType": "", "shape": {"kind": "null"}},
        ),
        "binary-arraybuffer": (
            "resolved",
            {
                "status": 200,
                "contentType": "application/octet-stream",
                "shape": {"kind": "bytes"},
            },
        ),
        "in-flight-slow": (
            "resolved",
            {
                "status": 200,
                "contentType": _JSON_MEDIA_TYPE,
                "shape": _expected_object_shape({"slowField": string_shape}),
            },
        ),
        "in-flight-fast": (
            "resolved",
            {
                "status": 200,
                "contentType": _JSON_MEDIA_TYPE,
                "shape": _expected_object_shape({"fastField": string_shape}),
            },
        ),
    }
    problems: list[str] = []
    if set(observed) != set(expected):
        problems.append(
            f"the capture self-test reported cases {sorted(observed)}; expected {sorted(expected)}."
        )
    for name, (outcome, capture) in expected.items():
        entry = observed.get(name)
        if entry is None:
            continue
        if entry["outcome"] != outcome:
            problems.append(f"capture case {name!r} ended {entry['outcome']!r}; expected {outcome!r}.")
        if entry["captured"] != capture:
            problems.append(
                f"capture case {name!r} recorded {entry['captured']!r}; expected {capture!r}."
            )
        problems.extend(_check_row_reader(name, entry["captured"]))
    problems.extend(_check_row_reader_rejects_malformed())
    if _texts_containing(PLANTED_SECRET, [text]):
        problems.append(
            "the planted secret appeared in the capture results file; a captured body must be "
            "reduced to its shape before anything is recorded."
        )
    if not problems:
        logger.info(
            "[OK] wire-capture self-test: %d planted response(s) through a real HttpClient "
            "recorded status, media type and value-free shape (success, error status, 204, "
            "binary, two requests in flight); the planted secret is absent from the results file",
            len(observed),
        )
    return problems


def run_self_test() -> list[str]:
    """Prove the shared comparator detects a planted mismatch before any real run.

    Drives the REAL comparator -- the same ``shape_comparator.mjs`` entry point
    the live path uses -- over a synthetic payload and a synthetic contract
    interface written to scratch space:

    * a matching pair, which must report parsed;
    * the same payload against an interface whose one property has been
      re-spelled in a different case, which must report unparsed and name that
      property;
    * the same payload against an interface whose nested property declares the
      wrong value kind, which must report unparsed and name that property.

    Severing the comparator fails the first leg's expectation or the last two,
    so this cannot pass with the comparison removed.

    The same run then proves the CROSS-LANGUAGE comparison
    (:func:`_run_cross_language_self_test`) and the harness's wire capture
    (:func:`_run_wire_capture_self_test`), neither of which needs Docker.

    Returns:
        Failure descriptions; empty means the comparator is sound.
    """
    problems: list[str] = []
    shutil.rmtree(SELF_TEST_DIR, ignore_errors=True)
    contract_dir = SELF_TEST_DIR / "contract"
    contract_dir.mkdir(parents=True, exist_ok=True)
    contract_file = contract_dir / f"{SELF_TEST_TYPE}.ts"
    payload = {SELF_TEST_FIELD: "probe", "selfTestNested": {SELF_TEST_NESTED_FIELD: 1}}

    def compare(leg: str, source: str) -> dict[str, object]:
        contract_file.write_text(source, encoding="utf-8")
        results = compare_shapes(
            SELF_TEST_DIR / f"shape-{leg}",
            [
                {
                    "caseId": SELF_TEST_ROUTE,
                    "typeExpression": f"@{{0}}.{SELF_TEST_TYPE}",
                    "typeFiles": [str(contract_file)],
                    "value": payload,
                }
            ],
        )
        if len(results) != 1:
            raise RuntimeError(
                f"The comparator returned {len(results)} results for one self-test case. "
                f"Expected exactly one."
            )
        return results[0]

    matching = compare("matching", _self_test_contract_source(SELF_TEST_FIELD, "number"))
    if not matching["parsedOk"]:
        problems.append(
            f"the comparator reported a synthetic MATCHING payload as unparsed -- "
            f"over-triggering: {matching['detail']}"
        )

    mis_cased_name = SELF_TEST_FIELD.lower()
    mis_cased = compare("mis-cased", _self_test_contract_source(mis_cased_name, "number"))
    if mis_cased["parsedOk"]:
        problems.append(
            f"the comparator reported a payload as parsed against an interface whose "
            f"{SELF_TEST_FIELD!r} property was re-spelled {mis_cased_name!r} -- the mis-cased "
            f"field defect this gate exists to catch would go undetected."
        )
    elif SELF_TEST_FIELD not in str(mis_cased["detail"]):
        problems.append(
            f"the comparator detected the planted mis-cased field but did not name "
            f"{SELF_TEST_FIELD!r} in its detail (got {mis_cased['detail']!r})."
        )

    wrong_kind = compare("wrong-kind", _self_test_contract_source(SELF_TEST_FIELD, "string"))
    if wrong_kind["parsedOk"]:
        problems.append(
            f"the comparator reported a numeric {SELF_TEST_NESTED_FIELD!r} as parsed against an "
            f"interface declaring it a string -- value kinds are not being compared."
        )
    elif SELF_TEST_NESTED_FIELD not in str(wrong_kind["detail"]):
        problems.append(
            f"the comparator detected the planted value-kind mismatch but did not name "
            f"{SELF_TEST_NESTED_FIELD!r} in its detail (got {wrong_kind['detail']!r})."
        )

    problems.extend(_run_untyped_field_self_test(contract_file))
    problems.extend(_run_void_response_self_test(contract_file))
    problems.extend(_run_cross_language_self_test())
    problems.extend(_run_wire_capture_self_test())

    return problems


def generate_backend_and_client(backend: str, output_dir: Path) -> None:
    """Generate the fixture application -- backend and client -- for one target.

    The client renderer activates off the fixture's own declared client
    configuration, so one pipeline run emits both trees. Generates from this
    backend's OWN source copy, never from the shared example tree: the fixture
    declares ``migrations { ledger = false; }``, so each backend renders a fresh
    baseline, and a private copy keeps every backend's generation side effects
    out of every other's (see :func:`prepare_isolated_source`).

    Args:
        backend: A ``datrix.languages`` entry-point name.
        output_dir: Explicit output directory for this backend's tree.

    Raises:
        RuntimeError: If the pipeline reports failure, or raises.
    """
    source_path = prepare_isolated_source(
        FIXTURE_ROOT, FIXTURE_SOURCE.name, WORK_ROOT / "sources" / backend
    )
    generate_project(source_path, output_dir, backend, FIXTURE_PROFILE)


def discover_client_targets(project_dir: Path) -> list[str]:
    """Return the client targets whose trees the generation run emitted.

    Args:
        project_dir: The generated project root.

    Returns:
        Sorted client target keys, read from the emitted tree layout rather
        than from any list held here.

    Raises:
        EmittedArtifactDefect: If the run emitted no client tree at all, which
            means the fixture no longer activates a client renderer and the
            gate would otherwise pass vacuously.
    """
    clients_root = project_dir / CLIENTS_DIR
    targets = (
        sorted(entry.name for entry in clients_root.iterdir() if entry.is_dir())
        if clients_root.is_dir()
        else []
    )
    if not targets:
        raise EmittedArtifactDefect(
            f"The generated project at {project_dir} contains no client tree under "
            f"'{CLIENTS_DIR}/'. Expected the fixture application's declared client target(s) to "
            f"emit one. Fix: restore the clients block in the fixture's system configuration, or "
            f"point this gate at a fixture that declares one."
        )
    return targets


def call_every_client_method(
    backend: str, client_target: str, project_dir: Path, base_url: str, token_file: Path
) -> tuple[list[RouteCallResult], dict[str, object]]:
    """Invoke every generated client method of one client target against the backend.

    Delegates to that target's Node harness, which compiles the emitted client
    with the real TypeScript compiler, constructs the generated classes through
    real framework dependency injection bound to *base_url*, calls every method
    the generated route manifest declares a route for, and hands each response
    to the shared response-shape comparator.

    Args:
        backend: The backend language target currently booted.
        client_target: The emitted client target key.
        project_dir: The generated project root.
        base_url: The booted stack's browser-facing base URL.
        token_file: File holding the bearer token the harness presents. Passed
            as a path rather than a value so the credential never appears in a
            process argument list.

    Returns:
        ``(results, summary)`` -- one result per declared route, plus the
        harness's own census of the emitted tree.

    Raises:
        RuntimeError: If the harness itself fails, which is distinct from an
            individual route reporting a mismatch.
    """
    harness = CLIENT_TARGET_HARNESSES[client_target]
    client_root = project_dir / client_target_subtree(client_target)
    out_path = WORK_ROOT / "results" / backend / f"{client_target}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(
        [
            _resolve_node(),
            str(harness),
            "--client-root",
            str(client_root),
            "--base-url",
            base_url,
            "--node-dir",
            str(NODE_DIR),
            "--auth-token-file",
            str(token_file),
            "--out",
            str(out_path),
        ],
        cwd=WORK_ROOT,
        timeout_seconds=_HARNESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"The {client_target!r} wire-shape harness failed for backend {backend!r} (exit "
            f"{result.returncode}). Expected it to write {out_path}.\n"
            f"{result.stdout}\n{result.stderr}"
        )
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    results = [
        RouteCallResult(
            backend=backend,
            client_target=client_target,
            route_key=str(row["routeKey"]),
            route=str(row["route"]),
            method_name=str(row["methodName"]),
            invoked=bool(row["invoked"]),
            outcome=str(row["outcome"]),
            http_status=int(row.get("httpStatus", 0)),
            parsed_ok=bool(row["parsedOk"]),
            detail=str(row["detail"]),
            response=_route_response_of_row(backend, client_target, row),
        )
        for row in summary["rows"]
    ]
    return results, summary


def _route_response_of_row(
    backend: str, client_target: str, row: Mapping[str, object]
) -> RouteResponse | None:
    """Read the wire capture a harness row carries, ``None`` when it carries none.

    The harness writes ``wire: null`` for a route that produced nothing
    comparable (no request was made, none completed, or the shared gateway
    throttled it) and ``wire: {status, contentType, shape}`` otherwise.

    Raises:
        RuntimeError: If the capture is present but not in that shape, which is
            a harness defect and must not read as a route with nothing to compare.
    """
    wire = row["wire"]
    if wire is None:
        return None
    status = wire.get("status") if isinstance(wire, dict) else None
    content_type = wire.get("contentType") if isinstance(wire, dict) else None
    shape = wire.get("shape") if isinstance(wire, dict) else None
    if not (
        isinstance(status, int) and isinstance(content_type, str) and isinstance(shape, dict)
    ):
        raise RuntimeError(
            f"The wire-shape harness wrote a malformed 'wire' capture for backend {backend!r} "
            f"route {row['route']!r}. Expected null or an object with an integer 'status', a "
            f"string 'contentType' and an object 'shape'. Fix: the capture is produced by "
            f"wire_capture.mjs and recorded by run.mjs; repair whichever side drifted."
        )
    return RouteResponse(
        backend=backend,
        client_target=client_target,
        route_key=str(row["routeKey"]),
        route=str(row["route"]),
        status=status,
        content_type=content_type,
        shape=shape,
    )


def _assert_one_response_per_backend(route_id: str, responses: Sequence[RouteResponse]) -> None:
    """Raise unless *responses* holds exactly one response per backend for *route_id*.

    The cross-language comparison costs one call per (backend, route) because a
    route's responses are captured from that single call and then paired in
    memory. A backend that appears twice for one route would mean a second call
    was made (or a capture was recorded twice), and would make a pair of
    "different languages" include one language twice.

    Raises:
        ValueError: If a response belongs to another route, or a backend repeats.
    """
    foreign = sorted({response.route_id for response in responses if response.route_id != route_id})
    if foreign:
        raise ValueError(
            f"Route {route_id!r} was handed responses belonging to {foreign}. Expected every "
            f"response grouped under a route to share that route's id."
        )
    counts = Counter(response.backend for response in responses)
    repeated = sorted(backend for backend, count in counts.items() if count > 1)
    if repeated:
        raise ValueError(
            f"Route {route_id!r} holds more than one response from backend(s) {repeated}. "
            f"Expected exactly one captured response per (backend, route): the harness makes one "
            f"call per route, and a repeat means a second call or a double capture."
        )


def collect_route_responses(runs: Sequence[BackendRun]) -> dict[str, list[RouteResponse]]:
    """Group every backend's captured wire responses by route.

    No request is issued here. Each backend is booted, exercised and torn down
    inside its own run -- the stacks publish fixed host ports and so cannot be
    up together -- and the harness's single call per route already recorded what
    arrived on the wire. Collecting those records is therefore the whole
    "call every backend once": exactly one captured response per
    (backend, route), through the same request pacer, bearer token and resolved
    base URL the per-backend comparison uses, with no second auth path and no
    unpaced traffic to add.

    Args:
        runs: Every backend that booted and was exercised. A backend that
            failed to generate or boot has no run and is reported SKIPPED by
            name elsewhere; it is absent here, never an empty entry.

    Returns:
        ``{route id: [one RouteResponse per backend that answered it]}``.

    Raises:
        ValueError: If a backend captured two responses for one route.
    """
    grouped: dict[str, list[RouteResponse]] = {}
    for run in runs:
        for result in run.results:
            if result.response is not None:
                grouped.setdefault(result.response.route_id, []).append(result.response)
    for route_id, responses in grouped.items():
        _assert_one_response_per_backend(route_id, responses)
    return grouped


def _response_pairs(
    responses_by_route: Mapping[str, Sequence[RouteResponse]],
) -> list[tuple[RouteResponse, RouteResponse]]:
    """Every pair of backends that both answered a route, in a stable order.

    A route only one backend answered yields no pair: the absent backend is
    reported by name where it was skipped, and an absence is not a disagreement.
    """
    pairs: list[tuple[RouteResponse, RouteResponse]] = []
    for route_id in sorted(responses_by_route):
        responses = responses_by_route[route_id]
        _assert_one_response_per_backend(route_id, responses)
        ordered = sorted(responses, key=lambda response: response.backend)
        pairs.extend(itertools.combinations(ordered, 2))
    return pairs


def _wire_side(response: RouteResponse) -> dict[str, object]:
    """One backend's response as the comparator's job spells it."""
    return {
        "label": response.backend,
        "status": response.status,
        "contentType": response.content_type,
        "shape": response.shape,
    }


def _mismatch_between(
    left: RouteResponse, right: RouteResponse, kind: str, json_path: str, detail: str
) -> CrossLanguageMismatch:
    return CrossLanguageMismatch(
        route_id=left.route_id,
        route=left.route,
        backend_a=left.backend,
        backend_b=right.backend,
        kind=kind,
        json_path=json_path,
        detail=detail,
    )


def compare_across_languages(
    responses_by_route: Mapping[str, Sequence[RouteResponse]], work_dir: Path
) -> list[CrossLanguageMismatch]:
    """Compare every pair of backends' responses to every route.

    For each route, each PAIR of backends that both answered is compared on
    status, media type, body shape and the casing of every field. The structural
    diff is the Node comparator's (``shape_comparator.mjs``), reached through
    one job for every pair of every route -- this function builds the pairs and
    reads the verdicts, and never diffs JSON itself. A difference the
    comparator cannot classify is reported as a mismatch, never skipped.

    A pair whose two manifests disagree about the verb and path a route key
    names is reported as such and not compared further: those were not the same
    request.

    Args:
        responses_by_route: ``{route id: [one RouteResponse per backend]}``, as
            :func:`collect_route_responses` returns.
        work_dir: Scratch directory for the comparator job.

    Returns:
        Every disagreement found. Empty means every pair agreed. No entry
        carries a response value.

    Raises:
        ValueError: If a backend appears twice under one route.
        RuntimeError: If the comparator fails or answers for the wrong pairs.
    """
    mismatches: list[CrossLanguageMismatch] = []
    pair_by_case: dict[str, tuple[RouteResponse, RouteResponse]] = {}
    for left, right in _response_pairs(responses_by_route):
        if left.route != right.route:
            mismatches.append(
                _mismatch_between(
                    left,
                    right,
                    MISMATCH_KIND_ROUTE,
                    "<route>",
                    f"route differs: {left.route!r} on {left.backend!r} vs {right.route!r} on "
                    f"{right.backend!r}",
                )
            )
            continue
        pair_by_case[f"{left.route_id}|{left.backend}|{right.backend}"] = (left, right)
    if not pair_by_case:
        return mismatches

    results = _run_comparator_job(
        work_dir,
        {
            "mode": COMPARATOR_MODE_WIRE_COMPARE,
            "cases": [
                {"caseId": case_id, "left": _wire_side(left), "right": _wire_side(right)}
                for case_id, (left, right) in pair_by_case.items()
            ],
        },
    )
    verdicts = {str(entry["caseId"]): entry for entry in results}
    if set(verdicts) != set(pair_by_case):
        raise RuntimeError(
            f"The comparator answered for {len(verdicts)} backend pair(s) but "
            f"{len(pair_by_case)} were submitted. Expected exactly one verdict per pair."
        )
    for case_id, (left, right) in pair_by_case.items():
        found = verdicts[case_id]["mismatches"]
        if not isinstance(found, list):
            raise RuntimeError(
                f"The comparator wrote a non-list 'mismatches' for pair {case_id!r}. "
                f"Expected a list, empty when the two responses agree."
            )
        mismatches.extend(
            _mismatch_between(
                left, right, str(entry["kind"]), str(entry["jsonPath"]), str(entry["detail"])
            )
            for entry in found
        )
    return mismatches


def _log_cross_language_mismatches(mismatches: Sequence[CrossLanguageMismatch]) -> None:
    """Log each mismatch: route, backend pair, kind, path and the two sides -- no value."""
    for mismatch in mismatches:
        logger.error(
            "CROSS-LANGUAGE MISMATCH route=%s (%s) backends=%s,%s kind=%s at %s: %s",
            mismatch.route_id,
            mismatch.route,
            mismatch.backend_a,
            mismatch.backend_b,
            mismatch.kind,
            mismatch.json_path,
            mismatch.detail,
        )


def _report_cross_language(
    runs: Sequence[BackendRun],
    booted: Sequence[str],
    skipped: Mapping[str, str],
    work_dir: Path,
) -> bool:
    """Compare every booted backend's responses against every other's; return whether they agree.

    Labelled ``CROSS-LANGUAGE`` throughout so it reads apart from the per-backend
    comparison of a response against its own generated interface. It fails
    closed: with fewer than two booted backends, or with no route answered by
    two of them, nothing was compared and the gate does not pass.

    Args:
        runs: Every backend that booted and was exercised.
        booted: Their names.
        skipped: Backends that could not be generated or booted, with the reason.
        work_dir: Scratch directory for the comparator job.
    """
    if len(booted) < MIN_BACKENDS_FOR_CROSS_LANGUAGE:
        logger.error(
            "CROSS-LANGUAGE COMPARISON CANNOT BE JUDGED: %d backend(s) booted (%s); at least %d "
            "are required to compare one language's responses against another's. Skipped: %s",
            len(booted),
            list(booted),
            MIN_BACKENDS_FOR_CROSS_LANGUAGE,
            sorted(skipped),
        )
        return False

    responses_by_route = collect_route_responses(runs)
    for route_id, responses in sorted(responses_by_route.items()):
        absent = sorted(set(booted) - {response.backend for response in responses})
        if absent:
            logger.warning(
                "CROSS-LANGUAGE NOT COMPARED route=%s: no response was captured from backend(s) "
                "%s, so the route is compared only between the backends that answered it",
                route_id,
                absent,
            )
    pairs = _response_pairs(responses_by_route)
    try:
        mismatches = compare_across_languages(responses_by_route, work_dir)
    except RuntimeError as exc:
        logger.error("CROSS-LANGUAGE COMPARATOR FAILED: %s", exc)
        return False

    logger.info(
        "cross-language: backends=%s routes_captured=%d backend_pairs_compared=%d mismatches=%d",
        list(booted),
        len(responses_by_route),
        len(pairs),
        len(mismatches),
    )
    _log_cross_language_mismatches(mismatches)
    if not pairs:
        logger.error(
            "CROSS-LANGUAGE COMPARISON IS VACUOUS: not one route was answered by two backends, "
            "so no response was compared against another language's. A run in which nothing was "
            "checked never passes."
        )
        return False
    return not mismatches


def _run_one_backend(backend: str, dialled_host: str, reuse_generated: bool) -> BackendRun:
    """Generate, boot, exercise, and tear down one backend target.

    Args:
        backend: The backend language target.
        dialled_host: The trusted host name :func:`resolve_dialled_host` proved
            every emitted service accepts and this machine resolves to loopback.
        reuse_generated: Exercise the tree already on disk instead of
            regenerating it. The only way to run the gate over a deliberately
            modified emitted file -- planting a mis-cased response field and
            requiring the gate to catch it -- since a fresh generation would
            overwrite the plant before the first request.

    Raises:
        EmittedArtifactDefect: If the emitted tree leaves nothing to check.
        RuntimeError: If generation, the boot, or a harness fails. The caller
            reports those as SKIPPED, by name and with the reason.
    """
    project_dir = WORK_ROOT / "projects" / backend
    if reuse_generated:
        if not (project_dir / COMPOSE_FILENAME).is_file():
            raise RuntimeError(
                f"Reuse of an already-generated tree was requested, but {project_dir} holds no "
                f"{COMPOSE_FILENAME}. Expected a tree a previous run left there. Fix: run the "
                f"gate once without the reuse switch to generate it."
            )
        logger.info(
            "backend=%s reusing the tree already at %s; nothing is regenerated.",
            backend,
            project_dir,
        )
    else:
        generate_backend_and_client(backend, project_dir)
    targets = discover_client_targets(project_dir)
    drivable = [target for target in targets if target in CLIENT_TARGET_HARNESSES]
    skipped = {
        target: "no harness in this gate can drive this client target's framework runtime"
        for target in targets
        if target not in CLIENT_TARGET_HARNESSES
    }
    if not drivable:
        raise EmittedArtifactDefect(
            f"Backend {backend!r} emitted client target(s) {targets} and this gate can drive none "
            f"of them. Expected at least one target with a harness "
            f"({sorted(CLIENT_TARGET_HARNESSES)}). Fix: add a harness for one of the emitted "
            f"targets rather than letting the round trip go unchecked."
        )

    results: list[RouteCallResult] = []
    emitted_methods = 0
    manifest_routes = 0
    diagnostics: list[str] = []
    unrouted: list[str] = []
    unreadable: list[str] = []
    entry_point = plan_entry_point(project_dir, FIXTURE_SOURCE, FIXTURE_PROFILE)
    issuance = plan_token_issuance(
        project_dir, fixture_demanded_roles(FIXTURE_SOURCE, FIXTURE_PROFILE)
    )
    assert_container_names_are_free(project_dir)
    assert_fixed_host_ports_are_free(project_dir)
    supplied = prepare_env_file(project_dir, _ENV_SUPPLIER)
    logger.info(
        "backend=%s supplied %d compose variable(s) the emitted template leaves to the "
        "deployment: %s",
        backend,
        len(supplied),
        supplied,
    )
    token_file = WORK_ROOT / "credentials" / f"{backend}.token"
    try:
        # Inside the try: a failed `up --wait` can still leave containers
        # behind, and the teardown below is what removes them.
        boot_stack(project_dir, entry_point.compose_env)
        base_url = resolve_entry_base_url(project_dir, entry_point, dialled_host)
        logger.info("backend=%s browser-facing base URL resolved to %s", backend, base_url)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(
            mint_bearer_token(issuance, str(uuid.uuid4())), encoding="utf-8"
        )
        for target in drivable:
            target_results, summary = call_every_client_method(
                backend, target, project_dir, base_url, token_file
            )
            results.extend(target_results)
            emitted_methods += int(summary["emittedMethodCount"])
            manifest_routes += int(summary["manifestRouteCount"])
            if not summary["clientCompileOk"]:
                diagnostics.extend(str(line) for line in summary["clientCompileDiagnostics"])
            unrouted.extend(str(name) for name in summary["unroutedMethods"])
            unreadable.extend(str(name) for name in summary["introspectionFailures"])
    finally:
        token_file.unlink(missing_ok=True)
        stop_stack(project_dir, entry_point.compose_env)

    return BackendRun(
        backend=backend,
        results=results,
        emitted_method_count=emitted_methods,
        manifest_route_count=manifest_routes,
        compile_diagnostics=diagnostics,
        unrouted_methods=unrouted,
        introspection_failures=unreadable,
        skipped_client_targets=skipped,
    )


def _report(
    runs: list[BackendRun],
    booted: list[str],
    skipped: dict[str, str],
    defects: dict[str, str],
) -> bool:
    """Log the full census and return whether the gate holds."""
    all_results = [result for run in runs for result in run.results]
    invoked = [result for result in all_results if result.invoked]
    parsed = [result for result in all_results if result.outcome == "parsed"]
    failing = [result for result in all_results if result.outcome in FAILING_OUTCOMES]
    unexercised = [result for result in all_results if result.outcome == "unexercised"]
    untyped = [result for result in all_results if result.outcome == "untyped"]

    for backend, reason in sorted(skipped.items()):
        logger.warning("SKIPPED backend=%s: %s", backend, reason)
    for run in runs:
        for target, reason in sorted(run.skipped_client_targets.items()):
            logger.warning("SKIPPED backend=%s client_target=%s: %s", run.backend, target, reason)

    logger.info(
        "wire-shape round-trip: backends_booted=%s backends_skipped=%s methods_invoked=%d "
        "methods_emitted=%d routes_declared=%d parsed=%d mismatched_or_unreachable=%d "
        "unexercised=%d untyped=%d",
        booted,
        sorted(skipped),
        len(invoked),
        sum(run.emitted_method_count for run in runs),
        sum(run.manifest_route_count for run in runs),
        len(parsed),
        len(failing),
        len(unexercised),
        len(untyped),
    )

    for result in unexercised:
        logger.warning(
            "UNEXERCISED backend=%s route=%s method=%s status=%d: %s",
            result.backend,
            result.route,
            result.method_name,
            result.http_status,
            result.detail,
        )
    for result in untyped:
        logger.warning(
            "UNTYPED RESPONSE backend=%s route=%s method=%s: %s",
            result.backend,
            result.route,
            result.method_name,
            result.detail,
        )
    for result in failing:
        logger.error(
            "WIRE-SHAPE FAILURE backend=%s route=%s method=%s outcome=%s: %s",
            result.backend,
            result.route,
            result.method_name,
            result.outcome,
            result.detail,
        )

    holds = not failing
    for backend, reason in sorted(defects.items()):
        logger.error("NOTHING TO CHECK backend=%s: %s", backend, reason)
        holds = False
    for run in runs:
        for diagnostic in run.compile_diagnostics:
            logger.error(
                "EMITTED CLIENT DOES NOT COMPILE backend=%s: %s", run.backend, diagnostic
            )
            holds = False
        for method in run.unrouted_methods:
            logger.error(
                "CLIENT METHOD OUTSIDE THE ROUTE MANIFEST backend=%s: %s issues a route the "
                "generated manifest does not declare",
                run.backend,
                method,
            )
            holds = False
        for failure in run.introspection_failures:
            logger.error(
                "EMITTED CLIENT METHOD COULD NOT BE READ backend=%s: %s", run.backend, failure
            )
            holds = False
    if not parsed:
        logger.error(
            "WIRE-SHAPE GATE IS VACUOUS: not one route produced a typed success body to compare. "
            "A run in which nothing was checked never passes."
        )
        holds = False
    return holds


def run_gate(reuse_generated: bool) -> int:
    """Run the real gate over every registered backend language.

    Args:
        reuse_generated: Exercise the trees already on disk rather than
            regenerating them.

    Returns:
        0 when every response that carried a typed body parsed against its
        generated interface for every backend that booted, and every pair of
        booted backends answered every route they both answered identically
        (status, media type, body shape, field casing); 1 when a response
        mismatched, a declared route had no reachable client method, the
        emitted client did not compile, two backends disagreed, or nothing was
        checked at all (including fewer than two backends booted, which leaves
        nothing to compare across languages); 2 when no backend targets are
        registered, no trusted host reaches this machine, or every registered
        backend failed.
    """
    backends = sorted(registered_language_names())
    if not backends:
        logger.error(
            "WIRE-SHAPE GATE CANNOT RUN: no 'datrix.languages' targets are registered. Expected "
            "at least one installed datrix-codegen-<language> package."
        )
        return 2

    # Before anything is generated or built: the Host the gate will dial has to
    # be one every emitted service trusts. The value is author-declared in the
    # fixture's own configuration and is the same for every backend, so it is
    # settled once, here, rather than discovered per backend as 44 opaque
    # server errors an image build later.
    try:
        dialled_host = resolve_dialled_host(FIXTURE_ROOT, FIXTURE_PROFILE)
    except RuntimeError as exc:
        logger.error("WIRE-SHAPE GATE CANNOT RUN: %s", exc)
        return 2

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    booted: list[str] = []
    skipped: dict[str, str] = {}
    defects: dict[str, str] = {}
    runs: list[BackendRun] = []
    for backend in backends:
        try:
            runs.append(_run_one_backend(backend, dialled_host, reuse_generated))
        except EmittedArtifactDefect as exc:
            defects[backend] = str(exc)
            continue
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            skipped[backend] = str(exc)
            continue
        booted.append(backend)

    if not booted:
        logger.error(
            "WIRE-SHAPE GATE CANNOT RUN: every registered backend %s failed before a single "
            "route could be called.",
            backends,
        )
        for backend, reason in sorted({**skipped, **defects}.items()):
            logger.error("  backend=%s: %s", backend, reason)
        return 2

    # Both reports always run: a failing per-backend comparison must not hide
    # the cross-language one, nor the reverse.
    per_backend_holds = _report(runs, booted, skipped, defects)
    cross_language_holds = _report_cross_language(runs, booted, skipped, CROSS_LANGUAGE_DIR)
    return 0 if per_backend_holds and cross_language_holds else 1


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = every typed response parsed against its generated
        interface and every pair of booted backends answered every shared route
        identically, 1 = at least one mismatch (per-backend or cross-language)
        or unreachable route or a client tree that does not compile, or nothing
        was compared, 2 = the non-vacuity self-test failed, no backend targets
        are registered, or every registered backend failed.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate a backend and a browser client for the adopted fixture application, boot "
            "the backend, call every generated client method against it, compare every "
            "response against the interface the client generator emitted for it, and compare "
            "every booted backend's responses against every other's (status, media type, body "
            "shape, field casing)."
        )
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real round trip",
    )
    parser.add_argument(
        "--reuse-generated",
        action="store_true",
        help=(
            "Boot and exercise the tree a previous run already generated instead of "
            "regenerating it -- the only way to run the gate over a deliberately modified "
            "emitted file"
        ),
    )
    args = parser.parse_args()

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
        "Non-vacuity self-test passed (matching, mis-cased field, wrong value kind, "
        "untyped 'unknown' field permitted + still strict beside it, 'void' accepts a "
        "null body + a required property still rejects one; cross-language: agreeing "
        "responses silent, field re-spelled in another casing, value-kind, missing "
        "property, status, media type, binary-vs-string, route and unrecognized-shape "
        "differences each reported with their path and both sides, a route one backend "
        "answered not compared, no response value in any report or log line, one captured "
        "call per backend and route, the report failing closed on one backend or disjoint "
        "routes and passing only on agreement; wire capture records status, media type and "
        "shape through a real HttpClient and no value, and the row reader accepts what the "
        "harness writes and refuses a malformed capture); "
        "diagnostic-durability self-test passed."
    )

    if args.self_test:
        return 0

    return run_gate(reuse_generated=args.reuse_generated)


if __name__ == "__main__":
    sys.exit(main())
