"""What the fixture author sends a local model to draft one catalog variant of an area project.

A draft is one *fragment* of the area file: the constructs provoking one variant, with its
``// @expect <CODE>.<variant>`` line, and the files they read (owner configurations, and seed
documents in a seeded area). The tool writes the area's header and its ``system`` declaration
itself and assembles the fragments under them, so every fragment is asked for alone.

The system prompt carries what every fragment of an area shares: the annotation forms (the module
docstrings of ``datrix_testing.cases.annotation_reading`` and ``datrix_testing.cases.annotations``),
the scaffold the area's root holds (its system configuration and datasource templates), and the
rules of a fragment. The user prompt carries the variant: its catalog entry, its names, the old
per-code fixture provoking it when one exists (an example only), the sections of the syntax
reference its words point to, and -- after a failed round -- what failed with the analyzer's
output and the previous draft.

The syntax reference is far larger than a local model's context window, so only its sections that
share the most words with the variant's catalog entry and example are sent, up to a budget.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from datrix_common.constants import DATRIX_FILE_EXTENSION
from datrix_semantic.diagnostics.catalog import DiagnosticCatalog
from datrix_semantic.diagnostics.security_families import code_family, security_tags_of
from datrix_testing.cases import annotation_reading, annotations
from datrix_testing.cases.annotation_reading import EXPECT, LINE_COMMENT_MARKER, PROFILE_DIRECTIVE, TAGS_DIRECTIVE
from datrix_testing.cases.annotations import DIAGNOSTIC_CONFIGS, PROJECT_FIXTURE_SOURCE, per_code_config_directory
from datrix_testing.cases.observers import VARIANT_SEPARATOR
from datrix_testing.context import TEST_PROFILE

from datrix_scripts.dev.fixture_author.diagnostics import (
    DATASOURCE_TEMPLATES,
    SYSTEM_CONFIG,
    AreaPlan,
    variant_code,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import markdown_sections

#: The answer every draft request is constrained to.
DRAFT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "configs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
                "required": ["path", "text"],
            },
        },
    },
    "required": ["source", "configs"],
}
#: The syntax reference the prompt draws its excerpts from.
SYNTAX_REFERENCE: Final[Path] = WORKSPACE_DIR / "datrix-language" / "docs" / "reference" / "datrix-syntax-reference.md"
#: How much of the syntax reference one request carries, in characters.
REFERENCE_BUDGET_CHARS: Final[int] = 24_000
#: How much of an old per-code fixture one request carries, in characters.
EXAMPLE_BUDGET_CHARS: Final[int] = 12_000
#: The deepest heading a reference excerpt is cut at.
REFERENCE_HEADING_LEVEL: Final[int] = 3
#: The namespace every area's services are declared in.
NAMESPACE: Final[str] = "shop"
#: The service-name and configuration-file suffixes of D2's naming.
SERVICE_SUFFIX: Final[str] = "Service"
SERVICE_CONFIG_SUFFIX: Final[str] = "-service.dcfg"
#: Where a seeded area's seed documents live, and their suffix.
SEED_DIRECTORY: Final[str] = "seed"
SEED_SUFFIX: Final[str] = ".dseed"

#: The lines that open the variant, the feedback after a failed round, and the previous draft.
VARIANT_LABEL: Final[str] = "VARIANT: "
FEEDBACK_HEADING: Final[str] = "THE PREVIOUS DRAFT FAILED"
PREVIOUS_DRAFT_HEADING: Final[str] = "PREVIOUS DRAFT"
ANALYZER_OUTPUT_HEADING: Final[str] = "ANALYZER OUTPUT"
#: The instruction sent with a cascade: a diagnostic fired that the fragment does not annotate.
CASCADE_INSTRUCTION: Final[str] = (
    "Something besides the variant fired. Move the construct that provokes the variant into its own "
    "service or module in the same file, so nothing else in the fragment is wrong; never annotate the "
    "other diagnostic."
)
#: The instruction sent with a variant not provoked on its annotated line.
NOT_PROVOKED_INSTRUCTION: Final[str] = (
    "The variant did not fire on the line its @expect describes. Read the catalog entry again and change "
    "the construct so the analyzer reports exactly this variant on that line."
)
#: What replaces a prompt part that carries a registered customer term.
WITHHELD: Final[str] = "(withheld: it carries a registered customer term)"

#: Folded into every derived container id, so a fixture's ids never coincide with another tool's.
_DATABASE_ID_NAMESPACE: Final[str] = "datrix-fixture-author:"
#: How much of a variant's kebab name its base path keeps: under the 32 characters a secret-looking
#: literal starts at.
_BASE_PATH_STEM: Final[int] = 20

_WORD: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9]{3,}")
_KEBAB_SPLIT: Final[re.Pattern[str]] = re.compile(r"[_\W]+")


@dataclass(frozen=True)
class VariantNames:
    """The names a variant's fragment declares, so no two fragments of an area collide.

    Attributes:
        kebab: ``example001-shape`` for ``EXAMPLE001.shape``.
        pascal: ``Example001Shape``.
    """

    kebab: str
    pascal: str

    @property
    def service(self) -> str:
        """The qualified name of the fragment's first service."""
        return f"{NAMESPACE}.{self.pascal}{SERVICE_SUFFIX}"

    @property
    def config(self) -> str:
        """The owner configuration of the fragment's first service, relative to the area root."""
        return f"{DIAGNOSTIC_CONFIGS}/{self.kebab}{SERVICE_CONFIG_SUFFIX}"

    @property
    def config_prefix(self) -> str:
        """What every configuration path of the fragment starts with."""
        return f"{DIAGNOSTIC_CONFIGS}/{self.kebab}"

    @property
    def database_id(self) -> str:
        """The container database id of the fragment's first service: a canonical UUID derived from
        its names, so the model copies it rather than inventing one."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{_DATABASE_ID_NAMESPACE}{self.kebab}"))

    @property
    def base_path(self) -> str:
        """A REST base path of the fragment's first service, short enough never to read as a secret."""
        return f"/v1/{self.kebab[:_BASE_PATH_STEM]}"


def variant_names(variant: str) -> VariantNames:
    """The names of *variant*'s fragment, read off its code and variant name."""
    parts = [part.lower() for part in _KEBAB_SPLIT.split(variant) if part]
    return VariantNames("-".join(parts), "".join(part[:1].upper() + part[1:] for part in parts))


def service_shape(names: VariantNames, version: str, expect: str | None) -> str:
    """A service that analyzes clean against the scaffold (a database, an entity and a public read,
    so the system's gateway has a route), declaring *version* and annotated ``@expect <expect>`` on
    its declaration line when *expect* is given."""
    annotation = f"{LINE_COMMENT_MARKER} @{EXPECT} {expect}\n" if expect is not None else ""
    return (
        f"{annotation}service {names.service}('{names.config}') : version('{version}') {{\n"
        "    discovery { }\n\n"
        "    rdbms db {\n"
        "        entity Plant {\n"
        "            UUID id : primaryKey, server = uuid();\n"
        "            String(100) name : trim;\n"
        "        }\n"
        "    }\n\n"
        f'    rest_api PlantAPI : basePath("{names.base_path}"), rdbms(db) {{\n'
        "        @path('/:id')\n"
        "        get(UUID id) : auth(public) -> db.Plant {\n"
        "            return db.Plant.findOrFail(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )


def owner_config_shape(names: VariantNames) -> str:
    """An owner configuration as the corpus writes one: a container database from the datasource
    templates and a non-wildcard host and CORS allow-list."""
    database = names.kebab.replace("-", "_")
    return (
        f"config service {names.service} {{\n"
        f'  import "{DATASOURCE_TEMPLATES.as_posix()}";\n\n'
        "  base {\n"
        "    port = 8000;\n"
        "    replicas = 1;\n"
        f'    rdbms db from postgresContainer(id: "{names.database_id}", database: "{database}");\n'
        "    httpSecurity {\n"
        f'      allowedHosts = ["{names.kebab}.example.com", "localhost"];\n'
        '      corsOrigins = ["https://app.example.com"];\n'
        '      corsMethods = ["GET", "OPTIONS"];\n'
        '      corsHeaders = ["Authorization", "Content-Type"];\n'
        "    }\n"
        "  }\n\n"
        f'  profile {TEST_PROFILE} as "{TEST_PROFILE}" extends base {{\n'
        '    alias env = "TEST";\n'
        '    alias resource = "test";\n'
        "  }\n"
        "}\n"
    )


#: The variant the system prompt's shapes are drawn with; no catalog declares the code.
_EXAMPLE_VARIANT: Final[str] = f"EXAMPLE001{VARIANT_SEPARATOR}shape"


def system_prompt(area: AreaPlan, root: Path, system_owner: str) -> str:
    """What every draft request of *area* (its project root *root*) shares."""
    example = variant_names(_EXAMPLE_VARIANT)
    entry = PROJECT_FIXTURE_SOURCE if area.seeded else f"{area.name}{DATRIX_FILE_EXTENSION}"
    rules = [
        "You write one fragment of a Datrix (.dtrx) diagnostics fixture: the constructs that provoke exactly "
        "one catalog diagnostic variant, and the files they read. Answer JSON: "
        '{"source": <the fragment>, "configs": [{"path": <path relative to the project root>, "text": <file>}]}.',
        f"The tool writes the file {entry}: its header comments and its system declaration "
        f"`system {system_owner}('{SYSTEM_CONFIG.as_posix()}') : version('1.0.0') {{}}`, then each fragment. "
        "Never write a system declaration, a header comment, an @profiles or an @analysis line.",
        f"Write `{LINE_COMMENT_MARKER} @{EXPECT} <VARIANT>` on its own line right ABOVE the line the variant fires "
        "on (never below it), or after the code on that line. Write no other @expect.",
        "Start from this clean service and change only what provokes the variant; here the variant fires on "
        "the service declaration's line:\n" + service_shape(example, "1.0.0", _EXAMPLE_VARIANT),
        "The system declares a gateway, so keep a public endpoint (auth(public), optional, required or webhook) "
        "in at least one service of the fragment unless the variant is about a service exposing none.",
        "Name each service as the request says, and give each its own owner configuration at the path the "
        "request says, in configs. An owner configuration imports the datasource templates and declares the "
        f"profile {TEST_PROFILE}; its container database takes the id the request names (a further service's, "
        "another lowercase UUID). Shape:\n" + owner_config_shape(example),
        f"When the variant needs a configuration value only one profile has, write `{LINE_COMMENT_MARKER} "
        f"@{PROFILE_DIRECTIVE} <p>` on the line right after the @expect, and declare `profile <p> as \"<p>\" "
        f"extends {TEST_PROFILE} {{ ... }}` in the owner configuration.",
        "Never write a password, token, key or other secret literal. A string literal of 32 or more letters, "
        "digits, '-', '_', '/' or '+' reads as one and fails the draft: keep paths and names shorter. Container "
        "databases keep `ssl = false;` from the templates; httpSecurity lists named hosts, never a wildcard.",
        "Provoke nothing else: any other diagnostic the fragment causes fails the draft.",
    ]
    if area.seeded:
        rules.append(f"Seed documents go in configs at {SEED_DIRECTORY}/<Entity>{SEED_SUFFIX}.")
    if area.target_checks:
        rules.append(
            "The file is analyzed and then checked against its targets once for every registered backend "
            "language: the variant is reported by those target checks, and must fire under each language, so "
            "provoke it with the source alone, never with a construct only one language has."
        )
    scaffold = "\n\n".join(
        f"--- {relative.as_posix()} ---\n{(root / relative).read_text(encoding='utf-8')}"
        for relative in (SYSTEM_CONFIG, DATASOURCE_TEMPLATES)
    )
    return "\n\n".join(
        [
            "RULES:\n" + "\n".join(f"- {rule}" for rule in rules),
            f"ANNOTATION FORMS:\n{annotation_reading.__doc__}",
            f"AREA PROJECTS:\n{annotations.__doc__}",
            f"THE PROJECT ROOT'S SCAFFOLD:\n{scaffold}",
        ]
    )


def catalog_entry(catalog: DiagnosticCatalog, variant: str) -> str:
    """The catalog entry of *variant*: its code's severity and summary, and the variant's texts."""
    code, _, name = variant.partition(VARIANT_SEPARATOR)
    entry = catalog.codes[code]
    found = entry.variants[name]
    lines = [
        f"code {code} ({entry.severity}): {entry.summary}",
        f"problem: {found.problem}",
        f"expected: {found.expected}",
    ]
    if found.valid is not None:
        lines.append(f"valid: {found.valid}")
    lines.append(f"fix: {found.fix}")
    tags = sorted(security_tags_of(code))
    if tags:
        lines.append(
            f"security: {code} guards a security control; its @expect carries one of the tags {tags} "
            f"(the area header carries them, or `{LINE_COMMENT_MARKER} @{TAGS_DIRECTIVE} <t>` right after it)."
        )
    return "\n".join(lines)


def old_example(diagnostics: Path, variant: str) -> str:
    """The old per-code fixture of *variant* under *diagnostics* -- its source and the configuration
    and seed documents beside it -- up to :data:`EXAMPLE_BUDGET_CHARS`; empty when none exists."""
    flat = diagnostics / f"{variant}{DATRIX_FILE_EXTENSION}"
    directory = diagnostics / variant
    if flat.is_file():
        files = [flat, *sorted(per_code_config_directory(flat).glob("*.dcfg"))]
        base = diagnostics
    elif (directory / PROJECT_FIXTURE_SOURCE).is_file():
        files = [directory / PROJECT_FIXTURE_SOURCE, *sorted(path for path in directory.rglob("*") if path.is_file()
                                                             and path.name != PROJECT_FIXTURE_SOURCE)]
        base = directory
    else:
        return ""
    parts: list[str] = []
    used = 0
    for path in files:
        text = f"--- {path.relative_to(base).as_posix()} ---\n{path.read_text(encoding='utf-8')}"
        if used + len(text) > EXAMPLE_BUDGET_CHARS:
            break
        parts.append(text)
        used += len(text)
    return "\n\n".join(parts)


def _words(text: str) -> frozenset[str]:
    return frozenset(word.lower() for word in _WORD.findall(text))


def reference_excerpt(reference: str, about: str, budget: int = REFERENCE_BUDGET_CHARS) -> str:
    """The sections of *reference* sharing the most words with *about*, in document order, up to
    *budget* characters; a section larger than what is left is passed over."""
    lines = reference.splitlines()
    sections = markdown_sections(lines, REFERENCE_HEADING_LEVEL)
    wanted = _words(about)
    texts = ["\n".join(lines[section.start - 1 : section.end]) for section in sections]
    ranked = sorted(range(len(texts)), key=lambda index: (-len(wanted & _words(texts[index])), index))
    chosen: list[int] = []
    used = 0
    for index in ranked:
        if not wanted & _words(texts[index]):
            break
        if used + len(texts[index]) <= budget:
            chosen.append(index)
            used += len(texts[index])
    return "\n\n".join(texts[index] for index in sorted(chosen))


@dataclass(frozen=True)
class DraftFiles:
    """One draft's fragment and the files it writes, as the model answered them.

    Attributes:
        source: The fragment of the area file.
        files: ``(path relative to the area root, text)`` for each configuration or seed document.
    """

    source: str
    files: tuple[tuple[str, str], ...]

    def rendered(self) -> str:
        """The draft as the prompt and the queue show it."""
        parts = [f"--- fragment ---\n{self.source}"]
        parts.extend(f"--- {path} ---\n{text}" for path, text in self.files)
        return "\n\n".join(parts)


def user_prompt(
    *,
    variant: str,
    catalog: DiagnosticCatalog,
    area: AreaPlan,
    example: str,
    reference: str,
    feedback: str,
    previous: DraftFiles | None,
    withheld: Callable[[str], bool],
) -> str:
    """The request for *variant*'s fragment: a part *withheld* flags is replaced by :data:`WITHHELD`."""

    def part(text: str) -> str:
        return WITHHELD if withheld(text) else text

    names = variant_names(variant)
    entry = catalog_entry(catalog, variant)
    sections = [
        f"{VARIANT_LABEL}{variant}",
        f"CATALOG ENTRY:\n{part(entry)}",
        f"NAMES: the first service is {names.service}, its owner configuration {names.config}, its container "
        f"database id {names.database_id}, its REST base path {names.base_path}; any further "
        f"service is {NAMESPACE}.{names.pascal}<Role>{SERVICE_SUFFIX} with its configuration at "
        f"{names.config_prefix}-<role>{SERVICE_CONFIG_SUFFIX}.",
    ]
    if example:
        sections.append(
            "AN OLDER FIXTURE PROVOKING THIS VARIANT (an example only: its system, names and paths do not "
            f"apply):\n{part(example)}"
        )
    excerpt = reference_excerpt(reference, f"{entry}\n{example}")
    if excerpt:
        sections.append(f"SYNTAX REFERENCE (excerpts):\n{part(excerpt)}")
    if feedback:
        sections.append(f"{FEEDBACK_HEADING}:\n{part(feedback)}")
    if previous is not None:
        sections.append(f"{PREVIOUS_DRAFT_HEADING}:\n{part(previous.rendered())}")
    return "\n\n".join(sections)


def area_reason(area: AreaPlan, variants: Iterable[str]) -> str:
    """The ``@reason`` of an area's header."""
    families = sorted({code_family(variant_code(variant)) for variant in variants})
    return (
        f"Each construct below provokes the catalog variant its @{EXPECT} names, and nothing else "
        f"({', '.join(families)} of area {area.name})."
    )


def allowed_path(path: str, names: VariantNames, *, seeded: bool) -> bool:
    """Whether a draft of the variant named *names* may write *path* (relative to its area root): an
    owner configuration under its own prefix, or in a seeded area a seed document."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or "\\" in path or ".." in pure.parts or not pure.parts:
        return False
    if path.startswith(names.config_prefix) and pure.suffix == ".dcfg" and len(pure.parts) == 2:
        return True
    return seeded and pure.parts[0] == SEED_DIRECTORY and pure.suffix == SEED_SUFFIX and len(pure.parts) == 2


__all__ = [
    "ANALYZER_OUTPUT_HEADING",
    "CASCADE_INSTRUCTION",
    "DRAFT_SCHEMA",
    "EXAMPLE_BUDGET_CHARS",
    "FEEDBACK_HEADING",
    "NAMESPACE",
    "NOT_PROVOKED_INSTRUCTION",
    "PREVIOUS_DRAFT_HEADING",
    "REFERENCE_BUDGET_CHARS",
    "SEED_DIRECTORY",
    "SEED_SUFFIX",
    "SERVICE_CONFIG_SUFFIX",
    "SERVICE_SUFFIX",
    "SYNTAX_REFERENCE",
    "VARIANT_LABEL",
    "WITHHELD",
    "DraftFiles",
    "VariantNames",
    "allowed_path",
    "area_reason",
    "catalog_entry",
    "old_example",
    "owner_config_shape",
    "reference_excerpt",
    "service_shape",
    "system_prompt",
    "user_prompt",
    "variant_names",
]
