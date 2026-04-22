#!/usr/bin/env python3
"""Summarize pylint R0801 duplicate-code text output into an insights markdown report."""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path


def parse_clusters(text: str) -> list[tuple[str, str, str, str, int, int]]:
    """Return list of (pkg1, mod1, pkg2, mod2, lines1, lines2) per duplicate cluster."""
    pat = re.compile(
        r"^==(datrix_\w+)\.([^:\[]+):\[(\d+):(\d+)\]\s*\n"
        r"==(?P<pkg2>datrix_\w+)\.(?P<mod2>[^:\[]+):\[(?P<a2>\d+):(?P<b2>\d+)\]",
        re.MULTILINE,
    )
    out: list[tuple[str, str, str, str, int, int]] = []
    for m in pat.finditer(text):
        pkg1, mod1, a1, b1 = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        pkg2 = m.group("pkg2")
        mod2 = m.group("mod2")
        a2, b2 = int(m.group("a2")), int(m.group("b2"))
        out.append((pkg1, mod1, pkg2, mod2, b1 - a1 + 1, b2 - a2 + 1))
    return out


def norm_pair(pkg1: str, pkg2: str) -> tuple[str, str]:
    return (pkg1, pkg2) if pkg1 <= pkg2 else (pkg2, pkg1)


def top_area(mod: str) -> str:
    if ".transpiler." in mod or mod.startswith("transpiler."):
        return "transpiler"
    if ".generators.api." in mod or mod.startswith("generators.api."):
        return "generators.api"
    if ".generators.service." in mod or mod.startswith("generators.service."):
        return "generators.service"
    if ".generators.persistence." in mod:
        return "generators.persistence"
    if ".generators.messaging." in mod:
        return "generators.messaging"
    if ".generators.entity." in mod:
        return "generators.entity"
    if ".generators.cross_cutting." in mod:
        return "generators.cross_cutting"
    if "registry" in mod:
        return "registry"
    if ".generators." in mod:
        return "generators.other"
    return "other"


def render_markdown(
    clusters: list[tuple[str, str, str, str, int, int]],
    source_dump: Path,
    min_lines_note: str,
) -> str:
    n = len(clusters)
    pair_counts: Counter[tuple[str, str]] = Counter()
    same_pkg_area: Counter[str] = Counter()
    cross_lang = 0
    approx_dup_lines = 0

    for pkg1, mod1, pkg2, mod2, ln1, ln2 in clusters:
        pair_counts[norm_pair(pkg1, pkg2)] += 1
        approx_dup_lines += min(ln1, ln2)
        p1, p2 = norm_pair(pkg1, pkg2)
        if {p1, p2} == {"datrix_codegen_python", "datrix_codegen_typescript"}:
            cross_lang += 1
        if pkg1 == pkg2:
            same_pkg_area[top_area(mod1) + " <-> " + top_area(mod2)] += 1

    lines: list[str] = []
    lines.append("# Repeating code patterns — insights report\n\n")
    lines.append(
        f"**Source:** `{source_dump.as_posix()}` (pylint R0801 duplicate-code, mono scan). "
        f"**Clusters analyzed:** {n}. {min_lines_note}\n"
    )
    lines.append(
        "_Pylint attributes each cluster to a synthetic module (`datrix_extensions.geo.__init__`); "
        "ignore that path — the real pair is in the `==package.module:[start:end]` lines below each hit in the dump._\n\n"
    )

    lines.append("## Executive summary\n\n")
    lines.append(
        f"The monorepo contains **{n}** separate duplicate-code clusters (pairs of regions with "
        f"≥ configured similar lines). Roughly **{cross_lang}** of those ({100 * cross_lang // max(n, 1)}%) are "
        "**Python vs TypeScript** under `datrix-codegen-python` and `datrix-codegen-typescript` — the same "
        "logical generators and transpilers implemented twice for two output languages.\n\n"
    )
    lines.append(
        "That is the dominant story: repetition is largely **structural parallelism between language backends**, "
        "not random copy-paste. A smaller slice is **cross-platform manifests** (e.g. Docker vs Kubernetes) and "
        "**intra-package** repetition (multiple GraphQL or API test modules in Python, or two TypeScript generators).\n\n"
    )

    lines.append("## What kind of repetition is this?\n\n")
    lines.append("| Kind | Meaning | Typical consolidation |\n")
    lines.append("|------|---------|------------------------|\n")
    lines.append(
        "| **Dual-target codegen** | Same feature implemented in Python and TS generators/transpilers | "
        "Language-agnostic IR or template data built once, thin per-language emitters; or accept drift cost |\n"
    )
    lines.append(
        "| **Platform twins** | Docker vs K8s (or AWS vs Azure) sharing PromQL, alerts, or doc stubs | "
        "Shared tables/helpers in `datrix-common` or `datrix-codegen-component` |\n"
    )
    lines.append(
        "| **Same-language, nearby modules** | e.g. multiple `graphql_*` or `_api_test_mixin_*` files in Python | "
        "Private shared helper module within the package |\n"
    )
    lines.append(
        "| **Re-export / string list** | e.g. `datrix_common.__init__` vs `utils.text` `__all__`-style lists | "
        "Single source of exported names |\n\n"
    )

    lines.append("## Package pairs (how often two packages overlap)\n\n")
    lines.append("| Package A | Package B | Clusters |\n")
    lines.append("|-----------|-----------|----------|\n")
    for (pa, pb), cnt in pair_counts.most_common(15):
        lines.append(f"| `{pa}` | `{pb}` | {cnt} |\n")
    if len(pair_counts) > 15:
        lines.append(f"| … | … | _{len(pair_counts) - 15} more pair types_ |\n")

    if same_pkg_area:
        lines.append("\n## Same-package clusters by rough area (both ends in one package)\n\n")
        lines.append("| Area pairing | Clusters |\n")
        lines.append("|--------------|----------|\n")
        for area, cnt in same_pkg_area.most_common(12):
            lines.append(f"| {area} | {cnt} |\n")

    lines.append("\n## What would actually “save” maintenance?\n\n")
    lines.append(
        "1. **Python + TypeScript mirrors (~bulk of hits):** merging files is usually wrong; the win is **one "
        "specification of behavior** (data structures, ordered steps, Jinja context keys) with two small printers. "
        "That reduces bug fixes applied twice and keeps outputs aligned.\n"
    )
    lines.append(
        "2. **Transpiler family (`_entity_query_*`, `special_calls`, `_transpiler_expressions`):** many clusters — "
        "extracting a **shared decision tree** (e.g. method name → handler id) into `datrix-common` or a tiny "
        "shared package used by both transpilers removes the highest-churn duplicate surface.\n"
    )
    lines.append(
        "3. **`doc_generator` / `registry`:** repeated registration and doc context shapes suggest **tables or "
        "builders** generated once or defined declaratively instead of parallel imperative blocks.\n"
    )
    lines.append(
        "4. **Observability / PromQL (Docker vs K8s):** one module of **aggregation → PromQL string** rules consumed "
        "by both platform generators removes manifest drift.\n"
    )
    lines.append(
        "5. **Low-risk cleanups:** `datrix_common` export lists vs `utils.text`, and any **identical line ranges** "
        "inside one language — merge helpers before touching cross-language pairs.\n"
    )

    lines.append("\n## Rough duplicate volume (order of magnitude)\n\n")
    lines.append(
        f"Summing `min(region_lines_A, region_lines_B)` per cluster gives about **{approx_dup_lines}** lines "
        "of _paired_ similar text (not net LOC removed after deduplication — consolidation rarely deletes 100%).\n"
    )

    lines.append("\n## Raw evidence\n\n")
    lines.append(
        f"See `{source_dump.name}` for every pylint snippet and line range. Re-run: "
        f"`datrix/scripts/metrics/duplicate.ps1 -Mono -MinLines 6` then regenerate this file with "
        f"`python datrix/scripts/library/metrics/duplicate_insights.py` "
        f"(from monorepo root; optional `--input` / `--output`).\n"
    )
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build insights markdown from R0801 text dump.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("reports/repeating-patterns-duplicates.txt"),
        help="Path to pylint duplicate text output",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/repeating-patterns-insights.md"),
        help="Path to write markdown (default under Datrix root)",
    )
    parser.add_argument(
        "--min-lines-note",
        default="Threshold was whatever you passed to duplicate.ps1 (`-MinLines`; mono run uses that value).",
        help="Sentence inserted into the report header",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[4]
    inp = args.input if args.input.is_absolute() else root / args.input
    out = args.output if args.output.is_absolute() else root / args.output

    text = inp.read_text(encoding="utf-8")
    clusters = parse_clusters(text)
    md = render_markdown(clusters, inp, args.min_lines_note)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out} ({len(clusters)} clusters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
