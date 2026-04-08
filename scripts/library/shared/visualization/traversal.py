"""AST traversal helpers for visualization scripts.

Provides service-scoped iteration patterns over the Application model.
All traversals follow the MANDATORY block-scoped access pattern:
iterate per-service, per-block — never flatten across services.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datrix_common.datrix_model.api import Endpoint, RestApi
    from datrix_common.datrix_model.blocks import (
        CacheBlock,
        NosqlBlock,
        RdbmsBlock,
        StorageBlock,
    )
    from datrix_common.datrix_model.containers import Application, Service
    from datrix_common.datrix_model.cqrs import CqrsBlock
    from datrix_common.datrix_model.entity import Entity, Relationship
    from datrix_common.datrix_model.pubsub import (
        Event,
        PubsubBlock,
        Subscription,
        Topic,
    )


def all_entities_with_service(
    app: Application,
) -> Iterator[tuple[Service, str, Entity]]:
    """Yield (service, block_name, entity) across all services and RDBMS blocks.

    Preserves service ownership context for each entity.
    """
    for service in app.services.values():
        for block_name, rdbms_block in service.rdbms_blocks.items():
            for entity in rdbms_block.entities.values():
                yield service, str(block_name), entity


def all_relationships_with_context(
    app: Application,
) -> Iterator[tuple[str, Entity, Relationship]]:
    """Yield (service_name, source_entity, relationship) across all entities.

    Preserves which service and entity owns each relationship.
    """
    for service in app.services.values():
        for rdbms_block in service.rdbms_blocks.values():
            for entity in rdbms_block.entities.values():
                for relationship in entity.relationships:
                    yield str(service.name), entity, relationship


def all_endpoints_with_service(
    app: Application,
) -> Iterator[tuple[Service, RestApi, Endpoint]]:
    """Yield (service, rest_api, endpoint) across all services and REST APIs."""
    for service in app.services.values():
        for rest_api in service.rest_apis.values():
            for endpoint in rest_api.endpoints.values():
                yield service, rest_api, endpoint


def all_events_with_context(
    app: Application,
) -> Iterator[tuple[Service, PubsubBlock, Topic, Event]]:
    """Yield (service, pubsub_block, topic, event) across all services."""
    for service in app.services.values():
        for pubsub_block in service.pubsub_blocks.values():
            for topic in pubsub_block.topics.values():
                for event in topic.events.values():
                    yield service, pubsub_block, topic, event


def all_subscriptions_with_context(
    app: Application,
) -> Iterator[tuple[Service, PubsubBlock, Subscription]]:
    """Yield (service, pubsub_block, subscription) across all services."""
    for service in app.services.values():
        for pubsub_block in service.pubsub_blocks.values():
            for subscription in pubsub_block.subscriptions:
                yield service, pubsub_block, subscription


def all_cqrs_with_service(
    app: Application,
) -> Iterator[tuple[Service, CqrsBlock]]:
    """Yield (service, cqrs_block) for services that have a CQRS block."""
    for service in app.services.values():
        if service.cqrs_block is not None:
            yield service, service.cqrs_block


def service_dependency_edges(app: Application) -> list[tuple[str, str]]:
    """Return (from_service_name, to_service_name) pairs for service dependencies."""
    edges: list[tuple[str, str]] = []
    for service in app.services.values():
        if service.discovery is None:
            continue
        for dependency in service.discovery.dependencies:
            if dependency.target_service.is_resolved:
                target_name = str(dependency.target_service.target.name)
            else:
                target_name = dependency.target_service.source_name
            edges.append((str(service.name), target_name))
    return edges
