"""What the parity gate reads off each conformance probe: the facets a parity row can select,
and the reading of each.

A parity row (``datrix_testing.cases.parity``) names a probe and a facet. This module is the
table the gate and its authoring tool share: for every probe a row may name, the fixture its
argument is built from (a generated example tree, the client trees of one example generated
for the run, an enum the example declares, or a web-security header-set fixture), and per facet the selector keys, the shape of the reading,
and the function that narrows the probe's return to that one value. A probe with no entry
here is refused by ``check`` -- a new reading is added as a facet here, and a new kind of
value as a Protocol method first.

Every reading is built from the probe's return alone: never a generated file path, never
source text beyond the value read, so a report can carry nothing but the reading and the
expectation. A reading that cannot be taken (the selected route is not registered, the
selected event is not published) raises ``SelectorError`` and the gate reports the row as
unreadable for that target.

Nothing here names a target; the readings are the same function for every language or
platform, and how a target's artifact is read stays in that target's own probe.
"""

from __future__ import annotations

import enum
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeVar

from datrix_common.datrix_model.wire_naming import body_wire_name
from datrix_common.utils.text import to_camel_case
from datrix_codegen_kernel.parity.conformance_probes import (
    EnumClassifierRender,
    EventEnvelopeCensus,
    PublishedEventEnvelope,
    RealizedGatewayProblem,
    RealizedRouteUrl,
    ResponseBodyWireField,
    RouteWireContract,
    route_key,
)
from datrix_codegen_kernel.platform.web_security_headers import WebSecurityHeaderSet, build_web_security_headers
from datrix_common.plugin.language_capability import EnumClassifierIdioms
from datrix_testing.cases.compare import Observation, Shape, stringify
from datrix_testing.cases.errors import SelectorError
from datrix_testing.cases.model import SelectorValue
from datrix_testing.cases.parity import FACET_KEY, ParityFacet, ParityObserver

Selector = Mapping[str, SelectorValue]
_T = TypeVar("_T")


class ProbeArgument(enum.Enum):
    """What a probe's argument is built from."""

    #: The example generated for the target; the probe reads the generated root.
    GENERATED_TREE = "generated-tree"
    #: One enum the example declares, rendered through the target's own enum generation.
    EXAMPLE_ENUM = "example-enum"
    #: A web-security header-set fixture, rendered through the target's static-site artifact.
    HEADER_SET = "header-set"
    #: Nothing: the probe renders the target's own system-gateway artifact.
    SYSTEM_GATEWAY = "system-gateway"
    #: The example generated once for the run; each client target reads its own client tree in it.
    CLIENT_TREE = "client-tree"


@dataclass(frozen=True)
class RenderedEnum:
    """A target's render of one enum, with the target's declared reading of it.

    Attributes:
        render: What the target's ``render_enum_classifier`` returned.
        idioms: How the target spells the classifier definitions (its capability declaration).
        declared_exception: The unrecognized-value exception the target's language profile declares.
    """

    render: EnumClassifierRender
    idioms: EnumClassifierIdioms
    declared_exception: str


@dataclass(frozen=True)
class FacetReading:
    """One facet: its spec, its reading, and the selectors a probe's return offers for it.

    Attributes:
        facet: The selector keys and the reading's shape.
        read: The probe's return and a row's selector to the one value the row compares.
        offers: The selectors (besides ``facet``) the probe's return offers, for proposing rows;
            ``None`` for a facet whose keys a person chooses.
    """

    facet: ParityFacet
    read: Callable[[object, Selector], Observation]
    offers: Callable[[object], Iterable[dict[str, SelectorValue]]] | None = None


@dataclass(frozen=True)
class ProbeReadings:
    """Everything the gate reads off one probe.

    Attributes:
        probe: The Protocol method.
        argument: What its argument is built from.
        facets: Its facets, by name.
        argument_keys: Selector keys every facet carries that choose the argument (an enum's name).
    """

    probe: str
    argument: ProbeArgument
    facets: Mapping[str, FacetReading]
    argument_keys: tuple[str, ...] = ()

    def facet_reading(self, selector: Selector) -> FacetReading:
        """The facet *selector* names.

        Raises:
            SelectorError: It names none of this probe's facets.
        """
        name = selector[FACET_KEY] if FACET_KEY in selector else None
        if not isinstance(name, str) or name not in self.facets:
            raise SelectorError(f"facet {name!r} is not one of {sorted(self.facets)} for {self.probe!r}")
        return self.facets[name]


def _typed(value: object, kind: type[_T], probe: str) -> _T:
    if not isinstance(value, kind):
        raise TypeError(f"probe {probe!r} returned a {type(value).__name__}, expected {kind.__name__}")
    return value


def _items(value: object, kind: type[_T], probe: str) -> tuple[_T, ...]:
    sequence = _typed(value, tuple, probe)
    return tuple(_typed(item, kind, probe) for item in sequence)


def _text(selector: Selector, key: str) -> str:
    value = selector[key]
    if not isinstance(value, str):
        raise SelectorError(f"selector key {key!r} is one string, got {value!r}")
    return value


def _texts(selector: Selector, key: str) -> frozenset[str]:
    value = selector[key]
    if not isinstance(value, list):
        raise SelectorError(f"selector key {key!r} is a list of strings, got {value!r}")
    return frozenset(value)


def _set(values: Iterable[str]) -> Observation:
    return Observation(Shape.SET, frozenset(values))


# ---------------------------------------------------------------------------
# Routes: route_wire_contracts
# ---------------------------------------------------------------------------

ROUTE_WIRE_CONTRACTS: Final[str] = "route_wire_contracts"


def route_label(contract: RouteWireContract) -> str:
    """``GET /api/v1/books/{}``: a route as a reading names it (verb and path shape)."""
    method, path = contract.key
    return f"{method.upper()} {path}"


def _contracts(result: object) -> tuple[RouteWireContract, ...]:
    return _items(result, RouteWireContract, ROUTE_WIRE_CONTRACTS)


def _read_route(result: object, selector: Selector) -> Observation:
    wanted = route_key(_text(selector, "verb"), _text(selector, "path"))
    matches = [contract for contract in _contracts(result) if contract.key == wanted]
    label = f"{wanted[0].upper()} {wanted[1]}"
    if not matches:
        raise SelectorError(f"{label} is not registered")
    if len(matches) > 1:
        raise SelectorError(f"{label} is registered {len(matches)} times")
    contract = matches[0]
    return Observation(
        Shape.MAPPING,
        {"status": stringify(contract.success_status), "body": contract.body_kind, "media-type": contract.media_type},
    )


def _one_route(result: object, selector: Selector) -> RouteWireContract:
    wanted = route_key(_text(selector, "verb"), _text(selector, "path"))
    matches = [contract for contract in _contracts(result) if contract.key == wanted]
    label = f"{wanted[0].upper()} {wanted[1]}"
    if len(matches) != 1:
        raise SelectorError(f"{label} is registered {len(matches)} times")
    return matches[0]


def _read_query_keys(result: object, selector: Selector) -> Observation:
    """The keys the route binds, each read as its camelCase words: every backend cases its
    query keys its own way (``sort_by``, ``sortBy``), so the row compares the set of
    parameters bound; each backend's own seam test proves its casing against the shared
    list-query derivation."""
    return _set(to_camel_case(key) for key in _one_route(result, selector).query_keys)


def _read_routes(result: object, selector: Selector) -> Observation:
    return _set(route_label(contract) for contract in _contracts(result))


def _read_duplicate_routes(result: object, selector: Selector) -> Observation:
    counts = Counter(route_label(contract) for contract in _contracts(result))
    return _set(label for label, count in counts.items() if count > 1)


def _offer_routes(result: object) -> Iterable[dict[str, SelectorValue]]:
    return [{"verb": contract.method, "path": contract.path} for contract in _contracts(result)]


# ---------------------------------------------------------------------------
# Response bodies: response_body_wire_fields
# ---------------------------------------------------------------------------

RESPONSE_BODY_WIRE_FIELDS: Final[str] = "response_body_wire_fields"


def _fields(result: object) -> tuple[ResponseBodyWireField, ...]:
    return _items(result, ResponseBodyWireField, RESPONSE_BODY_WIRE_FIELDS)


#: The schema kinds a migration proposes to set outside the population: a dependency response decodes
#: an upstream service's wire, whose casing that service dictates. A person confirms it per row.
_PROPOSED_EXCLUSIONS: Final[list[str]] = ["dependency_response"]


def _measured(result: object, selector: Selector) -> list[ResponseBodyWireField]:
    """The fields of every schema kind the selector does not exclude.

    A row never selects by schema kind, only excludes one: the kind is a response class's role on
    the wire, the same on every language, and the wire key a field emits is the fact.
    """
    excluded = _texts(selector, "excluding")
    return [item for item in _fields(result) if item.schema_kind not in excluded]


def _read_wire_name(result: object, selector: Selector) -> Observation:
    wanted = body_wire_name(_text(selector, "field"))
    return _set(
        item.effective_wire_name for item in _measured(result, selector) if body_wire_name(item.field_name) == wanted
    )


def _read_nonconformant_fields(result: object, selector: Selector) -> Observation:
    return _set(
        f"{item.schema_kind} {item.field_name} -> {item.effective_wire_name}"
        for item in _measured(result, selector)
        if item.effective_wire_name != body_wire_name(item.field_name)
    )


def _offer_wire_names(result: object) -> Iterable[dict[str, SelectorValue]]:
    fields = sorted({body_wire_name(item.field_name) for item in _fields(result)})
    return [{"field": name, "excluding": list(_PROPOSED_EXCLUSIONS)} for name in fields]


# ---------------------------------------------------------------------------
# Event envelopes: event_envelopes
# ---------------------------------------------------------------------------

EVENT_ENVELOPES: Final[str] = "event_envelopes"


def _census(result: object) -> EventEnvelopeCensus:
    return _typed(result, EventEnvelopeCensus, EVENT_ENVELOPES)


def _one_key_set(result: object, selector: Selector, keys_of: Callable[[PublishedEventEnvelope], frozenset[str]]) -> Observation:
    event = _text(selector, "event")
    key_sets = {keys_of(envelope) for envelope in _census(result).published if envelope.event_name == event}
    if not key_sets:
        raise SelectorError(f"event {event!r} is not published")
    if len(key_sets) > 1:
        listed = "; ".join(str(sorted(keys)) for keys in sorted(key_sets, key=sorted))
        raise SelectorError(f"the producers of event {event!r} write {len(key_sets)} different key sets: {listed}")
    return _set(next(iter(key_sets)))


def _read_envelope_keys(result: object, selector: Selector) -> Observation:
    return _one_key_set(result, selector, lambda envelope: envelope.envelope_keys)


def _read_payload_keys(result: object, selector: Selector) -> Observation:
    return _one_key_set(result, selector, lambda envelope: envelope.payload_keys)


def _read_published_events(result: object, selector: Selector) -> Observation:
    return _set(envelope.event_name for envelope in _census(result).published)


def _read_unwritten_consumed_keys(result: object, selector: Selector) -> Observation:
    census = _census(result)
    written = frozenset().union(*(envelope.envelope_keys for envelope in census.published))
    read = frozenset().union(*census.consumed_keys.values())
    return _set(read - written)


def _offer_events(result: object) -> Iterable[dict[str, SelectorValue]]:
    return [{"event": name} for name in sorted({envelope.event_name for envelope in _census(result).published})]


# ---------------------------------------------------------------------------
# Enum classifiers: render_enum_classifier
# ---------------------------------------------------------------------------

RENDER_ENUM_CLASSIFIER: Final[str] = "render_enum_classifier"
#: The selector key naming the example's enum the target renders.
ENUM_KEY: Final[str] = "enum"
#: The classifier families, by the DSL name a reading reports, and how each is recognized.
_CLASSIFIER_IDIOMS: Final[dict[str, Callable[[EnumClassifierIdioms], str]]] = {
    "equalsKeyword": lambda idioms: idioms.equals_keyword_definition,
    "containsKeyword": lambda idioms: idioms.contains_keyword_definition,
}
#: What a no-match raise of the target's own declared exception reads as.
DECLARED_EXCEPTION: Final[str] = "declared"


def _rendered_source(result: object) -> tuple[RenderedEnum, str]:
    rendered = _typed(result, RenderedEnum, RENDER_ENUM_CLASSIFIER)
    sources = rendered.render.sources
    if len(sources) != 1:
        raise SelectorError(f"the target rendered {len(sources)} source(s) for one enum; exactly one is expected")
    return rendered, sources[0]


def _read_classifiers(result: object, selector: Selector) -> Observation:
    rendered, source = _rendered_source(result)
    return _set(name for name, idiom in _CLASSIFIER_IDIOMS.items() if re.search(idiom(rendered.idioms), source))


def _read_no_match_raise(result: object, selector: Selector) -> Observation:
    rendered, source = _rendered_source(result)
    raises = {
        (DECLARED_EXCEPTION if exception == rendered.declared_exception else exception, message)
        for exception, message in re.findall(rendered.idioms.no_match_raise, source)
    }
    if not raises:
        raise SelectorError("the rendered source has no no-match raise")
    if len(raises) > 1:
        raise SelectorError(f"the rendered source has {len(raises)} different no-match raises: {sorted(raises)}")
    exception, message = next(iter(raises))
    return Observation(Shape.MAPPING, {"exception": exception, "message": message})


# ---------------------------------------------------------------------------
# Web security headers: realized_web_security_headers
# ---------------------------------------------------------------------------

REALIZED_WEB_SECURITY_HEADERS: Final[str] = "realized_web_security_headers"
#: Neutral origins the header-set fixtures are built with -- never a real or customer origin.
_FIXTURE_API_ORIGIN: Final[str] = "https://api.fixture.example"
_FIXTURE_IDENTITY_AUTHORITY: Final[str] = "https://auth.fixture.example"
#: The header-set fixtures a row may name, by whether the site is served on a loopback port.
HEADER_SET_FIXTURES: Final[dict[str, bool]] = {"web-security-domain": False, "web-security-loopback": True}


def header_set_fixture(name: str) -> WebSecurityHeaderSet:
    """The header set the fixture *name* stands for, built by the one shared builder.

    Raises:
        KeyError: *name* is not a header-set fixture.
    """
    return build_web_security_headers(
        api_origin=_FIXTURE_API_ORIGIN,
        identity_authority=_FIXTURE_IDENTITY_AUTHORITY,
        tile_origin=None,
        used_builtin_rows=frozenset(),
        is_loopback=HEADER_SET_FIXTURES[name],
    )


def _headers(result: object) -> Mapping[str, str]:
    headers = _typed(result, Mapping, REALIZED_WEB_SECURITY_HEADERS)
    return {_typed(name, str, REALIZED_WEB_SECURITY_HEADERS): _typed(value, str, REALIZED_WEB_SECURITY_HEADERS) for name, value in headers.items()}


def _read_header(result: object, selector: Selector) -> Observation:
    name = _text(selector, "name")
    headers = _headers(result)
    if name not in headers:
        raise SelectorError(f"header {name!r} is not emitted")
    return Observation(Shape.SCALAR, headers[name])


def _read_header_names(result: object, selector: Selector) -> Observation:
    return _set(_headers(result))


def _offer_headers(result: object) -> Iterable[dict[str, SelectorValue]]:
    return [{"name": name} for name in sorted(_headers(result))]


# ---------------------------------------------------------------------------
# Gateway problem documents: realized_gateway_problems
# ---------------------------------------------------------------------------

REALIZED_GATEWAY_PROBLEMS: Final[str] = "realized_gateway_problems"
#: The one fixture a gateway-problem row names: the target's own system gateway.
SYSTEM_GATEWAY_FIXTURE: Final[str] = "system-gateway"
#: The problem document members a reading carries (the body's own keys).
_PROBLEM_MEMBERS: Final[tuple[str, ...]] = ("type", "title", "status", "detail")


def _gateway_problems(result: object) -> dict[str, RealizedGatewayProblem]:
    problems = _items(result, RealizedGatewayProblem, REALIZED_GATEWAY_PROBLEMS)
    return {str(problem.status): problem for problem in problems}


def _read_gateway_problem(result: object, selector: Selector) -> Observation:
    status = _text(selector, "status")
    problems = _gateway_problems(result)
    if status not in problems:
        raise SelectorError(f"the gateway answers no status {status} itself")
    problem = problems[status]
    try:
        document = json.loads(problem.body)
    except json.JSONDecodeError as error:
        raise SelectorError(f"the gateway's {status} body is not a JSON document") from error
    if not isinstance(document, dict) or set(document) != set(_PROBLEM_MEMBERS):
        raise SelectorError(f"the gateway's {status} body is not a problem document with members {list(_PROBLEM_MEMBERS)}")
    reading = {member: stringify(document[member]) for member in _PROBLEM_MEMBERS}
    reading["content-type"] = problem.content_type
    return Observation(Shape.MAPPING, reading)


def _read_gateway_statuses(result: object, selector: Selector) -> Observation:
    return _set(_gateway_problems(result))


def _offer_gateway_statuses(result: object) -> Iterable[dict[str, SelectorValue]]:
    return [{"status": status} for status in sorted(_gateway_problems(result))]


# ---------------------------------------------------------------------------
# Client route URL builders: route_url_builders
# ---------------------------------------------------------------------------

ROUTE_URL_BUILDERS: Final[str] = "route_url_builders"
#: How a reading joins a route's query keys: in the order the builder writes them.
_QUERY_KEY_SEPARATOR: Final[str] = ","


def _route_urls(result: object) -> tuple[RealizedRouteUrl, ...]:
    return _items(result, RealizedRouteUrl, ROUTE_URL_BUILDERS)


def _read_route_url(result: object, selector: Selector) -> Observation:
    """The path a route's URL is built on (each path parameter ``{}``) and its query keys in order."""
    wanted = _text(selector, "route")
    matches = [builder for builder in _route_urls(result) if builder.route_key == wanted]
    if len(matches) != 1:
        raise SelectorError(f"route {wanted} has {len(matches)} URL builder entries")
    builder = matches[0]
    return Observation(
        Shape.MAPPING, {"path": builder.path, "query": _QUERY_KEY_SEPARATOR.join(builder.query_keys)}
    )


def _read_route_url_keys(result: object, selector: Selector) -> Observation:
    return _set(builder.route_key for builder in _route_urls(result))


def _offer_route_urls(result: object) -> Iterable[dict[str, SelectorValue]]:
    return [{"route": builder.route_key} for builder in _route_urls(result)]


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


def _facets(*readings: FacetReading) -> dict[str, FacetReading]:
    return {reading.facet.name: reading for reading in readings}


#: Every probe a parity row may name, and what the gate reads off it.
PROBE_READINGS: Final[dict[str, ProbeReadings]] = {
    readings.probe: readings
    for readings in (
        ProbeReadings(
            ROUTE_WIRE_CONTRACTS,
            ProbeArgument.GENERATED_TREE,
            _facets(
                FacetReading(
                    ParityFacet("route", Shape.MAPPING, ("verb", "path"), summary="status, body envelope and media type of one route"),
                    _read_route,
                    _offer_routes,
                ),
                FacetReading(ParityFacet("routes", Shape.SET, summary="every registered route, 'VERB /path/{}'"), _read_routes),
                FacetReading(
                    ParityFacet("duplicate-routes", Shape.SET, summary="routes registered more than once"), _read_duplicate_routes
                ),
                FacetReading(
                    ParityFacet(
                        "query-keys",
                        Shape.SET,
                        ("verb", "path"),
                        summary="the query keys one route binds, by the words of each key (casing is each backend's own)",
                    ),
                    _read_query_keys,
                    _offer_routes,
                ),
            ),
        ),
        ProbeReadings(
            RESPONSE_BODY_WIRE_FIELDS,
            ProbeArgument.GENERATED_TREE,
            _facets(
                FacetReading(
                    ParityFacet(
                        "wire-name",
                        Shape.SET,
                        ("field", "excluding"),
                        frozenset({"excluding"}),
                        summary="the wire keys one field emits, outside the excluded schema kinds",
                    ),
                    _read_wire_name,
                    _offer_wire_names,
                ),
                FacetReading(
                    ParityFacet(
                        "nonconformant-fields",
                        Shape.SET,
                        ("excluding",),
                        frozenset({"excluding"}),
                        summary="fields whose wire key is not the body wire-naming rule's, outside the excluded kinds",
                    ),
                    _read_nonconformant_fields,
                ),
            ),
        ),
        ProbeReadings(
            EVENT_ENVELOPES,
            ProbeArgument.GENERATED_TREE,
            _facets(
                FacetReading(
                    ParityFacet("envelope-keys", Shape.SET, ("event",), summary="the envelope keys one event is published under"),
                    _read_envelope_keys,
                    _offer_events,
                ),
                FacetReading(
                    ParityFacet("payload-keys", Shape.SET, ("event",), summary="the payload keys one event carries"),
                    _read_payload_keys,
                    _offer_events,
                ),
                FacetReading(ParityFacet("published-events", Shape.SET, summary="every event the tree publishes"), _read_published_events),
                FacetReading(
                    ParityFacet("unwritten-consumed-keys", Shape.SET, summary="envelope keys a consumer reads that no producer writes"),
                    _read_unwritten_consumed_keys,
                ),
            ),
        ),
        ProbeReadings(
            RENDER_ENUM_CLASSIFIER,
            ProbeArgument.EXAMPLE_ENUM,
            _facets(
                FacetReading(
                    ParityFacet("classifiers", Shape.SET, (ENUM_KEY,), summary="the keyword classifiers the enum's source defines"),
                    _read_classifiers,
                ),
                FacetReading(
                    ParityFacet("no-match-raise", Shape.MAPPING, (ENUM_KEY,), summary="exception and message of the no-match raise"),
                    _read_no_match_raise,
                ),
            ),
            argument_keys=(ENUM_KEY,),
        ),
        ProbeReadings(
            REALIZED_WEB_SECURITY_HEADERS,
            ProbeArgument.HEADER_SET,
            _facets(
                FacetReading(ParityFacet("header", Shape.SCALAR, ("name",), summary="the value one header is emitted with"), _read_header, _offer_headers),
                FacetReading(ParityFacet("headers", Shape.SET, summary="every header name the artifact emits"), _read_header_names),
            ),
        ),
        ProbeReadings(
            REALIZED_GATEWAY_PROBLEMS,
            ProbeArgument.SYSTEM_GATEWAY,
            _facets(
                FacetReading(
                    ParityFacet(
                        "problem",
                        Shape.MAPPING,
                        ("status",),
                        summary="content type and problem document members of one status the gateway answers itself",
                    ),
                    _read_gateway_problem,
                    _offer_gateway_statuses,
                ),
                FacetReading(
                    ParityFacet("statuses", Shape.SET, summary="every status the gateway answers itself"), _read_gateway_statuses
                ),
            ),
        ),
        ProbeReadings(
            ROUTE_URL_BUILDERS,
            ProbeArgument.CLIENT_TREE,
            _facets(
                FacetReading(
                    ParityFacet(
                        "url",
                        Shape.MAPPING,
                        ("route",),
                        summary="the path one route's URL is built on (each path parameter '{}') and its query keys, in order",
                    ),
                    _read_route_url,
                    _offer_route_urls,
                ),
                FacetReading(
                    ParityFacet("routes", Shape.SET, summary="every route key the client's URL builder takes"),
                    _read_route_url_keys,
                ),
            ),
        ),
    )
}


def accepted_inputs(readings: ProbeReadings, example_names: Sequence[str]) -> frozenset[str]:
    """The fixtures a row of *readings*' probe may name: the registered examples, or the header-set fixtures."""
    if readings.argument is ProbeArgument.HEADER_SET:
        return frozenset(HEADER_SET_FIXTURES)
    if readings.argument is ProbeArgument.SYSTEM_GATEWAY:
        return frozenset({SYSTEM_GATEWAY_FIXTURE})
    return frozenset(example_names)


def observer_specs(example_names: Sequence[str]) -> dict[str, ParityObserver]:
    """The facet specs of every probe in :data:`PROBE_READINGS`, for the parity row checks."""
    return {
        probe: ParityObserver(
            probe,
            {name: reading.facet for name, reading in readings.facets.items()},
            accepted_inputs(readings, example_names),
        )
        for probe, readings in PROBE_READINGS.items()
    }


__all__ = [
    "DECLARED_EXCEPTION",
    "ENUM_KEY",
    "EVENT_ENVELOPES",
    "HEADER_SET_FIXTURES",
    "PROBE_READINGS",
    "REALIZED_GATEWAY_PROBLEMS",
    "REALIZED_WEB_SECURITY_HEADERS",
    "SYSTEM_GATEWAY_FIXTURE",
    "RENDER_ENUM_CLASSIFIER",
    "RESPONSE_BODY_WIRE_FIELDS",
    "ROUTE_URL_BUILDERS",
    "ROUTE_WIRE_CONTRACTS",
    "FacetReading",
    "ProbeArgument",
    "ProbeReadings",
    "RenderedEnum",
    "Selector",
    "accepted_inputs",
    "header_set_fixture",
    "observer_specs",
    "route_label",
]
