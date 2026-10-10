#!/usr/bin/env python3
"""Template reachability gate: every Jinja template a framework package ships is
named by something that can render it.

A ``.j2`` file under a package's ``templates/`` tree that nothing names is dead
output: it is reviewed, kept in sync with its live siblings and shipped, yet no
generator can ever render it. Two cache-access templates once sat beside the
live one for exactly that reason, carrying an older access surface no service
received.

A template counts as named when any of these reaches it:

1. a Python string constant in any framework package's ``src/`` (``ast``;
   bare string statements -- docstrings -- excluded) equal to its path below
   its ``templates/`` root (or any ``/``-suffix of it, with or without
   ``.j2``), or to its bare file stem -- a render plan that composes
   ``{dir}/{stem}.{ext}.j2`` names a template by its stem;
2. a Python f-string, ``+`` concatenation or ``{placeholder}`` constant whose
   literal parts match it, provided the file-name part keeps at least one
   literal character (``f"pubsub_connection_{engine}.py.j2"`` names every
   engine variant; ``f"{name}.py.j2"`` names nothing);
3. a static Jinja ``include``/``import``/``from``/``extends`` in any template
   (parsed with ``jinja2.meta``; a template that does not parse is an error);
4. the ``template_name`` of a compiled genDSL ``FileDefinition`` of any
   registered generator target (the definition modules are imported and the
   compiled IR is walked -- genDSL lives in docstrings, so a text scan would
   miss it). A genDSL template name that matches no template on disk is a
   dangling reference and fails the gate too.

Rule 2 is static: a pattern names every variant it can spell, so a variant the
placeholder never takes at runtime is not reported. The gate proves the
templates are reachable by a name, not that every value is produced.

Non-vacuity, every run: a planted workspace with one literal-named, one
pattern-named, one included, one docstring-only and one unnamed template yields
exactly the docstring-only and unnamed ones; and the live genDSL walk must find
at least one template name for every target that declares template files.

Exit codes:
    0: Every template is named and every genDSL template name resolves.
    1: At least one unnamed template or dangling genDSL template name.
    2: Usage error, a template that does not parse, or the self-test failed.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import importlib
import json
import re
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import jinja2
from jinja2 import meta

from datrix_scripts.paths import WORKSPACE_DIR

EXEMPTIONS_RELATIVE_PATH = Path("datrix") / "scripts" / "config" / "template-reachability-exemptions.json"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

TEMPLATE_SUFFIX = ".j2"
TEMPLATES_DIR_NAME = "templates"
PACKAGE_GLOB = "datrix-*"
#: Stands for a computed part of a spelled name. A character no source literal
#: carries, so a ``*``, ``?`` or ``[`` a real constant contains stays literal.
WILDCARD = "\x00"
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
#: The fewest literal letters/digits a pattern's file-name stem keeps before it
#: counts as naming anything: ``f"{a}_{b}.py.j2"`` spells no template.
MIN_LITERAL_STEM_CHARS = 3
_ALNUM = re.compile(r"[0-9A-Za-z]")
_JINJA_EXTENSIONS: tuple[str, ...] = ("jinja2.ext.do", "jinja2.ext.loopcontrols")

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


@dataclass(frozen=True)
class Template:
    """One shipped template: its file and its path below its ``templates/`` root."""

    path: Path
    relative: str

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class ScanResult:
    """What the scan found: unnamed templates and genDSL names that resolve to none."""

    unnamed: tuple[Template, ...]
    dangling_gendsl: tuple[str, ...]
    gendsl_names_by_target: Mapping[str, frozenset[str]]


class TemplateParseError(ValueError):
    """A template that Jinja cannot parse, so its references cannot be read."""


class ExemptionFileError(ValueError):
    """The reviewed-exemptions file is missing or malformed."""


@dataclass(frozen=True)
class Exemption:
    """One reviewed unnamed template: its workspace-relative path and why it stays."""

    template: str
    reason: str


def load_exemptions(path: Path) -> list[Exemption]:
    """The reviewed exemptions in *path*.

    Raises:
        ExemptionFileError: The file is missing, or an entry lacks a non-empty
            ``template`` or ``reason``.
    """
    if not path.is_file():
        raise ExemptionFileError(f"Exemptions file not found: {path}")
    entries = json.loads(path.read_text(encoding="utf-8")).get("exemptions")
    if not isinstance(entries, list):
        raise ExemptionFileError(f"{path}: expected 'exemptions' (list).")
    exemptions: list[Exemption] = []
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry[key].strip() for key in ("template", "reason")
        ):
            raise ExemptionFileError(
                f"{path}: every exemption needs a non-empty 'template' and 'reason'; got {entry!r}."
            )
        exemptions.append(Exemption(template=entry["template"], reason=entry["reason"]))
    return exemptions


def apply_exemptions(
    unnamed: Iterable[Template], exemptions: Iterable[Exemption], base_dir: Path
) -> tuple[tuple[Template, ...], tuple[Exemption, ...]]:
    """(unnamed templates no exemption covers, exemptions covering no unnamed template)."""
    by_path = {t.path.relative_to(base_dir).as_posix(): t for t in unnamed}
    exempted = {e.template for e in exemptions}
    remaining = tuple(t for key, t in by_path.items() if key not in exempted)
    stale = tuple(e for e in exemptions if e.template not in by_path)
    return remaining, stale


def discover_package_sources(base_dir: Path) -> list[Path]:
    """Every framework package ``src/`` directory on disk."""
    return sorted(p / "src" for p in base_dir.glob(PACKAGE_GLOB) if (p / "src").is_dir())


def _templates_root(path: Path) -> Path | None:
    for parent in path.parents:
        if parent.name == TEMPLATES_DIR_NAME:
            return parent
    return None


def discover_templates(sources: Iterable[Path]) -> list[Template]:
    """Every ``.j2`` file below a ``templates/`` directory of a package source tree."""
    found: list[Template] = []
    for source in sources:
        for path in sorted(source.rglob(f"*{TEMPLATE_SUFFIX}")):
            root = _templates_root(path)
            if root is None:
                continue
            found.append(Template(path=path, relative=path.relative_to(root).as_posix()))
    return found


def _pattern_of(node: ast.expr) -> str | None:
    """The literal text of a string expression, each computed part as :data:`WILDCARD`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _PLACEHOLDER.sub(WILDCARD, node.value)
    if isinstance(node, ast.JoinedStr):
        return "".join(
            _PLACEHOLDER.sub(WILDCARD, part.value)
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
            else WILDCARD
            for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _pattern_of(node.left), _pattern_of(node.right)
        if left is None and right is None:
            return None
        return (left if left is not None else WILDCARD) + (right if right is not None else WILDCARD)
    return None


def _docstring_ids(tree: ast.Module) -> set[int]:
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def python_name_patterns(sources: Iterable[Path]) -> set[str]:
    """Every string pattern a Python module of *sources* spells (docstrings excluded)."""
    patterns: set[str] = set()
    for source in sources:
        for module in source.rglob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            docstrings = _docstring_ids(tree)
            for node in ast.walk(tree):
                if id(node) in docstrings or not isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp)):
                    continue
                pattern = _pattern_of(node)
                if pattern is not None and pattern.strip(WILDCARD):
                    patterns.add(pattern)
    return patterns


def jinja_references(templates: Iterable[Template]) -> set[str]:
    """Every template name a template statically includes, imports or extends.

    Raises:
        TemplateParseError: A template does not parse.
    """
    env = jinja2.Environment(extensions=list(_JINJA_EXTENSIONS))
    names: set[str] = set()
    for template in templates:
        try:
            parsed = env.parse(template.path.read_text(encoding="utf-8"))
        except jinja2.TemplateSyntaxError as error:
            raise TemplateParseError(
                f"{template.path}: line {error.lineno}: {error.message}. The gate reads a "
                f"template's references from its parse tree; fix the template or add the "
                f"Jinja extension it needs to _JINJA_EXTENSIONS."
            ) from error
        names.update(ref for ref in meta.find_referenced_templates(parsed) if ref is not None)
    return names


def _template_names_in(definitions: Iterable[object]) -> Iterator[str]:
    from datrix_codegen_kernel.generation.gendsl_ir import FileDefinition

    pending: list[object] = list(definitions)
    while pending:
        current = pending.pop()
        if isinstance(current, FileDefinition) and isinstance(current.template_name, str):
            yield current.template_name
        if dataclasses.is_dataclass(current) and not isinstance(current, type):
            pending.extend(getattr(current, field.name) for field in dataclasses.fields(current))
        elif isinstance(current, (list, tuple, frozenset, set)):
            pending.extend(current)
        elif isinstance(current, Mapping):
            pending.extend(current.values())


def gendsl_template_names() -> dict[str, frozenset[str]]:
    """Every compiled genDSL ``FileDefinition`` template name, per registered target."""
    from datrix_codegen_kernel.gendsl import target_registry
    from datrix_codegen_kernel.gendsl.compiler import get_definitions

    names: dict[str, frozenset[str]] = {}
    for target in sorted(target_registry.target_kind_map()):
        for module in target_registry.definition_modules_for(target):
            importlib.import_module(module)
        names[target] = frozenset(_template_names_in(get_definitions(target)))
    return names


def _names_anything(pattern: str) -> bool:
    """An exact literal always names what it spells; a computed pattern only while
    its file-name stem keeps :data:`MIN_LITERAL_STEM_CHARS` literal letters/digits."""
    if WILDCARD not in pattern:
        return bool(pattern)
    file_part = pattern.rsplit("/", 1)[-1].removesuffix(TEMPLATE_SUFFIX)
    stem = file_part.rsplit(".", 1)[0] if "." in file_part else file_part
    return len(_ALNUM.findall(stem.replace(WILDCARD, ""))) >= MIN_LITERAL_STEM_CHARS


def _matcher(pattern: str) -> re.Pattern[str]:
    """*pattern* as a regex: literal parts escaped, each computed part any run."""
    body = ".*".join(re.escape(part) for part in pattern.split(WILDCARD))
    return re.compile(rf"(?:.*/)?{body}(?:{re.escape(TEMPLATE_SUFFIX)})?")


def _names(pattern: str, template: Template) -> bool:
    if not _names_anything(pattern):
        return False
    return _matcher(pattern).fullmatch(template.relative) is not None


def _spellings(template: Template) -> set[str]:
    """Every literal a caller could name *template* by: each ``/``-suffix of its
    relative path, with and without the ``.j2`` suffix, and its bare file stem
    (a render plan that composes ``{dir}/{stem}.{ext}.j2`` names it by the stem)."""
    parts = template.relative.split("/")
    suffixes = {"/".join(parts[index:]) for index in range(len(parts))}
    bare_stem = template.name.split(".", 1)[0]
    return suffixes | {s.removesuffix(TEMPLATE_SUFFIX) for s in suffixes} | {bare_stem}


class _NameIndex:
    """The patterns split into exact literals (a set lookup) and computed ones (regexes)."""

    def __init__(self, patterns: Iterable[str]) -> None:
        usable = [p for p in patterns if _names_anything(p)]
        self._literals = frozenset(p for p in usable if WILDCARD not in p)
        self._computed = tuple(_matcher(p) for p in usable if WILDCARD in p)

    def names(self, template: Template) -> bool:
        if _spellings(template) & self._literals:
            return True
        return any(m.fullmatch(template.relative) for m in self._computed)


def scan(base_dir: Path, *, with_gendsl: bool) -> ScanResult:
    """Find every unnamed template and every genDSL template name naming none."""
    sources = discover_package_sources(base_dir)
    templates = discover_templates(sources)
    literal_names: set[str] = jinja_references(templates)
    gendsl = gendsl_template_names() if with_gendsl else {}
    gendsl_names = {_PLACEHOLDER.sub(WILDCARD, n) for names in gendsl.values() for n in names}
    literal_names |= gendsl_names
    index = _NameIndex(python_name_patterns(sources) | literal_names)
    unnamed = tuple(t for t in templates if not index.names(t))
    dangling = tuple(
        sorted(name for name in gendsl_names if not any(_names(name, t) for t in templates))
    )
    return ScanResult(unnamed=unnamed, dangling_gendsl=dangling, gendsl_names_by_target=gendsl)


_PLANT_FILES: Mapping[str, str] = {
    "datrix-plant/src/plant/templates/persistence/used.py.j2": '{% include "shared/included.j2" %}\n',
    "datrix-plant/src/plant/templates/shared/included.j2": "x\n",
    "datrix-plant/src/plant/templates/messaging/conn_kafka.py.j2": "x\n",
    "datrix-plant/src/plant/templates/messaging/jobs_runner.py.j2": "x\n",
    "datrix-plant/src/plant/templates/persistence/doc_only.py.j2": "x\n",
    "datrix-plant/src/plant/templates/persistence/orphan.py.j2": "x\n",
    "datrix-plant/src/plant/gen.py": (
        '"""Renders persistence/doc_only.py.j2 -- a mention, not a use."""\n'
        'USED = "persistence/used.py.j2"\n'
        "def conn(engine: str) -> str:\n"
        '    return f"messaging/conn_{engine}.py.j2"\n'
        "def anything(name: str) -> str:\n"
        '    return f"{name}.py.j2"\n'
        "def planned(stem: str, ext: str) -> str:\n"
        '    return f"messaging/{stem}.{ext}.j2"\n'
        'RUNNER = planned("jobs_runner", "py")\n'
    ),
}
_PLANT_EXPECTED_UNNAMED: frozenset[str] = frozenset(
    {"persistence/doc_only.py.j2", "persistence/orphan.py.j2"}
)


def self_test(base_dir: Path) -> list[str]:
    """Prove the matcher on a planted workspace and the genDSL walk on the real one."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for relative, text in _PLANT_FILES.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        planted = scan(root, with_gendsl=False)
        unnamed = frozenset(t.relative for t in planted.unnamed)
        if unnamed != _PLANT_EXPECTED_UNNAMED:
            failures.append(
                f"planted workspace: expected unnamed {sorted(_PLANT_EXPECTED_UNNAMED)}, "
                f"got {sorted(unnamed)}"
            )
    declared = gendsl_template_names()
    if not declared:
        failures.append("no genDSL generator target is registered; the genDSL walk is untested")
    if not any(declared.values()):
        failures.append("no registered genDSL target declares a template file; the walk found nothing")
    if not discover_templates(discover_package_sources(base_dir)):
        failures.append(f"no template found under {base_dir}; the scan would pass vacuously")
    return failures


def _report(result: ScanResult, exemptions: list[Exemption], base_dir: Path) -> int:
    unnamed, stale = apply_exemptions(result.unnamed, exemptions, base_dir)
    for template in unnamed:
        print(f"{RED}UNNAMED{RESET} {template.path.relative_to(base_dir).as_posix()}")
    for name in result.dangling_gendsl:
        print(f"{RED}DANGLING{RESET} genDSL template name {name!r} matches no template on disk")
    for exemption in stale:
        print(f"{RED}STALE EXEMPTION{RESET} {exemption.template} is named or gone; remove the entry")
    if unnamed or result.dangling_gendsl or stale:
        print(
            f"\n{len(unnamed)} unnamed template(s), {len(result.dangling_gendsl)} dangling genDSL "
            f"name(s), {len(stale)} stale exemption(s). Fix: delete a template nothing renders, or "
            f"name it from the generator that should; point a dangling genDSL name at an existing "
            f"template; drop a stale exemption."
        )
        return EXIT_FINDINGS
    counted = sum(len(names) for names in result.gendsl_names_by_target.values())
    print(
        f"{GREEN}OK{RESET} every template is named ({counted} genDSL template names resolved, "
        f"{len(exemptions)} reviewed exemption(s))"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-dir", type=Path, default=WORKSPACE_DIR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    base_dir: Path = args.base_dir.resolve()
    try:
        failures = self_test(base_dir)
        if failures:
            for failure in failures:
                print(f"{RED}SELF-TEST FAILED{RESET} {failure}")
            return EXIT_USAGE
        print(f"{GREEN}self-test passed{RESET}")
        if args.self_test:
            return EXIT_OK
        exemptions = load_exemptions(base_dir / EXEMPTIONS_RELATIVE_PATH)
        return _report(scan(base_dir, with_gendsl=True), exemptions, base_dir)
    except (TemplateParseError, ExemptionFileError) as error:
        print(f"{RED}ERROR{RESET} {error}")
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
