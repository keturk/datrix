r"""Fail if a Python-emitting Jinja template escapes an escape sequence.

Jinja copies template text through verbatim: it does not interpret backslashes.
So a doubled ``\\n`` written in a ``*.py.j2`` template reaches the EMITTED Python
source still doubled, where it is an escaped BACKSLASH followed by ``n`` -- so the
string the generated program builds at runtime carries the two literal characters
where a line break was meant. The escaping level was applied once for the emitting
layer and never unescaped for the emitted one.

The defect is invisible everywhere it matters. The emitted Python compiles, the
function that writes the file returns the right count, the artifact reads
plausibly to a human skimming it, and any downstream validator that accepts
comments (``nginx -t``, a YAML/JSON parser fed a single-line document) passes.
It surfaced first as a gateway config fragment whose whole body landed on one
physical line behind a leading ``#``, so every ``set_real_ip_from`` directive was
read as part of that comment and the proxy trusted nobody -- silently, through a
green smoke gate and a successful deploy. A second instance sat in an email
client template at the same time, putting a literal backslash into the body of
every templated message.

A run of exactly TWO backslashes before ``n``/``t``/``r`` is the shape. One
backslash is the correct escape. Four is a deliberate double-escape (a template
emitting Python that itself emits an escape) and is not flagged.

The non-vacuity self-test runs before every scan. This module is what
``gates/repo-hygiene/emitted-escape-integrity-gate.ps1`` (and its ``.sh`` twin) runs, in gate mode
(``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] emitted-escape-integrity PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes: 0 = clean (or a successful ``--self-test``), 1 = an escaped escape, a stale exemption, or
a failing ``--self-test``, 2 = usage error, an unreadable exemptions baseline, no templates discovered,
a template that cannot be read, or a self-test failing before a real scan.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from typing import Final

from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, EXIT_VIOLATION
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import base_dir_gate_parser
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test import wrappers

GATE: Final = "emitted-escape-integrity"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.emitted_escape_integrity_gate"
WRAPPER: Final = "emitted-escape-integrity-gate"

#: Exactly two backslashes before an escape letter -- not one (correct), and not
#: three or four (a deliberate, deeper escape). The lookbehind is what makes the
#: run length exact.
ESCAPED_ESCAPE = re.compile(r"(?<!\\)\\\\[ntr]")

#: Templates that emit Python. The suffix is the declaration: a template named
#: ``*.py.j2`` renders Python source, where a backslash escape is meaningful.
#: Templates emitting shell, TypeScript or regex are deliberately out of scope --
#: a doubled backslash is ordinary and correct in all three.
TEMPLATE_SUFFIX = ".py.j2"

SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        ".tmp",
        ".scripts",
        ".test-output",
        ".test_results",
        ".generated",
        "generated",
    }
)

DEFAULT_BASE_DIR = str(WORKSPACE_DIR)

EXEMPTIONS_RELPATH = "datrix/scripts/config/emitted-escape-exemptions.json"


def _norm(path: str, base_dir: str) -> str:
    normalized = path.replace("\\", "/")
    prefix = base_dir.replace("\\", "/").rstrip("/") + "/"
    return normalized[len(prefix) :] if normalized.startswith(prefix) else normalized


def discover_templates(base_dir: str) -> list[str]:
    """Return every Python-emitting template under each package's ``src/`` tree.

    The package set is walked from disk rather than listed, so a new
    ``datrix-codegen-<lang>`` package is covered with no edit here.
    """
    templates: list[str] = []
    for entry in sorted(os.listdir(base_dir)):
        if not entry.startswith("datrix"):
            continue
        src = os.path.join(base_dir, entry, "src")
        if not os.path.isdir(src):
            continue
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in sorted(filenames):
                if filename.endswith(TEMPLATE_SUFFIX):
                    templates.append(os.path.join(dirpath, filename))
    return templates


class TemplateReadError(RuntimeError):
    """A discovered template could not be read; skipping it would report its content as clean."""


def scan_files(paths: list[str], base_dir: str) -> list[tuple[str, int, str]]:
    """Return ``(relative_path, lineno, stripped_line)`` for every hit.

    Raises:
        TemplateReadError: a template could not be read. The scan stops rather than skip it.
    """
    hits: list[tuple[str, int, str]] = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as exc:
            raise TemplateReadError(
                f"{_norm(path, base_dir)} could not be read ({exc.strerror or exc}). The scan reads every "
                "Python-emitting template and stops rather than skip one. Close the program holding the "
                "file, then re-run."
            ) from exc
        for lineno, line in enumerate(text.splitlines(), 1):
            if ESCAPED_ESCAPE.search(line):
                hits.append((_norm(path, base_dir), lineno, line.strip()))
    return hits


def load_exemptions(base_dir: str) -> list[dict[str, str]]:
    """Return the reviewed exemption entries.

    Raises:
        ValueError: An entry is missing a required field -- the baseline
            stopped describing what it claims to, so nothing it says can be
            trusted.
    """
    path = os.path.join(base_dir, EXEMPTIONS_RELPATH)
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    entries = document["exemptions"]
    for entry in entries:
        missing = [key for key in ("file", "snippet", "reason") if not entry.get(key)]
        if missing:
            raise ValueError(
                f"{EXEMPTIONS_RELPATH} entry {entry!r} is missing {missing}. Every "
                f"exemption names the file, the exact matched line, and why the "
                f"doubled escape is correct there."
            )
    return entries


def apply_exemptions(
    hits: list[tuple[str, int, str]], entries: list[dict[str, str]]
) -> tuple[list[tuple[str, int, str]], list[dict[str, str]]]:
    """Split hits into unexcused ones and report exemptions that matched nothing.

    An exemption is pinned to the file AND the exact line text, so it cannot
    quietly widen into a whole-file allowance as the template changes around it.
    """
    excused_index = {(entry["file"], entry["snippet"]) for entry in entries}
    unexcused = [hit for hit in hits if (hit[0], hit[2]) not in excused_index]
    matched = {(hit[0], hit[2]) for hit in hits}
    stale = [
        entry for entry in entries if (entry["file"], entry["snippet"]) not in matched
    ]
    return unexcused, stale


def self_test() -> int:
    """Prove the detector fires on a planted escape and stays quiet otherwise.

    Covers all three run lengths, because the run length IS the rule: one
    backslash is the correct escape, two are the defect, four are a deliberate
    deeper escape. A detector that cannot tell them apart would either miss the
    defect or flag correct code until someone exempted it away.
    """
    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "clean.py.j2")
        with open(clean, "w", encoding="utf-8") as handle:
            handle.write('body = "first\\nsecond"\n')
        if scan_files([clean], tmp):
            print("SELF-TEST FAILED: a correct single-backslash escape was flagged")
            return 1

        deliberate = os.path.join(tmp, "deliberate.py.j2")
        with open(deliberate, "w", encoding="utf-8") as handle:
            handle.write('emitted = "printf %s\\\\\\\\n"\n')
        if scan_files([deliberate], tmp):
            print("SELF-TEST FAILED: a deliberate four-backslash escape was flagged")
            return 1

        dirty = os.path.join(tmp, "dirty.py.j2")
        with open(dirty, "w", encoding="utf-8") as handle:
            handle.write('body = "first\\\\nsecond"\n')
        found = scan_files([dirty], tmp)
        if len(found) != 1:
            print(
                f"SELF-TEST FAILED: expected exactly 1 hit on a planted escaped "
                f"escape, got {len(found)}"
            )
            return 1

        if not _unreadable_template_stops_the_scan(tmp):
            print("SELF-TEST FAILED: a template that cannot be read was skipped instead of stopping the scan")
            return 1

    print(
        "INFO: Non-vacuity self-test passed: the detector flags a doubled escape, "
        "leaves a single and a quadrupled one alone, and stops on a template it cannot read."
    )
    return 0


def _unreadable_template_stops_the_scan(directory: str) -> bool:
    """True when scanning a path that cannot be read as a file raises `TemplateReadError`."""
    unreadable = os.path.join(directory, "unreadable.py.j2")
    os.mkdir(unreadable)
    try:
        scan_files([unreadable], directory)
    except TemplateReadError:
        return True
    return False


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/emitted-escape-integrity-gate.ps1``: one per wrapper parameter,
    spelled exactly. The wrapper declares no ``-Dbg``, so ``args.debug`` is always False."""
    return base_dir_gate_parser(
        WRAPPER, "Fail if a Python-emitting Jinja template escapes an escape sequence.", debug=False
    )


def _run(args: argparse.Namespace) -> int:
    """Run the self-test, then scan every Python-emitting template (exit codes in the module docstring)."""
    if args.self_test:
        if self_test() != EXIT_PASS:
            return EXIT_VIOLATION
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )

    if self_test() != EXIT_PASS:
        return EXIT_USAGE

    base_dir = args.base_dir or DEFAULT_BASE_DIR
    templates = discover_templates(base_dir)
    if not templates:
        print(
            f"ERROR: no '{TEMPLATE_SUFFIX}' templates found under {base_dir}. The "
            f"scan would pass vacuously, so this is a failure, not a clean result."
        )
        return EXIT_USAGE

    if args.show_files:
        for path in templates:
            print(f"  scanning {_norm(path, base_dir)}")

    try:
        entries = load_exemptions(base_dir)
    except (OSError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return EXIT_USAGE
    return _report(templates, entries, base_dir)


def _report(templates: list[str], entries: list[dict[str, str]], base_dir: str) -> int:
    """Scan *templates* against the exemption *entries* and print the verdict; 1 on a hit or a stale entry,
    2 on a template that cannot be read."""
    try:
        hits = scan_files(templates, base_dir)
    except TemplateReadError as exc:
        print(f"ERROR: {exc}")
        return EXIT_USAGE
    unexcused, stale = apply_exemptions(hits, entries)

    if stale:
        print(f"ERROR: {len(stale)} exemption(s) match nothing in the tree:")
        for entry in stale:
            print(f"  {entry['file']}: {entry['snippet']}")
        print("\nThe defect they excused is gone. Remove each entry.")
        return EXIT_VIOLATION

    if not unexcused:
        print(
            f"INFO: {len(templates)} Python-emitting template(s) scanned, "
            f"{len(entries)} reviewed exemption(s), 0 escaped escapes."
        )
        print("Emitted-escape integrity check passed")
        return EXIT_PASS

    print(f"ERROR: {len(unexcused)} escaped escape(s) in Python-emitting templates:")
    for rel, lineno, line in unexcused:
        print(f"  {rel}:{lineno}: {line[:160]}")
    print(
        "\nJinja copies template text verbatim, so a doubled backslash here reaches "
        "the emitted Python as two literal characters -- the generated program then "
        "builds a string carrying a backslash where a line break was meant. Write a "
        "single backslash. If the doubling is deliberate, add a reviewed entry to "
        f"{EXEMPTIONS_RELPATH}."
    )
    return EXIT_VIOLATION


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
