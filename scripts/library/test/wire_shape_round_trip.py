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
"""

from __future__ import annotations

import argparse
import ast
import base64
import datetime
import io
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import jwt
import yaml
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

_HERE = Path(__file__).resolve()
_LIBRARY_DIR = _HERE.parent.parent
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

from datrix_cli.pipeline.contract import PipelineConfig, PipelineResult  # noqa: E402
from datrix_cli.pipeline.generation import GenerationPipeline  # noqa: E402

# The compose network a browser-facing container is attached to. Imported from
# the container-runtime generator that assigns it, so the gate reads the same
# fact the generator wrote rather than re-spelling the network name.
from datrix_codegen_docker.generators.compose._network_assignment import (  # noqa: E402
    NETWORK_FRONTEND,
)

# The producer/consumer seam between the emitted compose file and the
# environment file it interpolates, read with the owning package's own parser
# rather than a second one written here.
from datrix_codegen_docker.deploy_runtime import compose_required_variables  # noqa: E402

# The fixture's own declared configuration, read through the loader every
# generator reads it with -- so the trusted-host comparison below comes from the
# producer itself and not from one language's transcription of it.
from datrix_common.config.dcfg.parser import parse_dcfg  # noqa: E402
from datrix_common.config.unified_loader import load_service_config  # noqa: E402

# Where a container-runtime deployment mounts the identity provider plan, and
# the framework's handle for the provisioned JWT signing key. Both are read from
# the packages that emit them rather than re-spelled here.
from datrix_common.deployment.runtime_bootstrap import (  # noqa: E402
    LOCAL_IDENTITY_PROVIDER_PLAN_PATH,
)
from datrix_common.directory_constants import CLIENTS_DIR  # noqa: E402
from datrix_common.generation.framework_secret_handles import (  # noqa: E402
    JWT_PRIVATE_KEY_HANDLE,
)
from datrix_common.generation.client_output import client_target_subtree  # noqa: E402

# The lifecycle verb every Datrix-generated deployment CLI answers to, taken
# from the module that defines the shared vocabulary rather than spelled again.
from datrix_common.generation.deployment_lifecycle import VERB_DEPLOY  # noqa: E402
from datrix_common.generation.validation_level import ValidationLevel  # noqa: E402
from datrix_common.plugin.identity import LanguageId  # noqa: E402
from datrix_language.registration import register_all  # noqa: E402

# `GenerationPipeline.run()` parses real `.dtrx` source, which needs the stdlib
# parser protocol registered first -- normally done once by `datrix_cli.main`
# at CLI startup. This gate drives the pipeline directly, so it registers the
# same implementation itself before any real generation is attempted.
register_all()

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

#: Directory name of the per-application generation state that lives beside the
#: SOURCE rather than in the output tree -- the RDBMS migration ledger among
#: it. Omitted from each backend's private source copy; see
#: :func:`prepare_backend_source` for why one ledger cannot serve four backend
#: languages.
_LEDGER_DIR_NAME: Final[str] = ".datrix"

#: ``ConfigDecl.kind`` of a service configuration. The kind vocabulary
#: ("service" / "system" / "shared") is the one
#: ``unified_loader._load_dcfg_canonical_dict`` validates against; only the
#: system kind publishes a constant for it, so the service kind is named here.
SERVICE_CONFIG_KIND: Final[str] = "service"

#: Scratch space. Derived from DATRIX_DIR rather than written as an absolute
#: drive path: this file is committed and the workspace is cloned to different
#: roots on different machines. Never inside a package repository.
WORK_ROOT: Path = DATRIX_DIR.parent / ".tmp" / "wire-shape-round-trip"
NODE_DIR: Path = WORK_ROOT / "harness-node"
SELF_TEST_DIR: Path = WORK_ROOT / "self-test"

HARNESS_DIR: Path = _HERE.parent / "wire_shape_harness"
COMPARATOR_SCRIPT: Path = HARNESS_DIR / "shape_comparator.mjs"

#: Client targets this gate can drive, and the harness that drives each. A
#: harness knows one frontend framework's runtime, so there is one per target;
#: an emitted client target absent from this table is reported as SKIPPED by
#: name, never dropped in silence.
CLIENT_TARGET_HARNESSES: Final[dict[str, Path]] = {"angular": HARNESS_DIR / "run.mjs"}

COMPOSE_FILENAME: Final[str] = "docker-compose.yml"

#: The generated project's own deployment CLI, relative to its root. When a
#: project ships one it is the emitted front door for bringing the stack up,
#: and the only thing that knows how to build what compose cannot build for
#: itself (a shared per-system base image every service layers on). A project
#: whose services need nothing built outside compose ships none.
DEPLOY_SCRIPT_RELATIVE: Final[Path] = Path("scripts") / "deploy.py"

ENV_FILENAME: Final[str] = ".env"
ENV_EXAMPLE_FILENAME: Final[str] = ".env.example"

#: Bytes of entropy behind each secret this gate supplies to the stack it
#: boots. Generated with the standard library's cryptographic source, fresh per
#: run, and never printed -- the generated project treats its environment file
#: as operator-owned, and an operator does not paste a placeholder in.
_GENERATED_SECRET_BYTES: Final[int] = 24

#: Synthetic identifiers used only by the non-vacuity self-test. They are
#: deliberately unlike any real DSL name so a self-test artifact can never be
#: mistaken for a generated one.
SELF_TEST_ROUTE: Final[str] = "GET /self-test/wire-shape-probe"
SELF_TEST_FIELD: Final[str] = "selfTestField"
SELF_TEST_NESTED_FIELD: Final[str] = "selfTestInner"
SELF_TEST_TYPE: Final[str] = "WireShapeSelfTestProbe"

#: A character no Windows console code page can encode, observed verbatim in
#: pnpm's build transcript -- which reaches this gate embedded in a backend's
#: SKIPPED reason. It is the probe the diagnostic-durability self-test pushes
#: at every configured log stream. Spelled as a code point (U+2009 THIN SPACE)
#: on purpose: the character is invisible, so a literal one is unreviewable in
#: a diff and an editor can silently normalise it away.
UNENCODABLE_DIAGNOSTIC_PROBE: Final[str] = chr(0x2009)

#: The host to dial when NO emitted service constrains the Host header at all.
#: Only reached when every service's resolved configuration declares no trusted
#: host list, which is logged when it happens -- it is a distinct, reported
#: branch, never a fallback taken after a failed lookup.
UNCONSTRAINED_DIAL_HOST: Final[str] = "127.0.0.1"

#: Claim path a provider's roles live under when its plan entry names none.
#: Mirrors the generated identity module's own default.
DEFAULT_ROLE_CLAIM_PATH: Final[str] = "roles"

#: Lifetime of the bearer token this gate mints for the stack it booted. Long
#: enough to outlast a full 44-route paced harness run (well under two minutes)
#: with room for the rate-limit retry budget, short enough that a token left in
#: a torn-down project's scratch directory expires on its own.
_TOKEN_LIFETIME_SECONDS: Final[int] = 3600

#: File suffix of an emitted artifact this gate can read a JWKS document out of.
#: The in-stack JWKS sidecar every container-runtime deployment emits is a
#: Python module regardless of the backend language it serves, and its document
#: is written as adjacent string literals across several lines -- which a text
#: scan cannot reassemble and the language's own parser folds for free.
_JWKS_SOURCE_SUFFIX: Final[str] = ".py"

_COMPARATOR_TIMEOUT_SECONDS: Final[int] = 900
_HARNESS_TIMEOUT_SECONDS: Final[int] = 1800
_DOCKER_UP_TIMEOUT_SECONDS: Final[int] = 3600
_DOCKER_DOWN_TIMEOUT_SECONDS: Final[int] = 600
_DOCKER_PORT_TIMEOUT_SECONDS: Final[int] = 60

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


class EmittedArtifactDefect(RuntimeError):
    """A defect in what the generator emitted, never an environmental skip.

    A backend that cannot be generated or booted here is an environment
    problem and is reported as SKIPPED. A backend that generated fine but
    emitted no client tree to check, or one this gate cannot drive at all, is
    a hole in the round trip -- reporting it as a skip would let the gate go
    green while checking nothing, so it fails the gate instead.
    """


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


def configure_logging(debug: bool = False) -> None:
    """Configure logging output so no diagnostic can be lost to the console codec.

    Almost every line this gate reports carries text it did not author -- docker
    build transcripts, TypeScript compiler diagnostics, container logs -- and
    that text routinely contains characters the Windows console code page
    cannot encode (pnpm alone prints U+2009). A handler writing to such a
    stream raises ``UnicodeEncodeError`` *while formatting the record*, and the
    record is dropped: a backend's SKIPPED reason then disappears in silence,
    which is precisely the silent narrowing this gate promises never to do. The
    streams are therefore switched to escape unencodable characters instead of
    refusing the write. Escaping, not re-encoding: the console's own codec is
    left alone so the surrounding output stays readable.

    Both standard streams are reconfigured, not just the one this function
    would hand to ``basicConfig``. Importing the generation pipeline installs
    the datrix logging setup, which already owns the root logger and writes to
    **stdout** -- so ``basicConfig`` here is a no-op and the stream that
    actually carries these records is the one the import chose. Reconfiguring
    mutates the wrapper in place, so the handler holding it is fixed too, and
    doing both streams keeps the guarantee independent of which one a future
    setup picks.

    Args:
        debug: Emit DEBUG-level records as well as INFO and above.
    """
    level = logging.DEBUG if debug else logging.INFO
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


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


def _run(
    argv: list[str],
    cwd: Path,
    timeout_seconds: int,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing its output and never raising on a non-zero exit."""
    environment = None if env_overrides is None else {**os.environ, **env_overrides}
    return subprocess.run(  # noqa: S603 -- fixed argument vector, no shell
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        env=environment,
    )


def _free_host_port() -> int:
    """Reserve a host port the operating system reports as free.

    The generated compose file publishes the browser-facing container on a
    host port drawn from an environment variable with a fixed default. Taking
    that default would make the gate fail whenever anything else on the
    machine already holds it -- an environmental collision reported as a
    generator defect. Supplying a free port instead keeps the gate independent
    of what else is running, and the real mapping is still read back from the
    running stack rather than assumed.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _service_allowed_hosts() -> dict[str, list[str]]:
    """Return each fixture service's declared trusted-host list, keyed by config file.

    Read from the RESOLVED service configuration rather than from one backend's
    emitted transcription of it. ``httpSecurity.allowedHosts`` is author-declared
    and language-neutral: the Python target bakes it into
    ``config/settings.py``'s ``ALLOWED_HOSTS`` and installs Starlette's
    ``TrustedHostMiddleware`` over it, and every other target emits its own
    equivalent from the same value. Reading the producer keeps this comparison
    valid for every backend the gate enumerates instead of only the one whose
    emitted file shape is known here.

    Returns:
        ``{config file name: allowed hosts}``. A service that declares no list
        appears with an empty one -- it constrains nothing and is excluded from
        the intersection rather than silently emptying it.

    Raises:
        RuntimeError: If the fixture contains no service configuration at all,
            which would make the comparison vacuous.
    """
    declared: dict[str, list[str]] = {}
    for config_file in sorted(FIXTURE_ROOT.rglob("*.dcfg")):
        # utf-8-sig: the fixture's configuration files carry a byte-order mark,
        # which the ConfigDSL parser sees as a stray leading character.
        decl = parse_dcfg(config_file.read_text(encoding="utf-8-sig"), str(config_file))
        if decl.kind != SERVICE_CONFIG_KIND:
            continue
        security = load_service_config(config_file, FIXTURE_ROOT, FIXTURE_PROFILE).profile.http_security
        hosts = [] if security is None or security.allowed_hosts is None else list(security.allowed_hosts)
        declared[config_file.name] = hosts
    if not declared:
        raise RuntimeError(
            f"No service configuration was found under {FIXTURE_ROOT}. Expected at least one "
            f"'config {SERVICE_CONFIG_KIND} ...' .dcfg declaring the fixture's services, so the "
            f"host the gate dials can be compared against the hosts the emitted services trust. "
            f"Fix: point this gate at a fixture that ships service configuration."
        )
    return declared


def _resolves_to_loopback(host: str) -> tuple[bool, list[str]]:
    """Report whether *host* names this machine's own loopback, and what it resolved to.

    A published container port is bound on the host's loopback interface, so a
    trusted host name only addresses it when every address it resolves to is a
    loopback address. A name that also resolves to a routable address would send
    the gate's request somewhere else entirely, so it is not eligible.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False, []
    addresses = sorted({str(info[4][0]) for info in infos})
    loopback = all(ipaddress.ip_address(address).is_loopback for address in addresses)
    return bool(addresses) and loopback, addresses


def resolve_dialled_host() -> str:
    """Close the trusted-host seam before anything is generated or built.

    PRODUCED, by the fixture's own configuration: the set of Host header values
    every emitted service will trust. CONSUMED, by this gate: the single host
    name it puts in the URL the generated client dials. The gateway forwards the
    client's Host verbatim to the upstream service *and* to the JWT auth
    subrequest, so one name has to satisfy every service at once -- the
    intersection, not the union.

    A name only helps if it also reaches the published port on this machine, so
    the intersection is narrowed to the names that resolve to loopback here.

    Without this comparison a rejected Host is indistinguishable from a broken
    backend: Starlette answers ``400 Invalid host header``, and nginx's
    ``auth_request`` turns that same 400 on the auth subrequest into a 500, so
    every authenticated route reports an opaque server error.

    Returns:
        The host name to dial.

    Raises:
        RuntimeError: If no trusted host reaches this machine's loopback, naming
            every service's declared list and what each candidate resolved to.
    """
    produced = _service_allowed_hosts()
    for config_name, hosts in sorted(produced.items()):
        logger.info("trusted hosts declared by %s: %s", config_name, hosts)
    constraining = [set(hosts) for hosts in produced.values() if hosts]
    if not constraining:
        logger.info(
            "No fixture service declares a trusted-host list, so no service constrains the Host "
            "header; dialling %s.",
            UNCONSTRAINED_DIAL_HOST,
        )
        return UNCONSTRAINED_DIAL_HOST
    accepted = sorted(set.intersection(*constraining))
    resolutions = {host: _resolves_to_loopback(host) for host in accepted}
    reachable = sorted(host for host, (ok, _) in resolutions.items() if ok)
    if reachable:
        chosen = reachable[0]
        logger.info(
            "trusted-host seam: %d service config(s) trust %s in common; dialling %r "
            "(resolves to %s).",
            len(produced),
            accepted,
            chosen,
            resolutions[chosen][1],
        )
        return chosen
    detail = "; ".join(
        f"{host!r} -> {addresses or 'does not resolve on this machine'}"
        for host, (_, addresses) in sorted(resolutions.items())
    )
    declared = "; ".join(f"{name}: {hosts}" for name, hosts in sorted(produced.items()))
    raise RuntimeError(
        f"No host the emitted services trust reaches this machine's loopback, so the gate has no "
        f"address it can dial. Declared trusted hosts, per resolved service configuration under "
        f"{FIXTURE_ROOT}: {declared}. Trusted by every service in common: {accepted}. How each "
        f"resolves here: {detail}. Expected at least one common trusted host resolving only to a "
        f"loopback address, because the published container port is bound on loopback and the "
        f"gateway forwards the client's Host verbatim to every upstream service and to the JWT "
        f"auth subrequest. Fix: run the gate on a machine where one of those names resolves to "
        f"loopback (a hosts-file entry is enough) -- never by widening httpSecurity.allowedHosts, "
        f"which is an author-declared trust boundary of the application under test."
    )


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
    work_dir.mkdir(parents=True, exist_ok=True)
    job_path = work_dir / "job.json"
    out_path = work_dir / "results.json"
    job = {"workDir": str(work_dir), "nodeDir": str(NODE_DIR), "cases": cases}
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    result = _run(
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


def run_diagnostic_durability_self_test() -> list[str]:
    """Prove no diagnostic can be dropped by the console's character codec.

    This gate's contract is that a backend it could not exercise is reported by
    name, with its reason -- never narrowed in silence. Almost every such
    reason quotes a build transcript or a container log, text this gate did not
    author, and a single character the console code page cannot encode makes
    the logging handler raise *while writing the record*. The record is then
    discarded and the backend's reason vanishes, which looks exactly like a
    backend that had nothing to say. That happened: one backend's entire skip
    reason was lost to a U+2009 in pnpm's output.

    So before trusting any diagnostic, every configured stream handler is asked
    the same question the codec will ask it: can it render the probe character?
    A stream whose error handler is ``strict`` cannot, and says so here -- in a
    check that runs in milliseconds -- rather than by silently eating a
    diagnostic an hour into a run.

    Returns:
        Failure descriptions; empty means every configured stream can carry any
        text this gate might quote.
    """
    problems: list[str] = []
    for handler in logging.getLogger().handlers:
        if not isinstance(handler, logging.StreamHandler):
            continue
        stream = handler.stream
        if not isinstance(stream, io.TextIOWrapper):
            continue
        try:
            UNENCODABLE_DIAGNOSTIC_PROBE.encode(stream.encoding, errors=stream.errors)
        except UnicodeEncodeError:
            problems.append(
                f"the log stream {stream.name!r} encodes as {stream.encoding!r} with "
                f"errors={stream.errors!r}, so a diagnostic quoting a character outside that "
                f"code page is DROPPED rather than written -- a backend's skip reason would "
                f"disappear in silence. Fix: configure_logging() reconfigures the standard "
                f"streams to 'backslashreplace'; a handler added after it must do the same."
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

    return problems


def prepare_backend_source(backend: str) -> Path:
    """Give *backend* its own private copy of the fixture application source.

    Returns the ``system.dtrx`` inside that copy.

    **Why a copy, and why the migration ledger is left out of it.** The RDBMS
    migration ledger lives beside the SOURCE
    (``<app>/.datrix/rdbms-migrations/<profile>/<rdbms_id>/``), not in the
    output tree, and its path carries no language segment -- while
    ``revisions/_manifest.json`` records exactly one ``language`` per revision.
    So the ledger is a single-language lineage by construction: whichever
    backend generates first seals ``0001_initial`` as its own rendering, and
    every later backend re-rendering that same unchanged schema trips
    ``refuse_sealed_revision_rewrite`` -- "the schema itself is unchanged, so
    no forward revision was planned, only the rendering moved".

    That guard is correct and is deliberately NOT worked around here: the
    ledger records what a deployed database actually ran, and re-rendering a
    sealed revision in another language would make the record disagree with
    the database. What was wrong is this gate sharing ONE lineage across four
    backends. Each backend now gets its own source copy with no ledger at all,
    so each seals its own baseline in its own scratch directory and no backend
    can invalidate another's.

    Excluding the ledger costs the gate nothing: it boots a fresh database per
    run, so a from-scratch baseline is exactly the schema it needs, and this
    gate checks response SHAPES rather than migration history.

    Args:
        backend: A ``datrix.languages`` entry-point name.

    Returns:
        Path to the copied ``system.dtrx``.
    """
    source_root = WORK_ROOT / "sources" / backend
    shutil.rmtree(source_root, ignore_errors=True)
    source_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        FIXTURE_ROOT,
        source_root,
        ignore=shutil.ignore_patterns(_LEDGER_DIR_NAME),
    )
    copied_source = source_root / FIXTURE_SOURCE.name
    if not copied_source.is_file():
        raise RuntimeError(
            f"Preparing an isolated source for backend {backend!r} produced no "
            f"{FIXTURE_SOURCE.name} at {copied_source}. Expected a copy of "
            f"{FIXTURE_ROOT}."
        )
    return copied_source


def generate_backend_and_client(backend: str, output_dir: Path) -> None:
    """Generate the fixture application -- backend and client -- for one target.

    Real generation through ``datrix-cli``'s own ``GenerationPipeline``, the
    one true generation entry point, exactly as ``datrix generate`` invokes it.
    The client renderer activates off the fixture's own declared client
    configuration, so one pipeline run emits both trees.

    Generates from this backend's OWN source copy
    (:func:`prepare_backend_source`), never from the shared example tree --
    see that function for why a single migration ledger cannot serve four
    backend languages.

    Args:
        backend: A ``datrix.languages`` entry-point name.
        output_dir: Explicit output directory for this backend's tree.

    Raises:
        RuntimeError: If the pipeline reports failure, or raises. A generator
            may raise any exception type, and one backend's generation failing
            must be reported against that backend rather than ending the run
            for the ones that follow.
    """
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = prepare_backend_source(backend)
    config = PipelineConfig(
        target_language=LanguageId(backend),
        profile=FIXTURE_PROFILE,
        validation_level=ValidationLevel.FAST,
    )
    try:
        result: PipelineResult = GenerationPipeline().run(
            source_path=source_path, output_dir=output_dir, config=config
        )
    except Exception as exc:  # noqa: BLE001 -- re-raised with the backend named
        raise RuntimeError(
            f"Generating the wire-shape fixture for backend {backend!r} raised "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not result.success:
        raise RuntimeError(
            f"Generating the wire-shape fixture for backend {backend!r} failed: {result.errors}"
        )


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


def _compose_document(compose_file: Path) -> dict[str, object]:
    """Parse the generated compose file, failing loud and naming it."""
    if not compose_file.is_file():
        raise RuntimeError(
            f"No compose file at {compose_file}. Expected the generated project to contain one so "
            f"the browser-facing published port can be resolved from it. Fix: regenerate the "
            f"project for a container runtime that emits a compose file."
        )
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        raise RuntimeError(
            f"The compose file {compose_file} declares no 'services' mapping. Expected a compose "
            f"document whose services can be inspected for the browser-facing published port."
        )
    return document


#: A compose port mapping's host side written as an environment substitution,
#: e.g. ``${GATEWAY_PORT:-8080}``. The variable name is read out of the
#: generated file rather than spelled here, so nothing about which variable the
#: generator chose is hardcoded in this gate.
_ENV_SUBSTITUTION_RE: Final[re.Pattern[str]] = re.compile(r"^\$\{(?P<name>\w+)(:?-[^}]*)?\}$")


@dataclass(frozen=True)
class BrowserEntryPoint:
    """The generated stack's single browser-facing published port.

    Attributes:
        service_name: Compose service serving the client's declared routes.
        container_port: The port that service listens on inside its container.
        compose_env: Environment the stack must be brought up with for the
            host side of that mapping to land where this gate expects. Empty
            when the compose file fixes the host port itself.
    """

    service_name: str
    container_port: str
    compose_env: dict[str, str]


def _port_mapping_of(service_name: str, service: dict[str, object], compose_file: Path) -> str:
    """Return the single published port mapping of a browser-facing service."""
    ports = service.get("ports")
    if not isinstance(ports, list) or len(ports) != 1:
        raise RuntimeError(
            f"The browser-facing compose service {service_name!r} in {compose_file} publishes "
            f"{ports!r}. Expected exactly one published port mapping so the base URL is "
            f"unambiguous. Fix: resolve which port serves the client's routes and publish only it."
        )
    return str(ports[0])


def plan_browser_entry_point(project_dir: Path) -> BrowserEntryPoint:
    """Decide where the generated client's requests must be sent.

    Read from the generated compose file, never assumed. The browser-facing
    container is the one the generator attached to the front-end network and
    published a host port for; ambiguity there is a loud failure naming the
    file, never a guess.

    When the host side of that mapping is an environment substitution, this
    also reserves a free host port for the variable the generated file names,
    so the gate never collides with whatever else on the machine happens to
    hold the compose default.

    Args:
        project_dir: The generated project root holding the compose file.

    Raises:
        RuntimeError: If the compose file names no unambiguous browser-facing
            service, or its mapping cannot be read.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    services = _compose_document(compose_file)["services"]
    candidates = {
        name: service
        for name, service in services.items()
        if isinstance(service, dict)
        and NETWORK_FRONTEND in (service.get("networks") or [])
        and service.get("ports")
    }
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one browser-facing service in {compose_file} -- a service on the "
            f"{NETWORK_FRONTEND!r} network that publishes a host port -- but found "
            f"{sorted(candidates)}. Expected: one public entry point serving the routes the "
            f"generated client declares. Fix: if the application legitimately publishes several, "
            f"teach this gate which one the client's declared base URL addresses."
        )
    service_name, service = next(iter(candidates.items()))
    mapping = _port_mapping_of(service_name, service, compose_file)
    host_side, _, container_side = mapping.rpartition(":")
    container_port = container_side.split("/", 1)[0].strip()
    if not container_port.isdigit():
        raise RuntimeError(
            f"Could not read a container port out of the mapping {mapping!r} declared by "
            f"{service_name!r} in {compose_file}. Expected a '<host>:<container>' mapping."
        )
    substitution = _ENV_SUBSTITUTION_RE.match(host_side.strip())
    compose_env = (
        {substitution.group("name"): str(_free_host_port())} if substitution is not None else {}
    )
    return BrowserEntryPoint(
        service_name=service_name, container_port=container_port, compose_env=compose_env
    )


def resolve_base_url(project_dir: Path, entry_point: BrowserEntryPoint, host: str) -> str:
    """Ask the running stack which host port the browser-facing container landed on.

    The mapping's host side can be an environment substitution or an ephemeral
    assignment, so the compose text alone does not settle it -- the live stack
    does. Only the PORT comes from the stack: the host name is the one
    :func:`resolve_dialled_host` proved every emitted service trusts, because
    the address ``docker compose port`` reports is the bind address
    (``0.0.0.0``) and dialling that literally sends a Host header no service
    accepts.

    Args:
        project_dir: The generated project root.
        entry_point: The planned browser-facing service and container port.
        host: The trusted host name to dial, from :func:`resolve_dialled_host`.

    Raises:
        RuntimeError: If the published host port cannot be resolved.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    result = _run(
        ["docker", "compose", "port", entry_point.service_name, entry_point.container_port],
        cwd=project_dir,
        timeout_seconds=_DOCKER_PORT_TIMEOUT_SECONDS,
        env_overrides=entry_point.compose_env,
    )
    published = result.stdout.strip().splitlines()
    host_port = published[-1].rsplit(":", 1)[-1].strip() if published else ""
    if result.returncode != 0 or not host_port.isdigit():
        raise RuntimeError(
            f"Could not resolve the published host port for container port "
            f"{entry_point.container_port} of {entry_point.service_name!r}, declared in "
            f"{compose_file} (docker compose port exited {result.returncode}). Expected a "
            f"'<address>:<port>' line. Fix: confirm the stack is running and that the service "
            f"publishes the port its compose entry declares.\n{result.stdout}\n{result.stderr}"
        )
    return f"http://{host}:{host_port}"


def _assigned_values(env_text: str) -> dict[str, str]:
    """Return every ``KEY=value`` assignment in an environment file, last wins."""
    values: dict[str, str] = {}
    for line in env_text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def prepare_env_file(project_dir: Path) -> list[str]:
    """Close the compose/environment seam before booting the generated stack.

    The emitted compose file CONSUMES variables; the emitted ``.env.example``
    PRODUCES most of them but deliberately leaves the deployment-owned ones
    blank, because the generator must not invent a credential. Nothing compares
    the two sets, and an unsupplied one aborts interpolation with a message
    that names the variable and nothing else -- so this computes
    ``required - supplied`` from the emitted files themselves and supplies a
    freshly generated value for each remaining name.

    The values come from the standard library's cryptographic source, are new
    on every run, are never logged, and live only in the throwaway project this
    gate generates and tears down.

    Args:
        project_dir: The generated project root.

    Returns:
        The variable names this gate had to supply, so the run can report the
        seam it closed rather than closing it silently.

    Raises:
        RuntimeError: If the project emitted no compose file to read.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    if not compose_file.is_file():
        raise RuntimeError(
            f"No compose file at {compose_file}. Expected the generated project to contain one "
            f"before its environment file can be prepared."
        )
    example_file = project_dir / ENV_EXAMPLE_FILENAME
    example_text = example_file.read_text(encoding="utf-8") if example_file.is_file() else ""
    supplied = {name for name, value in _assigned_values(example_text).items() if value}
    missing = [
        name
        for name in compose_required_variables(compose_file.read_text(encoding="utf-8"))
        if name not in supplied
    ]
    generated = "\n".join(
        f"{name}={secrets.token_urlsafe(_GENERATED_SECRET_BYTES)}" for name in missing
    )
    body = (
        f"{example_text.rstrip()}\n\n"
        f"# Supplied by the wire-shape round-trip gate: every compose variable that declares\n"
        f"# itself required and carries no value in the emitted template. Freshly generated\n"
        f"# per run for this throwaway stack.\n"
        f"{generated}\n"
    )
    (project_dir / ENV_FILENAME).write_text(body, encoding="utf-8")
    return missing


@dataclass(frozen=True)
class TokenIssuance:
    """How to mint a bearer token the booted stack will accept.

    Every field is a non-secret fact resolved from the emitted project. The
    signing material itself is never held here -- only the path to the
    provisioned key file -- so no instance of this class can leak a credential
    into a log line or a traceback.

    Attributes:
        provider_name: The identity provider in the emitted plan that will
            verify the token.
        issuer: The ``iss`` claim that selects that provider.
        key_id: The ``kid`` header that selects the provisioned key in the
            provider's JWKS document.
        algorithm: Signing algorithm both the provider's allow-list and the
            JWKS entry name.
        role_claim_path: Dotted claim path the provider reads roles from.
        roles: Roles the emitted plan's surfaces require of this provider.
        private_key_file: The provisioned private key the stack mounts.
    """

    provider_name: str
    issuer: str
    key_id: str
    algorithm: str
    role_claim_path: str
    roles: tuple[str, ...]
    private_key_file: Path


def _compose_bind_mounts(project_dir: Path) -> list[tuple[str, Path, str]]:
    """Return every ``(service, host path, container path)`` bind mount the compose file declares."""
    services = _compose_document(project_dir / COMPOSE_FILENAME)["services"]
    mounts: list[tuple[str, Path, str]] = []
    for name, service in services.items():
        if not isinstance(service, dict):
            continue
        for entry in service.get("volumes") or []:
            if isinstance(entry, str):
                parts = entry.split(":")
                source, target = (parts + ["", ""])[:2]
            elif isinstance(entry, dict):
                source, target = str(entry.get("source", "")), str(entry.get("target", ""))
            else:
                continue
            if not source or not target:
                continue
            mounts.append((str(name), (project_dir / source).resolve(), target))
    return mounts


def _dns_names_of(service_name: str, service: dict[str, object]) -> set[str]:
    """Return every name other containers can reach *service_name* by."""
    names = {service_name}
    container_name = service.get("container_name")
    if container_name:
        names.add(str(container_name))
    networks = service.get("networks")
    if isinstance(networks, dict):
        for attachment in networks.values():
            if isinstance(attachment, dict):
                names.update(str(alias) for alias in attachment.get("aliases") or [])
    return names


def _jwks_documents_in(source_file: Path) -> list[dict[str, object]]:
    """Return every JWKS document embedded in an emitted source file.

    The document is a string constant inside the emitted JWKS sidecar, written
    as adjacent literals across several lines so it stays reviewable. A text
    scan cannot reassemble those; the language's own parser folds them into one
    constant for free, which is why this parses rather than greps.
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    documents: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        try:
            parsed = json.loads(node.value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("keys"), list):
            documents.append(parsed)
    return documents


def _jwks_documents_served_by(project_dir: Path, hostname: str) -> list[dict[str, object]]:
    """Return the JWKS documents the in-stack container answering to *hostname* serves."""
    services = _compose_document(project_dir / COMPOSE_FILENAME)["services"]
    serving = {
        str(name)
        for name, service in services.items()
        if isinstance(service, dict) and hostname in _dns_names_of(str(name), service)
    }
    if not serving:
        return []
    return [
        document
        for service_name, host_path, _ in _compose_bind_mounts(project_dir)
        if service_name in serving
        and host_path.suffix == _JWKS_SOURCE_SUFFIX
        and host_path.is_file()
        for document in _jwks_documents_in(host_path)
    ]


def _base64url_uint(value: object) -> int | None:
    """Decode a JWK base64url integer, or ``None`` when it is not one."""
    if not isinstance(value, str):
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        return None
    return int.from_bytes(raw, "big")


def _jwk_holds(jwk: object, private_key: RSAPrivateKey) -> bool:
    """Report whether *jwk* is the public half of *private_key*."""
    if not isinstance(jwk, dict) or str(jwk.get("kty")) != "RSA":
        return False
    numbers = private_key.public_key().public_numbers()
    return (
        _base64url_uint(jwk.get("n")) == numbers.n and _base64url_uint(jwk.get("e")) == numbers.e
    )


def _required_roles(plan: dict[str, object], provider_name: str, provider: dict[str, object]) -> tuple[str, ...]:
    """Return the roles the plan's surfaces demand of *provider_name*, in its own spelling.

    ``roleMappings`` maps a provider-issued role name onto the Datrix role a
    surface names, so the token has to carry the provider-side spelling. A role
    the provider does not remap passes through unchanged.
    """
    surfaces = plan.get("surfaces")
    demanded: set[str] = set()
    if isinstance(surfaces, dict):
        for surface in surfaces.values():
            if not isinstance(surface, dict) or provider_name not in (surface.get("providers") or []):
                continue
            demanded.update(str(role) for role in surface.get("roles") or [])
    mappings = provider.get("roleMappings")
    provider_spelling = (
        {str(datrix): str(issued) for issued, datrix in mappings.items()}
        if isinstance(mappings, dict)
        else {}
    )
    return tuple(sorted(provider_spelling.get(role, role) for role in demanded))


def _constrains_audience(provider: dict[str, object]) -> bool:
    """Report whether a provider requires an ``aud`` claim this gate cannot also satisfy."""
    return bool(provider.get("allowedAudiences") or provider.get("allowedAudienceRefs"))


def plan_token_issuance(project_dir: Path) -> TokenIssuance:
    """Resolve how to mint a token the emitted stack will accept, or fail loud.

    Every authenticated route in the fixture goes through two independent
    checks, and one token has to pass both:

    * the gateway's ``auth_request`` subrequest, which verifies the signature
      against the PROVISIONED public key the stack mounts; and
    * the service's own identity path, which selects a provider by the token's
      ``iss`` and verifies it against that provider's JWKS.

    So the provisioned private key is the only signing material that can work,
    and it is usable only if some provider's JWKS actually holds its public
    half. That is the set comparison this function performs -- over the emitted
    compose mounts, the emitted provider plan and the emitted JWKS document,
    never over a key this gate minted for itself.

    Args:
        project_dir: The generated project root.

    Returns:
        The non-secret facts :func:`mint_bearer_token` needs.

    Raises:
        EmittedArtifactDefect: If the emitted project provisions no private key,
            ships no provider plan, or names no provider whose JWKS holds the
            provisioned key. Every one of those leaves the gate unable to
            exercise an authenticated route, which is the vacuous run it exists
            to prevent -- so it fails the gate rather than quietly calling every
            route unauthenticated.
    """
    mounts = _compose_bind_mounts(project_dir)
    keys = [host for _, host, target in mounts if Path(target).name == JWT_PRIVATE_KEY_HANDLE]
    if not keys:
        raise EmittedArtifactDefect(
            f"The compose file in {project_dir} mounts no {JWT_PRIVATE_KEY_HANDLE!r} secret, so "
            f"this gate has no provisioned key to sign a bearer token with and every "
            f"authenticated route would go unexercised. Expected a bind mount whose container "
            f"path is named after the framework's provisioned signing-key handle. Fix: generate "
            f"a fixture whose services declare authentication, so the runtime provisions the key "
            f"pair -- never by minting a key pair here, which the running services would reject."
        )
    private_key_file = keys[0]
    if not private_key_file.is_file():
        raise EmittedArtifactDefect(
            f"The compose file in {project_dir} mounts {private_key_file} as the "
            f"{JWT_PRIVATE_KEY_HANDLE!r} secret, but no such file was emitted. Expected the "
            f"provisioned private key on disk before the stack is booted."
        )
    loaded = load_pem_private_key(private_key_file.read_bytes(), password=None)
    if not isinstance(loaded, RSAPrivateKey):
        raise EmittedArtifactDefect(
            f"The provisioned signing key at {private_key_file} is a "
            f"{type(loaded).__name__}, which this gate cannot match against a JWKS entry. "
            f"Expected an RSA private key. Fix: teach this gate the emitted key type rather "
            f"than substituting signing material of its own."
        )
    plan_files = [host for _, host, target in mounts if target == LOCAL_IDENTITY_PROVIDER_PLAN_PATH]
    if not plan_files or not plan_files[0].is_file():
        raise EmittedArtifactDefect(
            f"The compose file in {project_dir} mounts no identity provider plan at "
            f"{LOCAL_IDENTITY_PROVIDER_PLAN_PATH!r}, so no issuer this gate could sign for can be "
            f"resolved and every authenticated route would go unexercised. Expected the emitted "
            f"plan the services validate tokens against."
        )
    plan_file = plan_files[0]
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    providers = plan.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise EmittedArtifactDefect(
            f"The identity provider plan at {plan_file} declares no providers, so no token this "
            f"gate mints could ever be attributed. Expected at least one provider entry."
        )

    findings: list[str] = []
    for name, provider in sorted(providers.items()):
        if not isinstance(provider, dict):
            continue
        jwks_uri = str(provider.get("jwksUri", ""))
        hostname = urlparse(jwks_uri).hostname or ""
        documents = _jwks_documents_served_by(project_dir, hostname) if hostname else []
        matching = [
            jwk
            for document in documents
            for jwk in document["keys"]  # type: ignore[index]
            if _jwk_holds(jwk, loaded)
        ]
        if not matching:
            findings.append(
                f"{name!r}: jwksUri {jwks_uri!r} (host {hostname!r}) -> "
                f"{len(documents)} JWKS document(s) served from inside this stack, none holding "
                f"the provisioned key"
            )
            continue
        if _constrains_audience(provider):
            findings.append(
                f"{name!r}: holds the provisioned key but constrains 'aud' "
                f"({provider.get('allowedAudiences')!r} / "
                f"{provider.get('allowedAudienceRefs')!r}); the gateway's own verification "
                f"expects no audience, so one token cannot satisfy both"
            )
            continue
        jwk = matching[0]
        allowed = [
            algorithm
            for algorithm in provider.get("allowedAlgorithms") or []
            if isinstance(algorithm, str) and algorithm == str(jwk.get("alg", algorithm))
        ]
        if not allowed:
            findings.append(
                f"{name!r}: holds the provisioned key but its allow-list "
                f"{provider.get('allowedAlgorithms')!r} names no algorithm the JWKS entry "
                f"({jwk.get('alg')!r}) also declares"
            )
            continue
        role_source = provider.get("roleSource")
        issuance = TokenIssuance(
            provider_name=str(name),
            issuer=str(provider.get("issuer", "")),
            key_id=str(jwk.get("kid", "")),
            algorithm=sorted(allowed)[0],
            role_claim_path=(
                str(role_source.get("claimPath", DEFAULT_ROLE_CLAIM_PATH))
                if isinstance(role_source, dict)
                else DEFAULT_ROLE_CLAIM_PATH
            ),
            roles=_required_roles(plan, str(name), provider),
            private_key_file=private_key_file,
        )
        logger.info(
            "bearer credential: provider=%s issuer=%s kid=%s alg=%s roles=%s signed with the "
            "provisioned key at %s",
            issuance.provider_name,
            issuance.issuer,
            issuance.key_id,
            issuance.algorithm,
            list(issuance.roles),
            private_key_file,
        )
        return issuance

    raise EmittedArtifactDefect(
        f"No provider in {plan_file} can verify a token signed with the provisioned key at "
        f"{private_key_file}, so every authenticated route would answer 401 and the run would "
        f"check nothing. Per provider: {'; '.join(findings)}. Expected one provider whose "
        f"in-stack JWKS holds the public half of the provisioned key and constrains no audience. "
        f"Fix: correct whatever provisions the key pair or emits the JWKS -- never by minting a "
        f"second key pair here, injecting a public key as a secret, or falling back to calling "
        f"the routes unauthenticated."
    )


def mint_bearer_token(issuance: TokenIssuance) -> str:
    """Sign a short-lived bearer token with the stack's own provisioned private key.

    The returned value is a credential: it is written straight to a file the
    harness reads and is never logged, echoed into a process argument list, or
    stored on a dataclass.
    """
    now = datetime.datetime.now(datetime.UTC)
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "iss": issuance.issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(seconds=_TOKEN_LIFETIME_SECONDS)).timestamp()),
    }
    segments = issuance.role_claim_path.split(".")
    cursor: dict[str, object] = claims
    for segment in segments[:-1]:
        nested: dict[str, object] = {}
        cursor[segment] = nested
        cursor = nested
    cursor[segments[-1]] = list(issuance.roles)
    return jwt.encode(
        claims,
        issuance.private_key_file.read_text(encoding="utf-8"),
        algorithm=issuance.algorithm,
        headers={"kid": issuance.key_id},
    )


def assert_container_names_are_free(project_dir: Path) -> None:
    """Compare the names the emitted compose file claims against the ones the host holds.

    A Docker container name is global to the daemon, not scoped to the compose
    project, so a generated stack whose compose file fixes a container name
    cannot start while anything else on the host holds that name. Discovering
    that from ``docker compose up`` costs a full image build first and then
    reports it as an opaque daemon conflict, so the set comparison happens
    here, before anything is built, and names the holder.

    Args:
        project_dir: The generated project root holding the compose file.

    Raises:
        RuntimeError: If any name the compose file claims is already taken.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    services = _compose_document(compose_file)["services"]
    claimed = {
        str(service["container_name"]): name
        for name, service in services.items()
        if isinstance(service, dict) and service.get("container_name")
    }
    listed = _run(
        ["docker", "ps", "--all", "--format", "{{.Names}}"],
        cwd=project_dir,
        timeout_seconds=_DOCKER_PORT_TIMEOUT_SECONDS,
    )
    if listed.returncode != 0:
        raise RuntimeError(
            f"Could not list the container names the host already holds ('docker ps --all' "
            f"exited {listed.returncode}), so the names {compose_file} claims cannot be checked "
            f"for conflicts.\n{listed.stdout}\n{listed.stderr}"
        )
    taken = sorted(set(listed.stdout.split()) & set(claimed))
    if not taken:
        return
    holders = []
    for container in taken:
        owner = _run(
            [
                "docker",
                "inspect",
                container,
                "--format",
                '{{index .Config.Labels "com.docker.compose.project"}}',
            ],
            cwd=project_dir,
            timeout_seconds=_DOCKER_PORT_TIMEOUT_SECONDS,
        )
        project = owner.stdout.strip() or "an unlabelled container"
        holders.append(f"{container!r} (compose service {claimed[container]!r}, held by {project})")
    raise RuntimeError(
        f"{compose_file} fixes container name(s) this host already holds: {'; '.join(holders)}. "
        f"A container name is global to the Docker daemon, so the stack cannot start while they "
        f"are taken. Expected: every name the compose file claims to be free. Fix: stop whatever "
        f"holds them, or -- when the name carries no application prefix and therefore collides "
        f"with every other generated stack -- fix the generator that emits it."
    )


#: A published-port mapping as `docker ps` reports it, e.g.
#: ``0.0.0.0:29092->29092/tcp``. Only the host side is of interest.
_BOUND_HOST_PORT_RE: Final[re.Pattern[str]] = re.compile(r":(?P<port>\d+)->")


def assert_fixed_host_ports_are_free(project_dir: Path) -> None:
    """Compare the host ports the emitted compose file fixes against the ones already bound.

    Most published ports in a generated compose file are ephemeral or drawn
    from an environment substitution, and neither can collide. A port written
    as a literal on the host side can, and like a container name it is claimed
    from a namespace the whole machine shares. Finding that out from
    ``docker compose up`` costs an image build first, so the comparison happens
    here and names the holder.

    Args:
        project_dir: The generated project root holding the compose file.

    Raises:
        RuntimeError: If any host port the compose file fixes is already bound.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    services = _compose_document(compose_file)["services"]
    claimed: dict[str, str] = {}
    for name, service in services.items():
        if not isinstance(service, dict):
            continue
        for mapping in service.get("ports") or []:
            host_side = str(mapping).rpartition(":")[0].strip()
            if host_side.isdigit():
                claimed[host_side] = name
    if not claimed:
        return
    listed = _run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"],
        cwd=project_dir,
        timeout_seconds=_DOCKER_PORT_TIMEOUT_SECONDS,
    )
    if listed.returncode != 0:
        raise RuntimeError(
            f"Could not list the host ports already bound ('docker ps' exited "
            f"{listed.returncode}), so the ports {compose_file} fixes cannot be checked for "
            f"conflicts.\n{listed.stdout}\n{listed.stderr}"
        )
    conflicts = []
    for line in listed.stdout.splitlines():
        container, _, ports = line.partition("\t")
        bound = {match.group("port") for match in _BOUND_HOST_PORT_RE.finditer(ports)}
        for port in sorted(bound & set(claimed)):
            conflicts.append(f"{port} (compose service {claimed[port]!r}, bound by {container!r})")
    if not conflicts:
        return
    raise RuntimeError(
        f"{compose_file} fixes host port(s) this machine has already bound: "
        f"{'; '.join(sorted(conflicts))}. A published host port is machine-global, so the stack "
        f"cannot start while they are taken. Expected: every port the compose file fixes to be "
        f"free. Fix: stop whatever holds them, or -- when the port is a fixed literal rather than "
        f"an overridable substitution and therefore collides with every other generated stack -- "
        f"fix the generator that emits it."
    )


def boot_backend(project_dir: Path, entry_point: BrowserEntryPoint) -> None:
    """Boot the generated stack through its own deployment front door, then gate on health.

    The generated project ships the deployment CLI that knows what compose
    alone cannot do for it -- most concretely, building the shared per-system
    base image every service's Dockerfile is a thin layer on, which compose
    will otherwise try to pull from a registry that has never heard of it.
    Reimplementing that here would be a second, silently drifting copy of the
    emitted deployment, so the gate runs the emitted one, addressed by the
    lifecycle verb every Datrix deployment CLI shares.

    Not every target emits that CLI -- a project whose services need nothing
    built outside compose ships none -- so its absence is a different emitted
    shape rather than an error, and it is logged so a run never leaves which
    path it took to inference.

    Whichever path built the stack, turning "started" into "healthy" is one
    idempotent ``up --build --wait``, which fails loud on a container that
    never becomes healthy -- no readiness loop of our own, which could only
    hide that failure.

    Raises:
        RuntimeError: If the deployment fails, or the stack never reaches a
            healthy state.
    """
    deploy_script = project_dir / DEPLOY_SCRIPT_RELATIVE
    if deploy_script.is_file():
        deployed = _run(
            [sys.executable, str(deploy_script), VERB_DEPLOY],
            cwd=project_dir,
            timeout_seconds=_DOCKER_UP_TIMEOUT_SECONDS,
            env_overrides=entry_point.compose_env,
        )
        if deployed.returncode != 0:
            raise RuntimeError(
                f"'{deploy_script.name} {VERB_DEPLOY}' failed for {project_dir} (exit "
                f"{deployed.returncode}).\n{deployed.stdout}\n{deployed.stderr}"
            )
    else:
        logger.info(
            "%s ships no deployment CLI at %s, so compose is its whole deployment.",
            project_dir.name,
            DEPLOY_SCRIPT_RELATIVE,
        )
    healthy = _run(
        ["docker", "compose", "up", "-d", "--build", "--wait"],
        cwd=project_dir,
        timeout_seconds=_DOCKER_UP_TIMEOUT_SECONDS,
        env_overrides=entry_point.compose_env,
    )
    if healthy.returncode != 0:
        raise RuntimeError(
            f"The stack at {project_dir} started but never reached a healthy state "
            f"('docker compose up -d --build --wait' exited {healthy.returncode})."
            f"\n{healthy.stdout}\n{healthy.stderr}"
        )


def stop_backend(project_dir: Path, entry_point: BrowserEntryPoint) -> None:
    """Tear the stack down. Never raises: it runs where a real result already exists."""
    result = _run(
        ["docker", "compose", "down", "-v", "--remove-orphans"],
        cwd=project_dir,
        timeout_seconds=_DOCKER_DOWN_TIMEOUT_SECONDS,
        env_overrides=entry_point.compose_env,
    )
    if result.returncode != 0:
        logger.warning(
            "Tearing down the stack at %s exited %d; the gate result above stands.\n%s\n%s",
            project_dir,
            result.returncode,
            result.stdout,
            result.stderr,
        )


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
    result = _run(
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
        )
        for row in summary["rows"]
    ]
    return results, summary


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
    entry_point = plan_browser_entry_point(project_dir)
    issuance = plan_token_issuance(project_dir)
    assert_container_names_are_free(project_dir)
    assert_fixed_host_ports_are_free(project_dir)
    supplied = prepare_env_file(project_dir)
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
        boot_backend(project_dir, entry_point)
        base_url = resolve_base_url(project_dir, entry_point, dialled_host)
        logger.info("backend=%s browser-facing base URL resolved to %s", backend, base_url)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(mint_bearer_token(issuance), encoding="utf-8")
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
        stop_backend(project_dir, entry_point)

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
        generated interface for every backend that booted; 1 when a response
        mismatched, a declared route had no reachable client method, the
        emitted client did not compile, or nothing was checked at all; 2 when
        no backend targets are registered, no trusted host reaches this
        machine, or every registered backend failed.
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
        dialled_host = resolve_dialled_host()
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

    return 0 if _report(runs, booted, skipped, defects) else 1


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = every typed response parsed against its generated
        interface, 1 = at least one mismatch or unreachable route or a client
        tree that does not compile, 2 = the non-vacuity self-test failed, no
        backend targets are registered, or every registered backend failed.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate a backend and a browser client for the adopted fixture application, boot "
            "the backend, call every generated client method against it, and compare every "
            "response against the interface the client generator emitted for it."
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
        "null body + a required property still rejects one); "
        "diagnostic-durability self-test passed."
    )

    if args.self_test:
        return 0

    return run_gate(reuse_generated=args.reuse_generated)


if __name__ == "__main__":
    sys.exit(main())
