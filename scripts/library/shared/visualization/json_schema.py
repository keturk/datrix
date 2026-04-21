"""Datrix type to JSON Schema mapping and OpenAPI/AsyncAPI spec builders.

Provides exhaustive type mapping (no silent fallbacks) and spec generation
for REST APIs (OpenAPI 3.1) and Pub/Sub events (AsyncAPI 3.0).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datrix_common.datrix_model.api import Endpoint, RestApi
    from datrix_common.datrix_model.containers import Application, Module, Service
    from datrix_common.datrix_model.entity import Entity, Field
    from datrix_common.datrix_model.pubsub import Event, PubsubBlock, Topic

from datrix_common.datrix_model.exceptions import ExceptionDeclaration, ExceptionField

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


def _map_display_name_to_json_schema(type_name: str) -> dict[str, object]:
    """Map a resolved type display name to a JSON Schema fragment."""
    if type_name.startswith("String(") and type_name.endswith(")"):
        max_length = type_name[7:-1]
        schema: dict[str, object] = {"type": "string"}
        if max_length.isdigit():
            schema["maxLength"] = int(max_length)
        return schema

    if type_name.startswith("Array<") and type_name.endswith(">"):
        inner = type_name[6:-1]
        inner_schema = _resolve_type_schema(inner)
        return {"type": "array", "items": inner_schema}

    return _resolve_type_schema(type_name)


def map_field_to_json_schema(field: Field) -> dict[str, object]:
    """Map a single Datrix Field to a JSON Schema property.

    Args:
        field: A resolved Datrix Field.

    Returns:
        JSON Schema property dict.

    Raises:
        ValueError: If the field type cannot be mapped.
    """
    return _map_display_name_to_json_schema(field.resolved_type.display_name())


def map_exception_field_to_json_schema(field: ExceptionField) -> dict[str, object]:
    """Map an ExceptionField to a JSON Schema property (same rules as entity fields)."""
    type_name = field.resolved_type.display_name()
    return _map_display_name_to_json_schema(type_name)


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


def _exception_index_for_service(service: "Service") -> dict[str, ExceptionDeclaration]:
    """Map simple exception name -> ExceptionDeclaration for OpenAPI.

    Module exceptions from any ``source_module`` referenced by resolved imports are
    registered first; service-level declarations override on name collision.
    """
    from datrix_common.datrix_model.containers import Module

    index: dict[str, ExceptionDeclaration] = {}
    seen_module_ids: set[int] = set()

    for resolved in service.imports:
        mod_ref = resolved.source_module
        if not mod_ref.is_resolved:
            continue
        mod = mod_ref.target
        if not isinstance(mod, Module):
            continue
        mid = id(mod)
        if mid in seen_module_ids:
            continue
        seen_module_ids.add(mid)
        for exc in mod.exceptions:
            key = str(exc.name)
            if key not in index:
                index[key] = exc

    for exc in service.exceptions:
        index[str(exc.name)] = exc

    return index


def _openapi_exception_component_schema(exc: ExceptionDeclaration) -> dict[str, object]:
    """Build ``#/components/schemas/{Name}`` body for one ExceptionDeclaration."""
    status_code = int(exc.status_code)
    msg = exc.message
    example_message = msg if isinstance(msg, str) and msg else "Error"

    properties: dict[str, object] = {
        "statusCode": {
            "type": "integer",
            "example": status_code,
        },
        "message": {
            "type": "string",
            "example": example_message,
        },
    }
    required: list[str] = ["statusCode", "message"]

    for field in exc.fields:
        fname = str(field.name)
        properties[fname] = map_exception_field_to_json_schema(field)
        if not field.is_optional:
            required.append(fname)

    schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }
    return schema


def _throw_expression_to_exception_name(expression: object) -> str:
    """Extract the simple exception type name from a ``throw`` expression."""
    from datrix_common.datrix_model.expressions import CallNode, IdentifierNode, QualifiedNameNode

    if isinstance(expression, CallNode):
        return _throw_target_to_name(expression.target)
    return _throw_target_to_name(expression)


def _throw_target_to_name(target: object) -> str:
    from datrix_common.datrix_model.expressions import IdentifierNode, QualifiedNameNode

    if isinstance(target, IdentifierNode):
        return str(target.name)
    if isinstance(target, QualifiedNameNode):
        parts = target.parts
        if not parts:
            raise ValueError("throw target QualifiedNameNode has empty parts")
        return str(parts[-1])
    raise ValueError(
        f"Unsupported throw target expression type '{type(target).__name__}'. "
        "Expected IdentifierNode, QualifiedNameNode, or CallNode to such a target."
    )


def _collect_thrown_exception_names_from_statements(
    statements: tuple[object, ...],
) -> list[str]:
    """Collect simple exception names from throw statements (deterministic order)."""
    from datrix_common.datrix_model.expressions import (
        AssertStatement,
        AssignmentStatement,
        EmitStatement,
        ExpressionStatement,
        ForLoopStatement,
        ForStatement,
        IfStatement,
        ReturnStatement,
        SwitchStatement,
        ThrowStatement,
        TransactionStatement,
        TryStatement,
        VariableDeclaration,
        WhileStatement,
    )

    out: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            out.append(name)

    def walk(stmts: tuple[object, ...]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ThrowStatement):
                add(_throw_expression_to_exception_name(stmt.expression))
            elif isinstance(stmt, IfStatement):
                walk(stmt.then_body)
                for _cond, body in stmt.elif_clauses:
                    walk(body)
                if stmt.else_body is not None:
                    walk(stmt.else_body)
            elif isinstance(stmt, (ForStatement, WhileStatement)):
                walk(stmt.body)
            elif isinstance(stmt, ForLoopStatement):
                if stmt.init is not None:
                    walk((stmt.init,))
                walk(stmt.body)
            elif isinstance(stmt, SwitchStatement):
                for _case_expr, case_body in stmt.cases:
                    walk(case_body)
                if stmt.default_body is not None:
                    walk(stmt.default_body)
            elif isinstance(stmt, TryStatement):
                walk(stmt.try_body)
                for clause in stmt.catch_clauses:
                    walk(clause.body)
                if stmt.finally_body is not None:
                    walk(stmt.finally_body)
            elif isinstance(stmt, TransactionStatement):
                walk(stmt.body)
            elif isinstance(stmt, VariableDeclaration):
                if stmt.initializer is not None:
                    walk_expressions(stmt.initializer)
            elif isinstance(stmt, AssignmentStatement):
                walk_expressions(stmt.value)
            elif isinstance(stmt, ReturnStatement) and stmt.value is not None:
                walk_expressions(stmt.value)
            elif isinstance(stmt, ExpressionStatement):
                walk_expressions(stmt.expression)
            elif isinstance(stmt, AssertStatement):
                walk_expressions(stmt.expression)
            elif isinstance(stmt, EmitStatement):
                for arg in stmt.arguments:
                    walk_expressions(arg)

    def walk_expressions(expr: object) -> None:
        from datrix_common.datrix_model.expressions import CallNode, LambdaNode, MatchExpression

        if isinstance(expr, ThrowStatement):
            add(_throw_expression_to_exception_name(expr.expression))
        elif isinstance(expr, CallNode):
            walk_expressions(expr.target)
            for a in expr.arguments:
                walk_expressions(a)
            if expr.named_arguments:
                for v in expr.named_arguments.values():
                    walk_expressions(v)
        elif isinstance(expr, LambdaNode):
            walk_expressions(expr.body)
        elif isinstance(expr, MatchExpression):
            walk_expressions(expr.expression)
            for arm in expr.arms:
                walk_expressions(arm.body)

    walk(statements)
    return out


def _merge_error_responses_for_endpoint(
    endpoint: "Endpoint",
    exc_index: dict[str, ExceptionDeclaration],
) -> dict[str, object]:
    """Build OpenAPI ``responses`` entries for declared exceptions thrown in the endpoint."""
    names = _collect_thrown_exception_names_from_statements(endpoint.body)
    if not names:
        return {}

    decl_by_status: dict[int, ExceptionDeclaration] = {}
    responses: dict[str, object] = {}
    ep_id = f"{endpoint.method.upper()} {endpoint.full_path or endpoint.path or '/'}"

    for name in names:
        if name not in exc_index:
            available = sorted(exc_index.keys())
            raise ValueError(
                f"OpenAPI: throw references unknown exception '{name}' on endpoint {ep_id}. "
                f"Not found. Available: {available}"
            )
        decl = exc_index[name]
        code = int(decl.status_code)
        if code in decl_by_status and decl_by_status[code] is not decl:
            other = decl_by_status[code]
            raise ValueError(
                f"OpenAPI: endpoint {ep_id} throws multiple exceptions with HTTP {code}: "
                f"'{other.name}' and '{decl.name}'. OpenAPI response keys must be unique per status."
            )
        decl_by_status[code] = decl
        schema_name = str(decl.name)
        responses[str(code)] = {
            "description": str(decl.message) if decl.message else schema_name,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{schema_name}"},
                },
            },
        }
    return responses


def _build_endpoint_operation(
    endpoint: "Endpoint",
    exc_index: dict[str, ExceptionDeclaration],
) -> dict[str, object]:
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

    responses: dict[str, object] = {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {"type": "object"},
                },
            },
        },
    }
    responses.update(_merge_error_responses_for_endpoint(endpoint, exc_index))
    operation["responses"] = responses

    return operation


def build_openapi_spec(service: "Service", rest_api: "RestApi", app: "Application") -> dict[str, object]:
    """Build an OpenAPI 3.1 specification dict.

    Args:
        service: Service that owns the REST API.
        rest_api: The REST API block to document.
        app: Analyzed application (used for exception import visibility).

    Returns:
        Complete OpenAPI 3.1 specification as a dict (ready for YAML serialization).
    """
    if not any(s is service for s in app.services.values()):
        raise ValueError(
            "OpenAPI: ``service`` must be one of ``app.services`` values so exception "
            "visibility matches semantic analysis."
        )
    exc_index = _exception_index_for_service(service)

    paths: dict[str, dict[str, object]] = {}

    for endpoint in rest_api.endpoints.values():
        path = endpoint.full_path or endpoint.path or "/"
        method = endpoint.method.lower()

        if path not in paths:
            paths[path] = {}
        paths[path][method] = _build_endpoint_operation(endpoint, exc_index)

    # Collect entity schemas + exception error schemas
    schemas: dict[str, object] = {}
    for rdbms_block in service.rdbms_blocks.values():
        for entity in rdbms_block.entities.values():
            if not entity.is_abstract:
                schemas[str(entity.name)] = map_entity_to_json_schema(entity)

    for _name, decl in exc_index.items():
        schema_key = str(decl.name)
        schemas[schema_key] = _openapi_exception_component_schema(decl)

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
