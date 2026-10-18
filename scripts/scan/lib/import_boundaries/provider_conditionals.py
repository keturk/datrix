"""Provider-conditional and shared-package provider-literal scanners and their ratchets."""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.registered_targets import (
    registered_platform_names,
)
from import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_SCRIPT,
    PackageInfo,
    _check,
    _self_test_write_manifest,
    self_test_check,
    tighten_only_messages,
    write_count_baseline,
)
from import_boundaries.taxonomy import LANGUAGES_ENTRY_POINT_GROUP

# Root name(s) recognized as "the deployment/infrastructure provider" for the
# `.value`/`str(...)` detection forms below. Restricting to these roots (a
# bare `deployment` variable, or `self._deployment` / `self.deployment`) is
# what separates a genuine deployment-provider comparison from the many OTHER
# provider axes in the same files (StorageProvider, EmailProvider, SmsProvider,
# SearchProvider, PaymentProvider, metrics/tracing provider) which all reach
# their own `.provider` off a *different* config object (e.g. `cfg.provider`,
# `email_config.provider`, `metrics_config.provider`) and must NOT ratchet here.
_DEPLOYMENT_ROOT_ATTRS: frozenset[str] = frozenset({"deployment", "_deployment"})


def _is_providerid_call(node: ast.AST) -> bool:
    """True if *node* is a call to the ``ProviderId`` constructor (bare or
    module-qualified), e.g. ``ProviderId("azure")`` or ``identity.ProviderId(x)``.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "ProviderId"
    if isinstance(func, ast.Attribute):
        return func.attr == "ProviderId"
    return False


def _is_deployment_root(node: ast.AST) -> bool:
    """True if *node* is the deployment-config object itself: a bare
    ``deployment`` name, or an attribute access ending in ``deployment``/
    ``_deployment`` (e.g. ``self._deployment``, ``self.deployment``).
    """
    if isinstance(node, ast.Name):
        return node.id in _DEPLOYMENT_ROOT_ATTRS
    if isinstance(node, ast.Attribute):
        return node.attr in _DEPLOYMENT_ROOT_ATTRS
    return False


def _is_deployment_provider_attr(node: ast.AST) -> bool:
    """True if *node* is ``<deployment-root>.provider`` (the raw provider
    field read off the deployment config, before any ``.value``/``str()``).
    """
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "provider"
        and _is_deployment_root(node.value)
    )


def _is_deployment_provider_value_expr(node: ast.AST) -> bool:
    """True if *node* stringifies the DEPLOYMENT provider specifically --
    ``<deployment-root>.provider.value`` or ``str(<deployment-root>.provider)``
    (including the redundant ``str(<deployment-root>.provider.value)`` form).
    Deliberately narrower than "any `.provider.value`" so the many other
    provider axes (storage/email/sms/search/payment/metrics/tracing) --
    which share the `.provider`/`.value` shape but hang off a *different*
    config object -- never match (see ``_DEPLOYMENT_ROOT_ATTRS``).
    """
    if isinstance(node, ast.Attribute) and node.attr == "value":
        return _is_deployment_provider_attr(node.value)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
    ):
        arg = node.args[0]
        return _is_deployment_provider_attr(arg) or _is_deployment_provider_value_expr(
            arg
        )
    return False


def _provider_conditional_compare_kind(
    node: ast.Compare,
) -> Literal["providerid_compare", "deployment_provider_value_compare"] | None:
    """Classify a single ``ast.Compare`` node as a provider-conditional hit,
    or ``None`` if it isn't one.

    Only simple binary comparisons (exactly one operator) are considered --
    chained comparisons (``a == b == c``) are not a shape this ratchet's
    known sites use. Two forms match, checked against BOTH sides of the
    comparison:

      - ``providerid_compare``: either side is a call to ``ProviderId(...)``
        (covers ``== ProviderId(...)``, ``ProviderId(...) ==``, ``!=
        ProviderId(...)``, and a ``match``/``case`` guard's ``p ==
        ProviderId("aws")`` -- ``ProviderId`` names exactly ONE axis
        (deployment/infrastructure provider identity), so no other-axis
        exclusion is needed for this form).
      - ``deployment_provider_value_compare``: either side stringifies the
        deployment provider specifically (``_is_deployment_provider_value_expr``),
        covering ``deployment.provider.value == "..."`` and
        ``str(self._deployment.provider) != "aws"``.

    Only Eq/NotEq operators count (``==``/``!=``) -- an ``in``/``not in``
    membership test (e.g. a dict-dispatch-table lookup) is a different
    successor shape not yet in this ratchet's scope.
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return None

    sides = [node.left, node.comparators[0]]

    if any(_is_providerid_call(side) for side in sides):
        return "providerid_compare"
    if any(_is_deployment_provider_value_expr(side) for side in sides):
        return "deployment_provider_value_compare"
    return None


def _match_subject_is_provider(subject: ast.AST) -> bool:
    """True if a ``match`` statement's subject expression names a provider
    identity (e.g. ``match provider_id:``) -- a bare ``Name`` or the ``attr``
    of an ``Attribute`` chain whose final segment contains "provider"
    (case-insensitive).
    """
    if isinstance(subject, ast.Name):
        return "provider" in subject.id.lower()
    if isinstance(subject, ast.Attribute):
        return "provider" in subject.attr.lower()
    return False


def _string_literal_value(node: ast.AST) -> str | None:
    """Bare string-literal value of *node*, or None for any other expression
    shape (a Name, an f-string, a call, ...). Both D5 sub-patterns below only
    fire on an ACTUAL literal, never a variable that merely happens to be
    assigned a provider-id string elsewhere -- that keeps the ratchet
    precise (see ``_provider_literal_compare_kind``'s docstring for why a
    look-alike like ``"consul"`` must never match).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _provider_literal_compare_kind(
    node: ast.Compare, provider_ids: frozenset[str]
) -> Literal["provider_literal_compare"] | None:
    """D5's first provider-literal sub-pattern (invariant I6 successor,
    second AST pattern class): a plain Eq/NotEq comparison whose comparand
    (either side) is a bare string literal exactly equal to a REGISTERED
    platform provider id -- e.g. ``backend == "azure"``. This is the
    successor form the existing ``_provider_conditional_compare_kind`` does
    not cover: no ``ProviderId(...)`` wrapper, no ``.provider`` root, just a
    plain variable compared to a plain provider-name string.

    Only called for a Compare node the FIRST (ProviderId-shaped) pattern
    already rejected -- see ``_walk_for_provider_conditionals`` -- so the two
    never double-count the same node.

    Specificity comes entirely from membership in *provider_ids* (enumerated
    from the installed ``datrix.platforms`` entry points at scan time, never
    hardcoded): a literal equal to some OTHER string -- e.g. ``"consul"``, a
    service-discovery type, or ``"elasticsearch"``, a search backend -- never
    matches, however provider-adjacent the surrounding code looks.

    Args:
        node: The `ast.Compare` node under consideration.
        provider_ids: The registered platform provider ids for this scan run.

    Returns:
        ``"provider_literal_compare"`` on a match, else ``None``.
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return None
    sides = [node.left, node.comparators[0]]
    if any(_string_literal_value(side) in provider_ids for side in sides):
        return "provider_literal_compare"
    return None


def _provider_literal_container_ids(
    node: ast.AST, provider_ids: frozenset[str]
) -> frozenset[str]:
    """Provider ids among a List/Tuple/Set literal's OWN elements (D5's
    second provider-literal sub-pattern).

    Catches a closed-world provider-id collection literal wherever it is
    DEFINED -- ``frozenset({"azure"})``, ``{"aws", "azure"}``,
    ``("aws", "azure")`` -- not only when it sits directly inside a
    ``Compare``/``in`` test. A module-level
    ``_ALWAYS_REQUIRES_CREDENTIALS = frozenset({"azure"})`` is a
    collection-literal DEFINITION; a later ``backend in
    _ALWAYS_REQUIRES_CREDENTIALS`` membership test (a different line) compares
    against a bare ``Name``, which a Compare-only scan would never resolve
    back to the literal. Scanning every qualifying collection literal as its
    own node -- independent of its parent -- closes that gap.

    CLOSED-WORLD requirement (the precision fix a real scan run surfaced):
    every string-literal element of the collection must ITSELF be a
    registered provider id, not merely at-least-one. A collection that mixes
    a provider id with an OTHER axis's own literal -- e.g.
    ``SUPPORTED_STORAGE_PROVIDERS = frozenset({"s3", "minio", "azure_blob",
    "local"})`` in a language package's storage generator -- is that
    StorageProvider axis's own closed
    world (``s3``/``minio``/``azure_blob`` are never registered platform
    provider ids), not a platform-identity collection; "local" landing in it
    is coincidental token overlap, not a deployment-platform conditional, and
    must not ratchet. A genuine platform-identity collection (like
    ``_ALWAYS_REQUIRES_CREDENTIALS`` above) is drawn ENTIRELY from
    ``provider_ids`` with no off-axis sibling literal, so the subset check
    below distinguishes the two without any axis-name heuristic.

    Args:
        node: Any AST node; only `ast.List`/`ast.Tuple`/`ast.Set` produce hits.
        provider_ids: The registered platform provider ids for this scan run.

    Returns:
        *node*'s string-literal elements when they are a non-empty subset of
        *provider_ids* (i.e. closed-world), else an empty frozenset.
    """
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return frozenset()
    string_literals = frozenset(
        value for elt in node.elts if (value := _string_literal_value(elt)) is not None
    )
    if not string_literals or not string_literals.issubset(provider_ids):
        return frozenset()
    return string_literals


#: Every platform-identity conditional hit kind.
ProviderConditionalKind = Literal[
    "providerid_compare",
    "deployment_provider_value_compare",
    "match_case_provider_subject",
    "provider_literal_compare",
    "provider_literal_container",
]


@dataclass(frozen=True)
class ProviderConditionalHit:
    """One occurrence of a platform-identity conditional in a language-package file."""

    file_path: Path
    line_number: int
    kind: ProviderConditionalKind


def _walk_for_provider_conditionals(
    node: ast.AST,
    file_path: Path,
    hits: list[ProviderConditionalHit],
    provider_ids: frozenset[str],
) -> None:
    """Recursively walk *node* collecting ``ProviderConditionalHit``s.

    A custom walker (rather than ``ast.walk``) is required for exactly one
    reason: a ``match provider_id:`` statement is counted ONCE, as the
    ``match_case_provider_subject`` hit at the ``match`` line -- NOT once
    plus once again per ``case p if p == ProviderId(...):`` guard. Each
    ``case`` guard is itself an ``ast.Compare`` that would otherwise ALSO
    satisfy ``providerid_compare``, double-counting the same logical site.
    So when a qualifying ``ast.Match`` is found, its ``case`` guards are
    skipped while patterns and bodies are still walked normally (a guard
    is only ever the provider-identity check the match already counted;
    unrelated real conditionals inside a case body are not exempted).

    D5 second pattern class (added by this task): every ``ast.Compare`` node
    the existing ``ProviderId``-shaped pattern rejects is ALSO checked against
    ``_provider_literal_compare_kind`` (a bare literal comparand), and every
    ``ast.List``/``ast.Tuple``/``ast.Set`` node encountered anywhere in the
    walk is checked against ``_provider_literal_container_ids`` (a
    closed-world provider-id collection literal). Neither new check can
    double-count a node the first three forms already claimed, because the
    literal-compare check only runs when the ProviderId-shaped check returned
    ``None``, and the container check is a disjoint node type (a Compare node
    is never simultaneously a List/Tuple/Set node).
    """
    if isinstance(node, ast.Match):
        if _match_subject_is_provider(node.subject):
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    kind="match_case_provider_subject",
                )
            )
        for case in node.cases:
            # Deliberately skip case.guard -- see docstring above.
            for stmt in case.body:
                _walk_for_provider_conditionals(stmt, file_path, hits, provider_ids)
        return

    if isinstance(node, (ast.Compare, ast.List, ast.Tuple, ast.Set)):
        kind = _expression_conditional_kind(node, provider_ids)
        if kind is not None:
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path, line_number=node.lineno, kind=kind
                )
            )

    for child in ast.iter_child_nodes(node):
        _walk_for_provider_conditionals(child, file_path, hits, provider_ids)


def _expression_conditional_kind(
    node: ast.Compare | ast.List | ast.Tuple | ast.Set, provider_ids: frozenset[str]
) -> ProviderConditionalKind | None:
    """The hit kind of a comparison (the ``ProviderId``-shaped forms first,
    then a bare provider literal comparand) or of a closed-world provider-id
    collection literal; ``None`` when *node* is neither."""
    if isinstance(node, ast.Compare):
        compare_kind = _provider_conditional_compare_kind(node)
        if compare_kind is not None:
            return compare_kind
        return _provider_literal_compare_kind(node, provider_ids)
    if _provider_literal_container_ids(node, provider_ids):
        return "provider_literal_container"
    return None


def scan_file_for_provider_conditionals(
    file_path: Path, provider_ids: frozenset[str]
) -> list[ProviderConditionalHit]:
    """AST-walk *file_path* for platform-identity conditionals (I6 successor
    ratchet, DI-4/DI-5, plus the D5 provider-literal patterns).

    See ``_provider_conditional_compare_kind``, ``_match_subject_is_provider``,
    ``_provider_literal_compare_kind``, and ``_provider_literal_container_ids``
    for the exact matched/excluded shapes.

    Args:
        file_path: Path to Python source file.
        provider_ids: The registered platform provider ids this scan run
            checks literals against (see ``registered_platform_names()``).

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    hits: list[ProviderConditionalHit] = []
    _walk_for_provider_conditionals(tree, file_path, hits, provider_ids)
    return hits


def scan_provider_conditionals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    language_packages: tuple[str, ...],
) -> dict[Path, list[ProviderConditionalHit]]:
    """Scan every ``.py`` file under each language package's ``src/`` tree
    (via *packages*, as already discovered by ``discover_packages``) for
    platform-identity conditionals. Provider ids are derived once per call
    via ``registered_platform_names()`` -- never hardcoded -- and passed to
    every per-file scan.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        language_packages: The discovered taxonomy's language packages
            (``GeneratorTaxonomy.language_packages``).

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[ProviderConditionalHit]] = {}
    provider_ids = registered_platform_names()

    for package_name in language_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_provider_conditionals(py_file, provider_ids)
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                    f"A policed file that cannot be parsed would escape this scan "
                    f"(a silent blind spot); fix its syntax or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except (OSError, UnicodeDecodeError) as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                    f"cannot be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

            if hits:
                results[py_file] = hits

    return results


_PROVIDER_CONDITIONAL_BASELINE_HEADER = (
    "# I6 Successor Ratchet Baseline (invariant I6, DI-4/DI-5)\n"
    "#\n"
    "# Frozen per-file counts of platform-identity CONDITIONALS in the language\n"
    "# packages (datrix_codegen_python, datrix_codegen_typescript) -- the successor\n"
    "# form of the removed DeploymentProvider branches (the literal\n"
    "# `grep DeploymentProvider.` is already empty; DI-3 deleted the enum). These\n"
    "# sites are DI-5-deferred: legitimate today, but frozen so they cannot grow\n"
    "# while each cluster is migrated onto a decision engine.\n"
    "# Any INCREASE in a file's count fails datrix/scripts/scan/check-import-boundaries.ps1\n"
    "# --check-provider-conditionals. Decreases are always allowed and should be\n"
    "# captured by re-running with --update-baseline once a DI-5 change collapses a\n"
    "# cluster -- reaching 0 everywhere is the DI-5 end-state.\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
    "#   count = <int>\n"
)


def write_provider_conditional_baseline(
    baseline_path: Path, counts: dict[str, int]
) -> None:
    """Write ``counts`` to the provider-conditional baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs.

    Args:
        baseline_path: Path to the provider-conditional baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    write_count_baseline(
        baseline_path, counts, key_field="file", header=_PROVIDER_CONDITIONAL_BASELINE_HEADER
    )


def check_provider_conditional_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """One message per file whose provider-conditional count rose above its
    baseline (reaching 0 everywhere is the DI-5 goal), sorted by file path."""
    return tighten_only_messages(current_counts, baseline, "provider-conditional")


def scan_shared_package_provider_literals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    shared_packages: tuple[str, ...],
) -> dict[Path, list[ProviderConditionalHit]]:
    """Scan every ``.py`` file under each of *shared_packages*' ``src/`` tree
    for platform-identity conditionals -- REUSES
    ``scan_file_for_provider_conditionals`` (the two D5 sub-patterns plus the
    pre-existing ``ProviderId``/``match``-case forms) unmodified; only the
    package SCOPE differs from ``scan_provider_conditionals`` (which targets
    the discovered taxonomy's language packages).

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        shared_packages: The DERIVED shared-package set
            (``discover_shared_packages``) -- every discovered package
            registering none of the four taxonomy entry-point groups.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[ProviderConditionalHit]] = {}
    provider_ids = registered_platform_names()

    for package_name in shared_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_provider_conditionals(py_file, provider_ids)
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                    f"A policed file that cannot be parsed would escape this scan "
                    f"(a silent blind spot); fix its syntax or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except (OSError, UnicodeDecodeError) as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                    f"cannot be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

            if hits:
                results[py_file] = hits

    return results


def check_shared_package_provider_literals(
    hits_by_file: dict[Path, list[ProviderConditionalHit]],
    monorepo_root: Path,
) -> list[str]:
    """Return one message per hit found in a shared package -- ANY hit fails.

    Unlike ``check_provider_conditional_ratchet`` (decrease-only against a
    frozen, non-zero baseline for the language packages), this comparator
    has no baseline at all: a shared package's provider-literal count must
    be exactly zero, always. Returns an empty list only when
    ``hits_by_file`` is empty.

    Args:
        hits_by_file: Output of `scan_shared_package_provider_literals`.
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        List of human-readable failure messages, one per hit, sorted by
        (file, line).
    """
    messages: list[str] = []
    for file_path in sorted(hits_by_file):
        rel_path = file_path.relative_to(monorepo_root)
        for hit in sorted(hits_by_file[file_path], key=lambda h: h.line_number):
            messages.append(
                f"{rel_path}:{hit.line_number}: shared-package provider-literal "
                f"conditional ({hit.kind}) -- shared layers must never encode "
                "platform-specific policy (Principle 10, D1). Fix: replace this "
                "conditional with a PlatformCapabilityDeclaration/LanguagePlugin "
                "field the affected platform declares, and ask the resolved "
                "plugin instead of comparing a provider identifier here."
            )
    return messages


def _self_test_provider_literal_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-python package
    (a LANGUAGE package by its manifest's ``datrix.languages`` entry point)
    with a module carrying NO provider-literal conditional, plus a baseline
    TOML freezing that file at count 0."""
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-python", "datrix_codegen_python",
        entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"python": "PythonLanguagePlugin"}},
    )
    package_src = tmp_root / "datrix-codegen-python" / "src" / "datrix_codegen_python"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_backend.py"
    module_path.write_text(
        "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = config_dir / "provider-conditional-baseline.toml"
    baseline_path.write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-python/src/datrix_codegen_python/sample_backend.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_provider_literal_run_cli(
    tmp_root: Path,
) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--base-dir",
            str(tmp_root),
            "--check-provider-conditionals",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_provider_literal_cli_non_vacuity() -> bool:
    """End-to-end proof the D5 provider-literal ratchet actually FIRES.

    Plants a real ``== "azure"`` conditional in a real, isolated fixture
    monorepo whose baseline freezes the file at 0, proves the scanner exits 1
    and names the file plus the exact count delta, then reverts the mutation
    and proves the failure clears (exit 0). This is the manifest's required
    NEGATIVE acceptance proof ("a planted new `== \"azure\"` conditional in
    ANY language package fails the ratchet"), run against a synthetic fixture
    monorepo rather than the real committed baseline.
    """
    report_step(
        "Self-test 11/24: provider-literal ratchet CLI mutation non-vacuity "
        '(plant a real == "azure" conditional, prove detection, prove it clears on revert)'
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"provider-literal-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_provider_literal_build_fixture_monorepo(tmp_root)

        clean_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"clean fixture (no provider literal) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'azure'\n",
            encoding="utf-8",
        )
        failing_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"planted '== \"azure\"' conditional exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_backend.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
            encoding="utf-8",
        )
        reverted_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_shared_package_provider_literal_build_fixture_monorepo(
    tmp_root: Path,
) -> Path:
    """Build a minimal isolated monorepo: one datrix-common package with a
    module carrying NO provider-literal conditional (clean shared-package
    fixture -- no baseline file needed, since the shared-package check has
    none). Carries a manifest registering NO entry-point groups so
    ``discover_shared_packages`` classifies it as shared -- the DERIVED set
    main() now threads into ``scan_shared_package_provider_literals``,
    replacing the old hardcoded shared-package tuple this fixture used to
    rely on implicitly."""
    _self_test_write_manifest(
        tmp_root, "datrix-common", "datrix_common", entry_point_groups={}
    )
    package_src = tmp_root / "datrix-common" / "src" / "datrix_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_orchestrator.py"
    module_path.write_text(
        "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
        encoding="utf-8",
    )

    # The shared-package check has no baseline of its own, but it shares the
    # --check-provider-conditionals flag with the language-package ratchet,
    # which DOES require its baseline file to exist. This fixture monorepo
    # has no language package, so an empty (header-only) baseline is correct
    # -- it must merely exist, not carry any [[baseline]] entries.
    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "provider-conditional-baseline.toml").write_text(
        "# empty: no language package present in this fixture monorepo\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_shared_package_provider_literal_cli_non_vacuity() -> bool:
    """End-to-end proof the shared-package zero-tolerance check actually FIRES.

    Plants a real ``== "azure"`` conditional in a SHARED package (datrix-common)
    in an isolated fixture monorepo carrying NO baseline entry for it (there
    is no baseline mechanism for shared packages at all), proves the scanner
    exits 1, then reverts and proves it clears. This is the manifest's
    required NEGATIVE acceptance proof for D6.1's shared-package half.
    """
    report_step(
        "Self-test 12/24: shared-package provider-literal zero-tolerance CLI "
        'mutation non-vacuity (plant a real == "azure" conditional in '
        "datrix-common, prove detection, prove it clears on revert)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-provider-literal-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_package_provider_literal_build_fixture_monorepo(
            tmp_root
        )

        clean_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"clean shared-package fixture exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'azure'\n",
            encoding="utf-8",
        )
        failing_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            "planted shared-package '== \"azure\"' conditional exits 1, got "
            f"{failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated shared-package file",
            "sample_orchestrator.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output identifies it as a SHARED-package violation, not "
            "a baseline-ratchet message",
            "shared-package provider-literal" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
            encoding="utf-8",
        )
        reverted_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"reverting clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_provider_conditional_scanner() -> bool:
    """scan_file_for_provider_conditionals detects every known DI-5-deferred
    conditional shape (ProviderId-shaped, deployment-provider-value, match/case,
    and -- added by this task -- the two D5 provider-literal sub-patterns) and
    excludes every look-alike that must not ratchet."""
    report_step("Self-test 5/24: provider-conditional AST scanner (detection + exclusion)")
    ok = True
    provider_ids = registered_platform_names()
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"provider-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cases: tuple[tuple[str, str, int, str], ...] = (
        (
            "providerid_eq.py",
            "def f(provider):\n    if provider == ProviderId('azure'):\n        return True\n"
            "    return False\n",
            1,
            "providerid_compare",
        ),
        (
            "providerid_ne_helper.py",
            "def f(deployment):\n    if resolve_provider_identity(deployment) != ProviderId('aws'):\n"
            "        return None\n    return 1\n",
            1,
            "providerid_compare",
        ),
        (
            "deployment_value_eq.py",
            "class G:\n    def f(self):\n        if self._deployment.provider.value == 'azure':\n"
            "            return True\n        return False\n",
            1,
            "deployment_provider_value_compare",
        ),
        (
            "deployment_str_ne.py",
            "class G:\n    def f(self):\n        if str(self._deployment.provider) != 'aws':\n"
            "            return []\n        return None\n",
            1,
            "deployment_provider_value_compare",
        ),
        (
            "match_case.py",
            "def f(provider_id):\n"
            "    match provider_id:\n"
            "        case p if p == ProviderId('aws'):\n"
            "            return 'a'\n"
            "        case p if p == ProviderId('azure'):\n"
            "            return 'b'\n"
            "        case _:\n"
            "            raise ValueError('unknown')\n",
            1,
            "match_case_provider_subject",
        ),
        (
            "other_axis_excluded.py",
            "class G:\n"
            "    def f(self, storage_block, email_config):\n"
            "        a = storage_block.config.provider == StorageProvider.MINIO\n"
            "        b = str(email_config.provider.value) == 'sendgrid'\n"
            "        return a, b\n",
            0,
            "",
        ),
        (
            "boundary_rewrap_excluded.py",
            "def resolve_provider_identity(deployment):\n"
            "    return ProviderId(deployment.provider.value)\n",
            0,
            "",
        ),
        (
            "dict_dispatch_excluded.py",
            "_DEPLOYED = frozenset({ProviderId('aws'), ProviderId('azure')})\n\n"
            "def f(provider):\n    if provider not in _DEPLOYED:\n        return []\n"
            "    return None\n",
            0,
            "",
        ),
        (
            "non_deployment_rooted_excluded.py",
            "def f(cfg):\n"
            "    return cfg.container if str(cfg.provider) == 'azure_blob' else cfg.bucket\n",
            0,
            "",
        ),
        (
            "provider_literal_eq.py",
            "def f(backend):\n    if backend == 'azure':\n        return True\n"
            "    return False\n",
            1,
            "provider_literal_compare",
        ),
        (
            "provider_literal_container.py",
            "_ALWAYS_REQUIRES_CREDENTIALS: frozenset = frozenset({'azure'})\n\n"
            "def f(backend):\n    return backend in _ALWAYS_REQUIRES_CREDENTIALS\n",
            1,
            "provider_literal_container",
        ),
        (
            "provider_literal_inline_membership.py",
            "def f(provider_name):\n    return provider_name in ('aws', 'azure')\n",
            1,
            "provider_literal_container",
        ),
        (
            "non_provider_literal_excluded.py",
            "def f(discovery_type):\n    return discovery_type.lower() == 'consul'\n",
            0,
            "",
        ),
        (
            "provider_literal_in_log_excluded.py",
            "import logging\n\n_LOGGER = logging.getLogger(__name__)\n\n"
            "def f() -> None:\n    _LOGGER.info('azure backend selected')\n",
            0,
            "",
        ),
        (
            "provider_literal_in_docstring_excluded.py",
            'def f() -> None:\n    """Selects the azure backend when configured."""\n'
            "    return None\n",
            0,
            "",
        ),
        (
            "provider_literal_mixed_axis_excluded.py",
            "SUPPORTED_STORAGE_PROVIDERS: frozenset = frozenset(\n"
            "    {'s3', 'minio', 'azure_blob', 'local'}\n)\n",
            0,
            "",
        ),
    )
    try:
        for filename, source, expected_count, expected_kind in cases:
            file_path = scratch_dir / filename
            file_path.write_text(source, encoding="utf-8")
            hits = scan_file_for_provider_conditionals(file_path, provider_ids)
            ok &= _check(
                f"{filename}: expected {expected_count} hit(s), got {len(hits)}",
                len(hits) == expected_count,
            )
            if expected_kind and hits:
                ok &= _check(
                    f"{filename}: hit kind == {expected_kind!r}",
                    hits[0].kind == expected_kind,
                )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return ok


def self_test_checks() -> list[NamedCheck]:
    """The provider-conditional and provider-literal scanners' self-tests, each a check the CLI runs."""
    return [
        self_test_check(_self_test_provider_conditional_scanner),
        self_test_check(_self_test_provider_literal_cli_non_vacuity),
        self_test_check(_self_test_shared_package_provider_literal_cli_non_vacuity),
    ]
