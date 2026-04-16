"""SVG entity inheritance tree builder.

Produces a diagram showing entity inheritance (extends) and trait
composition (with) relationships.  Abstract entities appear at the top,
concrete entities below, and shared trait nodes on the right.

Layout uses hierarchical rows for the inheritance tree with trait
nodes in a dedicated column on the right side.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from .svg_common import (
    CARD_BG,
    CARD_STROKE,
    CORNER_R,
    FONT,
    HEADER_BG,
    HEADER_FG,
    SVG_PAD,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    esc,
    render_bezier_edge,
    svg_background,
    svg_open,
    svg_title,
)
from .traversal import all_entities_with_service

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

logger = logging.getLogger(__name__)

# ── Layout constants ──

NODE_W = 180
NODE_H = 32
H_GAP = 24
V_GAP = 50
TITLE_AREA_H = 48
TRAIT_COL_GAP = 80  # gap between entity columns and trait column

TRAIT_NODE_W = 150
TRAIT_NODE_H = 28

# ── Colors ──

ABSTRACT_BG = "#f6f8fa"
ABSTRACT_STROKE = "#8b949e"
ABSTRACT_FG = "#57606a"

CONCRETE_BG = HEADER_BG
CONCRETE_FG = HEADER_FG
CONCRETE_STROKE = CARD_STROKE

TRAIT_BG = "#fff8c5"
TRAIT_STROKE = "#d4a72c"
TRAIT_FG = "#7d4e00"

EXTENDS_COLOR = "#57606a"
TRAIT_LINE_COLOR = "#d4a72c"


# ── Data holders ──


class _EntityNode:
    """An entity in the inheritance tree."""

    __slots__ = ("name", "is_abstract", "parent_name", "trait_names", "level", "x", "y")

    def __init__(
        self,
        name: str,
        is_abstract: bool,
        parent_name: str,
        trait_names: list[str],
    ) -> None:
        self.name = name
        self.is_abstract = is_abstract
        self.parent_name = parent_name
        self.trait_names = trait_names
        self.level = 0
        self.x = 0.0
        self.y = 0.0


class _TraitNode:
    """A shared trait node."""

    __slots__ = ("name", "x", "y")

    def __init__(self, name: str) -> None:
        self.name = name
        self.x = 0.0
        self.y = 0.0


# ── Data collection ──


def _collect_data(
    app: Application,
) -> tuple[list[_EntityNode], list[_TraitNode]]:
    """Collect entities and traits from the application."""
    seen: set[str] = set()
    entity_nodes: list[_EntityNode] = []
    trait_set: set[str] = set()

    for _service, _block, entity in all_entities_with_service(app):
        ename = str(entity.name)
        if ename in seen:
            continue
        seen.add(ename)

        # Parent (extends)
        parent_name = ""
        if entity.extends:
            if entity.extends.is_resolved:
                parent_name = str(entity.extends.target.name)
            else:
                parent_name = entity.extends.source_name

        # Traits
        traits: list[str] = []
        for trait_ref in entity.traits:
            if trait_ref.is_resolved:
                tname = str(trait_ref.target.name)
            else:
                tname = trait_ref.source_name
            traits.append(tname)
            trait_set.add(tname)

        entity_nodes.append(
            _EntityNode(ename, entity.is_abstract, parent_name, traits)
        )

    # Ensure parent nodes exist (they may be in shared modules not in traversal)
    existing_names = {n.name for n in entity_nodes}
    for node in list(entity_nodes):
        if node.parent_name and node.parent_name not in existing_names:
            existing_names.add(node.parent_name)
            entity_nodes.append(
                _EntityNode(node.parent_name, True, "", [])
            )

    trait_nodes = [_TraitNode(name) for name in sorted(trait_set)]
    return entity_nodes, trait_nodes


# ── Level assignment ──


def _assign_levels(nodes: list[_EntityNode]) -> None:
    """Assign levels: abstract roots at 0, children at parent + 1."""
    node_map = {n.name: n for n in nodes}
    levels: dict[str, int] = {}
    computing: set[str] = set()

    def _get_level(name: str) -> int:
        if name in levels:
            return levels[name]
        if name in computing:
            levels[name] = 0
            return 0
        computing.add(name)

        node = node_map.get(name)
        if node is None or not node.parent_name:
            levels[name] = 0
        else:
            levels[name] = _get_level(node.parent_name) + 1

        computing.discard(name)
        return levels[name]

    for node in nodes:
        node.level = _get_level(node.name)


# ── Layout ──


def _layout(
    entities: list[_EntityNode],
    traits: list[_TraitNode],
) -> tuple[float, float]:
    """Position entities in rows by level, traits in a right column.

    Returns (total_width, total_height).
    """
    if not entities:
        return 400.0, 200.0

    by_level: dict[int, list[_EntityNode]] = defaultdict(list)
    for node in entities:
        by_level[node.level].append(node)

    sorted_levels = sorted(by_level.keys())
    max_per_level = max(len(by_level[lvl]) for lvl in sorted_levels)

    entity_area_w = max_per_level * NODE_W + max(0, max_per_level - 1) * H_GAP
    trait_area_w = TRAIT_NODE_W if traits else 0
    gap = TRAIT_COL_GAP if traits else 0

    total_width = SVG_PAD * 2 + entity_area_w + gap + trait_area_w
    total_width = max(total_width, 400.0)

    # Position entity nodes
    y = SVG_PAD + TITLE_AREA_H
    max_entity_bottom = y

    for level in sorted_levels:
        level_nodes = by_level[level]
        row_width = len(level_nodes) * NODE_W + max(0, len(level_nodes) - 1) * H_GAP
        x_start = SVG_PAD + (entity_area_w - row_width) / 2

        for i, node in enumerate(level_nodes):
            node.x = x_start + i * (NODE_W + H_GAP)
            node.y = y

        y += NODE_H + V_GAP
        max_entity_bottom = y - V_GAP + NODE_H

    # Position trait nodes in a column on the right
    if traits:
        trait_x = SVG_PAD + entity_area_w + TRAIT_COL_GAP
        trait_y = SVG_PAD + TITLE_AREA_H
        for trait_node in traits:
            trait_node.x = trait_x
            trait_node.y = trait_y
            trait_y += TRAIT_NODE_H + 12

        max_trait_bottom = trait_y - 12 + TRAIT_NODE_H
        content_bottom = max(max_entity_bottom, max_trait_bottom)
    else:
        content_bottom = max_entity_bottom

    total_height = content_bottom + SVG_PAD
    return total_width, max(total_height, 200.0)


# ── SVG rendering ──


def _svg_styles() -> str:
    return f"""<style>
  .abstract-name {{ font: italic 11px {FONT}; fill: {ABSTRACT_FG}; }}
  .concrete-name {{ font: bold 11px {FONT}; fill: {CONCRETE_FG}; }}
  .trait-name {{ font: bold 10px {FONT}; fill: {TRAIT_FG}; }}
</style>"""


def _render_entity(node: _EntityNode) -> str:
    """Render an entity node."""
    cx = node.x + NODE_W / 2
    cy = node.y + NODE_H / 2 + 4

    if node.is_abstract:
        return (
            f'<rect x="{node.x}" y="{node.y}" width="{NODE_W}" '
            f'height="{NODE_H}" rx="{CORNER_R}" '
            f'fill="{ABSTRACT_BG}" stroke="{ABSTRACT_STROKE}" '
            f'stroke-width="1" stroke-dasharray="4,3"/>\n'
            f'<text x="{cx}" y="{cy}" text-anchor="middle" '
            f'class="abstract-name">{esc(node.name)}</text>'
        )

    return (
        f'<rect x="{node.x}" y="{node.y}" width="{NODE_W}" '
        f'height="{NODE_H}" rx="{CORNER_R}" '
        f'fill="{CONCRETE_BG}" stroke="{CONCRETE_STROKE}" stroke-width="1"/>\n'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'class="concrete-name">{esc(node.name)}</text>'
    )


def _render_trait(node: _TraitNode) -> str:
    """Render a trait node as a colored hexagon-style box."""
    cx = node.x + TRAIT_NODE_W / 2
    cy = node.y + TRAIT_NODE_H / 2 + 4
    return (
        f'<rect x="{node.x}" y="{node.y}" width="{TRAIT_NODE_W}" '
        f'height="{TRAIT_NODE_H}" rx="14" '
        f'fill="{TRAIT_BG}" stroke="{TRAIT_STROKE}" stroke-width="1"/>\n'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'class="trait-name">{esc(node.name)}</text>'
    )


def _render_extends_edges(entities: list[_EntityNode]) -> str:
    """Render inheritance edges (parent → child)."""
    node_map = {n.name: n for n in entities}
    parts: list[str] = []

    for node in entities:
        if not node.parent_name:
            continue
        parent = node_map.get(node.parent_name)
        if parent is None:
            continue

        sx = parent.x + NODE_W / 2
        sy = parent.y + NODE_H
        tx = node.x + NODE_W / 2
        ty = node.y

        parts.append(render_bezier_edge(
            sx, sy, tx, ty,
            stroke=EXTENDS_COLOR,
            stroke_width=1.5,
        ))

    return "\n".join(parts)


def _render_trait_edges(
    entities: list[_EntityNode],
    traits: list[_TraitNode],
) -> str:
    """Render dashed lines from entities to their traits."""
    trait_map = {t.name: t for t in traits}
    parts: list[str] = []

    for entity in entities:
        for tname in entity.trait_names:
            trait_node = trait_map.get(tname)
            if trait_node is None:
                continue

            sx = entity.x + NODE_W
            sy = entity.y + NODE_H / 2
            tx = trait_node.x
            ty = trait_node.y + TRAIT_NODE_H / 2

            parts.append(render_bezier_edge(
                sx, sy, tx, ty,
                stroke=TRAIT_LINE_COLOR,
                stroke_width=0.8,
                dash="4,3",
            ))

    return "\n".join(parts)


# ── Public API ──


def build_inheritance_svg(app: Application) -> str:
    """Build an SVG entity inheritance tree diagram.

    Shows abstract entities at the top with concrete children below,
    connected by solid extends edges. Trait nodes appear in a right
    column connected by dashed lines.

    Args:
        app: Fully resolved Application model.

    Returns:
        SVG XML string.
    """
    entities, traits = _collect_data(app)

    if not entities:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 60" '
            'width="100%"><text x="20" y="30" font-size="14">'
            'No entities found.</text></svg>'
        )

    _assign_levels(entities)
    width, height = _layout(entities, traits)

    parts: list[str] = [
        svg_open(width, height),
        _svg_styles(),
        svg_background(width, height),
        svg_title(SVG_PAD, SVG_PAD + 16, "Entity Inheritance Tree"),
    ]

    # Edges first (below nodes)
    parts.append(_render_extends_edges(entities))
    parts.append(_render_trait_edges(entities, traits))

    # Entity nodes
    for entity in entities:
        parts.append(_render_entity(entity))

    # Trait nodes
    for trait in traits:
        parts.append(_render_trait(trait))

    parts.append("</svg>")

    logger.info(
        "inheritance_built entities=%d traits=%d",
        len(entities), len(traits),
    )

    return "\n".join(parts)
