"""Rename feature tags across every tag carrier of the package test trees, from a mapping file.

Carriers: pytest ``tag(...)`` calls (module ``pytestmark``, class, function, and
``pytest.param(..., marks=pytest.mark.tag(...))``) located with ``ast`` and rewritten at the exact
string-literal span; and fixture header lines ``// @tags a, b`` / ``# @tags a, b`` in ``.dtrx``,
``.dcfg`` and ``.dseed`` files under ``tests/``. Every other byte of a file is kept, line endings
included: files are read and written as bytes.

Mapping file (JSON):
    {"retags": [
        {"from": "aws", "to": "iac-data"},
        {"from": "auth", "to": "authorization", "paths": ["datrix-codegen-common/tests/unit/x.py"]},
        {"from": "auth", "to": "identity"}
    ]}
A rule with ``paths`` (workspace-relative, POSIX) applies to those files only and wins over a rule
without ``paths`` for the same ``from``. A ``from`` that has ONLY path-scoped rules must name every
file it occurs in: an occurrence no rule covers is refused (exit 1), never guessed.

When the ``to`` tag is already an argument of the same ``tag(...)`` call (or already listed on the
same header line), the ``from`` occurrence is removed instead of duplicated.

Default is a preview: the changes are listed and a unified diff is written to
``<workspace>/.tmp/retag/retag.diff``. ``--apply`` writes the files.

A self-test over planted files runs first on every invocation (exit 2 if it fails).

Exit codes: 0 = done (preview or applied); 1 = a refused occurrence or a bad mapping; 2 = self-test
failure or usage error.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.paths import WORKSPACE_DIR

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

FIXTURE_SUFFIXES = frozenset({".dtrx", ".dcfg", ".dseed"})
TAG_CALL_NAME = "tag"
HEADER_PATTERN = re.compile(r"^(?P<lead>\s*(?://|#)\s*@tags\s+)(?P<tags>.+?)(?P<trail>\s*)$")
TAG_SEPARATOR = re.compile(r"\s*,\s*|\s+")
SOURCE_ENCODING = "utf-8"
# The line breaks ``ast`` counts lines by; ``str.splitlines`` also breaks on form feeds and
# Unicode separators, which would shift every later line's offset.
AST_LINE_BREAK = re.compile(r"\r\n|\r|\n")


class RetagError(Exception):
    """A mapping or an occurrence the tool refuses, with what was expected."""


@dataclass(frozen=True)
class Rule:
    """One mapping entry."""

    source: str
    target: str
    paths: frozenset[str]


@dataclass(frozen=True)
class Edit:
    """A text replacement in one file: replace ``[start, end)`` with ``text``."""

    start: int
    end: int
    text: str


class Mapping:
    """The rules, resolved per (file, tag)."""

    def __init__(self, rules: Sequence[Rule]) -> None:
        self._scoped: dict[tuple[str, str], str] = {}
        self._global: dict[str, str] = {}
        for rule in rules:
            if rule.source == rule.target:
                raise RetagError(f"Rule renames {rule.source!r} to itself. Expected different 'from' and 'to'.")
            if rule.paths:
                for path in rule.paths:
                    self._scoped[(path, rule.source)] = rule.target
            elif rule.source in self._global:
                raise RetagError(f"Two unscoped rules for {rule.source!r}. Expected at most one rule without 'paths' per tag.")
            else:
                self._global[rule.source] = rule.target
        scoped_sources = {source for _, source in self._scoped}
        self._scoped_only = scoped_sources - set(self._global)

    @property
    def sources(self) -> frozenset[str]:
        return frozenset(self._global) | frozenset(source for _, source in self._scoped)

    def target_for(self, relative_path: str, tag: str) -> str | None:
        """The tag *tag* becomes in *relative_path*, or None when no rule maps it.

        Raises:
            RetagError: *tag* has only path-scoped rules and none names *relative_path*.
        """
        scoped = self._scoped.get((relative_path, tag))
        if scoped is not None:
            return scoped
        if tag in self._scoped_only:
            raise RetagError(
                f"{relative_path}: tag {tag!r} has only path-scoped rules and none names this file. "
                f"Expected every file using {tag!r} to be listed in a rule's 'paths', or one unscoped rule."
            )
        return self._global.get(tag)


def load_mapping(path: Path) -> Mapping:
    """Read and validate the mapping JSON.

    Raises:
        RetagError: The file is not a valid mapping.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("retags") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise RetagError(f"{path}: expected a JSON object with a non-empty 'retags' list.")
    rules: list[Rule] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("from"), str) or not isinstance(entry.get("to"), str):
            raise RetagError(f"{path}: retags[{index}] needs string 'from' and 'to'.")
        raw_paths = entry["paths"] if "paths" in entry else []
        if not isinstance(raw_paths, list) or not all(isinstance(p, str) for p in raw_paths):
            raise RetagError(f"{path}: retags[{index}].paths must be a list of workspace-relative POSIX paths.")
        rules.append(Rule(entry["from"], entry["to"], frozenset(raw_paths)))
    return Mapping(rules)


def read_source(path: Path) -> str:
    """The text of *path* exactly as stored: line endings are not translated."""
    return path.read_bytes().decode(SOURCE_ENCODING)


def write_source(path: Path, text: str) -> None:
    """Write *text* to *path* byte for byte: line endings are not translated."""
    path.write_bytes(text.encode(SOURCE_ENCODING))


class _Positions:
    """String indices of ``ast`` positions: 1-based lines, columns counted in UTF-8 bytes."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._line_starts = [0] + [match.end() for match in AST_LINE_BREAK.finditer(text)]

    def index(self, line: int, byte_column: int) -> int:
        start = self._line_starts[line - 1]
        prefix = self._text[start : start + byte_column].encode(SOURCE_ENCODING)[:byte_column]
        return start + len(prefix.decode(SOURCE_ENCODING))

    def span(self, node: ast.expr) -> tuple[int, int]:
        end_line = node.end_lineno if node.end_lineno is not None else node.lineno
        end_col = node.end_col_offset if node.end_col_offset is not None else node.col_offset
        return self.index(node.lineno, node.col_offset), self.index(end_line, end_col)


def _is_tag_call(node: ast.Call) -> bool:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name == TAG_CALL_NAME


def python_edits(text: str, relative_path: str, mapping: Mapping) -> list[Edit]:
    """Edits renaming mapped tags in every ``tag(...)`` call of *text*."""
    tree = ast.parse(text)
    offsets = _Positions(text)
    edits: list[Edit] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_tag_call(node)):
            continue
        present = {a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
        for index, arg in enumerate(node.args):
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            target = mapping.target_for(relative_path, arg.value)
            if target is None:
                continue
            start, end = offsets.span(arg)
            if target in present:
                edits.append(_removal(offsets, node, index, start, end))
                continue
            edits.append(Edit(start, end, _renamed_literal(text[start:end], target)))
            present.add(target)
    return edits


def _renamed_literal(literal: str, target: str) -> str:
    """*literal* (its source text) holding *target*, keeping its prefix and delimiter."""
    quote_at = min(index for index in (literal.find('"'), literal.find("'")) if index >= 0)
    quote = literal[quote_at]
    delimiter = quote * 3 if literal.startswith(quote * 3, quote_at) else quote
    return f"{literal[:quote_at]}{delimiter}{target}{delimiter}"


def _removal(offsets: _Positions, call: ast.Call, index: int, start: int, end: int) -> Edit:
    """Remove argument *index* of *call* together with one adjoining comma."""
    if index + 1 < len(call.args):
        following_start, _ = offsets.span(call.args[index + 1])
        return Edit(start, following_start, "")
    _, previous_end = offsets.span(call.args[index - 1])
    return Edit(previous_end, end, "")


def fixture_edits(text: str, relative_path: str, mapping: Mapping) -> list[Edit]:
    """Edits renaming mapped tags on ``@tags`` header lines of a fixture."""
    edits: list[Edit] = []
    position = 0
    for line in text.splitlines(keepends=True):
        match = HEADER_PATTERN.match(line.rstrip("\r\n"))
        if match:
            tags = [t for t in TAG_SEPARATOR.split(match["tags"].strip()) if t]
            renamed: list[str] = []
            for tag in tags:
                target = mapping.target_for(relative_path, tag)
                new = tag if target is None else target
                if new not in renamed:
                    renamed.append(new)
            if renamed != tags:
                start = position + match.start("tags")
                edits.append(Edit(start, start + len(match["tags"]), ", ".join(renamed)))
        position += len(line)
    return edits


def apply_edits(text: str, edits: Sequence[Edit]) -> str:
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        text = text[: edit.start] + edit.text + text[edit.end :]
    return text


def carrier_files(root: Path) -> list[Path]:
    """Every tag-carrier file under each package's ``tests/`` tree."""
    files: list[Path] = []
    for package in sorted(root.glob("datrix-*")):
        tests = package / "tests"
        if not tests.is_dir():
            continue
        for path in sorted(tests.rglob("*")):
            if path.is_file() and (path.suffix == ".py" or path.suffix in FIXTURE_SUFFIXES):
                files.append(path)
    return files


def plan(root: Path, mapping: Mapping) -> tuple[dict[Path, str], list[str]]:
    """New text per changed file, and every refusal."""
    changed: dict[Path, str] = {}
    refusals: list[str] = []
    for path in carrier_files(root):
        relative = path.relative_to(root).as_posix()
        text = read_source(path)
        if not any(source in text for source in mapping.sources):
            continue
        try:
            edits = python_edits(text, relative, mapping) if path.suffix == ".py" else fixture_edits(text, relative, mapping)
        except RetagError as exc:
            refusals.append(str(exc))
            continue
        except SyntaxError as exc:
            refusals.append(f"{relative}: does not parse ({exc}); its tags cannot be located.")
            continue
        if edits:
            changed[path] = apply_edits(text, edits)
    return changed, refusals


def _refuses(mapping: Mapping, text: str, relative_path: str) -> bool:
    """Whether locating the tags of *text* is refused by *mapping*."""
    try:
        python_edits(text, relative_path, mapping)
    except RetagError:
        return True
    return False


def run_self_test() -> list[str]:
    """Prove every behaviour on planted inputs; return the failures."""
    failures: list[str] = []
    mapping = Mapping([
        Rule("aws", "iac-data", frozenset()),
        Rule("auth", "authorization", frozenset({"datrix-x/tests/scoped.py"})),
        Rule("dup", "keep", frozenset()),
        Rule("only-scoped", "z", frozenset({"datrix-x/tests/scoped.py"})),
    ])
    python = 'pytestmark = pytest.mark.tag("aws", "rdbms")\n@pytest.mark.tag("keep", "dup")\ndef test_a(): ...\n'
    expected = 'pytestmark = pytest.mark.tag("iac-data", "rdbms")\n@pytest.mark.tag("keep")\ndef test_a(): ...\n'
    got = apply_edits(python, python_edits(python, "datrix-x/tests/a.py", mapping))
    if got != expected:
        failures.append(f"python rename/dedupe: {got!r} != {expected!r}")
    scoped = 'pytestmark = pytest.mark.tag("auth")\n'
    got = apply_edits(scoped, python_edits(scoped, "datrix-x/tests/scoped.py", mapping))
    if got != 'pytestmark = pytest.mark.tag("authorization")\n':
        failures.append(f"path-scoped rule not applied: {got!r}")
    if not _refuses(mapping, 'x = pytest.mark.tag("only-scoped")\n', "datrix-x/tests/other.py"):
        failures.append("an uncovered path-scoped-only tag was not refused")
    fixture = "// @tags aws, rdbms, iac-data\nservice X {}\n"
    got = apply_edits(fixture, fixture_edits(fixture, "datrix-x/tests/f.dtrx", mapping))
    if got != "// @tags iac-data, rdbms\nservice X {}\n":
        failures.append(f"fixture header rename/dedupe: {got!r}")
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        tests = root / "datrix-x" / "tests"
        tests.mkdir(parents=True)
        write_source(tests / "a.py", python)
        changed, refusals = plan(root, mapping)
        if refusals or list(changed.values()) != [expected]:
            failures.append(f"plan over a planted tree: changed={len(changed)} refusals={refusals}")
    return failures + _fidelity_failures(mapping)


def _fidelity_failures(mapping: Mapping) -> list[str]:
    """Prove a rewrite changes the tag literal only: exact span on any line, bytes kept elsewhere."""
    failures: list[str] = []
    planted = {
        'cases = [pytest.param("é", marks=pytest.mark.tag("aws"))]\n': (
            'cases = [pytest.param("é", marks=pytest.mark.tag("iac-data"))]\n'
        ),
        '"""a\x0cb"""\npytestmark = pytest.mark.tag("aws")\n': '"""a\x0cb"""\npytestmark = pytest.mark.tag("iac-data")\n',
        "pytestmark = pytest.mark.tag(r'aws', u\"\"\"aws\"\"\")\n": "pytestmark = pytest.mark.tag(r'iac-data')\n",
    }
    for source, expected in planted.items():
        got = apply_edits(source, python_edits(source, "datrix-x/tests/a.py", mapping))
        if got != expected:
            failures.append(f"span after a multi-byte character or a form feed, or a prefixed literal: {got!r} != {expected!r}")
    endings = {"lf.py": "\n", "crlf.py": "\r\n"}
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        tests = root / "datrix-x" / "tests"
        tests.mkdir(parents=True)
        for name, ending in endings.items():
            write_source(tests / name, f'"""Doc."""{ending}pytestmark = pytest.mark.tag("aws"){ending}')
        changed, _ = plan(root, mapping)
        for path, new_text in changed.items():
            write_source(path, new_text)
        for name, ending in endings.items():
            stored = (tests / name).read_bytes()
            wanted = f'"""Doc."""{ending}pytestmark = pytest.mark.tag("iac-data"){ending}'.encode(SOURCE_ENCODING)
            if stored != wanted:
                failures.append(f"line endings not kept in {name}: {stored!r} != {wanted!r}")
    return failures


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mapping", type=Path, help="mapping JSON")
    parser.add_argument("--apply", action="store_true", help="write the files (default: preview)")
    parser.add_argument("--self-test", action="store_true", help="run only the self-test")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = _parse_args(argv)
    failures = run_self_test()
    if failures:
        print("RETAG self-test FAILED: " + "; ".join(failures), file=sys.stderr)
        return EXIT_USAGE
    if args.self_test:
        print("RETAG self-test passed (rename, dedupe, path scope, refusal, fixture headers, planted tree, byte fidelity).")
        return EXIT_OK
    if args.mapping is None:
        print("Usage: --mapping <file.json> [--apply]", file=sys.stderr)
        return EXIT_USAGE
    try:
        mapping = load_mapping(args.mapping)
    except (RetagError, json.JSONDecodeError) as exc:
        print(f"RETAG bad mapping: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    changed, refusals = plan(WORKSPACE_DIR, mapping)
    for refusal in refusals:
        print(f"REFUSED {refusal}")
    if refusals:
        print(f"RETAG REFUSED {len(refusals)} occurrence(s); nothing written. Fix the mapping and re-run.")
        return EXIT_REFUSED
    diff_dir = WORKSPACE_DIR / ".tmp" / "retag"
    diff_dir.mkdir(parents=True, exist_ok=True)
    diff_lines: list[str] = []
    for path, new_text in changed.items():
        old_text = read_source(path)
        relative = path.relative_to(WORKSPACE_DIR).as_posix()
        diff_lines.extend(difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True), relative, relative))
        print(f"CHANGE {relative}")
        if args.apply:
            write_source(path, new_text)
    (diff_dir / "retag.diff").write_text("".join(diff_lines), encoding="utf-8")
    verb = "APPLIED" if args.apply else "PREVIEW"
    print(f"RETAG {verb} files={len(changed)} diff={diff_dir / 'retag.diff'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
