#!/usr/bin/env python3
"""Generate ``@test-rule`` conformance annotations for test functions via a local LLM.

Walks each package's ``tests/`` tree, finds un-annotated test functions, and asks a
local Ollama model to decide whether the test encodes a cross-target *conformance
rule* and, if so, to emit a structured marker (topic / dimensions / behavior /
differs / see). Results are written as reviewable proposals; a second ``--apply``
run inserts the reviewed markers above the test functions.

The markers feed the logic-map Rule Matrix (see logic_map.py / logic_map_report.py):
the shared ``topic`` joins a rule across targets, and ``@dim`` (open vocabulary —
language=, provider=, runtime=, variant=, ...) is the matrix column.

Two phases (never mutates source except under --apply):

    propose (default):
        python generate_test_rules.py --all
        python generate_test_rules.py datrix-codegen-python --limit 20
        -> .test-output/test-rules/<package>.json   (proposals)
        -> .test-output/test-rules/<package>.md      (human preview)

    apply:
        python generate_test_rules.py datrix-codegen-python --apply
        -> inserts reviewed @test-rule blocks above each test function

Or use the PowerShell wrapper:
        .\\scripts\\dev\\generate-test-rules.ps1 datrix-codegen-python
        .\\scripts\\dev\\generate-test-rules.ps1 datrix-codegen-python -Apply
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import logging
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root  # noqa: E402
from dev.logic_map import iter_python_files, resolve_scan_paths  # noqa: E402

LOG = logging.getLogger("generate_test_rules")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT = "http://10.94.0.100:11434"
DEFAULT_MODEL = "exaone-deep:32b"
DEFAULT_PARALLEL = 4
DEFAULT_NUM_CTX = 32768
DEFAULT_TIMEOUT_S = 240

# Test directories excluded by default (slow / cross-cutting; few per-target rules).
# Opt back in with --include-e2e / --include-integration, or target them via --path.
_DEFAULT_EXCLUDED_DIRS = frozenset({"e2e", "integration"})

# Write the .json + .md to disk every N completed functions (resumable checkpoint).
_CHECKPOINT_EVERY = 5

_OUTPUT_BASE = Path(".test-output") / "test-rules"


def _model_slug(model: str) -> str:
    """Filesystem-safe slug for a model (e.g. 'exaone-deep:32b' -> 'exaone-deep-32b')."""
    return "".join(c if c.isalnum() else "-" for c in model.lower()).strip("-")


def _output_dir(datrix_root: Path, model: str) -> Path:
    """Per-model proposal directory so different models' runs don't clobber each other."""
    return datrix_root / _OUTPUT_BASE / _model_slug(model)

# JSON schema constraining the model's response (Ollama grammar-constrained output).
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "topic": {"type": "string"},
        "summary": {"type": "string"},
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                "required": ["key", "value"],
            },
        },
        "behavior": {"type": "string"},
        "differs": {"type": "string"},
        "see": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["applicable", "topic", "summary", "dimensions", "behavior"],
}

_SYSTEM_PROMPT = """\
You annotate Python TEST functions for the Datrix code generator with "@test-rule" \
conformance markers. Datrix is a multi-language, multi-platform generator (many target \
languages and platforms — NOT limited to Python/TypeScript or AWS/Azure).

A @test-rule records a RULE the test enforces about generated output, so the same rule \
can be compared across targets in a matrix. You must decide, per test:

1. applicable (boolean): true ONLY if the test asserts a meaningful behavioral/conformance \
   rule about generated code or the generator's contract (e.g. how an operator maps, what a \
   type becomes, an invariant of emitted code, a provider/runtime-specific behavior). \
   Set false for mechanical/coverage/smoke tests, fixture wiring, error-message text checks, \
   import guards, or anything that does not encode a target-comparable rule. When false, the \
   other fields are ignored — still return them (empty is fine).

2. topic: a short stable slug "area/subarea" identifying the RULE independent of target \
   (e.g. "operators/equality", "types/decimal-mapping"). REUSE a listed topic ONLY when the \
   test concerns the SAME rule — identical topics are how targets line up in the matrix. NEVER \
   force an unrelated test under a listed topic just because it exists; when no listed topic \
   genuinely describes the same rule, invent a new precise slug. The topic must match the \
   summary/behavior you give.

3. summary: one concise sentence describing the rule (target-independent).

4. dimensions: the target this test pins, as key=value pairs. Open vocabulary. Use what fits: \
   language=<lang>, provider=<provider>, runtime=<runtime>, variant=<variant>. Derive from the \
   package and the test content. Most tests have exactly one dimension.

5. behavior: the concrete target-specific expected outcome this test asserts (the matrix cell). \
   Be specific and short (e.g. "== -> ===, != -> !==").

6. differs (optional): brief note on how this likely differs for other targets.

7. see (optional): related topic slugs.

Rules: Output ONLY the JSON object. Keep strings short. Use NEUTRAL domain terms only \
(Product/Order/Customer/Warehouse) — never customer/project domain words. Do not restate code.\
"""


# ---------------------------------------------------------------------------
# JSON coercion helpers (model output / proposal files are untrusted)
# ---------------------------------------------------------------------------

def _oneline(text: str) -> str:
    """Collapse all whitespace (incl. newlines) to single spaces.

    A marker field with an embedded newline would otherwise render as a bare,
    non-comment line and break the test file's Python syntax.
    """
    return " ".join(text.split())


def _as_int(value: object) -> int:
    """Coerce a JSON value to int (0 on anything non-numeric)."""
    return int(value) if isinstance(value, (int, str)) and str(value).lstrip("-").isdigit() else 0


def _as_str_list(value: object) -> list[str]:
    """Coerce a JSON value to a list of stripped non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(s).strip() for s in value if str(s).strip()]


def _as_pairs(value: object) -> list[tuple[str, str]]:
    """Coerce a JSON value to a list of (key, value) string pairs.

    Accepts both [[k, v], ...] (from proposal files) and [{"key":k,"value":v}, ...]
    (from model output).
    """
    out: list[tuple[str, str]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if isinstance(item, dict) and item.get("key") and item.get("value"):
            out.append(_norm_pair(str(item["key"]), str(item["value"])))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            out.append(_norm_pair(str(item[0]), str(item[1])))
    return out


def _norm_pair(key: str, value: str) -> tuple[str, str]:
    """Normalize a dimension to a lowercase slug so matrix columns align.

    `language=TypeScript` and `language=typescript` must map to one target.
    """
    return (key.strip().lower(), value.strip().lower())


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TestFunc:
    """A discovered test function awaiting annotation."""

    name: str
    qualname: str          # "Class.method" or bare function name
    class_name: str
    class_doc: str
    def_line: int          # 1-based line of the `def` keyword
    col: int               # indentation (col_offset of the def)
    source: str            # full source segment incl. decorators


@dataclass
class Proposal:
    """A generated annotation proposal for one test function."""

    file: str
    qualname: str
    name: str
    def_line: int
    col: int
    applicable: bool
    topic: str = ""
    summary: str = ""
    dimensions: list[tuple[str, str]] = field(default_factory=list)
    behavior: str = ""
    differs: str = ""
    see: list[str] = field(default_factory=list)
    error: str = ""

    def key(self) -> str:
        """Stable identity for resume/dedupe (file + function qualname)."""
        return f"{self.file}::{self.qualname}"

    def to_json(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict."""
        return {
            "file": self.file,
            "qualname": self.qualname,
            "name": self.name,
            "def_line": self.def_line,
            "col": self.col,
            "applicable": self.applicable,
            "topic": self.topic,
            "summary": self.summary,
            "dimensions": [list(d) for d in self.dimensions],
            "behavior": self.behavior,
            "differs": self.differs,
            "see": self.see,
            "error": self.error,
        }

    @staticmethod
    def from_json(d: dict[str, object]) -> Proposal:
        """Rebuild a Proposal from its serialized dict."""
        return Proposal(
            file=str(d.get("file", "")),
            qualname=str(d.get("qualname", "")),
            name=str(d.get("name", "")),
            def_line=_as_int(d.get("def_line")),
            col=_as_int(d.get("col")),
            applicable=bool(d.get("applicable")),
            topic=str(d.get("topic", "")),
            summary=str(d.get("summary", "")),
            dimensions=_as_pairs(d.get("dimensions")),
            behavior=str(d.get("behavior", "")),
            differs=str(d.get("differs", "")),
            see=_as_str_list(d.get("see")),
            error=str(d.get("error", "")),
        )


# ---------------------------------------------------------------------------
# Discovery (AST)
# ---------------------------------------------------------------------------

def discover_test_functions(text: str) -> list[TestFunc]:
    """Find all ``test*`` functions (module-level or in any class) via AST.

    Args:
        text: Full source of one Python file.

    Returns:
        Discovered test functions (empty on syntax error).
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    out: list[TestFunc] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _append_func(out, node, text, "", "")
        elif isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node) or ""
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _append_func(out, sub, text, node.name, class_doc)
    return out


def _append_func(
    out: list[TestFunc],
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    text: str,
    class_name: str,
    class_doc: str,
) -> None:
    """Append a TestFunc for ``node`` if it is a test function."""
    if not node.name.startswith("test"):
        return
    qual = f"{class_name}.{node.name}" if class_name else node.name
    out.append(TestFunc(
        name=node.name,
        qualname=qual,
        class_name=class_name,
        class_doc=class_doc,
        def_line=node.lineno,          # py3.8+: the `def` line, decorators excluded
        col=node.col_offset,
        source=ast.get_source_segment(text, node) or "",
    ))


def already_annotated(lines: list[str], def_line: int) -> bool:
    """Whether a ``@test-rule`` block already sits above the def (past decorators).

    Args:
        lines: File lines (no trailing newlines).
        def_line: 1-based line of the ``def`` keyword.

    Returns:
        True if an existing test-rule marker precedes the function.
    """
    idx = def_line - 2  # line directly above the def (0-based)
    while idx >= 0:
        s = lines[idx].strip()
        if s.startswith("#"):
            if "@test-rule(" in s:
                return True
            idx -= 1
            continue
        if s.startswith("@") or s == "":  # skip decorators / blank lines
            idx -= 1
            continue
        break
    return False


# ---------------------------------------------------------------------------
# LLM client (Ollama)
# ---------------------------------------------------------------------------

def _extract_json_object(content: str) -> dict[str, object]:
    """Parse a JSON object from model output, tolerating leading/trailing text."""
    content = content.strip()
    obj: object
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end <= start:
            raise
        obj = json.loads(content[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("model did not return a JSON object")
    return obj


def call_ollama(
    endpoint: str,
    model: str,
    user_prompt: str,
    *,
    timeout: int,
    num_ctx: int,
    system: str = _SYSTEM_PROMPT,
    schema: dict[str, object] | None = None,
) -> dict[str, object]:
    """Call Ollama ``/api/chat`` with a JSON-schema-constrained response.

    Args:
        endpoint: Base URL, e.g. http://10.94.0.100:11434.
        model: Ollama model name.
        user_prompt: The user message.
        timeout: Socket timeout in seconds.
        num_ctx: Context window for the request.
        system: System prompt (defaults to the annotation prompt).
        schema: Response JSON schema (defaults to _RESPONSE_SCHEMA).

    Returns:
        Parsed response object matching the schema.
    """
    url = endpoint.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": schema if schema is not None else _RESPONSE_SCHEMA,
        "options": {"temperature": 0.1, "num_ctx": num_ctx},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = str(data.get("message", {}).get("content", ""))
    return _extract_json_object(content)


def build_user_prompt(pkg: str, rel: str, tf: TestFunc, known_topics: list[str]) -> str:
    """Assemble the user message for one test function."""
    topics = "\n".join(f"  - {t}" for t in known_topics) or "  (none yet)"
    context = f"Class: {tf.class_name}\nClass docstring: {tf.class_doc}\n" if tf.class_name else ""
    return (
        f"Package: {pkg}\n"
        f"File: {rel}\n"
        f"{context}"
        f"\nExisting rule topics to REUSE when applicable:\n{topics}\n"
        f"\nTest function source:\n```python\n{tf.source}\n```\n"
    )


# ---------------------------------------------------------------------------
# Marker rendering
# ---------------------------------------------------------------------------

def render_marker(prop: Proposal) -> list[str]:
    """Render the ready-to-insert comment lines for an applicable proposal."""
    ind = " " * prop.col
    lines = [f"{ind}# @test-rule({_oneline(prop.topic)}): {_oneline(prop.summary)}"]
    lines.extend(f"{ind}# @dim: {_oneline(k)}={_oneline(v)}" for k, v in prop.dimensions)
    if prop.behavior:
        lines.append(f"{ind}# @behavior: {_oneline(prop.behavior)}")
    if prop.differs:
        lines.append(f"{ind}# @differs: {_oneline(prop.differs)}")
    lines.extend(f"{ind}# @see: {_oneline(ref)}" for ref in prop.see)
    return lines


# ---------------------------------------------------------------------------
# Topic consolidation (second pass)
# ---------------------------------------------------------------------------

_CONSOLIDATE_SYSTEM = """\
You merge a list of rule-topic slugs into a canonical taxonomy for a multi-target code \
generator. The slugs were generated independently per test, so there are near-duplicates \
and synonyms (e.g. "datetime/methods" and "types/datetime-methods"). Merge slugs that name \
the SAME underlying rule into ONE canonical slug. Rules: prefer an existing anchor slug when \
one fits; keep slugs short kebab-case "area/sub-area"; do NOT over-merge genuinely different \
rules; only emit a merge for a slug that should CHANGE. Output JSON only.\
"""

# Minimum slug-token Jaccard similarity for a model-proposed merge to be accepted.
# Guards against the model collapsing genuinely different rules into one topic.
_MERGE_MIN_SIMILARITY = 0.4

_CONSOLIDATE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "merges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
                "required": ["from", "to"],
            },
        }
    },
    "required": ["merges"],
}


def _kebab_topic(topic: str) -> str:
    """Normalize a topic to lowercase kebab slugs per slash segment."""
    segments = []
    for seg in topic.split("/"):
        slug = seg.strip().lower().replace("_", "-").replace(" ", "-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        slug = slug.strip("-")
        if slug:
            segments.append(slug)
    return "/".join(segments)


def _slug_tokens(slug: str) -> set[str]:
    """Tokenize a topic slug on '/' and '-' for similarity comparison."""
    return {t for t in slug.lower().replace("/", "-").split("-") if t}


def _merge_similarity(src: str, dst: str) -> float:
    """Jaccard similarity of two slugs' token sets (0..1)."""
    a, b = _slug_tokens(src), _slug_tokens(dst)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _resolve_topic(topic: str, mapping: dict[str, str]) -> str:
    """Follow a merge chain (A->B->C) to its canonical endpoint, guarding cycles."""
    seen: set[str] = set()
    while topic in mapping and topic not in seen:
        seen.add(topic)
        topic = mapping[topic]
    return topic


def _consolidation_prompt(topics: list[str], anchors: list[str]) -> str:
    """Build the user message for the consolidation pass."""
    anchor_block = "\n".join(f"  - {a}" for a in anchors) or "  (none)"
    topic_block = "\n".join(f"  - {t}" for t in topics)
    return (
        f"Anchor (existing canonical) topics:\n{anchor_block}\n\n"
        f"Proposed topics to consolidate:\n{topic_block}\n\n"
        "Return merges mapping each non-canonical slug to its canonical slug. "
        "Omit slugs that are already canonical."
    )


def consolidate_topics(proposals: list[Proposal], anchors: set[str], cfg: argparse.Namespace) -> dict[str, str]:
    """Ask the model for a merge map over the run's proposed topics (one LLM call)."""
    topics = sorted({p.topic for p in proposals if p.applicable and p.topic})
    if len(topics) < 2:
        return {}
    try:
        result = call_ollama(
            cfg.endpoint, cfg.model, _consolidation_prompt(topics, sorted(anchors)),
            timeout=cfg.timeout, num_ctx=cfg.num_ctx,
            system=_CONSOLIDATE_SYSTEM, schema=_CONSOLIDATE_SCHEMA,
        )
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
        LOG.warning("consolidation pass failed (%s); normalizing slugs only", exc)
        return {}
    merges = result.get("merges", [])
    if not isinstance(merges, list):
        return {}
    mapping: dict[str, str] = {}
    rejected = 0
    for merge in merges:
        if not (isinstance(merge, dict) and merge.get("from") and merge.get("to")):
            continue
        src = str(merge["from"]).strip()
        dst = str(merge["to"]).strip()
        if not (src and dst and src != dst):
            continue
        if _merge_similarity(src, dst) < _MERGE_MIN_SIMILARITY:
            rejected += 1  # guard: model tried to merge genuinely different rules
            continue
        mapping[src] = dst
    if rejected:
        LOG.info("Consolidation guard rejected %d over-broad merge(s)", rejected)
    return mapping


def apply_topic_map(proposals: list[Proposal], mapping: dict[str, str]) -> int:
    """Rewrite topics + see-refs through the merge map and kebab-normalize. Returns changes."""
    changed = 0
    for p in proposals:
        new_topic = _kebab_topic(_resolve_topic(p.topic, mapping))
        if new_topic != p.topic:
            changed += 1
        p.topic = new_topic
        seen: set[str] = set()
        deduped: list[str] = []
        for ref in p.see:
            slug = _kebab_topic(_resolve_topic(ref, mapping))
            if slug and slug != new_topic and slug not in seen:
                seen.add(slug)
                deduped.append(slug)
        p.see = deduped
    return changed


# ---------------------------------------------------------------------------
# Topic seeding
# ---------------------------------------------------------------------------

def seed_topics_from_db(datrix_root: Path) -> set[str]:
    """Seed the topic vocabulary from existing test-rule markers in the logic map."""
    db = datrix_root / ".logic-map" / "markers.db"
    if not db.exists():
        return set()
    try:
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute("SELECT DISTINCT topic FROM markers WHERE kind='test-rule'")
            return {str(r[0]) for r in rows}
        finally:
            conn.close()
    except sqlite3.Error:
        return set()


# ---------------------------------------------------------------------------
# Propose phase
# ---------------------------------------------------------------------------

class _Vocabulary:
    """Thread-safe accumulating set of known rule topics."""

    def __init__(self, seed: set[str]) -> None:
        self._topics = set(seed)
        self._lock = threading.Lock()

    def snapshot(self) -> list[str]:
        with self._lock:
            return sorted(self._topics)

    def add(self, topic: str) -> None:
        if not topic:
            return
        with self._lock:
            self._topics.add(topic)


def _result_to_proposal(rel: str, tf: TestFunc, result: dict[str, object]) -> Proposal:
    """Convert a raw LLM result into a Proposal."""
    topic = _oneline(str(result.get("topic", ""))).lower()
    see = [_oneline(s) for s in _as_str_list(result.get("see")) if _oneline(s).lower() != topic]
    return Proposal(
        file=rel,
        qualname=tf.qualname,
        name=tf.name,
        def_line=tf.def_line,
        col=tf.col,
        applicable=bool(result.get("applicable")),
        topic=topic,
        summary=_oneline(str(result.get("summary", ""))),
        dimensions=_as_pairs(result.get("dimensions")),
        behavior=_oneline(str(result.get("behavior", ""))),
        differs=_oneline(str(result.get("differs", ""))),
        see=see,
    )


def _process_one(
    tf: TestFunc,
    pkg: str,
    rel: str,
    vocab: _Vocabulary,
    cfg: argparse.Namespace,
) -> Proposal:
    """Annotate a single test function (one LLM call). Never raises."""
    try:
        result = call_ollama(
            cfg.endpoint, cfg.model,
            build_user_prompt(pkg, rel, tf, vocab.snapshot()),
            timeout=cfg.timeout, num_ctx=cfg.num_ctx,
        )
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
        LOG.warning("  %s :: %s -> error: %s", rel, tf.qualname, exc)
        return Proposal(file=rel, qualname=tf.qualname, name=tf.name,
                        def_line=tf.def_line, col=tf.col, applicable=False, error=str(exc))
    prop = _result_to_proposal(rel, tf, result)
    if prop.applicable and prop.topic:
        vocab.add(prop.topic)
    return prop


def _resolve_filters(paths: list[str], datrix_root: Path) -> list[Path]:
    """Resolve --path values (relative to datrix root or cwd) to existing paths."""
    out: list[Path] = []
    for p in paths:
        for base in (Path(p), datrix_root / p, Path.cwd() / p):
            if base.exists():
                out.append(base.resolve())
                break
        else:
            LOG.warning("--path not found, ignoring: %s", p)
    return out


def _projects_from_paths(filters: list[Path], datrix_root: Path) -> list[str]:
    """Derive package names (first path segment under the root) from --path values."""
    root = datrix_root.resolve()
    out: set[str] = set()
    for f in filters:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        if rel.parts:
            out.add(rel.parts[0])
    return sorted(out)


def _file_allowed(py_file: Path, filters: list[Path]) -> bool:
    """Whether a file passes the --path filter (no filters = allow all)."""
    if not filters:
        return True
    rp = py_file.resolve()
    return any(rp == f or rp.is_relative_to(f) for f in filters)


def _excluded_segment(py_file: Path, tests_dir: Path, excluded: frozenset[str]) -> str | None:
    """Return the excluded dir segment a file lives under, if any (e.g. 'e2e')."""
    try:
        parts = py_file.resolve().relative_to(tests_dir.resolve()).parts
    except ValueError:
        return None
    return next((seg for seg in parts if seg in excluded), None)


def _gather_pending(
    tests_dir: Path,
    datrix_root: Path,
    done_keys: set[str],
    limit: int,
    filters: list[Path],
    excluded: frozenset[str],
) -> list[tuple[str, TestFunc]]:
    """Collect (rel_path, TestFunc) for un-annotated, not-yet-done test functions."""
    pending: list[tuple[str, TestFunc]] = []
    for py_file in iter_python_files(tests_dir):
        if not _file_allowed(py_file, filters):
            continue
        seg = _excluded_segment(py_file, tests_dir, excluded)
        if seg is not None and not any(seg in f.parts for f in filters):
            continue  # excluded dir, unless an explicit --path reaches into it
        text = py_file.read_text(encoding="utf-8-sig", errors="replace")
        rel = _rel_path(py_file, datrix_root)
        lines = text.splitlines()
        for tf in discover_test_functions(text):
            if already_annotated(lines, tf.def_line):
                continue
            if f"{rel}::{tf.qualname}" in done_keys:
                continue
            pending.append((rel, tf))
            if 0 < limit <= len(pending):
                return pending
    return pending


def propose_package(
    pkg: str,
    tests_dir: Path,
    datrix_root: Path,
    vocab: _Vocabulary,
    cfg: argparse.Namespace,
) -> list[Proposal]:
    """Generate proposals for one package's tests tree (resumable)."""
    out_dir = _output_dir(datrix_root, cfg.model)
    out_json = out_dir / f"{pkg}.json"
    existing = _load_proposals(out_json)
    done_keys = {p.key() for p in existing}
    for p in existing:
        vocab.add(p.topic)

    pending = _gather_pending(
        tests_dir, datrix_root, done_keys, cfg.limit, cfg.filters, cfg.excluded_dirs
    )
    LOG.info("[%s] %d test function(s) to annotate (%d already done)", pkg, len(pending), len(existing))

    results: list[Proposal] = list(existing)
    if not pending:
        return results

    completed = 0
    out_md = out_dir / f"{pkg}.md"
    with ThreadPoolExecutor(max_workers=cfg.parallel) as pool:
        futures = {pool.submit(_process_one, tf, pkg, rel, vocab, cfg): (rel, tf) for rel, tf in pending}
        for fut in as_completed(futures):
            prop = fut.result()
            results.append(prop)
            completed += 1
            status = prop.topic if prop.applicable else ("ERROR" if prop.error else "skip")
            LOG.info("  [%d/%d] %s :: %s -> %s", completed, len(pending),
                     prop.file, prop.qualname, status)
            if completed % _CHECKPOINT_EVERY == 0:
                _write_proposals(out_json, results)
                _write_preview(out_md, pkg, results, cfg)

    _write_proposals(out_json, results)
    _write_preview(out_md, pkg, results, cfg)
    return results


# ---------------------------------------------------------------------------
# Apply phase
# ---------------------------------------------------------------------------

def apply_package(pkg: str, datrix_root: Path, model: str, filters: list[Path]) -> tuple[int, int]:
    """Insert reviewed applicable markers into the package's test files.

    Args:
        pkg: Package name.
        datrix_root: Workspace root.
        model: Model whose proposal set to apply (selects the per-model dir).
        filters: --path filters; when non-empty, only proposals under them are applied.

    Returns:
        (inserted, skipped) counts.
    """
    out_json = _output_dir(datrix_root, model) / f"{pkg}.json"
    proposals = [p for p in _load_proposals(out_json) if p.applicable and not p.error]
    if filters:
        proposals = [p for p in proposals if _file_allowed(datrix_root / p.file, filters)]
    if not proposals:
        LOG.info("[%s] no applicable proposals at %s", pkg, out_json)
        return (0, 0)

    by_file: dict[str, list[Proposal]] = {}
    for p in proposals:
        by_file.setdefault(p.file, []).append(p)

    inserted = skipped = 0
    for rel, props in sorted(by_file.items()):
        ins, skp = _apply_file(datrix_root / rel, props)
        inserted += ins
        skipped += skp
    return (inserted, skipped)


def _apply_file(path: Path, props: list[Proposal]) -> tuple[int, int]:
    """Insert markers for one file, re-deriving line numbers from current AST."""
    if not path.is_file():
        LOG.warning("  missing file, skipping: %s", path)
        return (0, len(props))

    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    current = {tf.qualname: tf for tf in discover_test_functions(text)}

    # Build (insert_index, marker_lines), newest-derived line numbers, applied bottom-up.
    insertions: list[tuple[int, list[str]]] = []
    skipped = 0
    for prop in props:
        tf = current.get(prop.qualname)
        if tf is None or already_annotated(lines, tf.def_line):
            skipped += 1
            continue
        prop.col = tf.col  # honor current indentation
        insertions.append((tf.def_line - 1, render_marker(prop)))

    if not insertions:
        return (0, skipped)

    for insert_idx, marker in sorted(insertions, key=lambda x: x[0], reverse=True):
        lines[insert_idx:insert_idx] = marker

    newline = "\r\n" if "\r\n" in text else "\n"
    path.write_text(newline.join(lines) + newline, encoding="utf-8")
    LOG.info("  %s: inserted %d marker(s)", path.name, len(insertions))
    return (len(insertions), skipped)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _rel_path(py_file: Path, datrix_root: Path) -> str:
    """Path relative to the datrix root, forward-slashed."""
    try:
        return str(py_file.resolve().relative_to(datrix_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(py_file.resolve()).replace("\\", "/")


def _load_proposals(path: Path) -> list[Proposal]:
    """Load existing proposals for resume (empty list if none)."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("proposals", [])
    if not isinstance(raw, list):
        return []
    return [Proposal.from_json(d) for d in raw if isinstance(d, dict)]


def _write_proposals(path: Path, proposals: list[Proposal]) -> None:
    """Persist proposals as JSON via atomic temp-file replace.

    A kill mid-write leaves the previous complete checkpoint intact, so resume
    never sees a truncated/corrupt file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(proposals),
        "applicable": sum(1 for p in proposals if p.applicable),
        "proposals": [p.to_json() for p in proposals],
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _write_preview(path: Path, pkg: str, proposals: list[Proposal], cfg: argparse.Namespace) -> None:
    """Write a human-readable Markdown preview of the proposals."""
    applicable = [p for p in proposals if p.applicable]
    errors = [p for p in proposals if p.error]
    lines = [
        f"# Test-rule proposals — {pkg}",
        "",
        f"- Model: `{cfg.model}` @ `{cfg.endpoint}`",
        f"- Generated: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- Total functions examined: {len(proposals)}",
        f"- Applicable (will insert): {len(applicable)}",
        f"- Skipped (not a rule): {len(proposals) - len(applicable) - len(errors)}",
        f"- Errors: {len(errors)}",
        "",
        "Review, then apply with `generate-test-rules.ps1 "
        f"{pkg} -Apply -Model {cfg.model}`.",
        "",
    ]
    by_file: dict[str, list[Proposal]] = {}
    for p in applicable:
        by_file.setdefault(p.file, []).append(p)

    for rel in sorted(by_file):
        lines.append(f"## `{rel}`")
        lines.append("")
        for p in sorted(by_file[rel], key=lambda x: x.def_line):
            dims = ", ".join(f"{k}={v}" for k, v in p.dimensions) or "—"
            lines.append(f"### `{p.qualname}` (line {p.def_line}) — {dims}")
            lines.append("")
            lines.append("```python")
            lines.extend(render_marker(p))
            lines.append(f"{' ' * p.col}def {p.name}(...):")
            lines.append("```")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _resolve_test_dirs(
    datrix_root: Path, projects: list[str], scan_all: bool
) -> list[tuple[str, Path]]:
    """Resolve (package, tests_dir) pairs — tests trees only."""
    return resolve_scan_paths(
        datrix_root, projects, scan_all, include_src=False, include_tests=True
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate @test-rule annotations for test functions via a local LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("projects", nargs="*", help="Package names (e.g. datrix-codegen-python)")
    parser.add_argument("--all", "-a", action="store_true", dest="scan_all",
                        help="Scan every datrix* package's tests tree")
    parser.add_argument("--apply", action="store_true",
                        help="Insert reviewed proposals into the test files (default: propose only)")
    parser.add_argument("--review", action="store_true",
                        help="Print a triage report of existing proposals (no LLM, no source changes)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                        help=f"Ollama base URL (default: {DEFAULT_ENDPOINT})")
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL,
                        help=f"Concurrent LLM calls (default: {DEFAULT_PARALLEL})")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max functions per package this run (0 = no limit)")
    parser.add_argument("--no-seed", action="store_true", dest="no_seed",
                        help="Do not seed the topic vocabulary from existing markers "
                             "(reduces the model forcing tests under existing topics)")
    parser.add_argument("--path", action="append", default=[], metavar="PATH",
                        help="Restrict to test files under this file/dir (repeatable). "
                             "Package(s) are derived from the path if none are given.")
    parser.add_argument("--no-consolidate", action="store_true", dest="no_consolidate",
                        help="Skip the topic-consolidation pass (default: consolidate)")
    parser.add_argument("--include-e2e", action="store_true", dest="include_e2e",
                        help="Include tests/e2e (excluded by default)")
    parser.add_argument("--include-integration", action="store_true", dest="include_integration",
                        help="Include tests/integration (excluded by default)")
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX, dest="num_ctx",
                        help=f"Model context window (default: {DEFAULT_NUM_CTX})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                        help=f"Per-call timeout seconds (default: {DEFAULT_TIMEOUT_S})")
    parser.add_argument("--debug", "-d", action="store_true", help="Debug logging")
    return parser


def main() -> int:
    """Main entry point."""
    cfg = _build_arg_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if cfg.debug else logging.INFO,
        format="%(message)s",
    )

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        LOG.error("Could not find Datrix root directory")
        return 1

    cfg.filters = _resolve_filters(cfg.path, datrix_root)
    excluded = set(_DEFAULT_EXCLUDED_DIRS)
    if cfg.include_e2e:
        excluded.discard("e2e")
    if cfg.include_integration:
        excluded.discard("integration")
    cfg.excluded_dirs = frozenset(excluded)

    projects = list(cfg.projects)
    if not projects and not cfg.scan_all:
        projects = _projects_from_paths(cfg.filters, datrix_root)
        if not projects:
            LOG.error("Provide package names, --path, or --all.")
            return 1

    try:
        pairs = _resolve_test_dirs(datrix_root, projects, cfg.scan_all)
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    if not pairs:
        LOG.info("No tests/ directories found to scan.")
        return 0

    if cfg.review:
        return _run_review(pairs, datrix_root, cfg)
    if cfg.apply:
        return _run_apply(pairs, datrix_root, cfg.model, cfg.filters)
    return _run_propose(pairs, datrix_root, cfg)


def _run_propose(pairs: list[tuple[str, Path]], datrix_root: Path, cfg: argparse.Namespace) -> int:
    """Propose phase across all resolved packages, then consolidate topics."""
    seed = set() if cfg.no_seed else seed_topics_from_db(datrix_root)
    vocab = _Vocabulary(seed)
    per_pkg: list[tuple[str, list[Proposal]]] = []
    for pkg, tests_dir in pairs:
        per_pkg.append((pkg, propose_package(pkg, tests_dir, datrix_root, vocab, cfg)))

    out_dir = _output_dir(datrix_root, cfg.model)
    if not cfg.no_consolidate:
        _consolidate_and_rewrite(per_pkg, out_dir, datrix_root, cfg)

    total_applicable = sum(1 for _, rs in per_pkg for p in rs if p.applicable)
    LOG.info("\n[OK] Proposals written under %s (%d applicable). Review, then re-run with --apply.",
             out_dir, total_applicable)
    return 0


def _consolidate_and_rewrite(
    per_pkg: list[tuple[str, list[Proposal]]],
    out_dir: Path,
    datrix_root: Path,
    cfg: argparse.Namespace,
) -> None:
    """Run the topic-consolidation pass over the whole run and re-write proposals."""
    all_props = [p for _, rs in per_pkg for p in rs]
    anchors = seed_topics_from_db(datrix_root)  # canonical anchors, even under --no-seed
    mapping = consolidate_topics(all_props, anchors, cfg)
    changed = apply_topic_map(all_props, mapping)  # also kebab-normalizes when mapping is empty
    LOG.info("Consolidation: %d merge rule(s), %d topic(s) rewritten", len(mapping), changed)
    for pkg, rs in per_pkg:
        _write_proposals(out_dir / f"{pkg}.json", rs)
        _write_preview(out_dir / f"{pkg}.md", pkg, rs, cfg)


# ---------------------------------------------------------------------------
# Review (triage) phase
# ---------------------------------------------------------------------------

# Dimension values that are almost never a real target (template leaks, vague, topic-like).
_SUSPICIOUS_DIM_VALUES = frozenset({
    "any", "none", "external", "customer", "builtin", "invalid_lang", "rdbms",
    "nosql", "cloud-managed", "self-hosted", "multi-provider", "worker",
    "directory-structure", "documentation-content", "auth", "auth-provider",
})


def _dim_is_suspicious(value: str) -> bool:
    """Heuristic: a dimension value that probably isn't a real target."""
    return (
        "${" in value
        or value in _SUSPICIOUS_DIM_VALUES
        or value.endswith("-mapping")
        or value.endswith("-default")
    )


def _print_review(pkg: str, proposals: list[Proposal]) -> None:
    """Log a triage report: counts, suspicious dims, weak behaviors, over-grouping."""
    ap = [p for p in proposals if p.applicable]
    errs = [p for p in proposals if p.error]
    counts: dict[str, int] = {}
    targets: dict[str, set[str]] = {}
    for p in ap:
        counts[p.topic] = counts.get(p.topic, 0) + 1
        key = ", ".join(f"{k}={v}" for k, v in sorted(p.dimensions)) or "—"
        targets.setdefault(p.topic, set()).add(key)

    LOG.info("\n=== review: %s ===", pkg)
    LOG.info("examined=%d  applicable=%d  skipped=%d  errors=%d  distinct-topics=%d",
             len(proposals), len(ap), len(proposals) - len(ap) - len(errs), len(errs), len(counts))

    suspicious = [(p, k, v) for p in ap for k, v in p.dimensions if _dim_is_suspicious(v)]
    LOG.info("\nsuspicious dimensions (%d):", len(suspicious))
    for p, k, v in suspicious[:30]:
        LOG.info("  %s=%s  <- %s", k, v, p.qualname)

    weak = [p for p in ap if len(p.behavior) < 8]
    LOG.info("\nweak/empty behavior (%d):", len(weak))
    for p in weak[:20]:
        LOG.info("  %r  <- %s", p.behavior, p.qualname)

    over = sorted(((t, n) for t, n in counts.items() if n >= 15), key=lambda x: -x[1])
    LOG.info("\nhigh-count topics — review for over-grouping (%d):", len(over))
    for topic, n in over:
        LOG.info("  %3d  %s", n, topic)

    single = sorted(t for t, ts in targets.items() if len(ts) == 1)
    LOG.info("\nsingle-target topics (%d): possible coverage gaps", len(single))


def _run_review(pairs: list[tuple[str, Path]], datrix_root: Path, cfg: argparse.Namespace) -> int:
    """Print a triage report of existing proposals (no LLM, no source changes)."""
    seen: set[str] = set()
    for pkg, _tests_dir in pairs:
        if pkg in seen:
            continue
        seen.add(pkg)
        proposals = _load_proposals(_output_dir(datrix_root, cfg.model) / f"{pkg}.json")
        if cfg.filters:
            proposals = [p for p in proposals if _file_allowed(datrix_root / p.file, cfg.filters)]
        if not proposals:
            LOG.info("\n=== review: %s === (no proposals found)", pkg)
            continue
        _print_review(pkg, proposals)
    return 0


def _run_apply(pairs: list[tuple[str, Path]], datrix_root: Path, model: str, filters: list[Path]) -> int:
    """Apply phase across all resolved packages."""
    total_ins = total_skip = 0
    for pkg, _tests_dir in pairs:
        ins, skp = apply_package(pkg, datrix_root, model, filters)
        total_ins += ins
        total_skip += skp
    LOG.info("\n[OK] Inserted %d marker(s); skipped %d. Rebuild: logic-map.ps1 -All",
             total_ins, total_skip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
