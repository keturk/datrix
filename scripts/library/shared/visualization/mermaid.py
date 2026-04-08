"""Mermaid diagram builders for Datrix Application models.

Provides syntax helpers and 8 diagram builders that produce Mermaid-compatible
strings from a fully resolved Application AST.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from datrix_common.generation.relationship_kind import RelationshipKind
from datrix_common.paths import ServicePaths
from datrix_common.utils.text import to_snake_case

from .traversal import (
    all_cqrs_with_service,
    all_endpoints_with_service,
    all_entities_with_service,
    all_events_with_context,
    all_relationships_with_context,
    all_subscriptions_with_context,
    service_dependency_edges,
)

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application, Service
    from datrix_common.datrix_model.entity import Entity

# ── Cardinality map (extracted from doc_generator.py, with MANY_TO_MANY added) ──

CARDINALITY_MAP: dict[str, str] = {
    RelationshipKind.HAS_MANY.value: "||--o{",
    RelationshipKind.BELONGS_TO.value: "}o--||",
    RelationshipKind.HAS_ONE.value: "||--||",
    RelationshipKind.MANY_TO_MANY.value: "}o--o{",
}

# ── Mermaid shape templates ──

_SHAPES: dict[str, tuple[str, str]] = {
    "default": ("[", "]"),
    "rounded": ("(", ")"),
    "database": ("[(", ")]"),
    "queue": ("[[", "]]"),
    "stadium": ("([", "])"),
    "hexagon": ("{{", "}}"),
    "trapezoid": ("[/", "/]"),
}

_NON_ALNUM = re.compile(r"[^a-zA-Z0-9_]")


# ── Syntax helpers ──


def sanitize_id(name: str) -> str:
    """Convert a qualified name to a valid Mermaid node ID.

    Replaces dots, hyphens, and spaces with underscores, then lowercases.
    """
    return str(to_snake_case(str(name).replace(".", "_").replace("-", "_")))


def mermaid_node(node_id: str, label: str, shape: str = "default") -> str:
    """Render a Mermaid node definition.

    Args:
        node_id: Valid Mermaid ID (use sanitize_id to produce).
        label: Human-readable label.
        shape: One of default, rounded, database, queue, stadium, hexagon, trapezoid.

    Returns:
        Mermaid node string, e.g. ``my_db[(PostgreSQL)]``.

    Raises:
        ValueError: If shape is not a recognized Mermaid shape.
    """
    if shape not in _SHAPES:
        available = sorted(_SHAPES.keys())
        raise ValueError(
            f"Unknown Mermaid shape '{shape}'. Available: {', '.join(available)}"
        )
    left, right = _SHAPES[shape]
    escaped_label = str(label).replace('"', "'")
    return f"    {node_id}{left}\"{escaped_label}\"{right}"


def mermaid_edge(
    from_id: str,
    to_id: str,
    label: str = "",
    style: str = "-->",
) -> str:
    """Render a Mermaid edge definition.

    Args:
        from_id: Source node ID.
        to_id: Target node ID.
        label: Optional edge label.
        style: Arrow style (-->, -.-, ==>, etc.).

    Returns:
        Mermaid edge string.
    """
    if label:
        return f"    {from_id} {style}|{label}| {to_id}"
    return f"    {from_id} {style} {to_id}"


def mermaid_subgraph(title: str, lines: list[str]) -> str:
    """Wrap lines in a Mermaid subgraph block.

    Args:
        title: Subgraph title.
        lines: Lines of Mermaid content (nodes, edges).

    Returns:
        Multi-line string with subgraph block.
    """
    body = "\n".join(f"    {line.strip()}" for line in lines if line.strip())
    return f'    subgraph "{title}"\n{body}\n    end'


# ── Helper for extracting service simple name ──


def _simple_name(service: Service) -> str:
    """Extract the short service name (without namespace)."""
    return ServicePaths(service.name).simple_name


def _service_id(service: Service) -> str:
    """Produce a Mermaid-safe ID for a service."""
    return sanitize_id(_simple_name(service))


# ── Diagram builders ──


def build_system_context(app: Application) -> str:
    """Build a C4-inspired system context diagram (graph TD).

    Shows external actors, system boundary, and services.
    """
    lines: list[str] = ["graph TD"]

    # Collect services
    service_ids: list[str] = []
    for service in app.services.values():
        sid = _service_id(service)
        sname = _simple_name(service)
        service_ids.append(sid)
        lines.append(mermaid_node(sid, sname, "rounded"))

    # Service-to-service dependencies
    for from_name, to_name in service_dependency_edges(app):
        from_id = sanitize_id(ServicePaths(from_name).simple_name)
        to_id = sanitize_id(ServicePaths(to_name).simple_name)
        if from_id in service_ids and to_id in service_ids:
            lines.append(mermaid_edge(from_id, to_id))

    return "\n".join(lines)


class _InfraGroup:
    """Tracks connections from services to a shared infrastructure node."""

    __slots__ = ("engine_label", "shape", "connections")

    def __init__(self, engine_label: str, shape: str) -> None:
        self.engine_label = engine_label
        self.shape = shape
        self.connections: list[tuple[str, str]] = []  # (service_id, edge_label)


def _brokers_identity(brokers: list[str] | str | None) -> str:
    """Produce a stable string identity for a pubsub brokers config value.

    Handles list of strings, single string, EnvRef objects, or None.
    """
    if brokers is None:
        return ""
    if isinstance(brokers, str):
        return brokers
    if isinstance(brokers, list):
        return ",".join(str(b) for b in sorted(str(b) for b in brokers))
    return str(brokers)


def _host_port_label(key: tuple[str, ...]) -> str:
    """Extract a host:port suffix from an infra identity key for display.

    Returns empty string if no meaningful host/port, otherwise ' (host:port)'.
    Key format is (engine_label, host_or_id, port_or_extra).
    """
    if len(key) < 3:
        return ""
    host = key[1]
    port = key[2]
    # Skip if host looks like a sanitized service ID (no dots, no 'localhost')
    if not host or (host != "localhost" and "." not in host and ":" not in host):
        return ""
    # If host already contains port (e.g. brokers "localhost:9092"), don't append port again
    if ":" in host:
        return f" ({host})"
    if port:
        return f" ({host}:{port})"
    return f" ({host})"


def build_service_map(app: Application) -> str:
    """Build a service map with shared infrastructure nodes (graph TD).

    Groups infrastructure by resolved config identity (engine + host + port)
    so that services sharing the same server appear connected to one node.
    When config is not resolved, falls back to per-service infra nodes.
    """
    lines: list[str] = ["graph LR"]

    # ── Phase 1: Collect infrastructure identities ──
    #
    # Each dict maps an identity key → (engine_label, list of (service_id, edge_label))
    # Identity keys are tuples like ("postgres", "localhost", 5432).

    rdbms_infra: dict[tuple[str, ...], _InfraGroup] = {}
    cache_infra: dict[tuple[str, ...], _InfraGroup] = {}
    pubsub_infra: dict[tuple[str, ...], _InfraGroup] = {}
    nosql_infra: dict[tuple[str, ...], _InfraGroup] = {}
    # Storage is always per-service (no host/port concept)
    storage_edges: list[tuple[str, str]] = []  # (service_id, block_name)

    for service in app.services.values():
        sid = _service_id(service)

        # RDBMS blocks
        for block_name, rdbms_block in service.rdbms_blocks.items():
            if rdbms_block._config is not None:
                cfg = rdbms_block.config
                engine_label = str(cfg.engine.canonical_name)
                key: tuple[str, ...] = (engine_label, cfg.host or "", str(cfg.port or ""))
                db_name = cfg.database or str(block_name)
            else:
                engine_label = "PostgreSQL"
                # No config → unique per service+block
                key = (engine_label, sid, str(block_name))
                db_name = str(block_name)

            group = rdbms_infra.setdefault(key, _InfraGroup(engine_label, "database"))
            group.connections.append((sid, db_name))

        # Cache block
        if service.cache_block is not None:
            if service.cache_block._config is not None:
                cfg_cache = service.cache_block.config
                engine_label = str(cfg_cache.engine.canonical_name)
                key = (engine_label, cfg_cache.host or "", str(cfg_cache.port or ""))
            else:
                engine_label = "Redis"
                key = (engine_label, sid, "cache")

            group = cache_infra.setdefault(key, _InfraGroup(engine_label, "default"))
            group.connections.append((sid, ""))

        # Pubsub blocks
        for block_name, pubsub_block in service.pubsub_blocks.items():
            if pubsub_block._config is not None:
                cfg_mq = pubsub_block.config
                engine_label = str(cfg_mq.engine.canonical_name)
                brokers_str = _brokers_identity(cfg_mq.brokers)
                key = (engine_label, brokers_str, str(cfg_mq.port or ""))
            else:
                engine_label = "MQ"
                key = (engine_label, sid, str(block_name))

            group = pubsub_infra.setdefault(key, _InfraGroup(engine_label, "queue"))
            group.connections.append((sid, str(block_name)))

        # NoSQL blocks
        for block_name, nosql_block in service.nosql_blocks.items():
            if nosql_block._config is not None:
                cfg_nosql = nosql_block.config
                engine_label = str(cfg_nosql.engine.canonical_name)
                key = (engine_label, str(cfg_nosql.host or ""), str(cfg_nosql.port or ""))
                db_name = str(cfg_nosql.database or block_name)
            else:
                engine_label = "NoSQL"
                key = (engine_label, sid, str(block_name))
                db_name = str(block_name)

            group = nosql_infra.setdefault(key, _InfraGroup(engine_label, "database"))
            group.connections.append((sid, db_name))

        # Storage blocks (always per-service)
        for block_name in service.storage_blocks:
            storage_edges.append((sid, str(block_name)))

    # ── Phase 2: Draw service nodes ──

    for service in app.services.values():
        sid = _service_id(service)
        sname = _simple_name(service)
        lines.append(mermaid_node(sid, sname, "rounded"))

    # ── Phase 3: Draw shared infrastructure nodes and edges ──

    infra_counter = 0

    def _emit_infra_group(
        infra_dict: dict[tuple[str, ...], _InfraGroup],
        prefix: str,
    ) -> None:
        nonlocal infra_counter
        for key, group in infra_dict.items():
            infra_counter += 1
            node_id = f"{prefix}_{infra_counter}"
            # Build label: engine + host:port if available
            host_port = _host_port_label(key)
            label = f"{group.engine_label}{host_port}"
            lines.append(mermaid_node(node_id, label, group.shape))
            for svc_id, edge_label in group.connections:
                lines.append(mermaid_edge(svc_id, node_id, edge_label))

    _emit_infra_group(rdbms_infra, "rdbms")
    _emit_infra_group(cache_infra, "cache")
    _emit_infra_group(pubsub_infra, "mq")
    _emit_infra_group(nosql_infra, "nosql")

    # Storage (always per-service)
    for svc_id, block_name in storage_edges:
        infra_counter += 1
        node_id = f"storage_{infra_counter}"
        lines.append(mermaid_node(node_id, f"Storage: {block_name}", "trapezoid"))
        lines.append(mermaid_edge(svc_id, node_id))

    # ── Phase 4: Service-to-service dependencies ──

    for from_name, to_name in service_dependency_edges(app):
        from_id = _service_id_from_name(from_name)
        to_id = _service_id_from_name(to_name)
        lines.append(mermaid_edge(from_id, to_id, "HTTP"))

    return "\n".join(lines)


def _service_id_from_name(name: str) -> str:
    """Produce a Mermaid-safe ID from a full service name."""
    return sanitize_id(ServicePaths(name).simple_name)


_ERD_SANITIZE = re.compile(r"[^a-zA-Z0-9_]")


def _erd_type_display(field_type: object) -> tuple[str, bool]:
    """Convert a DatrixType to a Mermaid ERD-safe type name.

    Mermaid ERD only accepts ``[A-Za-z_][A-Za-z0-9_]*`` for attribute types.

    Returns:
        (sanitized_type_name, is_nullable)
    """
    is_nullable = field_type.is_optional()
    inner = field_type.unwrap()
    raw = inner.display_name()
    # Replace (100) → _100, <String> → _String, commas/spaces → _
    sanitized = raw.replace("(", "_").replace(")", "").replace("<", "_").replace(">", "")
    sanitized = sanitized.replace(", ", "_").replace(",", "_").replace(" ", "_")
    # Strip any remaining invalid characters
    sanitized = _ERD_SANITIZE.sub("", sanitized)
    return sanitized or "Unknown", is_nullable


def build_erd(app: Application, service_name: str | None = None) -> str:
    """Build an entity-relationship diagram (erDiagram).

    Args:
        app: Fully resolved Application model.
        service_name: If provided, scope to this service only.

    Returns:
        Mermaid erDiagram string.
    """
    lines: list[str] = ["erDiagram"]

    # Collect entity names (optionally filtered) — no field details,
    # the goal is to show relationships between entities.
    entity_names: set[str] = set()
    for service, _block, entity in all_entities_with_service(app):
        if service_name and str(service.name) != service_name:
            continue
        if entity.is_abstract:
            continue
        entity_names.add(str(entity.name))

    # Relationships
    seen_rels: set[str] = set()
    for svc_name, entity, relationship in all_relationships_with_context(app):
        if service_name and svc_name != service_name:
            continue
        if entity.is_abstract:
            continue
        if relationship.target.is_resolved:
            target_name = str(relationship.target.target.name)
        else:
            target_name = relationship.target.source_name.split(".")[-1]
        source_name = str(entity.name)

        if target_name not in entity_names:
            continue

        cardinality = CARDINALITY_MAP.get(relationship.kind)
        if cardinality is None:
            continue

        rel_key = f"{source_name}-{target_name}-{relationship.kind}"
        if rel_key in seen_rels:
            continue
        seen_rels.add(rel_key)

        label = relationship.alias or relationship.kind
        lines.append(f'    {source_name} {cardinality} {target_name} : "{label}"')

    return "\n".join(lines)


def build_inheritance_tree(app: Application) -> str:
    """Build an entity inheritance tree diagram (graph TD).

    Shows abstract entities, concrete entities, and trait composition.
    """
    lines: list[str] = ["graph TD"]
    seen_entities: set[str] = set()

    for _service, _block, entity in all_entities_with_service(app):
        ename = str(entity.name)
        if ename in seen_entities:
            continue
        seen_entities.add(ename)

        # Node label
        if entity.is_abstract:
            label = f"{ename} (abstract)"
        else:
            label = ename
        lines.append(mermaid_node(sanitize_id(ename), label))

        # Inheritance edge (extends)
        if entity.extends:
            if entity.extends.is_resolved:
                parent_name = str(entity.extends.target.name)
            else:
                parent_name = entity.extends.source_name
            parent_id = sanitize_id(parent_name)

            # Ensure parent node exists (may be in a shared module outside traversal)
            if parent_id not in seen_entities:
                seen_entities.add(parent_id)
                lines.append(mermaid_node(parent_id, f"{parent_name} (abstract)"))

            lines.append(
                mermaid_edge(parent_id, sanitize_id(ename))
            )

        # Trait composition edges
        for trait in entity.traits:
            if trait.is_resolved:
                trait_name = str(trait.target.name)
            else:
                trait_name = trait.source_name
            trait_id = sanitize_id(f"trait_{trait_name}")
            if trait_id not in seen_entities:
                seen_entities.add(trait_id)
                lines.append(mermaid_node(trait_id, f"with {trait_name}", "hexagon"))
            lines.append(
                mermaid_edge(sanitize_id(ename), trait_id, "trait", "-.-")
            )

    return "\n".join(lines)


def build_event_flow(app: Application) -> str:
    """Build an event flow diagram (graph LR) showing pub/sub choreography.

    Groups events by publisher service using subgraphs so ownership is clear.
    In-service subscriptions are shown as solid arrows within the subgraph.
    Cross-service subscriptions are shown as dashed arrows between subgraphs.
    """
    lines: list[str] = ["graph LR"]

    # ── Phase 1: Collect published topics + events per service ──

    # service_id → (service_name, list of raw Mermaid lines for the subgraph)
    service_subgraphs: dict[str, tuple[str, list[str]]] = {}
    # event_name → (publisher_service_id, event_node_id)
    event_publisher_map: dict[str, tuple[str, str]] = {}

    for service in app.services.values():
        sid = _service_id(service)
        sname = _simple_name(service)
        sg_lines: list[str] = []
        seen_topics: set[str] = set()

        for pubsub_block in service.pubsub_blocks.values():
            for topic in pubsub_block.topics.values():
                topic_id = f"{sid}_topic_{sanitize_id(str(topic.name))}"
                if topic_id not in seen_topics:
                    seen_topics.add(topic_id)
                    sg_lines.append(f'{topic_id}[["{topic.name}"]]')

                for event in topic.events.values():
                    ename = str(event.name)
                    event_id = f"{sid}_evt_{sanitize_id(ename)}"
                    sg_lines.append(f'{event_id}("{ename}")')
                    sg_lines.append(f"{topic_id} --> {event_id}")
                    event_publisher_map[ename] = (sid, event_id)

        if sg_lines:
            service_subgraphs[sid] = (sname, sg_lines)

    # ── Phase 2: Add handler nodes for all subscriptions ──

    # Cross-service edges rendered outside subgraphs (dashed)
    cross_edges: list[tuple[str, str]] = []
    seen_handlers: set[str] = set()

    for service, _block, subscription in all_subscriptions_with_context(app):
        subscriber_sid = _service_id(service)
        sname = _simple_name(service)

        for handler in subscription.handlers:
            event_name = handler.event_name()
            if not event_name:
                continue

            publisher_info = event_publisher_map.get(event_name)
            if not publisher_info:
                continue
            publisher_sid, event_node_id = publisher_info

            handler_id = f"{subscriber_sid}_on_{sanitize_id(event_name)}"
            if handler_id in seen_handlers:
                continue
            seen_handlers.add(handler_id)

            if publisher_sid == subscriber_sid:
                # In-service: handler node + solid arrow within same subgraph
                if subscriber_sid in service_subgraphs:
                    service_subgraphs[subscriber_sid][1].append(
                        f'{handler_id}[/"on {event_name}"/]'
                    )
                    service_subgraphs[subscriber_sid][1].append(
                        f"{event_node_id} --> {handler_id}"
                    )
            else:
                # Cross-service: handler node in subscriber's subgraph
                if subscriber_sid not in service_subgraphs:
                    service_subgraphs[subscriber_sid] = (sname, [])
                service_subgraphs[subscriber_sid][1].append(
                    f'{handler_id}[/"on {event_name}"/]'
                )
                cross_edges.append((event_node_id, handler_id))

    # ── Phase 3: Render subgraphs ──

    for _sid, (sname, sg_lines) in service_subgraphs.items():
        if sg_lines:
            lines.append(mermaid_subgraph(sname, sg_lines))

    # ── Phase 4: Cross-service subscription edges (dashed arrows) ──

    for from_id, to_id in cross_edges:
        lines.append(mermaid_edge(from_id, to_id, "subscribes", "-.->"))

    return "\n".join(lines)


def build_api_catalog_table(app: Application) -> str | None:
    """Build a Markdown table of all REST endpoints across all services.

    Returns a Markdown table string (not Mermaid).
    """
    rows: list[str] = [
        "| Service | Method | Path | Entity |",
        "|---------|--------|------|--------|",
    ]

    for service, _api, endpoint in all_endpoints_with_service(app):
        sname = _simple_name(service)
        method = endpoint.method.upper()
        path = endpoint.full_path or endpoint.path or ""
        entity_name = str(endpoint.entity) if hasattr(endpoint, "entity") and endpoint.entity else ""
        rows.append(f"| {sname} | {method} | {path} | {entity_name} |")

    if len(rows) <= 2:
        return None

    return "\n".join(rows)


def build_cqrs_flow(app: Application, service_name: str | None = None) -> str | None:
    """Build a CQRS data flow diagram (graph TD).

    Shows command -> event -> projection -> view -> query pipeline.

    Args:
        app: Fully resolved Application model.
        service_name: If provided, scope to this service only.
    """
    lines: list[str] = ["graph TD"]
    found_cqrs = False

    for service, cqrs_block in all_cqrs_with_service(app):
        if service_name and str(service.name) != service_name:
            continue
        found_cqrs = True

        # Commands
        cmd_lines: list[str] = []
        for cmd_name in cqrs_block.commands:
            cmd_id = sanitize_id(f"cmd_{cmd_name}")
            cmd_lines.append(f'{cmd_id}["{cmd_name}"]')
        if cmd_lines:
            lines.append(mermaid_subgraph("Commands", cmd_lines))

        # Views
        view_lines: list[str] = []
        for view_name in cqrs_block.views:
            view_id = sanitize_id(f"view_{view_name}")
            view_lines.append(f'{view_id}[("{view_name}")]')
        if view_lines:
            lines.append(mermaid_subgraph("Views", view_lines))

        # Queries
        query_lines: list[str] = []
        for query_name in cqrs_block.queries:
            query_id = sanitize_id(f"query_{query_name}")
            query_lines.append(f'{query_id}["{query_name}"]')
        if query_lines:
            lines.append(mermaid_subgraph("Queries", query_lines))

        # Projections — connect events to views
        for proj_name, projection in cqrs_block.projections.items():
            proj_id = sanitize_id(f"proj_{proj_name}")
            lines.append(mermaid_node(proj_id, str(proj_name), "trapezoid"))

            # Events → projection
            for event_name in projection.handled_event_names():
                event_id = sanitize_id(f"evt_{event_name}")
                lines.append(mermaid_node(event_id, event_name, "rounded"))
                lines.append(mermaid_edge(event_id, proj_id))

            # Projection → views
            for view_name in projection.target_view_names():
                view_id = sanitize_id(f"view_{view_name}")
                lines.append(mermaid_edge(proj_id, view_id))

        # Queries → views
        for query_name, query in cqrs_block.queries.items():
            query_id = sanitize_id(f"query_{query_name}")
            # Link queries to views — heuristic: query name contains view name
            for view_name in cqrs_block.views:
                view_id = sanitize_id(f"view_{view_name}")
                lines.append(mermaid_edge(query_id, view_id))

    if not found_cqrs:
        return None

    return "\n".join(lines)


def build_data_store_topology(app: Application) -> str:
    """Build a data store topology diagram (graph LR).

    Shows which services own which data stores and their types.
    """
    lines: list[str] = ["graph LR"]

    for service in app.services.values():
        sid = _service_id(service)
        sname = _simple_name(service)
        sg_lines: list[str] = []

        for block_name, rdbms_block in service.rdbms_blocks.items():
            block_id = f"{sid}_rdbms_{sanitize_id(str(block_name))}"
            engine_label = "PostgreSQL"
            if getattr(rdbms_block, "_config", None) is not None:
                engine_label = str(rdbms_block.config.engine.canonical_name)
            entity_count = len(rdbms_block.entities)
            sg_lines.append(
                f'{block_id}[("{block_name} / {engine_label} ({entity_count} entities)")]'
            )

        for block_name in service.nosql_blocks:
            block_id = f"{sid}_nosql_{sanitize_id(str(block_name))}"
            sg_lines.append(f'{block_id}[("{block_name} / NoSQL")]')

        if service.cache_block is not None:
            cache_id = f"{sid}_cache"
            engine_label = "Redis"
            if getattr(service.cache_block, "_config", None) is not None:
                engine_label = str(service.cache_block.config.engine.canonical_name)
            sg_lines.append(f'{cache_id}["{engine_label}"]')

        for block_name in service.pubsub_blocks:
            block_id = f"{sid}_mq_{sanitize_id(str(block_name))}"
            sg_lines.append(f'{block_id}[["{block_name} / MQ"]]')

        for block_name in service.storage_blocks:
            block_id = f"{sid}_storage_{sanitize_id(str(block_name))}"
            sg_lines.append(f'{block_id}[/"{block_name} / Storage"/]')

        if service.jobs_block is not None:
            jobs_id = f"{sid}_jobs"
            sg_lines.append(f'{jobs_id}[/"Jobs"/]')

        if sg_lines:
            lines.append(mermaid_subgraph(sname, sg_lines))

    return "\n".join(lines)


# ── Diagram type registry ──

DIAGRAM_TYPES: dict[str, str] = {
    "system-context": "System Context Diagram (C4-inspired)",
    "service-map": "Service Map with Infrastructure",
    "erd": "Entity-Relationship Diagram",
    "inheritance": "Entity Inheritance Tree",
    "event-flow": "Event Flow Diagram",
    "api-catalog": "API Catalog (Markdown table)",
    "cqrs-flow": "CQRS Data Flow",
    "infrastructure": "Data Store Topology",
}


def build_diagram(
    diagram_type: str,
    app: Application,
    service_name: str | None = None,
) -> str | None:
    """Build a specific diagram type.

    Args:
        diagram_type: One of the keys in DIAGRAM_TYPES.
        app: Fully resolved Application model.
        service_name: Optional service scope.

    Returns:
        Diagram content string (Mermaid or Markdown table), or None
        if the application has no data for this diagram type.

    Raises:
        ValueError: If diagram_type is not recognized.
    """
    builders: dict[str, object] = {
        "system-context": lambda: build_system_context(app),
        "service-map": lambda: build_service_map(app),
        "erd": lambda: build_erd(app, service_name),
        "inheritance": lambda: build_inheritance_tree(app),
        "event-flow": lambda: build_event_flow(app),
        "api-catalog": lambda: build_api_catalog_table(app),
        "cqrs-flow": lambda: build_cqrs_flow(app, service_name),
        "infrastructure": lambda: build_data_store_topology(app),
    }
    if diagram_type not in builders:
        available = sorted(builders.keys())
        raise ValueError(
            f"Unknown diagram type '{diagram_type}'. "
            f"Available: {', '.join(available)}"
        )
    builder = builders[diagram_type]
    return builder()
