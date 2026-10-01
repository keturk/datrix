#!/usr/bin/env python3
"""Generate, boot, address, authenticate against, and tear down a generated compose stack.

The machinery every repo-level gate that drives a GENERATED application against
a RUNNING backend shares: real generation through ``datrix-cli``'s own
``GenerationPipeline`` from a private copy of a fixture source, the
compose/environment seam closer, the trusted-host seam closer, the pre-boot
container-name and host-port conflict checks, booting through the project's own
deployment front door, minting a bearer token the booted stack's own identity
plumbing accepts, and teardown.

It lives once, here, because more than one gate drives a live stack and each of
them needs exactly the same answers to "which host do I dial", "which variables
does compose still need", and "which key signs a token this stack accepts".
A second copy of any of those in a gate is a second answer that drifts.

Nothing here hardcodes a target language, a compose service name, or a
variable name: every fact is read from the emitted project or the fixture's own
analyzed application.
"""

from __future__ import annotations

import ast
import base64
import datetime
import functools
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
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import jwt
import yaml
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from datrix_cli.generation.validation_level import ValidationLevel
from datrix_cli.pipeline.contract import PipelineConfig, PipelineResult
from datrix_cli.pipeline.generation import GenerationPipeline

# The producer/consumer seam between the emitted compose file and the
# environment file it interpolates, read with the owning package's own parser
# rather than a second one written here.
from datrix_codegen_docker.deploy_runtime import compose_required_variables

# The compose network the public entry point is attached to. Imported from the
# container-runtime generator that assigns it, so a gate reads the same fact
# the generator wrote rather than re-spelling the network name.
from datrix_codegen_docker.generators.compose._network_assignment import NETWORK_FRONTEND

# The API gateway's compose service name, derived by the generator that names it.
from datrix_codegen_docker.generators.config.gateway._core import gateway_compose_service_key

# The fixture's own declared configuration, read through the loader every
# generator reads it with -- so the trusted-host comparison below comes from the
# producer itself and not from one language's transcription of it.
from datrix_common.config.dcfg.parser import parse_dcfg
from datrix_common.config.unified_loader import load_service_config

# Where a container-runtime deployment mounts the identity provider plan, and
# the framework's handle for the provisioned JWT signing key. Both are read from
# the packages that emit them rather than re-spelled here.
from datrix_common.deployment.runtime_bootstrap import LOCAL_IDENTITY_PROVIDER_PLAN_PATH
from datrix_codegen_kernel.generation.framework_secret_handles import JWT_PRIVATE_KEY_HANDLE

# The lifecycle verb every Datrix-generated deployment CLI answers to, taken
# from the module that defines the shared vocabulary rather than spelled again.
from datrix_codegen_kernel.platform.deployment_lifecycle import VERB_DEPLOY
from datrix_common.plugin.identity import LanguageId

# The roles a bearer token must carry are read from the fixture's own analyzed
# application -- the per-route auth contracts every generator renders -- since
# the identity provider plan carries providers only.
from datrix_cli.pipeline.stages.analysis import run_pre_analysis_pipeline
from datrix_common.datrix_model.auth_contract import AuthMode
from datrix_common.datrix_model.containers import Application
from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
from datrix_language.registration import register_all

# `GenerationPipeline.run()` parses real `.dtrx` source, which needs the stdlib
# parser protocol registered first -- normally done once by `datrix_cli.main`
# at CLI startup. A gate drives the pipeline directly, so this module registers
# the same implementation itself before any real generation is attempted.
register_all()

logger = logging.getLogger(__name__)

COMPOSE_FILENAME: Final[str] = "docker-compose.yml"

#: The generated project's own deployment CLI, relative to its root. When a
#: project ships one it is the emitted front door for bringing the stack up,
#: and the only thing that knows how to build what compose cannot build for
#: itself (a shared per-system base image every service layers on). A project
#: whose services need nothing built outside compose ships none.
DEPLOY_SCRIPT_RELATIVE: Final[Path] = Path("scripts") / "deploy.py"

ENV_FILENAME: Final[str] = ".env"
ENV_EXAMPLE_FILENAME: Final[str] = ".env.example"

#: Directory name of the per-application generation state that lives beside the
#: SOURCE rather than in the output tree -- the RDBMS migration ledger among
#: it. Omitted from every private source copy; see
#: :func:`prepare_isolated_source`.
_LEDGER_DIR_NAME: Final[str] = ".datrix"

#: ``ConfigDecl.kind`` of a service configuration. The kind vocabulary
#: ("service" / "system" / "shared") is the one
#: ``unified_loader._load_dcfg_canonical_dict`` validates against; only the
#: system kind publishes a constant for it, so the service kind is named here.
SERVICE_CONFIG_KIND: Final[str] = "service"

#: Bytes of entropy behind each secret a gate supplies to the stack it boots.
#: Generated with the standard library's cryptographic source, fresh per run,
#: and never printed -- the generated project treats its environment file as
#: operator-owned, and an operator does not paste a placeholder in.
_GENERATED_SECRET_BYTES: Final[int] = 24

#: A character no Windows console code page can encode, observed verbatim in
#: pnpm's build transcript -- which reaches a gate embedded in a backend's
#: failure reason. It is the probe the diagnostic-durability self-test pushes
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

#: Lifetime of a bearer token minted for a booted stack. Long enough to outlast
#: a gate's whole run against one stack, short enough that a token left in a
#: torn-down project's scratch directory expires on its own.
_TOKEN_LIFETIME_SECONDS: Final[int] = 3600

#: File suffix of an emitted artifact a JWKS document can be read out of. The
#: in-stack JWKS sidecar every container-runtime deployment emits is a Python
#: module regardless of the backend language it serves, and its document is
#: written as adjacent string literals across several lines -- which a text
#: scan cannot reassemble and the language's own parser folds for free.
_JWKS_SOURCE_SUFFIX: Final[str] = ".py"

DOCKER_UP_TIMEOUT_SECONDS: Final[int] = 3600
DOCKER_DOWN_TIMEOUT_SECONDS: Final[int] = 600
DOCKER_QUERY_TIMEOUT_SECONDS: Final[int] = 60

#: A compose port mapping's host side written as an environment substitution,
#: e.g. ``${GATEWAY_PORT:-8080}``. The variable name is read out of the
#: generated file rather than spelled here, so nothing about which variable the
#: generator chose is hardcoded in a gate.
ENV_SUBSTITUTION_RE: Final[re.Pattern[str]] = re.compile(r"^\$\{(?P<name>\w+)(:?-[^}]*)?\}$")

#: A published-port mapping as `docker ps` reports it, e.g.
#: ``0.0.0.0:29092->29092/tcp``. Only the host side is of interest.
_BOUND_HOST_PORT_RE: Final[re.Pattern[str]] = re.compile(r":(?P<port>\d+)->")


class EmittedArtifactDefect(RuntimeError):
    """A defect in what the generator emitted, never an environmental failure.

    A backend that cannot be generated or booted is an environment problem. A
    backend that generated fine but emitted something a gate cannot drive at
    all is a hole in the round trip -- reporting it as an environment problem
    would let a gate go green while checking nothing, so it is its own class.
    """


def configure_logging(debug: bool = False) -> None:
    """Configure logging output so no diagnostic can be lost to the console codec.

    Almost every line a live-stack gate reports carries text it did not author
    -- docker build transcripts, compiler diagnostics, container logs -- and
    that text routinely contains characters the Windows console code page
    cannot encode (pnpm alone prints U+2009). A handler writing to such a
    stream raises ``UnicodeEncodeError`` *while formatting the record*, and the
    record is dropped: a backend's failure reason then disappears in silence.
    The streams are therefore switched to escape unencodable characters instead
    of refusing the write. Escaping, not re-encoding: the console's own codec is
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


def run_diagnostic_durability_self_test() -> list[str]:
    """Prove no diagnostic can be dropped by the console's character codec.

    A live-stack gate's contract is that a backend it could not exercise is
    reported by name, with its reason -- never narrowed in silence. Almost every
    such reason quotes a build transcript or a container log, text the gate did
    not author, and a single character the console code page cannot encode
    makes the logging handler raise *while writing the record*. The record is
    then discarded and the backend's reason vanishes, which looks exactly like a
    backend that had nothing to say. That happened: one backend's entire skip
    reason was lost to a U+2009 in pnpm's output.

    So before trusting any diagnostic, every configured stream handler is asked
    the same question the codec will ask it: can it render the probe character?

    Returns:
        Failure descriptions; empty means every configured stream can carry any
        text a gate might quote.
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
                f"code page is DROPPED rather than written -- a backend's failure reason would "
                f"disappear in silence. Fix: configure_logging() reconfigures the standard "
                f"streams to 'backslashreplace'; a handler added after it must do the same."
            )
    return problems


def run_command(
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


def free_host_port() -> int:
    """Reserve a host port the operating system reports as free.

    A generated compose file publishes its entry point on a host port drawn
    from an environment variable with a fixed default. Taking that default
    would make a gate fail whenever anything else on the machine already holds
    it -- an environmental collision reported as a generator defect. Supplying a
    free port instead keeps a gate independent of what else is running, and the
    real mapping is still read back from the running stack rather than assumed.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def compose_document(compose_file: Path) -> dict[str, object]:
    """Parse the generated compose file, failing loud and naming it."""
    if not compose_file.is_file():
        raise RuntimeError(
            f"No compose file at {compose_file}. Expected the generated project to contain one so "
            f"its services, ports and mounts can be read from it. Fix: regenerate the project for "
            f"a container runtime that emits a compose file."
        )
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        raise RuntimeError(
            f"The compose file {compose_file} declares no 'services' mapping. Expected a compose "
            f"document whose services can be inspected."
        )
    return document


def compose_services(project_dir: Path) -> dict[str, dict[str, object]]:
    """Return the generated compose file's services, keyed by compose service name."""
    services = compose_document(project_dir / COMPOSE_FILENAME)["services"]
    if not isinstance(services, dict):
        raise RuntimeError(f"The compose file in {project_dir} declares no 'services' mapping.")
    return {str(name): service for name, service in services.items() if isinstance(service, dict)}


def port_mapping_of(service_name: str, service: dict[str, object], compose_file: Path) -> str:
    """Return the single published port mapping of an entry-point service."""
    ports = service.get("ports")
    if not isinstance(ports, list) or len(ports) != 1:
        raise RuntimeError(
            f"The entry-point compose service {service_name!r} in {compose_file} publishes "
            f"{ports!r}. Expected exactly one published port mapping so the base URL is "
            f"unambiguous. Fix: resolve which port serves the routes and publish only it."
        )
    return str(ports[0])


def published_host_port(
    project_dir: Path, service_name: str, container_port: str, compose_env: dict[str, str]
) -> int:
    """Ask the running stack which host port a container port of a service landed on.

    A mapping's host side can be an environment substitution or an ephemeral
    assignment, so the compose text alone does not settle it -- the live stack
    does.

    Raises:
        RuntimeError: If the published host port cannot be resolved.
    """
    result = run_command(
        ["docker", "compose", "port", service_name, container_port],
        cwd=project_dir,
        timeout_seconds=DOCKER_QUERY_TIMEOUT_SECONDS,
        env_overrides=compose_env,
    )
    published = result.stdout.strip().splitlines()
    host_port = published[-1].rsplit(":", 1)[-1].strip() if published else ""
    if result.returncode != 0 or not host_port.isdigit():
        raise RuntimeError(
            f"Could not resolve the published host port for container port {container_port} of "
            f"{service_name!r} in {project_dir / COMPOSE_FILENAME} (docker compose port exited "
            f"{result.returncode}). Expected a '<address>:<port>' line. Fix: confirm the stack is "
            f"running and that the service publishes the port its compose entry declares."
            f"\n{result.stdout}\n{result.stderr}"
        )
    return int(host_port)


@dataclass(frozen=True)
class EntryPoint:
    """The generated stack's single public, browser-facing published port -- its gateway.

    Attributes:
        service_name: Compose service serving the application's public routes.
        container_port: The port that service listens on inside its container.
        compose_env: Environment the stack must be brought up with for the
            host side of that mapping to land where the gate expects. Empty
            when the compose file fixes the host port itself.
    """

    service_name: str
    container_port: str
    compose_env: dict[str, str]


def plan_entry_point(project_dir: Path, source: Path, profile: str) -> EntryPoint:
    """Decide where requests to the generated application's API routes must be sent.

    The API gateway's compose service name is derived from the fixture's own
    analyzed application by the container-runtime generator's own function --
    never guessed from what happens to publish a port, since a browser app's
    static site is published on the same front-end network beside it. The
    service must exist, sit on the front-end network, and publish exactly one
    port; anything else is a loud failure naming the file.

    When the host side of that mapping is an environment substitution, this
    also reserves a free host port for the variable the generated file names,
    so the gate never collides with whatever else on the machine happens to
    hold the compose default.

    Args:
        project_dir: The generated project root holding the compose file.
        source: The fixture's entry ``.dtrx`` the project was generated from.
        profile: The profile it was generated under.

    Raises:
        RuntimeError: If the gateway service is absent, off the front-end
            network, or its mapping cannot be read.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    service_name = gateway_compose_service_key(analyze_fixture(source, profile))
    services = compose_services(project_dir)
    if service_name not in services:
        raise RuntimeError(
            f"The compose file {compose_file} has no {service_name!r} service, the API gateway the "
            f"application's routes are served through. Services: {sorted(services)}. Fix: generate "
            f"for a profile that declares a gateway."
        )
    service = services[service_name]
    if NETWORK_FRONTEND not in (service.get("networks") or []):
        raise RuntimeError(
            f"The gateway {service_name!r} in {compose_file} is not on the {NETWORK_FRONTEND!r} "
            f"network, so it is not the public entry point."
        )
    mapping = port_mapping_of(service_name, service, compose_file)
    host_side, _, container_side = mapping.rpartition(":")
    container_port = container_side.split("/", 1)[0].strip()
    if not container_port.isdigit():
        raise RuntimeError(
            f"Could not read a container port out of the mapping {mapping!r} declared by "
            f"{service_name!r} in {compose_file}. Expected a '<host>:<container>' mapping."
        )
    if ENV_SUBSTITUTION_RE.match(host_side.strip()) is None:
        logger.info(
            "%s publishes the gateway on a host port it fixes (%r), not an overridable one.",
            compose_file,
            host_side,
        )
    return EntryPoint(
        service_name=service_name,
        container_port=container_port,
        compose_env=overridable_host_ports(project_dir),
    )


def overridable_host_ports(project_dir: Path) -> dict[str, str]:
    """A free host port for every published port the compose file leaves overridable.

    A mapping whose host side is an environment substitution
    (``${GATEWAY_PORT:-8080}:80``) is the generator's own declaration that the
    host port is the operator's to move. Taking its default would make a boot
    fail whenever anything else on the machine -- another generated stack --
    already holds it, so each such variable is given a port the operating
    system reports free. The emitted ``.env`` keeps its own value; the
    process environment a stack is brought up with takes precedence over it.
    """
    assigned: dict[str, str] = {}
    for service in compose_services(project_dir).values():
        for mapping in service.get("ports") or []:
            host_side = str(mapping).rpartition(":")[0].strip()
            substitution = ENV_SUBSTITUTION_RE.match(host_side)
            if substitution is not None and substitution.group("name") not in assigned:
                assigned[substitution.group("name")] = str(free_host_port())
    if assigned:
        logger.info("%s: overridable host ports moved to free ports: %s", project_dir.name, assigned)
    return assigned


def resolve_entry_base_url(project_dir: Path, entry_point: EntryPoint, host: str) -> str:
    """Ask the running stack which host port the public entry point landed on.

    Only the PORT comes from the stack: the host name is the one
    :func:`resolve_dialled_host` proved every emitted service trusts, because
    the address ``docker compose port`` reports is the bind address
    (``0.0.0.0``) and dialling that literally sends a Host header no service
    accepts.

    Args:
        project_dir: The generated project root.
        entry_point: The planned entry-point service and container port.
        host: The trusted host name to dial, from :func:`resolve_dialled_host`.

    Raises:
        RuntimeError: If the published host port cannot be resolved.
    """
    host_port = published_host_port(
        project_dir, entry_point.service_name, entry_point.container_port, entry_point.compose_env
    )
    return f"http://{host}:{host_port}"


def assigned_values(env_text: str) -> dict[str, str]:
    """Return every ``KEY=value`` assignment in an environment file, last wins."""
    values: dict[str, str] = {}
    for line in env_text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def prepare_env_file(project_dir: Path, supplier: str) -> list[str]:
    """Close the compose/environment seam before booting the generated stack.

    The emitted compose file CONSUMES variables; the emitted ``.env.example``
    PRODUCES every one the generator is the authority for (on a local profile
    that includes every credential of a container the generator itself
    provisions) but deliberately leaves blank the ones an operator or a
    provider's deploy step supplies -- an external database's admin password, a
    provider-realized endpoint -- because the generator cannot know those. An
    unsupplied one aborts interpolation with a message that names the variable
    and nothing else -- so this computes ``required - supplied`` from the
    emitted files themselves and supplies a freshly generated value for each
    remaining name. On a fully provisioned project the remaining set is empty;
    a non-empty one on such a project is a generator seam defect, not something
    to paper over, which is why the names are returned and reported.

    The values come from the standard library's cryptographic source, are new
    on every run, are never logged, and live only in the throwaway project the
    gate generates and tears down.

    Args:
        project_dir: The generated project root.
        supplier: The gate supplying the values, named in the written file.

    Returns:
        The variable names that had to be supplied, so the run can report the
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
    supplied = {name for name, value in assigned_values(example_text).items() if value}
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
        f"# Supplied by the {supplier}: every compose variable that declares\n"
        f"# itself required and carries no value in the emitted template. Freshly generated\n"
        f"# per run for this throwaway stack.\n"
        f"{generated}\n"
    )
    (project_dir / ENV_FILENAME).write_text(body, encoding="utf-8")
    return missing


def env_file_values(project_dir: Path) -> dict[str, str]:
    """Return the assignments of the environment file the stack was booted with.

    Raises:
        RuntimeError: If the project carries no prepared environment file.
    """
    env_file = project_dir / ENV_FILENAME
    if not env_file.is_file():
        raise RuntimeError(
            f"No environment file at {env_file}. Expected prepare_env_file() to have written it "
            f"before the stack was booted."
        )
    return assigned_values(env_file.read_text(encoding="utf-8"))


def _service_allowed_hosts(fixture_root: Path, profile: str) -> dict[str, list[str]]:
    """Return each fixture service's declared trusted-host list, keyed by config file.

    Read from the RESOLVED service configuration rather than from one backend's
    emitted transcription of it. ``httpSecurity.allowedHosts`` is author-declared
    and language-neutral: every target emits its own trusted-host guard from the
    same value. Reading the producer keeps this comparison valid for every
    backend a gate enumerates instead of only the one whose emitted file shape
    is known.

    Returns:
        ``{config file name: allowed hosts}``. A service that declares no list
        appears with an empty one -- it constrains nothing and is excluded from
        the intersection rather than silently emptying it.

    Raises:
        RuntimeError: If the fixture contains no service configuration at all,
            which would make the comparison vacuous.
    """
    declared: dict[str, list[str]] = {}
    for config_file in sorted(fixture_root.rglob("*.dcfg")):
        # utf-8-sig: fixture configuration files may carry a byte-order mark,
        # which the ConfigDSL parser sees as a stray leading character.
        decl = parse_dcfg(config_file.read_text(encoding="utf-8-sig"), str(config_file))
        if decl.kind != SERVICE_CONFIG_KIND:
            continue
        security = load_service_config(config_file, fixture_root, profile).profile.http_security
        hosts = [] if security is None or security.allowed_hosts is None else list(security.allowed_hosts)
        declared[config_file.name] = hosts
    if not declared:
        raise RuntimeError(
            f"No service configuration was found under {fixture_root}. Expected at least one "
            f"'config {SERVICE_CONFIG_KIND} ...' .dcfg declaring the fixture's services, so the "
            f"host a gate dials can be compared against the hosts the emitted services trust. "
            f"Fix: point the gate at a fixture that ships service configuration."
        )
    return declared


def _resolves_to_loopback(host: str) -> tuple[bool, list[str]]:
    """Report whether *host* names this machine's own loopback, and what it resolved to.

    A published container port is bound on the host's loopback interface, so a
    trusted host name only addresses it when every address it resolves to is a
    loopback address. A name that also resolves to a routable address would send
    the request somewhere else entirely, so it is not eligible.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False, []
    addresses = sorted({str(info[4][0]) for info in infos})
    loopback = all(ipaddress.ip_address(address).is_loopback for address in addresses)
    return bool(addresses) and loopback, addresses


def resolve_dialled_host(fixture_root: Path, profile: str) -> str:
    """Close the trusted-host seam before anything is generated or built.

    PRODUCED, by the fixture's own configuration: the set of Host header values
    every emitted service will trust. CONSUMED, by the gate: the single host
    name it puts in every URL it dials. The gateway forwards the client's Host
    verbatim to the upstream service *and* to its auth subrequest, so one name
    has to satisfy every service at once -- the intersection, not the union.

    A name only helps if it also reaches the published port on this machine, so
    the intersection is narrowed to the names that resolve to loopback here.

    Without this comparison a rejected Host is indistinguishable from a broken
    backend: the trusted-host guard answers ``400 Invalid host header``, and the
    gateway's auth subrequest turns that same 400 into a 500, so every
    authenticated route reports an opaque server error.

    Returns:
        The host name to dial.

    Raises:
        RuntimeError: If no trusted host reaches this machine's loopback, naming
            every service's declared list and what each candidate resolved to.
    """
    produced = _service_allowed_hosts(fixture_root, profile)
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
        f"{fixture_root}: {declared}. Trusted by every service in common: {accepted}. How each "
        f"resolves here: {detail}. Expected at least one common trusted host resolving only to a "
        f"loopback address, because the published container port is bound on loopback and the "
        f"gateway forwards the client's Host verbatim to every upstream service and to its auth "
        f"subrequest. Fix: run the gate on a machine where one of those names resolves to "
        f"loopback (a hosts-file entry is enough) -- never by widening httpSecurity.allowedHosts, "
        f"which is an author-declared trust boundary of the application under test."
    )


def prepare_isolated_source(fixture_root: Path, source_name: str, destination: Path) -> Path:
    """Give one backend its own private copy of a fixture application source.

    **Why a copy.** Several backends generate from the same fixture in one run;
    a private copy per backend keeps every generation's side effects (the
    ``.datrix`` manifest, any post-generation tool cache) in that backend's own
    scratch directory, so no backend can disturb another's.

    **Why the migration ledger is excluded from the copy.** A ledger is a
    single-language lineage by construction (``revisions/_manifest.json``
    records one ``language`` per revision), and a second backend against it is
    refused up front by ``guard_foreign_language_ledger``. A booted gate meets a
    fresh database every run, so a from-scratch baseline is the schema it
    wants; the exclusion is the stray guard for a ledger an ad-hoc run left
    behind.

    Args:
        fixture_root: The fixture application's root directory.
        source_name: The fixture's entry ``.dtrx`` file name.
        destination: The private directory to copy into (recreated).

    Returns:
        Path to the copied entry source.
    """
    shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_root, destination, ignore=shutil.ignore_patterns(_LEDGER_DIR_NAME))
    copied_source = destination / source_name
    if not copied_source.is_file():
        raise RuntimeError(
            f"Preparing an isolated source copy of {fixture_root} produced no {source_name} at "
            f"{copied_source}. Expected a copy of the fixture's entry source."
        )
    return copied_source


def generate_project(source_path: Path, output_dir: Path, backend: str, profile: str) -> None:
    """Generate an application for one backend language target.

    Real generation through ``datrix-cli``'s own ``GenerationPipeline``, the
    one true generation entry point, exactly as ``datrix generate`` invokes it
    -- at its default, full validation level. A booted gate needs a DEPLOYABLE
    tree, and part of what makes one deployable is written by the
    post-generation hooks that level runs (a web client target's workspace
    lockfile, which its container build installs from with ``npm ci``); a
    reduced level leaves a tree whose image build fails at ``COPY``.

    Args:
        source_path: The entry ``.dtrx`` to generate (normally a private copy).
        output_dir: Explicit output directory for this backend's tree.
        backend: A ``datrix.languages`` entry-point name.
        profile: The configuration profile to generate under.

    Raises:
        RuntimeError: If the pipeline reports failure, or raises. A generator
            may raise any exception type, and one backend's generation failing
            must be reported against that backend rather than ending the run
            for the ones that follow.
    """
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = PipelineConfig(
        target_language=LanguageId(backend),
        profile=profile,
        validation_level=ValidationLevel.STANDARD,
    )
    try:
        result: PipelineResult = GenerationPipeline().run(
            source_path=source_path, output_dir=output_dir, config=config
        )
    except Exception as exc:  # noqa: BLE001 -- re-raised with the backend named
        raise RuntimeError(
            f"Generating {source_path} for backend {backend!r} raised "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not result.success:
        raise RuntimeError(
            f"Generating {source_path} for backend {backend!r} failed: {result.errors}"
        )


@functools.lru_cache(maxsize=8)
def analyze_fixture(source: Path, profile: str) -> Application:
    """Parse and analyze a fixture application through generation's own pre-analysis sequence.

    ``run_pre_analysis_pipeline`` is the sequence the generation pipeline runs
    before its generators -- config resolution, system-entity injection, and
    analysis with infrastructure configuration attached to every block -- so
    the tree read here is the one the generators rendered from, never a
    partial re-derivation of it.

    Raises:
        EmittedArtifactDefect: If the fixture does not analyze cleanly -- a gate
            cannot read the facts it needs from it without that.
    """
    resolved = source.resolve()
    parsed = TreeSitterParser().parse_file(resolved)
    result = run_pre_analysis_pipeline(parsed, resolved.parent, resolved, profile)
    if not result.is_valid:
        errors = "; ".join(f"{d.code}: {d.message}" for d in result.errors)
        raise EmittedArtifactDefect(
            f"The fixture {resolved} does not pass semantic analysis for profile {profile!r}: "
            f"{errors}. Expected the fixture to analyze cleanly, as generation requires."
        )
    return result.app


def fixture_demanded_roles(source: Path, profile: str) -> frozenset[str]:
    """Return every Datrix role an authenticated REST route of the fixture demands.

    The identity provider plan carries providers only; which roles a route
    requires is enforced by the auth contract emitted with that route. So the
    roles a bearer token must carry to exercise every route are read from the
    same source the generators render those contracts from: the fixture's own
    analyzed application, one ``AuthContract`` per REST endpoint.

    Roles are any-of per route, so a token carrying the union of every route's
    roles satisfies each role check; a route whose provider allow-list excludes
    the token's provider refuses it on the provider check regardless.
    """
    app = analyze_fixture(source, profile)
    endpoints = (
        endpoint
        for service in app.services.values()
        for api in service.rest_apis.values()
        for endpoint in api.endpoints.values()
    )
    demanded: set[str] = set()
    for endpoint in endpoints:
        contract = endpoint.auth_contract
        if contract.mode in (AuthMode.PUBLIC, AuthMode.WEBHOOK):
            continue
        demanded.update(contract.roles)
    logger.info("fixture %s routes demand roles %s", source.name, sorted(demanded))
    return frozenset(demanded)


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
        roles: Roles the fixture's authenticated routes demand, in this
            provider's own spelling.
        private_key_file: The provisioned private key the stack mounts.
    """

    provider_name: str
    issuer: str
    key_id: str
    algorithm: str
    role_claim_path: str
    roles: tuple[str, ...]
    private_key_file: Path


def compose_bind_mounts(project_dir: Path) -> list[tuple[str, Path, str]]:
    """Return every ``(service, host path, container path)`` bind mount the compose file declares."""
    mounts: list[tuple[str, Path, str]] = []
    for name, service in compose_services(project_dir).items():
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
            mounts.append((name, (project_dir / source).resolve(), target))
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
    serving = {
        name
        for name, service in compose_services(project_dir).items()
        if hostname in _dns_names_of(name, service)
    }
    if not serving:
        return []
    return [
        document
        for service_name, host_path, _ in compose_bind_mounts(project_dir)
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


def _required_roles(demanded: frozenset[str], provider: dict[str, object]) -> tuple[str, ...]:
    """Return *demanded* Datrix roles in *provider*'s own spelling.

    ``roleMappings`` maps a provider-issued role name onto the Datrix role a
    route names, so the token has to carry the provider-side spelling. A role
    the provider does not remap passes through unchanged.
    """
    mappings = provider.get("roleMappings")
    provider_spelling = (
        {str(datrix): str(issued) for issued, datrix in mappings.items()}
        if isinstance(mappings, dict)
        else {}
    )
    return tuple(sorted(provider_spelling.get(role, role) for role in demanded))


def _constrains_audience(provider: dict[str, object]) -> bool:
    """Report whether a provider requires an ``aud`` claim a gate cannot also satisfy."""
    return bool(provider.get("allowedAudiences") or provider.get("allowedAudienceRefs"))


def plan_token_issuance(project_dir: Path, demanded_roles: frozenset[str]) -> TokenIssuance:
    """Resolve how to mint a token the emitted stack will accept, or fail loud.

    Every authenticated route goes through two independent checks, and one
    token has to pass both:

    * the gateway's auth subrequest, which verifies the signature against the
      PROVISIONED public key the stack mounts; and
    * the service's own identity path, which selects a provider by the token's
      ``iss`` and verifies it against that provider's JWKS.

    So the provisioned private key is the only signing material that can work,
    and it is usable only if some provider's JWKS actually holds its public
    half. That is the set comparison this function performs -- over the emitted
    compose mounts, the emitted provider plan and the emitted JWKS document,
    never over a key a gate minted for itself.

    Args:
        project_dir: The generated project root.
        demanded_roles: The Datrix roles the token must carry.

    Returns:
        The non-secret facts :func:`mint_bearer_token` needs.

    Raises:
        EmittedArtifactDefect: If the emitted project provisions no private key,
            ships no provider plan, or names no provider whose JWKS holds the
            provisioned key. Every one of those leaves a gate unable to
            exercise an authenticated route, which is the vacuous run it exists
            to prevent.
    """
    mounts = compose_bind_mounts(project_dir)
    keys = [host for _, host, target in mounts if Path(target).name == JWT_PRIVATE_KEY_HANDLE]
    if not keys:
        raise EmittedArtifactDefect(
            f"The compose file in {project_dir} mounts no {JWT_PRIVATE_KEY_HANDLE!r} secret, so "
            f"there is no provisioned key to sign a bearer token with and every authenticated "
            f"route would go unexercised. Expected a bind mount whose container path is named "
            f"after the framework's provisioned signing-key handle. Fix: generate a fixture whose "
            f"services declare authentication, so the runtime provisions the key pair -- never by "
            f"minting a key pair in a gate, which the running services would reject."
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
            f"{type(loaded).__name__}, which cannot be matched against a JWKS entry here. "
            f"Expected an RSA private key. Fix: teach the gate the emitted key type rather "
            f"than substituting signing material of its own."
        )
    plan_files = [host for _, host, target in mounts if target == LOCAL_IDENTITY_PROVIDER_PLAN_PATH]
    if not plan_files or not plan_files[0].is_file():
        raise EmittedArtifactDefect(
            f"The compose file in {project_dir} mounts no identity provider plan at "
            f"{LOCAL_IDENTITY_PROVIDER_PLAN_PATH!r}, so no issuer can be resolved to sign for and "
            f"every authenticated route would go unexercised. Expected the emitted plan the "
            f"services validate tokens against."
        )
    plan_file = plan_files[0]
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    providers = plan.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise EmittedArtifactDefect(
            f"The identity provider plan at {plan_file} declares no providers, so no token a "
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
            for jwk in document["keys"]  # type: ignore[union-attr]
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
            roles=_required_roles(demanded_roles, provider),
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
        f"second key pair in a gate, injecting a public key as a secret, or falling back to "
        f"calling the routes unauthenticated."
    )


def mint_bearer_token(issuance: TokenIssuance, subject: str) -> str:
    """Sign a short-lived bearer token with the stack's own provisioned private key.

    The returned value is a credential: callers hold it in memory or write it
    straight to a file a harness reads, and never log it, echo it into a
    process argument list, or store it on a dataclass.

    Args:
        issuance: The non-secret facts :func:`plan_token_issuance` resolved.
        subject: The ``sub`` claim -- the identity the token speaks for.
    """
    now = datetime.datetime.now(datetime.UTC)
    claims: dict[str, object] = {
        "sub": subject,
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

    Raises:
        RuntimeError: If any name the compose file claims is already taken.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    claimed = {
        str(service["container_name"]): name
        for name, service in compose_services(project_dir).items()
        if service.get("container_name")
    }
    listed = run_command(
        ["docker", "ps", "--all", "--format", "{{.Names}}"],
        cwd=project_dir,
        timeout_seconds=DOCKER_QUERY_TIMEOUT_SECONDS,
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
        owner = run_command(
            [
                "docker",
                "inspect",
                container,
                "--format",
                '{{index .Config.Labels "com.docker.compose.project"}}',
            ],
            cwd=project_dir,
            timeout_seconds=DOCKER_QUERY_TIMEOUT_SECONDS,
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


def fixed_host_port_of(mapping: str) -> str | None:
    """The literal host port a compose short-syntax port mapping fixes, if it fixes one.

    ``"C"`` and ``"IP::C"`` publish on an ephemeral port and ``"${VAR:-H}:C"``
    on an overridable one -- none of those can be claimed ahead of time. ``"H:C"``
    and ``"IP:H:C"`` (``127.0.0.1:29092:29092``) fix ``H``. The host port is the
    second-to-last ``:`` segment of the mapping, whatever precedes it.
    """
    segments = mapping.split("/", 1)[0].split(":")
    if len(segments) < 2:
        return None
    host_port = segments[-2].strip()
    return host_port if host_port.isdigit() else None


def assert_fixed_host_ports_are_free(project_dir: Path) -> None:
    """Compare the host ports the emitted compose file fixes against the ones already bound.

    Most published ports in a generated compose file are ephemeral or drawn
    from an environment substitution, and neither can collide. A port written
    as a literal on the host side can, and like a container name it is claimed
    from a namespace the whole machine shares. Finding that out from
    ``docker compose up`` costs an image build first, so the comparison happens
    here and names the holder.

    Raises:
        RuntimeError: If any host port the compose file fixes is already bound.
    """
    compose_file = project_dir / COMPOSE_FILENAME
    claimed: dict[str, str] = {}
    for name, service in compose_services(project_dir).items():
        for mapping in service.get("ports") or []:
            host_port = fixed_host_port_of(str(mapping))
            if host_port is not None:
                claimed[host_port] = name
    if not claimed:
        return
    listed = run_command(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"],
        cwd=project_dir,
        timeout_seconds=DOCKER_QUERY_TIMEOUT_SECONDS,
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


def boot_stack(project_dir: Path, compose_env: dict[str, str]) -> None:
    """Boot the generated stack through its own deployment front door, then gate on health.

    The generated project ships the deployment CLI that knows what compose
    alone cannot do for it -- most concretely, building the shared per-system
    base image every service's Dockerfile is a thin layer on, which compose
    will otherwise try to pull from a registry that has never heard of it.
    Reimplementing that here would be a second, silently drifting copy of the
    emitted deployment, so the emitted one runs, addressed by the lifecycle
    verb every Datrix deployment CLI shares.

    Not every target emits that CLI -- a project whose services need nothing
    built outside compose ships none -- so its absence is a different emitted
    shape rather than an error, and it is logged so a run never leaves which
    path it took to inference.

    Whichever path built the stack, one idempotent ``up -d --build`` brings
    every service up, and :func:`wait_until_settled` then gates on every
    container reaching its settled state. ``up --wait`` cannot be that gate:
    it reports a one-shot container that nothing depends on (a broker
    configuration check) as a failure the moment it completes successfully.

    Raises:
        RuntimeError: If the deployment fails, or the stack never settles.
    """
    deploy_script = project_dir / DEPLOY_SCRIPT_RELATIVE
    if deploy_script.is_file():
        deployed = run_command(
            [sys.executable, str(deploy_script), VERB_DEPLOY],
            cwd=project_dir,
            timeout_seconds=DOCKER_UP_TIMEOUT_SECONDS,
            env_overrides=compose_env,
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
    started = run_command(
        ["docker", "compose", "up", "-d", "--build"],
        cwd=project_dir,
        timeout_seconds=DOCKER_UP_TIMEOUT_SECONDS,
        env_overrides=compose_env,
    )
    if started.returncode != 0:
        raise RuntimeError(
            f"The stack at {project_dir} could not be started ('docker compose up -d --build' "
            f"exited {started.returncode}).\n{started.stdout}\n{started.stderr}"
        )
    wait_until_settled(project_dir, compose_env)


#: How long a booted stack may take for every container to settle, and how
#: often its container states are read while it does.
STACK_SETTLE_TIMEOUT_SECONDS: Final[int] = 900
_STACK_SETTLE_POLL_SECONDS: Final[float] = 5.0
_STATE_RUNNING: Final[str] = "running"
_STATE_EXITED: Final[str] = "exited"
_HEALTH_HEALTHY: Final[str] = "healthy"
_HEALTH_UNHEALTHY: Final[str] = "unhealthy"
_NO_HEALTHCHECK: Final[str] = ""


def _container_states(project_dir: Path, compose_env: dict[str, str]) -> list[dict[str, object]]:
    """Every container of the project with its state, health and exit code.

    Raises:
        RuntimeError: If compose cannot report them.
    """
    listed = run_command(
        ["docker", "compose", "ps", "--all", "--format", "json"],
        cwd=project_dir,
        timeout_seconds=DOCKER_QUERY_TIMEOUT_SECONDS,
        env_overrides=compose_env,
    )
    if listed.returncode != 0:
        raise RuntimeError(
            f"'docker compose ps' exited {listed.returncode} for {project_dir}.\n{listed.stdout}\n{listed.stderr}"
        )
    states: list[dict[str, object]] = []
    for line in listed.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            entry = json.loads(line)
            if isinstance(entry, dict):
                states.append(entry)
    return states


def settled_state_problems(states: Sequence[dict[str, object]]) -> tuple[list[str], list[str]]:
    """Split container states into failures and containers still settling.

    A container is settled when it runs and is healthy (or declares no
    healthcheck), or when it exited 0 -- a one-shot that did its job. A
    container that exited non-zero or reports unhealthy has FAILED; nothing
    else is waited on forever.

    Returns:
        ``(failed, pending)`` descriptions, each naming the service and its state.
    """
    failed: list[str] = []
    pending: list[str] = []
    for entry in states:
        name = str(entry["Service"])
        state = str(entry["State"])
        health = str(entry["Health"])
        exit_code = int(str(entry["ExitCode"]))
        if state == _STATE_EXITED:
            if exit_code != 0:
                failed.append(f"{name} exited {exit_code}")
            continue
        if health == _HEALTH_UNHEALTHY:
            failed.append(f"{name} is unhealthy")
        elif state != _STATE_RUNNING or health not in (_HEALTH_HEALTHY, _NO_HEALTHCHECK):
            pending.append(f"{name} ({state}, health {health or 'none'})")
    return failed, pending


def wait_until_settled(project_dir: Path, compose_env: dict[str, str]) -> None:
    """Gate on every container of a started stack settling, failing on the first failure.

    Raises:
        RuntimeError: If a container exits non-zero or turns unhealthy (naming
            it, with its log tail), or the stack has not settled in time.
    """
    deadline = time.monotonic() + STACK_SETTLE_TIMEOUT_SECONDS
    while True:
        states = _container_states(project_dir, compose_env)
        failed, pending = settled_state_problems(states)
        if failed:
            logs = run_command(
                ["docker", "compose", "logs", "--no-color", "--tail", "80"],
                cwd=project_dir,
                timeout_seconds=DOCKER_QUERY_TIMEOUT_SECONDS,
                env_overrides=compose_env,
            )
            raise RuntimeError(
                f"The stack at {project_dir} failed to settle: {'; '.join(failed)}.\n{logs.stdout[-20000:]}"
            )
        if not pending and states:
            logger.info("%s settled: %d container(s) running or completed", project_dir.name, len(states))
            return
        if time.monotonic() > deadline:
            raise RuntimeError(
                f"The stack at {project_dir} did not settle within {STACK_SETTLE_TIMEOUT_SECONDS}s; "
                f"still pending: {'; '.join(pending) or 'no containers listed'}."
            )
        time.sleep(_STACK_SETTLE_POLL_SECONDS)


def stop_stack(project_dir: Path, compose_env: dict[str, str]) -> bool:
    """Tear the stack down, volumes included. Never raises: it runs where a real result exists.

    Returns:
        Whether the teardown command succeeded; a failure is logged with its
        output so a leaked stack is never silent.
    """
    result = run_command(
        ["docker", "compose", "down", "-v", "--remove-orphans"],
        cwd=project_dir,
        timeout_seconds=DOCKER_DOWN_TIMEOUT_SECONDS,
        env_overrides=compose_env,
    )
    if result.returncode != 0:
        logger.warning(
            "Tearing down the stack at %s exited %d; the gate result above stands.\n%s\n%s",
            project_dir,
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return False
    return True
