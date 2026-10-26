"""What a non-Python file defines, read with each format's own parser.

Python goes through ``extract.extract_file``; every other indexed format is read here and
recorded as definitions only (no imports, references or logic-map markers):

- Markdown: each heading is a ``section`` spanning to the next heading of its level or above,
  read with markdown-it, so headings inside code fences are not sections.
- PowerShell: script and function parameters and functions, read with PowerShell's own parser
  through ``datrix_scripts.code_index.powershell_outline``, many files per process.
- ``.dtrx``: the language server's outline (``datrix_language.lsp.symbols``) over a tolerant,
  buffer-only parse, so a definition carries the kind the editor shows for it.
- ``.dcfg``: config documents, blocks, profiles, templates, keys and settings, read from the
  Datrix grammar's syntax tree.
- TypeScript: classes, interfaces, type aliases, enums, namespaces, functions, methods, class
  fields and module-level variables, read from the tree-sitter TypeScript grammar.

A non-Python file's module name is its workspace-relative path (``sources.module_name``).
"""

from __future__ import annotations

import functools
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import tree_sitter_typescript
from markdown_it import MarkdownIt
from markdown_it.token import Token
from tree_sitter import Language, Node, Parser

from datrix_scripts.code_index.extract import (
    MAX_SIGNATURE_CHARS,
    SYMBOL_ATTRIBUTE,
    SYMBOL_CLASS,
    SYMBOL_FUNCTION,
    SYMBOL_METHOD,
    SYMBOL_VARIABLE,
    FileFacts,
    SymbolFact,
    clip,
    extract_file,
    first_paragraph,
)
from datrix_scripts.code_index.powershell_outline import FILES_PER_PROCESS, PROGRAM_NAME, run_outline
from datrix_scripts.code_index.sources import (
    DATRIX_CONFIG_SUFFIX,
    DATRIX_SUFFIX,
    INDEXED_SUFFIXES,
    MARKDOWN_SUFFIX,
    POWERSHELL_SUFFIX,
    PYTHON_SUFFIX,
    TYPESCRIPT_SUFFIX,
)

SYMBOL_SECTION = "section"
SYMBOL_PARAMETER = "parameter"
SYMBOL_INTERFACE = "interface"
SYMBOL_TYPE = "type"
SYMBOL_ENUM = "enum"
SYMBOL_NAMESPACE = "namespace"
SYMBOL_CONFIG = "config"
SYMBOL_BLOCK = "block"
SYMBOL_PROFILE = "profile"
SYMBOL_TEMPLATE = "template"
SYMBOL_KEY = "key"
SYMBOL_SETTING = "setting"

# The kinds the language server's outline gives a .dtrx definition: ``SymbolKind`` member names,
# lower-cased. Listed here, not imported, so the index answers queries without importing the
# language package; code-index-gate compares the two sets.
DATRIX_OUTLINE_KINDS = (
    "system", "module", "service", "shared", "extern_service", "infrastructure_block", "entity",
    "struct", "enum", "field", "computed_field", "relationship", "function", "api", "endpoint",
    "pubsub_topic", "pubsub_event", "app", "page", "component", "form", "table", "layout", "workspace",
)

# Every kind a non-Python file's definition can have.
FORMAT_SYMBOL_KINDS = tuple(dict.fromkeys((
    SYMBOL_SECTION, SYMBOL_PARAMETER, SYMBOL_INTERFACE, SYMBOL_TYPE, SYMBOL_ENUM, SYMBOL_NAMESPACE,
    SYMBOL_CONFIG, SYMBOL_BLOCK, SYMBOL_PROFILE, SYMBOL_TEMPLATE, SYMBOL_KEY, SYMBOL_SETTING,
    *DATRIX_OUTLINE_KINDS,
)))

_MARKDOWN_HEADING_OPEN = "heading_open"
_MARKDOWN_INLINE = "inline"
_MARKDOWN_PARAGRAPH_OPEN = "paragraph_open"

# TypeScript node type -> definition kind.
_TYPESCRIPT_KINDS = {
    "class_declaration": SYMBOL_CLASS,
    "abstract_class_declaration": SYMBOL_CLASS,
    "interface_declaration": SYMBOL_INTERFACE,
    "type_alias_declaration": SYMBOL_TYPE,
    "enum_declaration": SYMBOL_ENUM,
    "internal_module": SYMBOL_NAMESPACE,
    "module": SYMBOL_NAMESPACE,
    "function_declaration": SYMBOL_FUNCTION,
    "generator_function_declaration": SYMBOL_FUNCTION,
    "function_signature": SYMBOL_FUNCTION,
    "method_definition": SYMBOL_METHOD,
    "method_signature": SYMBOL_METHOD,
    "abstract_method_signature": SYMBOL_METHOD,
    "public_field_definition": SYMBOL_ATTRIBUTE,
    "property_signature": SYMBOL_ATTRIBUTE,
    "variable_declarator": SYMBOL_VARIABLE,
}
# Definitions whose body holds further definitions.
_TYPESCRIPT_SCOPES = frozenset({SYMBOL_CLASS, SYMBOL_INTERFACE, SYMBOL_NAMESPACE})
# Statements that wrap definitions without being one: their definitions belong to the enclosing scope.
_TYPESCRIPT_WRAPPERS = frozenset({
    "export_statement", "lexical_declaration", "variable_declaration", "ambient_declaration",
    "expression_statement",
})
_TYPESCRIPT_DOC_OPEN = "/**"

# .dcfg node type -> definition kind; the name is the node's ``name`` field, else ``owner``,
# else its first identifier.
_DCFG_KINDS = {
    "config_profiled_document": SYMBOL_CONFIG,
    "config_strings_document": SYMBOL_CONFIG,
    "config_block_assignment": SYMBOL_BLOCK,
    "config_inline_named_block": SYMBOL_BLOCK,
    "config_template_named_block": SYMBOL_BLOCK,
    "config_template": SYMBOL_TEMPLATE,
    "config_profile": SYMBOL_PROFILE,
    "config_key": SYMBOL_KEY,
    "config_field_assignment": SYMBOL_SETTING,
}
_DCFG_NAME_FIELDS = ("name", "owner")
_IDENTIFIER = "identifier"


@dataclass(frozen=True)
class _Source:
    """One file's text, split into lines for signatures."""

    text: str
    lines: list[str]

    @classmethod
    def decode(cls, data: bytes) -> _Source:
        text = data.decode("utf-8-sig", errors="replace")
        return cls(text, text.splitlines())

    def signature(self, line: int) -> str:
        """The definition's source line, whitespace collapsed and clipped."""
        if not 1 <= line <= len(self.lines):
            return ""
        return clip(" ".join(self.lines[line - 1].split()), MAX_SIGNATURE_CHARS)

    def facts(self, symbols: list[SymbolFact], module_doc: str = "", parse_error: str = "") -> FileFacts:
        kept = () if parse_error else tuple(symbols)
        return FileFacts(first_paragraph(module_doc), len(self.lines), kept, (), (), (), parse_error)


def suffix_of(rel_path: str) -> str:
    return PurePosixPath(rel_path).suffix.lower()


def is_batched(rel_path: str) -> bool:
    """Whether ``rel_path`` is read many files per process (``extract_batch``) rather than one at a time."""
    return suffix_of(rel_path) == POWERSHELL_SUFFIX


# --- Markdown --------------------------------------------------------------------------------


@functools.cache
def _markdown() -> MarkdownIt:
    return MarkdownIt("commonmark")


def extract_markdown(data: bytes) -> FileFacts:
    source = _Source.decode(data)
    tokens = _markdown().parse(source.text)
    headings: list[tuple[int, int, str, str]] = []  # (line, level, title, first paragraph)
    for index, token in enumerate(tokens):
        if token.type != _MARKDOWN_HEADING_OPEN or token.map is None:
            continue
        # heading_open, its inline text, heading_close; a paragraph directly after starts next.
        title = tokens[index + 1].content.strip()
        headings.append((token.map[0] + 1, int(token.tag[1:]), title, _paragraph_after(tokens, index + 3)))
    symbols = []
    for position, (line, level, title, doc) in enumerate(headings):
        following = (h[0] for h in headings[position + 1:] if h[1] <= level)
        end_line = next(following, len(source.lines) + 1) - 1
        symbols.append(SymbolFact(title, title, SYMBOL_SECTION, line, max(line, end_line),
                                  clip(f"{'#' * level} {title}", MAX_SIGNATURE_CHARS), first_paragraph(doc)))
    title = headings[0][2] if headings else ""
    return source.facts(symbols, title)


def _paragraph_after(tokens: list[Token], start: int) -> str:
    """The text of the paragraph directly after a heading, before any other block."""
    if start + 1 < len(tokens) and tokens[start].type == _MARKDOWN_PARAGRAPH_OPEN \
            and tokens[start + 1].type == _MARKDOWN_INLINE:
        return str(tokens[start + 1].content)
    return ""


# --- TypeScript ------------------------------------------------------------------------------


@functools.cache
def _typescript_parser() -> Parser:
    return Parser(Language(tree_sitter_typescript.language_typescript()))


def _node_text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _typescript_doc(statement: Node) -> str:
    """The ``/** ... */`` comment ending on the line before ``statement``, without its markers."""
    previous = statement.prev_sibling
    if previous is None or previous.type != "comment" or previous.end_point[0] != statement.start_point[0] - 1:
        return ""
    text = _node_text(previous)
    if not text.startswith(_TYPESCRIPT_DOC_OPEN):
        return ""
    lines = (line.strip().lstrip("*").strip() for line in text[3:].removesuffix("*/").splitlines())
    return "\n".join(lines)


class _TypeScriptCollector:
    """Walks declarations scope by scope, keeping each one's qualified name."""

    def __init__(self, source: _Source) -> None:
        self.source = source
        self.symbols: list[SymbolFact] = []

    def scope(self, nodes: list[Node], prefix: str, statement: Node | None) -> None:
        for node in nodes:
            outer = statement or node
            if node.type in _TYPESCRIPT_WRAPPERS:
                self.scope(node.named_children, prefix, outer)
            elif node.type in _TYPESCRIPT_KINDS:
                self._definition(node, prefix, outer)

    def _definition(self, node: Node, prefix: str, statement: Node) -> None:
        name = _node_text(node.child_by_field_name("name"))
        if not name:
            return
        kind = _TYPESCRIPT_KINDS[node.type]
        qualname = f"{prefix}{name}"
        line = node.start_point[0] + 1
        self.symbols.append(SymbolFact(name, qualname, kind, line, node.end_point[0] + 1,
                                       self.source.signature(line), first_paragraph(_typescript_doc(statement))))
        body = node.child_by_field_name("body")
        if kind in _TYPESCRIPT_SCOPES and body is not None:
            self.scope(body.named_children, f"{qualname}.", None)


def extract_typescript(data: bytes) -> FileFacts:
    source = _Source.decode(data)
    tree = _typescript_parser().parse(data)
    collector = _TypeScriptCollector(source)
    collector.scope(tree.root_node.named_children, "", None)
    return source.facts(collector.symbols)


# --- .dcfg -----------------------------------------------------------------------------------


@functools.cache
def _datrix_parser() -> Parser:
    from datrix_language.parser.tree_sitter_datrix.parser import load_datrix_language

    return Parser(load_datrix_language())


def _dcfg_name(node: Node) -> str:
    for field in _DCFG_NAME_FIELDS:
        named = node.child_by_field_name(field)
        if named is not None:
            return _node_text(named)
    identifier = next((child for child in node.named_children if child.type == _IDENTIFIER), None)
    return _node_text(identifier)


def _dcfg_symbols(node: Node, prefix: str, source: _Source) -> Iterator[SymbolFact]:
    for child in node.named_children:
        full_name = _dcfg_name(child) if child.type in _DCFG_KINDS else ""
        if not full_name:
            yield from _dcfg_symbols(child, prefix, source)
            continue
        kind = _DCFG_KINDS[child.type]
        name = full_name.rsplit(".", 1)[-1]
        qualname = f"{prefix}{name}"
        line = child.start_point[0] + 1
        yield SymbolFact(name, qualname, kind, line, child.end_point[0] + 1, source.signature(line), "")
        yield from _dcfg_symbols(child, f"{qualname}.", source)


def extract_dcfg(data: bytes) -> FileFacts:
    source = _Source.decode(data)
    tree = _datrix_parser().parse(data)
    error = _first_syntax_error(tree.root_node)
    return source.facts(list(_dcfg_symbols(tree.root_node, "", source)), parse_error=error)


def _first_syntax_error(root: Node) -> str:
    if not root.has_error:
        return ""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            return f"SyntaxError: line {node.start_point[0] + 1}: unexpected or missing '{node.type}'"
        stack.extend(child for child in reversed(node.children) if child.has_error)
    return "SyntaxError: the file does not parse"


# --- .dtrx -----------------------------------------------------------------------------------


def extract_datrix(data: bytes, rel_path: str) -> FileFacts:
    # datrix-language is installed with the shared venv, so it is imported unconditionally (here, so only a
    # run that reads a .dtrx pays for it): a venv without it fails the index loudly, never a quiet empty file.
    from datrix_language.lsp.symbols import build_symbol_index
    from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser

    source = _Source.decode(data)
    path = Path(rel_path)
    result = TreeSitterParser().parse_partial(source.text, file_path=path, require_system=False,
                                              inject_builtins=False)
    if result.ast is None:
        first = str(result.errors[0]) if result.errors else "no syntax tree"
        return source.facts([], parse_error=f"ParseError: {first}")
    qualnames: dict[str, str] = {}
    symbols = []
    for record in build_symbol_index(result.ast).records:
        location = record.location
        if location is None or location.line is None or location.file_path != path:
            continue
        name = record.name.rsplit(".", 1)[-1]
        container = record.container_name or ""
        qualname = f"{qualnames[container]}.{name}" if container in qualnames else name
        qualnames[record.name] = qualname
        symbols.append(SymbolFact(name, qualname, record.kind.name.lower(), location.line, location.line,
                                  source.signature(location.line), ""))
    return source.facts(symbols)


# --- PowerShell ------------------------------------------------------------------------------


def _powershell_symbol(entry: dict[str, object], source: _Source) -> SymbolFact:
    line = int(str(entry["line"]))
    return SymbolFact(
        name=str(entry["name"]), qualname=str(entry["qualname"]), kind=str(entry["kind"]), line=line,
        end_line=int(str(entry["end_line"])), signature=source.signature(line),
        doc=first_paragraph(str(entry["doc"] or "")),
    )


def _powershell_facts(source: _Source, outline: dict[str, object]) -> FileFacts:
    entries = outline["symbols"]
    if not isinstance(entries, list):
        raise ValueError(f"{PROGRAM_NAME} returned symbols that are not a list: {entries!r}")
    symbols = [_powershell_symbol(entry, source) for entry in entries]
    return source.facts(symbols, str(outline["synopsis"] or ""), str(outline["error"] or ""))


def extract_powershell(files: list[tuple[bytes, str]]) -> list[FileFacts]:
    """The facts of each ``(data, rel_path)``, in order, reading many files per PowerShell process."""
    facts: list[FileFacts] = []
    for start in range(0, len(files), FILES_PER_PROCESS):
        chunk = [(rel_path, _Source.decode(data)) for data, rel_path in files[start:start + FILES_PER_PROCESS]]
        outlines = run_outline([(rel_path, source.text) for rel_path, source in chunk])
        if isinstance(outlines, str):
            facts.extend(source.facts([], parse_error=outlines) for _, source in chunk)
        else:
            facts.extend(_powershell_facts(source, outline) for (_, source), outline in zip(chunk, outlines))
    return facts


# --- Dispatch --------------------------------------------------------------------------------


def extract_source(data: bytes, rel_path: str, module: str, is_package: bool) -> FileFacts:
    """Everything the index records about one file of any indexed format."""
    suffix = suffix_of(rel_path)
    if suffix == PYTHON_SUFFIX:
        return extract_file(data, rel_path, module, is_package)
    if suffix == MARKDOWN_SUFFIX:
        return extract_markdown(data)
    if suffix == TYPESCRIPT_SUFFIX:
        return extract_typescript(data)
    if suffix == DATRIX_SUFFIX:
        return extract_datrix(data, rel_path)
    if suffix == DATRIX_CONFIG_SUFFIX:
        return extract_dcfg(data)
    if suffix == POWERSHELL_SUFFIX:
        return extract_powershell([(data, rel_path)])[0]
    raise ValueError(f"'{rel_path}' has suffix '{suffix}', which the code index does not read. "
                     f"Indexed suffixes: {', '.join(INDEXED_SUFFIXES)}.")


def extract_source_job(job: tuple[bytes, str, str, bool]) -> FileFacts:
    """``extract_source`` for a process pool, which maps over single arguments."""
    return extract_source(*job)
