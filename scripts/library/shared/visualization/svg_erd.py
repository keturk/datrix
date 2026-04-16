"""SVG ERD builder for Datrix visualizations.

Produces per-service entity-relationship diagrams as self-contained SVG.
Each service with RDBMS entities gets its own SVG showing:
- Entity cards with fields (name, type, nullable markers)
- Relationship lines with cardinality labels
- Hierarchical top-to-bottom layout (parents above children)

Renders in GitHub, VS Code, and browsers without external dependencies.
"""

from __future__ import annotations

import html
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from datrix_common.generation.relationship_kind import RelationshipKind
from datrix_common.paths import ServicePaths

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application, Service
    from datrix_common.types import DatrixType

logger = logging.getLogger(__name__)

# ── Layout constants ──

CARD_WIDTH = 300
CARD_PAD_X = 14
CARD_PAD_Y = 8
HEADER_H = 32
FIELD_ROW_H = 22
PK_COL_W = 26
H_GAP = 120
V_GAP = 70
SVG_PAD = 28
CORNER_R = 6
TITLE_H = 32

# ── Colors ──

HEADER_BG = "#24292f"
HEADER_FG = "#ffffff"
CARD_BG = "#ffffff"
CARD_STROKE = "#d0d7de"
CARD_SHADOW = "rgba(0,0,0,0.08)"
FIELD_NAME_COLOR = "#1f2328"
TYPE_COLOR = "#656d76"
PK_COLOR = "#cf222e"
NULLABLE_COLOR = "#8b949e"
REL_LINE_COLOR = "#8b949e"
CARDINALITY_COLOR = "#57606a"
REL_LABEL_COLOR = "#656d76"
TITLE_COLOR = "#1f2328"
SUBTITLE_COLOR = "#656d76"
FONT = '"Segoe UI", system-ui, -apple-system, sans-serif'


# ── Data holders ──


class _FieldRow:
    """A field in an entity card."""

    __slots__ = ("name", "type_display", "is_pk", "is_nullable")

    def __init__(
        self, name: str, type_display: str, is_pk: bool, is_nullable: bool
    ) -> None:
        self.name = name
        self.type_display = type_display
        self.is_pk = is_pk
        self.is_nullable = is_nullable


class _EntityCard:
    """An entity rendered as a card with header and field rows."""

    __slots__ = ("name", "fields", "level", "x", "y", "width", "height")

    def __init__(self, name: str, fields: list[_FieldRow]) -> None:
        self.name = name
        self.fields = fields
        self.level = 0
        self.x = 0.0
        self.y = 0.0
        self.width = float(CARD_WIDTH)
        content_h = max(len(fields) * FIELD_ROW_H, FIELD_ROW_H)
        self.height = float(HEADER_H + CARD_PAD_Y * 2 + content_h)


class _RelEdge:
    """A deduplicated relationship between two entities.

    ``source`` is always the "one" side (parent) for one-to-many,
    or alphabetically first for many-to-many / one-to-one.
    """

    __slots__ = ("source", "target", "source_cardinality", "target_cardinality", "label")

    def __init__(
        self,
        source: str,
        target: str,
        source_cardinality: str,
        target_cardinality: str,
        label: str,
    ) -> None:
        self.source = source
        self.target = target
        self.source_cardinality = source_cardinality
        self.target_cardinality = target_cardinality
        self.label = label


# ── Helpers ──


def _esc(text: str) -> str:
    """Escape text for SVG/XML."""
    return html.escape(text, quote=True)


def _type_label(resolved_type: DatrixType) -> tuple[str, bool]:
    """Get display name and nullable status for a field type.

    Returns:
        (type_display_name, is_nullable)
    """
    is_nullable = resolved_type.is_optional()
    inner = resolved_type.unwrap()
    return inner.display_name(), is_nullable


def _simple_name(service_name: str) -> str:
    """Extract short service name from qualified name."""
    return ServicePaths(service_name).simple_name


# ── Data collection ──


def _collect_service_data(
    service: Service,
) -> tuple[list[_EntityCard], list[_RelEdge]]:
    """Collect entities and relationships for a single service.

    Returns:
        (entity_cards, relationship_edges)
    """
    cards: list[_EntityCard] = []
    entity_names: set[str] = set()

    for rdbms_block in service.rdbms_blocks.values():
        for entity in rdbms_block.entities.values():
            if entity.is_abstract:
                continue
            ename = str(entity.name)
            entity_names.add(ename)

            fields: list[_FieldRow] = []
            for field in entity.fields.values():
                if field.is_inherited():
                    continue
                type_name, is_nullable = _type_label(field.resolved_type)
                fields.append(
                    _FieldRow(
                        name=str(field.name),
                        type_display=type_name,
                        is_pk=field.is_primary_key,
                        is_nullable=is_nullable,
                    )
                )
            cards.append(_EntityCard(ename, fields))

    # Deduplicate relationships — one edge per entity pair
    edges: list[_RelEdge] = []
    seen_pairs: set[str] = set()

    for rdbms_block in service.rdbms_blocks.values():
        for entity in rdbms_block.entities.values():
            if entity.is_abstract:
                continue
            source_name = str(entity.name)

            for rel in entity.relationships:
                if rel.target.is_resolved:
                    target_name = str(rel.target.target.name)
                else:
                    target_name = rel.target.source_name.split(".")[-1]

                if target_name not in entity_names:
                    continue

                # Dedup by sorted pair
                pair_key = ":".join(sorted([source_name, target_name]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                label = rel.alias or ""
                kind = rel.kind

                if kind == RelationshipKind.HAS_MANY.value:
                    edges.append(
                        _RelEdge(source_name, target_name, "1", "*", label)
                    )
                elif kind == RelationshipKind.BELONGS_TO.value:
                    # Reverse so parent (one) is source
                    edges.append(
                        _RelEdge(target_name, source_name, "1", "*", label)
                    )
                elif kind == RelationshipKind.HAS_ONE.value:
                    edges.append(
                        _RelEdge(source_name, target_name, "1", "1", label)
                    )
                elif kind == RelationshipKind.MANY_TO_MANY.value:
                    edges.append(
                        _RelEdge(source_name, target_name, "*", "*", label)
                    )

    return cards, edges


# ── Level assignment ──


def _assign_levels(cards: list[_EntityCard], edges: list[_RelEdge]) -> None:
    """Assign hierarchy levels based on one-to-many relationships.

    Parent entities (the "1" side) get lower levels (higher on screen)
    than child entities (the "*" side).
    """
    card_names = {c.name for c in cards}
    card_map = {c.name: c for c in cards}

    # child -> parent (from 1-to-many edges)
    parent_of: dict[str, str] = {}
    for edge in edges:
        if edge.source_cardinality == "1" and edge.target_cardinality == "*":
            if edge.target in card_names and edge.source in card_names:
                parent_of[edge.target] = edge.source

    levels: dict[str, int] = {}
    computing: set[str] = set()

    def _get_level(name: str) -> int:
        if name in levels:
            return levels[name]
        if name in computing:
            levels[name] = 0
            return 0
        computing.add(name)

        parent = parent_of.get(name)
        if parent is None or parent not in card_names:
            levels[name] = 0
        else:
            levels[name] = _get_level(parent) + 1

        computing.discard(name)
        return levels[name]

    for card in cards:
        card.level = _get_level(card.name)


# ── Layout ──


def _layout_cards(cards: list[_EntityCard]) -> tuple[float, float]:
    """Arrange cards in rows by level, centered horizontally.

    Returns:
        (total_width, total_height)
    """
    if not cards:
        return float(SVG_PAD * 2), float(SVG_PAD * 2)

    by_level: dict[int, list[_EntityCard]] = defaultdict(list)
    for card in cards:
        by_level[card.level].append(card)

    sorted_levels = sorted(by_level.keys())
    max_per_level = max(len(by_level[lvl]) for lvl in sorted_levels)

    total_width = SVG_PAD * 2 + max_per_level * CARD_WIDTH + max(0, max_per_level - 1) * H_GAP
    total_width = max(total_width, 400.0)

    y = SVG_PAD + TITLE_H

    for level in sorted_levels:
        level_cards = by_level[level]
        row_width = len(level_cards) * CARD_WIDTH + max(0, len(level_cards) - 1) * H_GAP
        x_start = (total_width - row_width) / 2

        max_height = 0.0
        for i, card in enumerate(level_cards):
            card.x = x_start + i * (CARD_WIDTH + H_GAP)
            card.y = y
            max_height = max(max_height, card.height)

        y += max_height + V_GAP

    total_height = y - V_GAP + SVG_PAD
    return total_width, max(total_height, 200.0)


# ── SVG rendering ──


def _svg_styles() -> str:
    """Render the <style> block."""
    return f"""<style>
  .entity-name {{ font: bold 13px {FONT}; fill: {HEADER_FG}; }}
  .field-name {{ font: 11px {FONT}; fill: {FIELD_NAME_COLOR}; }}
  .field-type {{ font: 11px {FONT}; fill: {TYPE_COLOR}; }}
  .pk-badge {{ font: bold 9px {FONT}; fill: {PK_COLOR}; }}
  .rel-line {{ stroke: {REL_LINE_COLOR}; fill: none; stroke-width: 1.5; }}
  .cardinality {{ font: bold 11px {FONT}; fill: {CARDINALITY_COLOR}; }}
  .rel-label {{ font: italic 10px {FONT}; fill: {REL_LABEL_COLOR}; }}
  .title {{ font: bold 16px {FONT}; fill: {TITLE_COLOR}; }}
  .subtitle {{ font: 11px {FONT}; fill: {SUBTITLE_COLOR}; }}
</style>"""


def _svg_defs() -> str:
    """Render filter and marker definitions."""
    return f"""<defs>
  <filter id="shadow" x="-4%" y="-4%" width="108%" height="112%">
    <feDropShadow dx="0" dy="1" stdDeviation="3" flood-color="{CARD_SHADOW}"/>
  </filter>
</defs>"""


def _render_card(card: _EntityCard) -> str:
    """Render a single entity card."""
    parts: list[str] = []

    # Card background with shadow
    parts.append(
        f'<rect x="{card.x}" y="{card.y}" width="{card.width}" '
        f'height="{card.height}" rx="{CORNER_R}" '
        f'fill="{CARD_BG}" stroke="{CARD_STROKE}" stroke-width="1" '
        f'filter="url(#shadow)"/>'
    )

    # Header bar
    parts.append(
        f'<rect x="{card.x}" y="{card.y}" width="{card.width}" '
        f'height="{HEADER_H}" rx="{CORNER_R}" fill="{HEADER_BG}"/>'
    )
    # Square off bottom corners of header
    parts.append(
        f'<rect x="{card.x}" y="{card.y + HEADER_H - CORNER_R}" '
        f'width="{card.width}" height="{CORNER_R}" fill="{HEADER_BG}"/>'
    )
    # Entity name
    parts.append(
        f'<text x="{card.x + CARD_PAD_X}" '
        f'y="{card.y + HEADER_H / 2 + 5}" class="entity-name">'
        f'{_esc(card.name)}</text>'
    )

    # Fields
    field_y = card.y + HEADER_H + CARD_PAD_Y

    for field in card.fields:
        fy_text = field_y + FIELD_ROW_H / 2 + 4

        # PK badge
        if field.is_pk:
            parts.append(
                f'<text x="{card.x + CARD_PAD_X + 2}" y="{fy_text}" '
                f'class="pk-badge">PK</text>'
            )

        # Field name (with ? for nullable)
        name_x = card.x + CARD_PAD_X + PK_COL_W
        display_name = f"{field.name}?" if field.is_nullable else field.name
        parts.append(
            f'<text x="{name_x}" y="{fy_text}" '
            f'class="field-name">{_esc(display_name)}</text>'
        )

        # Type (right-aligned)
        type_x = card.x + card.width - CARD_PAD_X
        parts.append(
            f'<text x="{type_x}" y="{fy_text}" '
            f'text-anchor="end" class="field-type">{_esc(field.type_display)}</text>'
        )

        # Subtle divider between rows
        div_y = field_y + FIELD_ROW_H
        if field is not card.fields[-1]:
            parts.append(
                f'<line x1="{card.x + CARD_PAD_X}" y1="{div_y}" '
                f'x2="{card.x + card.width - CARD_PAD_X}" y2="{div_y}" '
                f'stroke="#f0f0f0" stroke-width="0.5"/>'
            )

        field_y += FIELD_ROW_H

    return "\n".join(parts)


def _edge_anchor(
    source: _EntityCard,
    target: _EntityCard,
    edge_index: int,
) -> tuple[float, float, float, float, str]:
    """Compute connection anchor points for an edge.

    Returns:
        (source_x, source_y, target_x, target_y, orientation)
        orientation is "vertical" or "horizontal".
    """
    # Spread multiple connections across the card edge
    offset = (edge_index % 5 - 2) * 10.0

    source_bottom = source.y + source.height
    target_top = target.y

    if source_bottom + 10 < target_top:
        # Source above target — connect bottom-to-top
        sx = source.x + source.width / 2 + offset
        sy = source_bottom
        tx = target.x + target.width / 2 + offset
        ty = target_top
        return sx, sy, tx, ty, "vertical"

    if target.y + target.height + 10 < source.y:
        # Target above source — connect top-to-bottom (reversed)
        sx = source.x + source.width / 2 + offset
        sy = source.y
        tx = target.x + target.width / 2 + offset
        ty = target.y + target.height
        return sx, sy, tx, ty, "vertical"

    # Same level — connect sides
    if source.x < target.x:
        sx = source.x + source.width
        sy = source.y + source.height / 2 + offset
        tx = target.x
        ty = target.y + target.height / 2 + offset
    else:
        sx = source.x
        sy = source.y + source.height / 2 + offset
        tx = target.x + target.width
        ty = target.y + target.height / 2 + offset

    return sx, sy, tx, ty, "horizontal"


def _render_edge(
    edge: _RelEdge,
    card_map: dict[str, _EntityCard],
    edge_index: int,
) -> str:
    """Render a relationship line between two entity cards."""
    source_card = card_map.get(edge.source)
    target_card = card_map.get(edge.target)
    if source_card is None or target_card is None:
        return ""

    # Self-referential relationship
    if edge.source == edge.target:
        return _render_self_edge(edge, source_card)

    sx, sy, tx, ty, orientation = _edge_anchor(
        source_card, target_card, edge_index
    )

    # Bezier curve
    if orientation == "vertical":
        mid_y = (sy + ty) / 2
        path = f"M {sx:.1f} {sy:.1f} C {sx:.1f} {mid_y:.1f} {tx:.1f} {mid_y:.1f} {tx:.1f} {ty:.1f}"
    else:
        mid_x = (sx + tx) / 2
        path = f"M {sx:.1f} {sy:.1f} C {mid_x:.1f} {sy:.1f} {mid_x:.1f} {ty:.1f} {tx:.1f} {ty:.1f}"

    parts: list[str] = [f'<path d="{path}" class="rel-line"/>']

    # Cardinality labels at endpoints
    _append_cardinality_label(parts, sx, sy, tx, ty, edge.source_cardinality, near_source=True)
    _append_cardinality_label(parts, sx, sy, tx, ty, edge.target_cardinality, near_source=False)

    # Relationship label at midpoint
    if edge.label:
        mid_x = (sx + tx) / 2
        mid_y = (sy + ty) / 2
        # Background rect for readability
        parts.append(
            f'<rect x="{mid_x - 20}" y="{mid_y - 12}" width="40" height="14" '
            f'rx="3" fill="white" stroke="{CARD_STROKE}" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{mid_x}" y="{mid_y - 2}" text-anchor="middle" '
            f'class="rel-label">{_esc(edge.label)}</text>'
        )

    return "\n".join(parts)


def _append_cardinality_label(
    parts: list[str],
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    cardinality: str,
    near_source: bool,
) -> None:
    """Append a cardinality label near an endpoint."""
    t = 0.08 if near_source else 0.92
    lx = sx + (tx - sx) * t
    ly = sy + (ty - sy) * t

    # Offset label perpendicular to the line direction
    dx = tx - sx
    dy = ty - sy
    length = max((dx * dx + dy * dy) ** 0.5, 1.0)
    # Perpendicular offset (rotate 90 degrees)
    offset_x = -dy / length * 10
    offset_y = dx / length * 10

    lx += offset_x
    ly += offset_y

    parts.append(
        f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
        f'class="cardinality">{_esc(cardinality)}</text>'
    )


def _render_self_edge(edge: _RelEdge, card: _EntityCard) -> str:
    """Render a self-referential relationship as a loop on the right side."""
    rx = card.x + card.width
    cy = card.y + card.height / 2
    loop_w = 30
    loop_h = 24

    path = (
        f"M {rx:.1f} {cy - loop_h:.1f} "
        f"C {rx + loop_w:.1f} {cy - loop_h:.1f} "
        f"{rx + loop_w:.1f} {cy + loop_h:.1f} "
        f"{rx:.1f} {cy + loop_h:.1f}"
    )

    parts: list[str] = [f'<path d="{path}" class="rel-line"/>']

    # Cardinality labels
    parts.append(
        f'<text x="{rx + loop_w + 4:.1f}" y="{cy - 4:.1f}" '
        f'class="cardinality">{_esc(edge.source_cardinality)}</text>'
    )
    parts.append(
        f'<text x="{rx + loop_w + 4:.1f}" y="{cy + 12:.1f}" '
        f'class="cardinality">{_esc(edge.target_cardinality)}</text>'
    )

    if edge.label:
        parts.append(
            f'<text x="{rx + loop_w + 4:.1f}" y="{cy + 24:.1f}" '
            f'class="rel-label">{_esc(edge.label)}</text>'
        )

    return "\n".join(parts)


def _render_svg(
    service_display_name: str,
    cards: list[_EntityCard],
    edges: list[_RelEdge],
    width: float,
    height: float,
) -> str:
    """Assemble the complete SVG document."""
    card_map = {c.name: c for c in cards}

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width:.0f} {height:.0f}">',
        _svg_styles(),
        _svg_defs(),
        # White background
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="white"/>',
        # Title
        f'<text x="{SVG_PAD}" y="{SVG_PAD + 16}" class="title">'
        f'{_esc(service_display_name)}</text>',
        f'<text x="{SVG_PAD}" y="{SVG_PAD + 30}" class="subtitle">'
        f'Entity-Relationship Diagram</text>',
    ]

    # Relationship lines (drawn first so cards overlay them)
    for i, edge in enumerate(edges):
        line_svg = _render_edge(edge, card_map, i)
        if line_svg:
            parts.append(line_svg)

    # Entity cards
    for card in cards:
        parts.append(_render_card(card))

    parts.append("</svg>")
    return "\n".join(parts)


# ── Public API ──


def build_erd_svgs(app: Application) -> dict[str, str]:
    """Build per-service ERD SVG diagrams.

    Iterates over all services in the application. For each service with
    RDBMS entities, produces a self-contained SVG string showing entities
    and their relationships in a hierarchical layout.

    Args:
        app: Fully resolved Application model.

    Returns:
        Dict mapping service simple name to SVG string.
        Services with no concrete entities are omitted.
    """
    result: dict[str, str] = {}

    for service in app.services.values():
        sname = _simple_name(str(service.name))
        cards, edges = _collect_service_data(service)

        if not cards:
            logger.debug("erd_skip service=%s reason=no_entities", sname)
            continue

        _assign_levels(cards, edges)
        width, height = _layout_cards(cards)
        svg = _render_svg(sname, cards, edges, width, height)
        result[sname] = svg

        entity_count = len(cards)
        rel_count = len(edges)
        logger.info(
            "erd_built service=%s entities=%d relationships=%d",
            sname, entity_count, rel_count,
        )

    return result
