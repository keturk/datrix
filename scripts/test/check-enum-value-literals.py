#!/usr/bin/env python
"""Hard-zero gate: no generator may branch on a user enum's member VALUES.

A ``.dtrx`` enum's members are the declaring project's vocabulary, not the
generator's. A generator that reads one by literal name has quietly made the
spelling of somebody else's domain into policy: rename the member and the
behaviour silently disappears; name an unrelated enum the same way and the
behaviour silently appears where nobody asked for it.

This existed. ``datrix-codegen-python`` decided an entity tracked background work
if some enum spelled ``Running`` and ``Failed``, and on that inference emitted a
destructive ``UPDATE`` into every matching service's startup. It fired on a
cross-service queue table whose ``Running`` meant "another service is doing the
work", failed the record of a live ingestion, and released the lane it held. The
replacement is a declared ``work { }`` contract, where every value is a reference
into the author's own model.

Two shapes are detected, both by AST rather than text:

A. ``<expr>.get_value("X")`` / ``<expr>.require_value("X")`` -- looking a member
   up by literal name.
B. ``"X" in <names>`` / ``"X" == <names>`` where ``<names>`` is one of the
   identifiers this codebase uses for a collection of enum member names.

The baseline is a hard zero. There is no exemption file on purpose: a legitimate
need to branch on a member value is a design defect, not an entry to record.

Self-test runs first on every invocation, plants one instance of each shape,
requires both to be found, and requires clean source to report none -- so a
scanner that can only return zero fails here rather than being believed.

Exit codes: 0 = clean (or a successful --self-test), 1 = a violation was found,
2 = usage error or the self-test failed.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

#: Methods that resolve an enum member from a name.
_MEMBER_LOOKUPS: frozenset[str] = frozenset({"get_value", "require_value"})

#: Identifiers this codebase binds a collection of enum member names to. A
#: literal compared against one of these is branching on somebody's vocabulary.
_MEMBER_NAME_COLLECTIONS: frozenset[str] = frozenset(
    {"value_names", "member_names", "enum_values", "enum_value_names", "members"}
)

#: Packages whose source may not branch on enum member values. The language
#: packages and the shared foundation both emit and analyze; neither owns any
#: project's vocabulary.
_SCANNED_PREFIXES: tuple[str, ...] = ("datrix-codegen-", "datrix-common", "datrix-language")


@dataclass(frozen=True)
class Violation:
    """One place where framework source reads a user enum member by literal."""

    path: Path
    line: int
    shape: str
    literal: str
    detail: str

    def render(self, base_dir: Path) -> str:
        """One reviewer-facing line naming the file, line and offending literal."""
        try:
            shown = self.path.relative_to(base_dir)
        except ValueError:
            shown = self.path
        return f"  {shown}:{self.line}  [{self.shape}] {self.literal!r} -- {self.detail}"


def _string_constant(node: ast.expr) -> str | None:
    """Return the value of a string-literal node, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_lookup_calls(tree: ast.AST, path: Path) -> list[Violation]:
    """Shape A: a member looked up by literal name."""
    found: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _MEMBER_LOOKUPS:
            continue
        for arg in node.args:
            literal = _string_constant(arg)
            if literal is None:
                continue
            found.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    shape="member-lookup",
                    literal=literal,
                    detail=(
                        f"{func.attr}() called with a literal member name; take "
                        f"the member from a declaration instead"
                    ),
                )
            )
    return found


def _scan_membership_tests(tree: ast.AST, path: Path) -> list[Violation]:
    """Shape B: a literal compared against a collection of member names."""
    found: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        literals = [lit for lit in (_string_constant(o) for o in operands) if lit]
        if not literals:
            continue
        names = {o.id for o in operands if isinstance(o, ast.Name)}
        touched = names & _MEMBER_NAME_COLLECTIONS
        if not touched:
            continue
        for literal in literals:
            found.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    shape="member-name-test",
                    literal=literal,
                    detail=(
                        f"compared against {sorted(touched)[0]!r}; the set of "
                        f"member names belongs to the declaring project"
                    ),
                )
            )
    return found


def scan_source(source: str, path: Path) -> list[Violation]:
    """Return every violation in one module's source text.

    Args:
        source: Python source text.
        path: Path reported in violations (never read here).

    Returns:
        Violations in file order. A file that does not parse yields none --
        a syntax error is another gate's failure, not this one's.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return sorted(
        _scan_lookup_calls(tree, path) + _scan_membership_tests(tree, path),
        key=lambda v: (v.line, v.shape),
    )


def discover_source_files(base_dir: Path) -> list[Path]:
    """Every ``src/`` Python file of every scanned package, sorted."""
    files: list[Path] = []
    for package in sorted(base_dir.iterdir()):
        if not package.is_dir():
            continue
        if not package.name.startswith(_SCANNED_PREFIXES):
            continue
        src = package / "src"
        if not src.is_dir():
            continue
        files.extend(sorted(p for p in src.rglob("*.py") if "__pycache__" not in p.parts))
    return files


_SELF_TEST_DIRTY = '''
def decide(entity, enum_obj):
    value_names = {str(v.name) for v in enum_obj.values}
    if "Running" in value_names:
        return enum_obj.require_value("Failed")
    return None
'''

_SELF_TEST_CLEAN = '''
def decide(contract):
    return contract.interrupted_value, contract.in_flight_values
'''


def run_self_test() -> bool:
    """Plant each shape, require detection; require clean source to be clean.

    Returns:
        True when the scanner proves it can both find and not-find.
    """
    dirty = scan_source(_SELF_TEST_DIRTY, Path("self_test_dirty.py"))
    shapes = {v.shape for v in dirty}
    ok = True
    if "member-name-test" not in shapes:
        print("[FAIL] self-test: planted member-name test was not detected")
        ok = False
    if "member-lookup" not in shapes:
        print("[FAIL] self-test: planted member lookup was not detected")
        ok = False
    clean = scan_source(_SELF_TEST_CLEAN, Path("self_test_clean.py"))
    if clean:
        print(f"[FAIL] self-test: clean source reported {len(clean)} violation(s)")
        ok = False
    if ok:
        print("[OK] self-test: both shapes detected, clean source reports none")
    return ok


def main(argv: list[str] | None = None) -> int:
    """Run the self-test, then scan every scanned package's ``src/`` tree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", default="", help="Monorepo root")
    parser.add_argument("--self-test", action="store_true", help="Self-test only")
    parser.add_argument("--verbose", action="store_true", help="Print scanned files")
    args = parser.parse_args(argv)

    if not run_self_test():
        return 2
    if args.self_test:
        return 0

    base_dir = Path(args.base_dir).resolve() if args.base_dir else Path(__file__).resolve().parents[3]
    if not base_dir.is_dir():
        print(f"Base directory not found: {base_dir}")
        return 2

    files = discover_source_files(base_dir)
    if not files:
        print(f"No package source found under {base_dir} -- refusing to pass vacuously")
        return 2

    violations: list[Violation] = []
    for path in files:
        if args.verbose:
            print(f"  scanning {path}")
        violations.extend(scan_source(path.read_text(encoding="utf-8", errors="replace"), path))

    print(f"Scanned {len(files)} file(s) across {', '.join(_SCANNED_PREFIXES)}*")
    if violations:
        print(f"\nENUM-VALUE LITERAL GATE FAILED: {len(violations)} violation(s)\n")
        for violation in violations:
            print(violation.render(base_dir))
        print(
            "\nA generator may not read a user enum's member by name. Take the "
            "member from a declaration (see the work { } contract for the shape) "
            "so the project's vocabulary stays the project's."
        )
        return 1
    print("[OK] no generator branches on a user enum's member values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
