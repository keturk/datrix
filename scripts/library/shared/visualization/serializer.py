"""Application model to JSON-serializable dict serializer.

Used for schema snapshots and interactive dashboard data embedding.
Strips source locations and internal refs, keeps only names and structural data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datrix_common.paths import ServicePaths

if TYPE_CHECKING:
    from datrix_common.datrix_model.api import Endpoint, RestApi
    from datrix_common.datrix_model.containers import Application, Service
    from datrix_common.datrix_model.entity import Entity, Field, Relationship


def serialize_field(field: Field) -> dict[str, object]:
    """Serialize a single Field to a JSON-compatible dict."""
    return {
        "name": str(field.name),
        "type": field.resolved_type.display_name(),
        "is_primary_key": field.is_primary_key,
        "is_optional": field.is_optional,
        "is_unique": field.is_unique,
        "is_indexed": field.is_indexed,
    }


def serialize_relationship(relationship: Relationship) -> dict[str, str]:
    """Serialize a single Relationship to a JSON-compatible dict."""
    if relationship.target.is_resolved:
        target_name = str(relationship.target.target.name)
    else:
        target_name = relationship.target.source_name
    return {
        "kind": relationship.kind,
        "target": target_name,
        "alias": relationship.alias or "",
    }


def serialize_entity(entity: Entity) -> dict[str, object]:
    """Serialize an Entity to a JSON-compatible dict."""
    fields = [serialize_field(f) for f in entity.fields.values()]
    relationships = [serialize_relationship(r) for r in entity.relationships]
    traits = [str(t) for t in entity.traits]

    result: dict[str, object] = {
        "name": str(entity.name),
        "is_abstract": entity.is_abstract,
        "fields": fields,
        "relationships": relationships,
        "traits": traits,
    }
    if entity.extends:
        result["extends"] = str(entity.extends)
    return result


def _serialize_endpoint(endpoint: Endpoint) -> dict[str, str]:
    """Serialize an Endpoint to a JSON-compatible dict."""
    return {
        "name": str(endpoint.name) if endpoint.name else "",
        "method": endpoint.method,
        "path": endpoint.full_path or endpoint.path or "",
    }


def _serialize_rest_api(rest_api: RestApi) -> dict[str, object]:
    """Serialize a RestApi to a JSON-compatible dict."""
    endpoints = [_serialize_endpoint(ep) for ep in rest_api.endpoints.values()]
    return {
        "name": str(rest_api.name),
        "endpoints": endpoints,
    }


def serialize_service(service: Service) -> dict[str, object]:
    """Serialize a Service to a JSON-compatible dict.

    Includes all blocks: RDBMS, NoSQL, cache, pubsub, storage, CQRS, jobs.
    """
    paths = ServicePaths(service.name)

    # RDBMS blocks with entities
    rdbms_blocks: list[dict[str, object]] = []
    for block_name, rdbms_block in service.rdbms_blocks.items():
        entities = [
            serialize_entity(e) for e in rdbms_block.entities.values()
        ]
        rdbms_blocks.append({
            "name": str(block_name),
            "entities": entities,
        })

    # REST APIs
    rest_apis = [_serialize_rest_api(api) for api in service.rest_apis.values()]

    # Pubsub blocks
    pubsub_blocks: list[dict[str, object]] = []
    for block_name, pubsub_block in service.pubsub_blocks.items():
        topics: list[dict[str, object]] = []
        for topic in pubsub_block.topics.values():
            events = [
                {
                    "name": str(e.name),
                    "parameters": [
                        {"name": str(p.name), "type": p.resolved_type.display_name()}
                        for p in e.parameters
                        if hasattr(p, "resolved_type")
                    ],
                }
                for e in topic.events.values()
            ]
            topics.append({"name": str(topic.name), "events": events})

        subscriptions: list[dict[str, object]] = []
        for sub in pubsub_block.subscriptions.values():
            handlers = [
                {"name": str(h.name), "event": h.event_name()}
                for h in sub.handlers
            ]
            subscriptions.append({
                "name": str(sub.name),
                "handlers": handlers,
            })

        pubsub_blocks.append({
            "name": str(block_name),
            "topics": topics,
            "subscriptions": subscriptions,
        })

    # CQRS block
    cqrs: dict[str, object] | None = None
    if service.cqrs_block is not None:
        cqrs_block = service.cqrs_block
        cqrs = {
            "commands": [str(k) for k in cqrs_block.commands],
            "queries": [str(k) for k in cqrs_block.queries],
            "views": [str(k) for k in cqrs_block.views],
            "projections": [str(k) for k in cqrs_block.projections],
        }

    # Dependencies
    dependencies: list[str] = []
    if service.discovery:
        for dep in service.discovery.dependencies:
            if dep.target_service.is_resolved:
                dependencies.append(str(dep.target_service.target.name))
            else:
                dependencies.append(str(dep.name))

    result: dict[str, object] = {
        "name": str(service.name),
        "simple_name": paths.simple_name,
        "version": service.version or "",
        "port": service.config.port if service.config else 0,
        "rdbms_blocks": rdbms_blocks,
        "rest_apis": rest_apis,
        "pubsub_blocks": pubsub_blocks,
        "has_cache": service.cache_block is not None,
        "has_nosql": bool(service.nosql_blocks),
        "has_storage": bool(service.storage_blocks),
        "has_jobs": service.jobs_block is not None,
        "dependencies": dependencies,
    }
    if cqrs is not None:
        result["cqrs"] = cqrs
    return result


def serialize_application(app: Application) -> dict[str, object]:
    """Serialize an entire Application to a JSON-compatible dict.

    Args:
        app: Fully resolved Application model.

    Returns:
        JSON-serializable dict with all services, entities, endpoints, events.
    """
    services = [serialize_service(svc) for svc in app.services.values()]

    # Derive application name from first service namespace
    app_name = ""
    if app.services:
        first_name = str(next(iter(app.services.keys())))
        parts = first_name.split(".")
        if len(parts) > 1:
            app_name = parts[0]
        else:
            app_name = first_name

    return {
        "name": app_name,
        "service_count": len(services),
        "services": services,
    }
