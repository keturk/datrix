"""Whether a corpus entry provides what its tests need: needed − provided, read off the analyzed application.

An entry of the plan (``library_plan``) passes when, under every profile its system's config declares:

- the entry analyzes with no error diagnostic, and every ``.dcfg`` it reaches that declares a profile
  declares that one (a profile has no fallback to ``base``);
- every needed declaration is provided: a node of the analyzed ``Application`` whose class (or a base
  class) is the need's kind and whose path ends with the need's path, and every fact of the need is held by
  one such node. A system-level need (``System``, ``Application``) is the entry's system whatever its path;
  a ``ConfigDecl`` need is a ``.dcfg`` the entry reaches, by owner, ``<kind>.<owner>`` or file path, its
  facts read from the document resolved for the profile;
- every block family some service holds is lacking from another service of the entry: the control
  service an absence assertion reads.

A node's path is its owners' names and its own, split on ``.``; a node with no name adds none. A fact
``<key> <value>`` is held when its key resolves on the node and some resolved value, rendered, contains the
value (a bare key: some resolved value is present). The key resolves through the typed key table first
(the keys whose name is no attribute of the kind, from the census of ``needs.json``), then to the node's
attribute of that name or ``is_`` that name, compared without case, ``_`` or ``-``. ``type`` holds the
node's kind, a base class's name or the node's own path besides what the table resolves. A key that
resolves to nothing is unprovided: the need is never assumed. In a value, ``:name`` and ``{name}`` route
parameters are the same, and a ``%(name)s`` placeholder holds any word.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import Final

from datrix_common.config.dcfg.ast_nodes import ConfigDecl
from datrix_common.config.dcfg.errors import DcfgResolutionError
from datrix_common.config.dcfg.resolver import DcfgResolver
from datrix_common.config_resolution import ConfigResolutionError
from datrix_common.datrix_model.base import NamedNode, Node
from datrix_common.datrix_model.callables import Endpoint
from datrix_common.datrix_model.containers import Application, Service
from datrix_common.datrix_model.project_root import application_project_root
from datrix_common.datrix_model.ref import Ref
from datrix_common.errors.codegen import SeedParseStageError
from datrix_common.types.base import DatrixType
from datrix_testing.config_documents import disk_config_documents
from datrix_testing.corpus import corpus_entry, corpus_project_root, corpus_reached_files
from datrix_testing.parsing import parse_as_written, register_installed_parsers
from datrix_testing.project import analysis_of

from datrix_scripts.dev.fixture_author.library_plan import (
    LIBRARY_ENTRY,
    SYSTEM_KINDS,
    ChoiceKeys,
    EntryPlan,
    LibraryPlan,
    fact_parts,
)
from datrix_scripts.dev.fixture_author.needs_reading import Declaration

#: The fact key every kind answers with its own kind name.
TYPE_KEY: Final = "type"
#: The prefix a boolean attribute carries before the name a fact reads (``indexed`` is ``is_indexed``).
FLAG_PREFIX: Final = "is"
CONFIG_SUFFIX: Final = ".dcfg"

_SEGMENT_BREAK: Final = re.compile(r"[./]")
_KEY_SEPARATOR: Final = "."
_NAME_NOISE: Final = re.compile(r"[_\-]")
_ROUTE_PARAMETER: Final = re.compile(r":(\w+)")
_PLACEHOLDER: Final = re.compile(r"%\\\(\w+\\\)s")
_ANY_WORD: Final = r"\S+"
_RENDER_JOIN: Final = ", "
_SHOWN_VALUES: Final = 3
_SHOWN_CHARS: Final = 120
_SCALARS: Final = (str, int, float, bool, Enum)


class FactState(StrEnum):
    """Whether a node holds a fact, and why not."""

    HELD = "held"
    NO_KEY = "its key names nothing on the declaration"
    NOT_HELD = "no resolved value holds it"


@dataclass(frozen=True)
class ResolvedConfig:
    """A ``.dcfg`` the entry reaches: its declaration and its values resolved for one profile, by dotted key."""

    decl: ConfigDecl
    path: Path
    values: Mapping[str, object]


@dataclass(frozen=True)
class Provided:
    """One declaration the analyzed entry holds: its class and base class names, its path and the subject read."""

    kinds: frozenset[str]
    path: tuple[str, ...]
    subject: Node | ResolvedConfig


@dataclass(frozen=True)
class Unprovided:
    """A need, or one fact of it, the entry does not provide under *profile*, and why."""

    profile: str
    kind: str
    path: str
    fact: str | None
    reason: str


@dataclass(frozen=True)
class EntryCheck:
    """One entry's verdict: the profiles run, the errors, the needs unprovided and the families every
    service holds (no control service lacks them)."""

    entry: str
    profiles: tuple[str, ...]
    errors: tuple[str, ...]
    unprovided: tuple[Unprovided, ...]
    uncontrolled: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """No error, nothing unprovided and every family controlled."""
        return not self.errors and not self.unprovided and not self.uncontrolled


def segments(path: str) -> tuple[str, ...]:
    """The segments of a declaration path, split on ``.`` and ``/``."""
    return tuple(part for part in _SEGMENT_BREAK.split(path) if part)


def _normal(name: str) -> str:
    return _NAME_NOISE.sub("", name).lower()


def _route(node: Node) -> list[object]:
    if not isinstance(node, Endpoint) or not node.method:
        return []
    return [f"{node.method.upper()} {node.full_path}"]


def _method(node: Node) -> list[object]:
    if not isinstance(node, Endpoint) or not node.method:
        return []
    return [node.method.upper()]


def _attributes(*names: str) -> Callable[[Node], list[object]]:
    def read(node: Node) -> list[object]:
        return [getattr(node, name) for name in names if hasattr(node, name)]

    return read


#: The keys ``needs.json`` reads that name no attribute of their kind, by (kind or base class, normalized
#: key), each with what it reads. Built from the key census of ``needs.json``: a key absent from it and from
#: the kind's attributes resolves to nothing.
KEY_TABLE: Final[Mapping[tuple[str, str], Callable[[Node], list[object]]]] = {
    ("Field", TYPE_KEY): _attributes("resolved_type"),
    ("ComputedField", TYPE_KEY): _attributes("resolved_type"),
    ("Parameter", TYPE_KEY): _attributes("resolved_type"),
    ("Callable", TYPE_KEY): _attributes("return_type"),
    ("Endpoint", "route"): _route,
    ("Endpoint", "method"): _method,
    ("Endpoint", "path"): _attributes("path", "full_path"),
    ("Endpoint", "auth"): _attributes("auth_syntax"),
    ("RestApi", "route"): _attributes("base_path"),
    ("GraphqlApi", "route"): _attributes("base_path"),
    ("FieldContainer", "field"): _attributes("fields"),
    ("Entity", "tenantable"): _attributes("traits"),
    ("Service", "uses"): _attributes("uses_directives"),
}


def _attribute_names(subject: object) -> dict[str, str]:
    """Each public attribute of *subject* holding a value, by normalized name."""
    names: dict[str, str] = {}
    for name in dir(subject):
        if not name.startswith("_"):
            names.setdefault(_normal(name), name)
    return names


def _attribute_values(subject: object, key: str) -> list[object]:
    names = _attribute_names(subject)
    found: list[object] = []
    for normal in (_normal(key), FLAG_PREFIX + _normal(key)):
        if normal in names:
            try:
                value = getattr(subject, names[normal])
            except AttributeError:
                continue
            if not callable(value) or isinstance(value, (Node, Ref, DatrixType)):
                found.append(value)
    return found


def _config_values(config: ResolvedConfig, key: str) -> list[object]:
    wanted = _normal(key)
    found = [
        value for dotted, value in config.values.items()
        if _normal(dotted) == wanted or _normal(dotted.rsplit(_KEY_SEPARATOR, 1)[-1]) == wanted
    ]
    if wanted == TYPE_KEY:
        found.append(config.decl.kind)
    return found + _attribute_values(config.decl, key)


def resolve_key(provided: Provided, key: str) -> list[object]:
    """Every value *key* resolves to on *provided*: the typed key table's, then its attributes'; a dotted
    key resolves its first name so, then each further name as an attribute of what the last one held."""
    subject = provided.subject
    if isinstance(subject, ResolvedConfig):
        return _config_values(subject, key)
    head, *tail = key.split(_KEY_SEPARATOR)
    found = _own_values(provided, head)
    for name in tail:
        found = [value for held in found for value in _attribute_values(held, name)]
    return found


def _own_values(provided: Provided, key: str) -> list[object]:
    subject = provided.subject
    found: list[object] = []
    for kind in sorted(provided.kinds):
        read = KEY_TABLE.get((kind, _normal(key)))
        if read is not None:
            found.extend(read(subject))
    return found + _attribute_values(subject, key)


def render(value: object) -> str:
    """*value* as text: a name for a node, reference or type; keys of a mapping; members of a collection."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, DatrixType):
        return value.display_name()
    if isinstance(value, Ref):
        return str(value.source_name)
    if isinstance(value, NamedNode):
        return render(value.name)
    if isinstance(value, Mapping):
        return _RENDER_JOIN.join(render(key) for key in value)
    if isinstance(value, (set, frozenset)):
        return _RENDER_JOIN.join(sorted(render(each) for each in value))
    if isinstance(value, (list, tuple)):
        return _RENDER_JOIN.join(render(each) for each in value)
    return str(value)


def _present(value: object) -> bool:
    if value is None or value is False or value == "":
        return False
    return not (isinstance(value, (Mapping, list, tuple, set, frozenset)) and not value)


def _routes(text: str) -> str:
    return _ROUTE_PARAMETER.sub(r"{\1}", text)


def _value_pattern(value: str) -> re.Pattern[str]:
    return re.compile(_PLACEHOLDER.sub(lambda _: _ANY_WORD, re.escape(_routes(value))))


def _names_itself(provided: Provided, value: str) -> bool:
    if value in provided.kinds:
        return True
    named = segments(value)
    return bool(named) and provided.path[-len(named):] == named


def fact_state(provided: Provided, fact: str) -> tuple[FactState, tuple[str, ...]]:
    """Whether *provided* holds *fact*, with the rendered values its key resolved to."""
    key, value = fact_parts(fact)
    if key == TYPE_KEY and value and _names_itself(provided, value):
        return FactState.HELD, ()
    values = resolve_key(provided, key)
    if not values:
        return FactState.NO_KEY, ()
    rendered = tuple(_routes(render(each)) for each in values)
    if not value:
        held = any(_present(each) for each in values)
    else:
        pattern = _value_pattern(value)
        held = any(pattern.search(text) for text in rendered)
    return (FactState.HELD if held else FactState.NOT_HELD), rendered


def _kind_names(subject: object) -> frozenset[str]:
    return frozenset(cls.__name__ for cls in type(subject).__mro__ if cls is not object)


def _node_segments(node: Node) -> tuple[str, ...]:
    if isinstance(node, NamedNode) and node.name:
        return segments(str(node.name))
    return ()


def _walk(root: Node, prefix: tuple[str, ...], seen: set[int]) -> Iterator[Provided]:
    pending = [(root, prefix)]
    while pending:
        node, owner = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        path = owner + _node_segments(node)
        yield Provided(_kind_names(node), path, node)
        pending.extend((child, path) for child in node.children())


def application_declarations(application: Application) -> list[Provided]:
    """Every declaration of *application*: the system and the application itself at the system's path,
    each service, module and their members, and the identity block with its providers."""
    system = application.system
    system_path = segments(str(system.name)) if system is not None else ()
    seen: set[int] = {id(application)}
    provided = [Provided(_kind_names(application), system_path, application)]
    if system is not None:
        provided.extend(_walk(system, (), seen))
    for child in application.children():
        provided.extend(_walk(child, (), seen))
    identity = application.identity
    if identity is not None:
        provided.extend(_walk(identity, (), seen))
        identity_path = _node_segments(identity)
        for provider in identity.providers:
            provided.extend(_walk(provider, identity_path, seen))
    return provided


def _flatten(values: Mapping[str, object], prefix: str = "") -> Iterator[tuple[str, object]]:
    for key, value in values.items():
        dotted = f"{prefix}{key}"
        yield dotted, value
        if isinstance(value, Mapping):
            yield from _flatten(value, f"{dotted}.")


def _declared_profiles(decl: ConfigDecl) -> tuple[str, ...]:
    return tuple(profile.name for profile in decl.profiles)


def config_declarations(root: Path, scenario: str, profile: str) -> tuple[list[Provided], list[str]]:
    """Every ``.dcfg`` *scenario* of the corpus at *root* reaches, resolved for *profile*, and the errors:
    a document declaring profiles but not this one, or one that does not resolve."""
    documents = disk_config_documents()
    provided: list[Provided] = []
    errors: list[str] = []
    for path in corpus_reached_files(root, scenario):
        if path.suffix != CONFIG_SUFFIX:
            continue
        decl = documents.config_document(path)
        values: dict[str, object] = {}
        declared = _declared_profiles(decl)
        if declared and profile not in declared:
            errors.append(f"{profile}: {path.name} declares the profiles {list(declared)}, not {profile!r}")
        elif declared:
            # A document of templates only declares no profile: it is read through an import.
            resolver = DcfgResolver(decl, corpus_project_root(root, path), str(path), documents=documents)
            try:
                values = dict(_flatten(resolver.resolve(profile)))
            except DcfgResolutionError as error:
                errors.append(f"{profile}: {path.name} does not resolve: {error}")
        owner = segments(decl.owner)
        for config_path in (owner, (decl.kind, *owner), segments(path.relative_to(root.resolve()).as_posix())):
            provided.append(Provided(_kind_names(decl), config_path, ResolvedConfig(decl, path, values)))
    return provided, errors


def entry_profiles(entry: Path) -> tuple[str, ...]:
    """The profiles the system config of the entry at *entry* declares: the profiles it runs.

    Raises:
        ValueError: the entry declares no system, its system names no config, or the config declares no
            profile.
    """
    application = parse_as_written(entry)
    project_root = application_project_root(application)
    system = application.system
    if system is None or project_root is None or not system.config_path:
        raise ValueError(f"{entry.name} declares no system naming a config, so it runs no profile")
    profiles = _declared_profiles(disk_config_documents().config_document(project_root / system.config_path))
    if not profiles:
        raise ValueError(f"{entry.name}: the system config {system.config_path} declares no profile")
    return profiles


def _candidates(need: Declaration, provided: Sequence[Provided]) -> list[Provided]:
    of_kind = [each for each in provided if need.kind in each.kinds]
    if need.kind in SYSTEM_KINDS:
        return of_kind
    named = segments(need.path)
    if not named:
        return []
    return [each for each in of_kind if each.path[-len(named):] == named]


def _shown(values: Iterable[tuple[str, ...]]) -> str:
    texts = sorted({text for rendered in values for text in rendered if text})
    shown = "; ".join(text[:_SHOWN_CHARS] for text in texts[:_SHOWN_VALUES])
    return f" (it holds: {shown})" if shown else ""


def unprovided_needs(needs: Iterable[Declaration], provided: Sequence[Provided], profile: str) -> list[Unprovided]:
    """needed − provided: each need with no candidate declaration, and each fact no candidate holds."""
    missing: list[Unprovided] = []
    for need in needs:
        candidates = _candidates(need, provided)
        if not candidates:
            missing.append(Unprovided(profile, need.kind, need.path, None, f"no {need.kind} at {need.path!r}"))
            continue
        for fact in need.facts:
            states = [fact_state(each, fact) for each in candidates]
            if any(state is FactState.HELD for state, _ in states):
                continue
            no_key = all(state is FactState.NO_KEY for state, _ in states)
            reason = FactState.NO_KEY if no_key else FactState.NOT_HELD
            shown = "" if no_key else _shown(rendered for _, rendered in states)
            missing.append(Unprovided(profile, need.kind, need.path, fact, f"{reason.value}{shown}"))
    return missing


def uncontrolled_families(provided: Sequence[Provided], families: Mapping[str, str]) -> list[str]:
    """The block families every service of the entry holds: no service lacks them for an absence assertion."""
    services = [each.path for each in provided if Service.__name__ in each.kinds]
    held: list[set[str]] = []
    for service in dict.fromkeys(services):
        held.append({
            families[kind]
            for each in provided
            if len(each.path) > len(service) and each.path[: len(service)] == service
            for kind in each.kinds & families.keys()
        })
    return sorted(set.intersection(*held)) if held else []


def _analysis_errors(entry: Path, profile: str) -> tuple[Application | None, list[str]]:
    try:
        result = analysis_of(entry, profile=profile)
    except (ConfigResolutionError, DcfgResolutionError, SeedParseStageError) as error:
        return None, [f"{profile}: {error}"]
    if not result.is_valid:
        return None, [f"{profile}: {each.code} {each.location}: {each.message}" for each in result.errors]
    return result.app, []


def check_entry(root: Path, plan: EntryPlan, families: Mapping[str, str]) -> EntryCheck:
    """Check the entry *plan* names in the corpus at *root* under every profile it runs."""
    register_installed_parsers()
    needs = plan.needs()
    try:
        entry = corpus_entry(root, plan.entry)
        profiles = entry_profiles(entry)
    except (FileNotFoundError, ValueError) as error:
        not_run = tuple(Unprovided("", need.kind, need.path, None, "the entry does not run") for need in needs)
        return EntryCheck(plan.entry, (), (str(error),), not_run, ())
    errors: list[str] = []
    missing: list[Unprovided] = []
    uncontrolled: set[str] = set()
    for profile in profiles:
        application, analysis_errors = _analysis_errors(entry, profile)
        configs, config_errors = config_declarations(root, plan.entry, profile)
        errors.extend(analysis_errors + config_errors)
        if application is None:
            continue
        provided = application_declarations(application) + configs
        missing.extend(unprovided_needs(needs, provided, profile))
        uncontrolled.update(uncontrolled_families(provided, families))
    return EntryCheck(plan.entry, profiles, tuple(errors), tuple(missing), tuple(sorted(uncontrolled)))


def check_library(root: Path, plan: LibraryPlan, families: Mapping[str, str]) -> tuple[EntryCheck, ...]:
    """Check every entry of *plan* in the corpus at *root*."""
    return tuple(check_entry(root, entry, families) for entry in plan.entries)


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, _SCALARS)


def _number(text: str, kind: type[float]) -> bool:
    try:
        kind(text)
    except ValueError:
        return False
    return True


def _could_hold(current: object, value: str) -> bool:
    """Whether a scalar of *current*'s type can render as *value*: the value of a choice, not prose. A text
    choice (or one unset) is one word, as the system choices are identifiers and versions."""
    if isinstance(current, bool):
        return value.lower() in {render(True), render(False)}
    if isinstance(current, Enum):
        return value in {str(member.value) for member in type(current)} | set(type(current).__members__)
    if isinstance(current, int):
        return _number(value, int)
    if isinstance(current, float):
        return _number(value, float)
    return len(value.split()) == 1


def system_choices(application: Application) -> ChoiceKeys:
    """Whether a fact of a system-level declaration is a choice: its key resolves on *application*'s system
    or the application itself to scalar values only, so the entry holds one value for it, and its value is
    one those scalars' types can take."""
    provided = [each for each in application_declarations(application) if each.kinds & SYSTEM_KINDS]

    def is_choice(kind: str, key: str, value: str) -> bool:
        values = [held for each in provided if kind in each.kinds for held in resolve_key(each, key)]
        return bool(values) and all(_is_scalar(held) and _could_hold(held, value) for held in values)

    return is_choice


def library_choices(root: Path) -> ChoiceKeys:
    """The system choices of the ``library`` entry of the corpus at *root*, analyzed under its first profile.

    Raises:
        ValueError: the library entry does not analyze clean, naming its errors.
        FileNotFoundError: the corpus at *root* holds no ``library`` entry.
    """
    register_installed_parsers()
    entry = corpus_entry(root, LIBRARY_ENTRY)
    profile = entry_profiles(entry)[0]
    application, errors = _analysis_errors(entry, profile)
    if application is None:
        raise ValueError(f"{entry} does not analyze clean under {profile!r}: {errors}")
    return system_choices(application)


__all__ = [
    "CONFIG_SUFFIX",
    "FLAG_PREFIX",
    "KEY_TABLE",
    "TYPE_KEY",
    "EntryCheck",
    "FactState",
    "Provided",
    "ResolvedConfig",
    "Unprovided",
    "application_declarations",
    "check_entry",
    "check_library",
    "config_declarations",
    "entry_profiles",
    "fact_state",
    "library_choices",
    "render",
    "resolve_key",
    "segments",
    "system_choices",
    "unprovided_needs",
    "uncontrolled_families",
]
