#!/usr/bin/env python3
"""One-shot silent-fallback audit: Semgrep + LibCST + .j2 scan → markdown report.

Writes ``<datrix-root>/silent-fallback-audit-report.md`` (overwrites).
Requires ``semgrep`` on PATH (e.g. venv ``Scripts``). Run:

    python scripts/library/dev/silent_fallback_audit_report.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

_LIBRARY = Path(__file__).resolve().parent.parent
if str(_LIBRARY) not in sys.path:
    sys.path.insert(0, str(_LIBRARY))

from dev.libcst_scanner import resolve_scan_paths, scan_directory  # noqa: E402
from dev.semgrep_scanner import (  # noqa: E402
    resolve_rule_paths,
    resolve_scan_targets,
    scan_with_rules,
)
from shared.venv import get_datrix_root  # noqa: E402

PROJECTS = [
    "datrix-cli",
    "datrix-codegen-aws",
    "datrix-codegen-azure",
    "datrix-codegen-component",
    "datrix-codegen-docker",
    "datrix-codegen-k8s",
    "datrix-codegen-python",
    "datrix-codegen-sql",
    "datrix-codegen-typescript",
    "datrix-common",
    "datrix-extensions",
    "datrix-language",
]

SEMGREP_RULES = [
    "silent-fallback-none",
    "default-type-mapping",
    "return-none-lookup",
]

_J2_FALLBACK = re.compile(r"\?\?|\|\||\.catch\(")


def _package_from_rel(rel: str) -> str:
    parts = rel.replace("\\", "/").split("/")
    return parts[0] if parts else "unknown"


def _excerpt(abs_path: Path, line_no: int, width: int = 120) -> str:
    try:
        file_lines = abs_path.read_text(encoding="utf-8").splitlines()
        idx = line_no - 1
        if 0 <= idx < len(file_lines):
            s = file_lines[idx].strip()
            if len(s) > width:
                return s[: width - 3] + "..."
            return s
    except OSError:
        pass
    return "(could not read line)"


def _scan_j2_under_src(datrix_root: Path) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for pkg in PROJECTS:
        src = datrix_root / pkg / "src"
        if not src.is_dir():
            continue
        for path in sorted(src.rglob("*.j2")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            rel = str(path.relative_to(datrix_root)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), start=1):
                if _J2_FALLBACK.search(line):
                    hits.append((rel, i, line.strip()[:200]))
    return hits


def main() -> int:
    datrix_root = get_datrix_root()
    out_path = datrix_root / "silent-fallback-audit-report.md"

    targets = resolve_scan_targets(datrix_root, PROJECTS, scan_all=False)
    rule_paths = resolve_rule_paths(SEMGREP_RULES)

    print("Semgrep (single-pass)...", flush=True)
    semgrep_findings, semgrep_errors = scan_with_rules(
        rule_paths,
        targets,
        verbose=False,
        single_pass=True,
    )

    print("LibCST (silent-fallback only)...", flush=True)
    scan_pairs = resolve_scan_paths(datrix_root, PROJECTS, scan_all=False)
    libcst_silent: list[tuple[str, int, str]] = []
    for _name, directory in scan_pairs:
        result = scan_directory(directory, datrix_root)
        for f in result.findings:
            if f.rule == "silent-fallback":
                libcst_silent.append((f.file.replace("\\", "/"), f.line, f.message))

    libcst_by_key = {(f[0], f[1]) for f in libcst_silent}

    print("Scanning *.j2 under */src...", flush=True)
    j2_hits = _scan_j2_under_src(datrix_root)

    semgrep_none_keys: set[tuple[str, int]] = set()
    for h in semgrep_findings:
        cid = h.get("check_id", "")
        if "silent-fallback-none" not in cid:
            continue
        p = Path(h.get("path", ""))
        try:
            rel = str(p.resolve().relative_to(datrix_root)).replace("\\", "/")
        except ValueError:
            rel = str(p).replace("\\", "/")
        line = int(h.get("start", {}).get("line", 0))
        semgrep_none_keys.add((rel, line))

    only_semgrep = semgrep_none_keys - libcst_by_key
    only_libcst = libcst_by_key - semgrep_none_keys

    by_rule: dict[str, list[dict]] = defaultdict(list)
    for h in semgrep_findings:
        by_rule[h.get("check_id", "unknown")].append(h)

    by_pkg_rule: dict[tuple[str, str], int] = defaultdict(int)
    for h in semgrep_findings:
        p = Path(h.get("path", ""))
        try:
            rel = str(p.resolve().relative_to(datrix_root)).replace("\\", "/")
        except ValueError:
            rel = str(p)
        pkg = _package_from_rel(rel)
        by_pkg_rule[(pkg, h.get("check_id", "?"))] += 1

    lines: list[str] = []
    lines.append("# Silent fallback audit report\n\n")
    lines.append(
        "Mechanical matches for Datrix fail-fast rules (see `.cursorrules`). "
        "Humans should triage before changing code.\n\n"
    )
    lines.append("- **Output:** `silent-fallback-audit-report.md` at monorepo root\n")
    lines.append("- **Script:** `datrix/scripts/library/dev/silent_fallback_audit_report.py`\n")
    lines.append(f"- **Monorepo root:** `{datrix_root}`\n")
    lines.append(f"- **Packages:** {', '.join(PROJECTS)}\n")
    lines.append(f"- **Semgrep rules:** {', '.join(SEMGREP_RULES)} (single-pass scan)\n")
    lines.append("- **LibCST:** `silent-fallback` only (`.get(..., None)`)\n")
    lines.append(
        "- **Templates:** `*.j2` under each package `src/` matching `??`, `||`, or `.catch(` "
        "(manual triage)\n\n"
    )

    lines.append("## Summary\n\n")
    lines.append(f"- **Semgrep findings (total):** {len(semgrep_findings)}\n")
    lines.append(f"- **Semgrep errors:** {len(semgrep_errors)}\n")
    lines.append(f"- **LibCST silent-fallback hits:** {len(libcst_silent)}\n")
    lines.append(f"- **`.j2` template lines flagged:** {len(j2_hits)}\n\n")

    lines.append("### Semgrep counts by rule\n\n")
    for cid in sorted(by_rule, key=lambda x: (x.split(".")[-1], x)):
        lines.append(f"- `{cid}`: **{len(by_rule[cid])}**\n")
    lines.append("\n### Semgrep counts by package (all rules)\n\n")
    pkgs_sorted = sorted({p for (p, _) in by_pkg_rule})
    for pkg in pkgs_sorted:
        subtotal = sum(c for (p, _), c in by_pkg_rule.items() if p == pkg)
        lines.append(f"- **{pkg}** ({subtotal} total)\n")
        for (p, cid), c in sorted(by_pkg_rule.items()):
            if p != pkg:
                continue
            short = cid.split(".")[-1] if "." in cid else cid
            lines.append(f"  - `{short}`: {c}\n")
    lines.append("\n")

    lines.append("## Semgrep / LibCST drift (`.get(..., None)` only)\n\n")
    lines.append(
        "Semgrep `silent-fallback-none` vs LibCST `silent-fallback` should largely overlap; "
        "small differences can come from pattern edge cases.\n\n"
    )
    lines.append(f"- **In Semgrep only:** {len(only_semgrep)}\n")
    lines.append(f"- **In LibCST only:** {len(only_libcst)}\n\n")
    if only_semgrep and len(only_semgrep) <= 40:
        lines.append("### Semgrep-only keys `(file, line)`\n\n")
        for k in sorted(only_semgrep):
            lines.append(f"- `{k[0]}:{k[1]}`\n")
        lines.append("\n")
    elif only_semgrep:
        lines.append("(More than 40 Semgrep-only keys; omitted for brevity.)\n\n")
    if only_libcst and len(only_libcst) <= 40:
        lines.append("### LibCST-only keys `(file, line)`\n\n")
        for k in sorted(only_libcst):
            lines.append(f"- `{k[0]}:{k[1]}`\n")
        lines.append("\n")
    elif only_libcst:
        lines.append("(More than 40 LibCST-only keys; omitted for brevity.)\n\n")

    lines.append("## Semgrep findings (detail)\n\n")
    for cid in sorted(by_rule, key=lambda x: (x.split(".")[-1], x)):
        hits = by_rule[cid]
        sev = hits[0].get("extra", {}).get("severity", "?") if hits else "?"
        lines.append(f"### `{cid}` [{sev}] ({len(hits)})\n\n")
        for h in sorted(hits, key=lambda x: (x.get("path", ""), x.get("start", {}).get("line", 0))):
            p = Path(h.get("path", ""))
            try:
                rel = str(p.resolve().relative_to(datrix_root)).replace("\\", "/")
            except ValueError:
                rel = str(p)
            ln = int(h.get("start", {}).get("line", 0))
            msg = (h.get("extra", {}) or {}).get("message", "").strip().replace("\n", " ")
            abs_p = p if p.is_absolute() else (datrix_root / rel)
            ex = _excerpt(abs_p, ln)
            lines.append(f"- `{rel}:{ln}` — {msg}\n")
            lines.append(f"  - excerpt: `{ex}`\n")
        lines.append("\n")

    if semgrep_errors:
        lines.append(f"## Semgrep engine messages ({len(semgrep_errors)})\n\n")
        lines.append(
            "These are **not** silent-fallback findings. They are Semgrep parse or "
            "skip notifications (e.g. Python version / tree-sitter mismatch). "
            "Rule matches in the sections above still come from successfully parsed targets.\n\n"
        )
        paths: set[str] = set()
        for err in semgrep_errors:
            p = err.get("path")
            if isinstance(p, str) and p:
                try:
                    paths.add(
                        str(Path(p).resolve().relative_to(datrix_root)).replace("\\", "/")
                    )
                except ValueError:
                    paths.add(p.replace("\\", "/"))
        sample = sorted(paths)[:25]
        lines.append(f"- **Distinct paths mentioned:** {len(paths)}\n")
        for s in sample:
            lines.append(f"  - `{s}`\n")
        if len(paths) > len(sample):
            lines.append(f"  - … and {len(paths) - len(sample)} more\n")
        lines.append("\n")

    lines.append("## LibCST: silent-fallback only\n\n")
    for file, line, msg in sorted(libcst_silent):
        abs_p = datrix_root / file
        ex = _excerpt(abs_p, line)
        lines.append(f"- `{file}:{line}` — {msg}\n")
        lines.append(f"  - excerpt: `{ex}`\n")
    if not libcst_silent:
        lines.append("_No LibCST silent-fallback hits._\n")
    lines.append("\n")

    lines.append("## Appendix: `*.j2` lines (`??` / `||` / `.catch(`)\n\n")
    lines.append("_Manual triage; many matches are benign in templates._\n\n")
    for rel, ln, content in j2_hits:
        lines.append(f"- `{rel}:{ln}` — `{content}`\n")
    if not j2_hits:
        lines.append("_No lines matched._\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
