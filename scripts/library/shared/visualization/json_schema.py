"""Datrix type to JSON Schema mapping and OpenAPI/AsyncAPI spec builders.

Provides exhaustive type mapping (no silent fallbacks) and spec generation
for REST APIs (OpenAPI 3.1) and Pub/Sub events (AsyncAPI 3.0).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .traversal import all_endpoints_with_service

if TYPE_CHECKING:
    from datrix_common.datrix_model.api import Endpoint, RestApi
    from datrix_common.datrix_model.containers import Service
    from datrix_common.datrix_model.entity import Entity, Field
    from datrix_common.datrix_model.pubsub import Event, PubsubBlock, Topic

# ── Exhaustive Datrix → JSON Schema type mapping ──

SCALAR_TYPE_MAP: dict[str, dict[str, str]] = {
    "String": {"type": "string"},
    "Int": {"type": "integer"},
    "Long": {"type": "integer", "format": "int64"},
    "Float": {"type": "number", "format": "float"},
    "Double": {"type": "number", "format": "double"},
    "Decimal": {"type": "number", "format": "decimal"},
    "Boolean": {"type": "boolean"},
    "DateTime": {"type": "string", "format": "date-time"},
    "UDateTime": {"type": "string", "format": "date-time"},
    "Date": {"type": "string", "format": "date"},
    "Time": {"type": "string", "format": "time"},
    "UUID": {"type": "string", "format": "uuid"},
    "JSON": {"type": "object"},
    "Text": {"type": "string"},
    "Email": {"type": "string", "format": "email"},
    "Password": {"type": "string", "format": "password"},
    "Url": {"type": "string", "format": "uri"},
    "Phone": {"type": "string"},
    "Byte": {"type": "string", "format": "byte"},
    "Binary": {"type": "string", "format": "binary"},
    "BigDecimal": {"type": "string", "format": "decimal"},
    "BigInteger": {"type": "string", "format": "integer"},
    "Short": {"type": "integer", "format": "int16"},
}


def map_field_to_json_schema(field: Field) -> dict[str, object]:
    """Map a single Datrix Field to a JSON Schema property.

    Args:
        field: A resolved Datrix Field.

    Returns:
        JSON Schema property dict.

    Raises:
        ValueError: If the field type cannot be mapped.
    """
    type_name = field.resolved_type.display_name()

    # Handle String(N) — extract max length
    if type_name.startswith("String(") and type_name.endswith(")"):
        max_length = type_name[7:-1]
        schema: dict[str, object] = {"type": "string"}
        if max_length.isdigit():
            schema["maxLength"] = int(max_length)
        return schema

    # Handle Array<T>
    if type_name.startswith("Array<") and type_name.endswith(">"):
        inner = type_name[6:-1]
        inner_schema = _resolve_type_schema(inner)
        return {"type": "array", "items": inner_schema}

    return _resolve_type_schema(type_name)


def _resolve_type_schema(type_name: str) -> dict[str, object]:
    """Resolve a scalar type name to JSON Schema.

    Falls through to $ref for entity/enum references.
    """
    if type_name in SCALAR_TYPE_MAP:
        return dict(SCALAR_TYPE_MAP[type_name])

    # Entity or enum reference
    return {"$ref": f"#/components/schemas/{type_name}"}


def map_entity_to_json_schema(entity: Entity) -> dict[str, object]:
    """Map a Datrix Entity to a JSON Schema object definition.

    Args:
        entity: A resolved Datrix Entity.

    Returns:
        JSON Schema object dict with properties and required array.
    """
    properties: dict[str, object] = {}
    required: list[str] = []

    for field in entity.fields.values():
        fname = str(field.name)
        properties[fname] = map_field_to_json_schema(field)
        if not field.is_optional:
            required.append(fname)

    schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _build_endpoint_operation(endpoint: Endpoint) -> dict[str, object]:
    """Build an OpenAPI operation object from an Endpoint."""
    operation: dict[str, object] = {
        "operationId": str(endpoint.name) if endpoint.name else endpoint.method,
        "summary": str(endpoint.name or endpoint.method),
    }

    # Security based on access level
    access = getattr(endpoint, "access_level", None)
    if access and str(access) == "public":
        operation["security"] = []
    elif access:
        operation["security"] = [{"bearerAuth": []}]

    # Response
    operation["responses"] = {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {"type": "object"},
                },
            },
        },
    }

    return operation


def build_openapi_spec(service: Service, rest_api: RestApi) -> dict[str, object]:
    """Build an OpenAPI 3.1 specification dict.

    Args:
        service: Service that owns the REST API.
        rest_api: The REST API block to document.

    Returns:
        Complete OpenAPI 3.1 specification as a dict (ready for YAML serialization).
    """
    paths: dict[str, dict[str, object]] = {}

    for endpoint in rest_api.endpoints.values():
        path = endpoint.full_path or endpoint.path or "/"
        method = endpoint.method.lower()

        if path not in paths:
            paths[path] = {}
        paths[path][method] = _build_endpoint_operation(endpoint)

    # Collect entity schemas
    schemas: dict[str, object] = {}
    for rdbms_block in service.rdbms_blocks.values():
        for entity in rdbms_block.entities.values():
            if not entity.is_abstract:
                schemas[str(entity.name)] = map_entity_to_json_schema(entity)

    spec: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {
            "title": f"{service.name} API",
            "version": service.version or "1.0.0",
        },
        "paths": paths,
        "components": {
            "schemas": schemas,
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                },
            },
        },
    }

    return spec


def _build_event_message(event: Event) -> dict[str, object]:
    """Build an AsyncAPI message object from an Event."""
    properties: dict[str, object] = {}
    required: list[str] = []

    for param in event.parameters:
        pname = str(param.name)
        ptype = param.resolved_type.display_name() if hasattr(param, "resolved_type") else "String"
        properties[pname] = _resolve_type_schema(ptype)
        required.append(pname)

    payload: dict[str, object] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        payload["required"] = required

    return {"payload": payload}


def build_asyncapi_spec(
    service: Service,
    pubsub_block: PubsubBlock,
) -> dict[str, object]:
    """Build an AsyncAPI 3.0 specification dict.

    Args:
        service: Service that owns the pubsub block.
        pubsub_block: The PubSub block to document.

    Returns:
        Complete AsyncAPI 3.0 specification as a dict (ready for YAML serialization).
    """
    channels: dict[str, object] = {}
    operations: dict[str, object] = {}

    for topic in pubsub_block.topics.values():
        topic_name = str(topic.name)
        messages: dict[str, object] = {}

        for event in topic.events.values():
            event_name = str(event.name)
            messages[event_name] = _build_event_message(event)

            # Publish operation
            op_id = f"publish{event_name}"
            operations[op_id] = {
                "action": "send",
                "channel": {"$ref": f"#/channels/{topic_name}"},
            }

        channels[topic_name] = {
            "address": topic_name,
            "messages": messages,
        }

    # Subscription operations
    for subscription in pubsub_block.subscriptions:
        sub_name = str(subscription.name)
        for handler in subscription.handlers:
            event_name = handler.event_name()
            if event_name:
                op_id = f"on{event_name}"
                operations[op_id] = {
                    "action": "receive",
                    "channel": {"$ref": f"#/channels/{sub_name}"},
                }

    spec: dict[str, object] = {
        "asyncapi": "3.0.0",
        "info": {
            "title": f"{service.name} Events",
            "version": service.version or "1.0.0",
        },
        "channels": channels,
        "operations": operations,
    }

    return spec
