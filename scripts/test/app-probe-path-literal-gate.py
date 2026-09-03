#!/usr/bin/env python3
"""Application probe-path literal gate: no platform package may hardcode a route
a language declares as its readiness or liveness probe.

The route a traffic-routing probe consults (a Compose ``healthcheck``, an ECS
or App Runner health check, an ALB/NLB target-group health check, a Front Door
origin probe, an App Service health monitor) is a route the LANGUAGE's
generated application mounts. Each registered language declares its two
routes on ``LanguageRuntimeSpec`` (``readiness_probe_path`` and
``app_service_liveness_probe_path``) and every platform reads them from the
resolved plugin. A platform package that spells one of those routes as a
string literal has assumed a route on the language's behalf -- the shape that
once left one registered language probed at a 404 on three platforms, because
its controller never mounted the ``/ready`` every platform had assumed.

What the gate does, every run:

1. Discovers the platform packages from disk: every ``datrix-*/pyproject.toml``
   registering a ``datrix.platforms`` entry point (``tomllib``, no installed
   environment needed for discovery).
2. Collects the declared probe routes from the INSTALLED language plugins:
   every ``datrix.languages`` entry point's ``runtime_spec`` answers
   ``readiness_probe_path()`` and ``app_service_liveness_probe_path()``.
3. Scans each platform package's ``src/`` tree -- Python string constants
   (``ast``, docstrings excluded) and quoted literals in ``.j2`` templates
   (comment lines excluded) -- for any literal equal to a declared route.
4. Fails on any hit not covered by a reviewed exemption in
   ``datrix/scripts/config/app-probe-path-exemptions.json`` (file + exact
   snippet + reason; ``expected_count`` must equal the entry count; an entry
   whose snippet no longer matches a hit is stale and fails the gate).

Non-vacuity, before the real scan:

- A planted platform package carrying a declared route in code, in a
  docstring, in a template code line and in a template comment line yields
  exactly the two code hits; a clean planted package yields none.
- The scanner run over the LANGUAGE packages' own ``src/`` trees finds every
  declared route at least once -- the matcher is proven against the real
  literals the languages mount, not only against fixtures.
- Fewer than two discovered platform packages or fewer than two registered
  languages is a refusal, never a vacuous pass.

Exit codes:
    0: No unexempted hit (or a successful --self-test run).
    1: At least one unexempted or stale-exempted hit.
    2: Usage error, too few packages/languages, or the self-test failed.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

PLATFORMS_ENTRY_POINT_GROUP = "datrix.platforms"
LANGUAGES_ENTRY_POINT_GROUP = "datrix.languages"
EXEMPTIONS_RELATIVE_PATH = Path("datrix") / "scripts" / "config" / "app-probe-path-exemptions.json"
MIN_PLATFORM_PACKAGES = 2
MIN_LANGUAGES = 2
TEMPLATE_SUFFIX = ".j2"
TEMPLATE_COMMENT_PREFIXES: tuple[str, ...] = ("#", "//", "{#", "*", "--", "<!--", "/*")
# A character that would CONTINUE a path: a route followed by one of these is
# a longer path (``/health/circuits`` is not ``/health``), anything else ends it.
_PATH_CONTINUATION = re.compile(r"[A-Za-z0-9_.\-/]")
# A path-segment character: the run of these immediately BEFORE a route decides
# whether the route is a whole path or the tail of a longer one (see
# ``_starts_a_path``).
_SEGMENT_CHAR = re.compile(r"[A-Za-z0-9_.\-]")
_SCHEME_SEPARATOR = "://"

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


class GateError(Exception):
    """A gate-level failure (usage, discovery, or self-test)."""


@dataclass(frozen=True)
class PackageSrc:
    distribution: str
    src_dir: Path


@dataclass(frozen=True)
class Hit:
    file: Path
    line: int
    literal: str
    #: Last source line of the matched constant. A Python string built by
    #: implicit concatenation spans several lines; the exemption snippet may
    #: sit on any of them.
    end_line: int

    def relative_to(self, base_dir: Path) -> str:
        return self.file.relative_to(base_dir).as_posix()


@dataclass(frozen=True)
class Exemption:
    file: str
    snippet: str
    reason: str


def _ok(message: str) -> None:
    print(f"{GREEN}[OK]{RESET} {message}")


def _fail(message: str) -> None:
    print(f"{RED}[FAIL]{RESET} {message}")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _manifest_registers_group(manifest: dict[str, object], group: str) -> bool:
    project = manifest.get("project")
    if not isinstance(project, dict):
        return False
    groups = project.get("entry-points")
    return isinstance(groups, dict) and group in groups


def _first_import_root(manifest: dict[str, object], group: str) -> str:
    project = manifest["project"]
    assert isinstance(project, dict)
    groups = project["entry-points"]
    assert isinstance(groups, dict)
    entries = groups[group]
    assert isinstance(entries, dict)
    first_target = next(iter(entries.values()))
    assert isinstance(first_target, str)
    return first_target.split(":", 1)[0].split(".", 1)[0]


def discover_packages_registering(base_dir: Path, group: str) -> list[PackageSrc]:
    """Every ``datrix-*`` package on disk whose manifest registers *group*."""
    found: list[PackageSrc] = []
    for pyproject in sorted(base_dir.glob("datrix-*/pyproject.toml")):
        manifest = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        if not _manifest_registers_group(manifest, group):
            continue
        import_root = _first_import_root(manifest, group)
        src_dir = pyproject.parent / "src" / import_root
        if not src_dir.is_dir():
            raise GateError(
                f"{pyproject.parent.name} registers {group} under import root "
                f"{import_root!r} but {src_dir} does not exist."
            )
        found.append(PackageSrc(distribution=pyproject.parent.name, src_dir=src_dir))
    return found


def declared_probe_routes() -> dict[str, frozenset[str]]:
    """Registered language name -> the probe routes its runtime spec declares."""
    from datrix_common.generation.language_runtime_spec import (
        discover_language_runtime_spec,
    )
    from datrix_common.plugin.identity import LanguageId

    routes: dict[str, frozenset[str]] = {}
    for entry in entry_points(group=LANGUAGES_ENTRY_POINT_GROUP):
        spec = discover_language_runtime_spec(LanguageId(entry.name))
        declared = frozenset({spec.readiness_probe_path(), spec.app_service_liveness_probe_path()})
        for route in declared:
            if not route.startswith("/"):
                raise GateError(
                    f"Language {entry.name!r} declares probe route {route!r}, which is "
                    "not an absolute HTTP route."
                )
        routes[entry.name] = declared
    return routes


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """``id()`` of every Constant node that is a docstring."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    return docstrings


def _starts_a_path(text: str, index: int) -> bool:
    """Whether the route at *index* is the whole path, not the tail of one.

    Walk back over the segment characters immediately before the route. If
    that run is preceded by a ``/`` that is not the ``://`` of a URL scheme,
    the route hangs off an earlier path segment (``/_cluster/health``,
    ``/minio/health/live``, ``/api/health``) and is a different route. A run
    preceded by anything else -- a port (``localhost:8000/ready``), a scheme
    (``http://localhost/ready``), a quote, a brace, whitespace -- is a host or
    a bare literal, and the route is the path.
    """
    run_start = index
    while run_start > 0 and _SEGMENT_CHAR.match(text[run_start - 1]):
        run_start -= 1
    if run_start == 0 or text[run_start - 1] != "/":
        return True
    return text[:run_start].endswith(_SCHEME_SEPARATOR)


def route_occurrences(text: str, routes: frozenset[str]) -> list[str]:
    """Every declared route that occurs in *text* as a whole path.

    The match is a substring match, deliberately: the defect this gate exists
    for was a route embedded in a longer string
    (``f"curl -f http://localhost:{port}/ready || exit 1"``), which an
    equality check on the whole constant would never see. A route followed by
    a path-continuation character, or hanging off an earlier path segment, is
    a longer path and not the route.
    """
    found: list[str] = []
    for route in sorted(routes):
        start = 0
        while True:
            index = text.find(route, start)
            if index < 0:
                break
            end = index + len(route)
            ends_here = end >= len(text) or not _PATH_CONTINUATION.match(text[end])
            if ends_here and _starts_a_path(text, index):
                found.append(route)
                break
            start = end
    return found


def scan_python_file(path: Path, routes: frozenset[str]) -> list[Hit]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        end_line = node.end_lineno if node.end_lineno is not None else node.lineno
        for literal in route_occurrences(node.value, routes):
            hits.append(Hit(file=path, line=node.lineno, literal=literal, end_line=end_line))
    return hits


def scan_template_file(path: Path, routes: frozenset[str]) -> list[Hit]:
    hits: list[Hit] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(TEMPLATE_COMMENT_PREFIXES):
            continue
        for literal in route_occurrences(line, routes):
            hits.append(Hit(file=path, line=line_number, literal=literal, end_line=line_number))
    return hits


def scan_src_tree(src_dir: Path, routes: frozenset[str], *, verbose: bool = False) -> list[Hit]:
    hits: list[Hit] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix == ".py":
            if verbose:
                print(f"  scanning {path}")
            hits.extend(scan_python_file(path, routes))
        elif path.suffix == TEMPLATE_SUFFIX:
            if verbose:
                print(f"  scanning {path}")
            hits.extend(scan_template_file(path, routes))
    return hits


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------


def load_exemptions(path: Path) -> list[Exemption]:
    if not path.is_file():
        raise GateError(f"Exemptions file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    expected_count = data.get("expected_count")
    if not isinstance(entries, list) or not isinstance(expected_count, int):
        raise GateError(f"{path}: expected 'exemptions' (list) and 'expected_count' (int).")
    if expected_count != len(entries):
        raise GateError(
            f"{path}: expected_count={expected_count} but {len(entries)} entries are listed; "
            "remediation removes the entry AND decrements the count in the same change."
        )
    exemptions: list[Exemption] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise GateError(f"{path}: every exemption must be an object, got {entry!r}.")
        for key in ("file", "snippet", "reason"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise GateError(f"{path}: exemption {entry!r} is missing a non-empty {key!r}.")
        exemptions.append(Exemption(file=entry["file"], snippet=entry["snippet"], reason=entry["reason"]))
    return exemptions


def _hit_line_text(hit: Hit) -> str:
    """The stripped source text of the matched constant, all of its lines."""
    lines = hit.file.read_text(encoding="utf-8").splitlines()[hit.line - 1 : hit.end_line]
    return "\n".join(line.strip() for line in lines)


def apply_exemptions(
    hits: list[Hit], exemptions: list[Exemption], base_dir: Path
) -> tuple[list[Hit], list[Exemption]]:
    """Return (unexempted hits, stale exemptions matching no hit)."""
    remaining: list[Hit] = []
    used: set[int] = set()
    for hit in hits:
        relative = hit.relative_to(base_dir)
        line_text = _hit_line_text(hit)
        covered = False
        for index, exemption in enumerate(exemptions):
            if exemption.file == relative and exemption.snippet in line_text:
                used.add(index)
                covered = True
                break
        if not covered:
            remaining.append(hit)
    stale = [exemption for index, exemption in enumerate(exemptions) if index not in used]
    return remaining, stale


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _plant_platform_package(root: Path, name: str, *, planted: bool, route: str) -> None:
    import_root = name.replace("-", "_")
    _write(
        root / name / "pyproject.toml",
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0.0.0"\n'
        f'[project.entry-points."{PLATFORMS_ENTRY_POINT_GROUP}"]\n'
        f'{name} = "{import_root}.plugin:PLUGIN"\n',
    )
    if planted:
        _write(
            root / name / "src" / import_root / "probe.py",
            '"""Module docstring mentioning ' + route + ' must not count."""\n'
            "\n"
            "\n"
            "def probe_url(port: int) -> str:\n"
            '    """Function docstring mentioning ' + route + ' must not count."""\n'
            f'    return f"http://localhost:{{port}}{route}"\n'
            "\n"
            "\n"
            f'PROBE_PATH = "{route}"\n'
            f'SHELL_CHECK = f"curl -f http://localhost:{{port}}{route} || exit 1"\n'
            f'LONGER_PATH = "{route}/sub-resource"\n'
            f'INFRA_PATH = "http://localhost:9200/_cluster{route}"\n'
            f'NO_PORT_URL = "http://localhost{route}"\n',
        )
        _write(
            root / name / "src" / import_root / "compose.yml.j2",
            f"// a comment mentioning '{route}' must not count\n"
            f"healthcheck: curl -f http://localhost:8000{route}\n"
            f"probe_path: '{route}'\n"
            f"other_path: '{route}extra'\n"
            f"infra_path: '/minio{route}/live'\n",
        )
    else:
        _write(
            root / name / "src" / import_root / "clean.py",
            '"""Clean module."""\n\nVALUE = "/not-a-probe-route"\n',
        )


def run_self_test(base_dir: Path, routes_by_language: dict[str, frozenset[str]]) -> bool:
    ok = True
    all_routes = frozenset().union(*routes_by_language.values())
    sample_route = sorted(all_routes)[0]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant_platform_package(root, "datrix-selftest-planted", planted=True, route=sample_route)
        _plant_platform_package(root, "datrix-selftest-clean", planted=False, route=sample_route)
        packages = discover_packages_registering(root, PLATFORMS_ENTRY_POINT_GROUP)
        if [p.distribution for p in packages] == ["datrix-selftest-clean", "datrix-selftest-planted"]:
            _ok("discovery finds every planted platform package from its manifest")
        else:
            _fail(f"discovery returned {[p.distribution for p in packages]}")
            ok = False
        planted_hits = scan_src_tree(root / "datrix-selftest-planted" / "src", all_routes)
        literals = sorted((h.file.name, h.line) for h in planted_hits)
        expected = [
            ("compose.yml.j2", 2),
            ("compose.yml.j2", 3),
            ("probe.py", 6),
            ("probe.py", 9),
            ("probe.py", 10),
            ("probe.py", 13),
        ]
        if literals == expected:
            _ok(
                "planted literals (bare constant, f-string part, route embedded in a "
                "shell command, scheme-only URL, quoted and unquoted template lines) are "
                "reported; docstrings, template comments, longer paths sharing the prefix "
                "and routes hanging off an earlier segment are not"
            )
        else:
            _fail(f"planted package yielded {literals}, expected {expected}")
            ok = False
        clean_hits = scan_src_tree(root / "datrix-selftest-clean" / "src", all_routes)
        if not clean_hits:
            _ok("clean planted package yields zero hits")
        else:
            _fail(f"clean package yielded {clean_hits}")
            ok = False
        try:
            _require_enough(packages[:1], routes_by_language)
        except GateError:
            _ok("fewer than two platform packages is refused, never a silent pass")
        else:
            _fail("a single platform package was accepted")
            ok = False

    # Live non-vacuity: the languages' own src trees carry every declared route.
    language_packages = discover_packages_registering(base_dir, LANGUAGES_ENTRY_POINT_GROUP)
    seen: set[str] = set()
    for package in language_packages:
        seen.update(hit.literal for hit in scan_src_tree(package.src_dir, all_routes))
    missing = sorted(all_routes - seen)
    if not missing:
        _ok(f"live scan of the language packages finds every declared route {sorted(all_routes)}")
    else:
        _fail(f"declared routes {missing} were not found in any language package src tree")
        ok = False
    return ok


def _require_enough(
    platform_packages: list[PackageSrc], routes_by_language: dict[str, frozenset[str]]
) -> None:
    if len(platform_packages) < MIN_PLATFORM_PACKAGES:
        raise GateError(
            f"Discovered {len(platform_packages)} platform package(s); at least "
            f"{MIN_PLATFORM_PACKAGES} are required for a non-vacuous scan."
        )
    if len(routes_by_language) < MIN_LANGUAGES:
        raise GateError(
            f"Discovered {len(routes_by_language)} registered language(s); at least "
            f"{MIN_LANGUAGES} are required for a non-vacuous scan."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _detect_base_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    base_dir = (args.base_dir or _detect_base_dir()).resolve()

    try:
        routes_by_language = declared_probe_routes()
        platform_packages = discover_packages_registering(base_dir, PLATFORMS_ENTRY_POINT_GROUP)
        _require_enough(platform_packages, routes_by_language)
        if not run_self_test(base_dir, routes_by_language):
            print(f"{RED}SELF-TEST FAILED{RESET}")
            return 2
        print(f"{GREEN}SELF-TEST PASSED{RESET}")
        if args.self_test:
            return 0

        all_routes = frozenset().union(*routes_by_language.values())
        for language, routes in sorted(routes_by_language.items()):
            print(f"INFO: language={language} declared_probe_routes={sorted(routes)}")
        hits: list[Hit] = []
        for package in platform_packages:
            package_hits = scan_src_tree(package.src_dir, all_routes, verbose=args.verbose)
            print(f"INFO: package={package.distribution} literal_hits={len(package_hits)}")
            hits.extend(package_hits)
        exemptions = load_exemptions(base_dir / EXEMPTIONS_RELATIVE_PATH)
        unexempted, stale = apply_exemptions(hits, exemptions, base_dir)
    except GateError as error:
        print(f"{RED}ERROR{RESET}: {error}", file=sys.stderr)
        return 2

    for hit in unexempted:
        _fail(
            f"{hit.relative_to(base_dir)}:{hit.line} hardcodes probe route {hit.literal!r}; "
            "read LanguageRuntimeSpec.readiness_probe_path() / "
            "app_service_liveness_probe_path() from the resolved language plugin instead."
        )
    for exemption in stale:
        _fail(f"stale exemption: {exemption.file} no longer carries snippet {exemption.snippet!r}")
    print(
        f"APP PROBE-PATH LITERAL REPORT: {len(platform_packages)} platform package(s) scanned, "
        f"{len(hits)} literal(s) found, {len(exemptions) - len(stale)} exempted, "
        f"{len(unexempted)} violation(s), {len(stale)} stale exemption(s)."
    )
    if unexempted or stale:
        return 1
    print(f"{GREEN}App probe-path literal gate passed{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
