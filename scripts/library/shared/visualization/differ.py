"""AST structural diff engine for comparing two Application versions.

Produces typed diff results classifying changes as breaking or non-breaking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .traversal import (
    all_endpoints_with_service,
    all_entities_with_service,
    all_events_with_context,
)

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application


@dataclass
class FieldChange:
    """A change to a single entity field."""

    name: str
    change_type: str  # "added", "removed", "type_changed"
    old_value: str = ""
    new_value: str = ""


@dataclass
class EntityChange:
    """A change to an entity."""

    name: str
    service_name: str
    change_type: str  # "added", "removed", "modified"
    field_changes: list[FieldChange] = field(default_factory=list)
    relationship_changes: list[str] = field(default_factory=list)


@dataclass
class EndpointChange:
    """A change to an API endpoint."""

    service_name: str
    method: str
    path: str
    change_type: str  # "added", "removed", "modified"
    details: str = ""


@dataclass
class EventChange:
    """A change to a pub/sub event."""

    service_name: str
    topic: str
    event_name: str
    change_type: str  # "added", "removed"


@dataclass
class DiffResult:
    """Complete diff result between two Application versions."""

    entity_changes: list[EntityChange] = field(default_factory=list)
    endpoint_changes: list[EndpointChange] = field(default_factory=list)
    event_changes: list[EventChange] = field(default_factory=list)

    @property
    def entities_added(self) -> list[EntityChange]:
        """Entities present in 'after' but not in 'before'."""
        return [c for c in self.entity_changes if c.change_type == "added"]

    @property
    def entities_removed(self) -> list[EntityChange]:
        """Entities present in 'before' but not in 'after'."""
        return [c for c in self.entity_changes if c.change_type == "removed"]

    @property
    def entities_modified(self) -> list[EntityChange]:
        """Entities that changed between versions."""
        return [c for c in self.entity_changes if c.change_type == "modified"]

    @property
    def breaking_changes(self) -> list[str]:
        """Summary of breaking changes."""
        breaking: list[str] = []
        for ec in self.entities_removed:
            breaking.append(f"REMOVED entity '{ec.name}' ({ec.service_name})")
        for ec in self.entities_modified:
            for fc in ec.field_changes:
                if fc.change_type == "removed":
                    breaking.append(
                        f"REMOVED field '{ec.name}.{fc.name}' ({ec.service_name})"
                    )
                elif fc.change_type == "type_changed":
                    breaking.append(
                        f"TYPE CHANGED '{ec.name}.{fc.name}': "
                        f"{fc.old_value} -> {fc.new_value} ({ec.service_name})"
                    )
        for epc in self.endpoint_changes:
            if epc.change_type == "removed":
                breaking.append(
                    f"REMOVED endpoint {epc.method} {epc.path} ({epc.service_name})"
                )
        return breaking

    @property
    def non_breaking_changes(self) -> list[str]:
        """Summary of non-breaking changes."""
        non_breaking: list[str] = []
        for ec in self.entities_added:
            non_breaking.append(f"ADDED entity '{ec.name}' ({ec.service_name})")
        for ec in self.entities_modified:
            for fc in ec.field_changes:
                if fc.change_type == "added":
                    non_breaking.append(
                        f"ADDED field '{ec.name}.{fc.name}' ({ec.service_name})"
                    )
        for epc in self.endpoint_changes:
            if epc.change_type == "added":
                non_breaking.append(
                    f"ADDED endpoint {epc.method} {epc.path} ({epc.service_name})"
                )
        for evc in self.event_changes:
            if evc.change_type == "added":
                non_breaking.append(
                    f"ADDED event '{evc.event_name}' on {evc.topic} ({evc.service_name})"
                )
        return non_breaking

    @property
    def has_changes(self) -> bool:
        """True if any changes were detected."""
        return bool(
            self.entity_changes or self.endpoint_changes or self.event_changes
        )


def _collect_entities(
    app: Application,
) -> dict[str, tuple[str, dict[str, str], list[str]]]:
    """Collect entities keyed by name: (service_name, {field_name: type}, [relationship_strs])."""
    result: dict[str, tuple[str, dict[str, str], list[str]]] = {}
    for service, _block, entity in all_entities_with_service(app):
        if entity.is_abstract:
            continue
        ename = str(entity.name)
        fields = {
            str(f.name): f.resolved_type.display_name()
            for f in entity.fields.values()
        }
        rels = [
            f"{r.kind} {r.target.source_name}"
            for r in entity.relationships
        ]
        result[ename] = (str(service.name), fields, rels)
    return result


def _collect_endpoints(
    app: Application,
) -> dict[str, tuple[str, str, str]]:
    """Collect endpoints keyed by 'METHOD /path': (service_name, method, path)."""
    result: dict[str, tuple[str, str, str]] = {}
    for service, _api, endpoint in all_endpoints_with_service(app):
        method = endpoint.method.upper()
        path = endpoint.full_path or endpoint.path or ""
        key = f"{method} {path}"
        result[key] = (str(service.name), method, path)
    return result


def _collect_events(
    app: Application,
) -> dict[str, tuple[str, str]]:
    """Collect events keyed by event_name: (service_name, topic_name)."""
    result: dict[str, tuple[str, str]] = {}
    for service, _block, topic, event in all_events_with_context(app):
        result[str(event.name)] = (str(service.name), str(topic.name))
    return result


def diff_applications(before: Application, after: Application) -> DiffResult:
    """Compare two Application versions and produce a structured diff.

    Args:
        before: The earlier Application version.
        after: The later Application version.

    Returns:
        DiffResult with all changes classified.
    """
    result = DiffResult()

    # ── Entity diff ──
    before_entities = _collect_entities(before)
    after_entities = _collect_entities(after)

    before_names = set(before_entities.keys())
    after_names = set(after_entities.keys())

    # Added entities
    for name in sorted(after_names - before_names):
        svc_name, _fields, _rels = after_entities[name]
        result.entity_changes.append(
            EntityChange(name=name, service_name=svc_name, change_type="added")
        )

    # Removed entities
    for name in sorted(before_names - after_names):
        svc_name, _fields, _rels = before_entities[name]
        result.entity_changes.append(
            EntityChange(name=name, service_name=svc_name, change_type="removed")
        )

    # Modified entities
    for name in sorted(before_names & after_names):
        before_svc, before_fields, before_rels = before_entities[name]
        after_svc, after_fields, after_rels = after_entities[name]

        field_changes: list[FieldChange] = []

        # Added fields
        for fname in sorted(set(after_fields) - set(before_fields)):
            field_changes.append(
                FieldChange(name=fname, change_type="added", new_value=after_fields[fname])
            )

        # Removed fields
        for fname in sorted(set(before_fields) - set(after_fields)):
            field_changes.append(
                FieldChange(name=fname, change_type="removed", old_value=before_fields[fname])
            )

        # Type-changed fields
        for fname in sorted(set(before_fields) & set(after_fields)):
            if before_fields[fname] != after_fields[fname]:
                field_changes.append(
                    FieldChange(
                        name=fname,
                        change_type="type_changed",
                        old_value=before_fields[fname],
                        new_value=after_fields[fname],
                    )
                )

        # Relationship changes
        rel_changes: list[str] = []
        for rel in sorted(set(after_rels) - set(before_rels)):
            rel_changes.append(f"added: {rel}")
        for rel in sorted(set(before_rels) - set(after_rels)):
            rel_changes.append(f"removed: {rel}")

        if field_changes or rel_changes:
            result.entity_changes.append(
                EntityChange(
                    name=name,
                    service_name=after_svc,
                    change_type="modified",
                    field_changes=field_changes,
                    relationship_changes=rel_changes,
                )
            )

    # ── Endpoint diff ──
    before_eps = _collect_endpoints(before)
    after_eps = _collect_endpoints(after)

    for key in sorted(set(after_eps) - set(before_eps)):
        svc, method, path = after_eps[key]
        result.endpoint_changes.append(
            EndpointChange(service_name=svc, method=method, path=path, change_type="added")
        )
    for key in sorted(set(before_eps) - set(after_eps)):
        svc, method, path = before_eps[key]
        result.endpoint_changes.append(
            EndpointChange(service_name=svc, method=method, path=path, change_type="removed")
        )

    # ── Event diff ──
    before_events = _collect_events(before)
    after_events = _collect_events(after)

    for name in sorted(set(after_events) - set(before_events)):
        svc, topic = after_events[name]
        result.event_changes.append(
            EventChange(service_name=svc, topic=topic, event_name=name, change_type="added")
        )
    for name in sorted(set(before_events) - set(after_events)):
        svc, topic = before_events[name]
        result.event_changes.append(
            EventChange(service_name=svc, topic=topic, event_name=name, change_type="removed")
        )

    return result


def render_diff_markdown(diff: DiffResult) -> str:
    """Render a DiffResult as a Markdown report.

    Args:
        diff: The diff result to render.

    Returns:
        Markdown string.
    """
    lines: list[str] = ["# Schema Changes\n"]

    # Summary
    lines.append("## Summary\n")
    lines.append(f"- {len(diff.entities_added)} entities added")
    lines.append(f"- {len(diff.entities_removed)} entities removed")
    lines.append(f"- {len(diff.entities_modified)} entities modified")
    lines.append(f"- {len(diff.endpoint_changes)} endpoint changes")
    lines.append(f"- {len(diff.event_changes)} event changes")
    lines.append("")

    # Breaking changes
    breaking = diff.breaking_changes
    if breaking:
        lines.append("## Breaking Changes\n")
        for change in breaking:
            lines.append(f"- **{change}**")
        lines.append("")

    # Non-breaking changes
    non_breaking = diff.non_breaking_changes
    if non_breaking:
        lines.append("## Non-Breaking Changes\n")
        for change in non_breaking:
            lines.append(f"- {change}")
        lines.append("")

    # Entity details
    if diff.entities_modified:
        lines.append("## Modified Entities\n")
        for ec in diff.entities_modified:
            lines.append(f"### {ec.name} ({ec.service_name})\n")
            for fc in ec.field_changes:
                if fc.change_type == "added":
                    lines.append(f"- **Added** field `{fc.name}: {fc.new_value}`")
                elif fc.change_type == "removed":
                    lines.append(f"- **Removed** field `{fc.name}: {fc.old_value}`")
                elif fc.change_type == "type_changed":
                    lines.append(
                        f"- **Changed** field `{fc.name}`: "
                        f"`{fc.old_value}` -> `{fc.new_value}`"
                    )
            for rc in ec.relationship_changes:
                lines.append(f"- Relationship {rc}")
            lines.append("")

    if not diff.has_changes:
        lines.append("No changes detected.\n")

    return "\n".join(lines)


def render_diff_json(diff: DiffResult) -> dict[str, object]:
    """Render a DiffResult as a JSON-serializable dict.

    Args:
        diff: The diff result to render.

    Returns:
        JSON-compatible dict.
    """
    entity_changes = []
    for ec in diff.entity_changes:
        entry: dict[str, object] = {
            "name": ec.name,
            "service": ec.service_name,
            "change_type": ec.change_type,
        }
        if ec.field_changes:
            entry["field_changes"] = [
                {
                    "name": fc.name,
                    "change_type": fc.change_type,
                    "old_value": fc.old_value,
                    "new_value": fc.new_value,
                }
                for fc in ec.field_changes
            ]
        if ec.relationship_changes:
            entry["relationship_changes"] = ec.relationship_changes
        entity_changes.append(entry)

    endpoint_changes = [
        {
            "service": epc.service_name,
            "method": epc.method,
            "path": epc.path,
            "change_type": epc.change_type,
            "details": epc.details,
        }
        for epc in diff.endpoint_changes
    ]

    event_changes = [
        {
            "service": evc.service_name,
            "topic": evc.topic,
            "event": evc.event_name,
            "change_type": evc.change_type,
        }
        for evc in diff.event_changes
    ]

    return {
        "has_changes": diff.has_changes,
        "breaking_changes": diff.breaking_changes,
        "non_breaking_changes": diff.non_breaking_changes,
        "entity_changes": entity_changes,
        "endpoint_changes": endpoint_changes,
        "event_changes": event_changes,
    }
