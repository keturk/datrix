"""SVG system context diagram builder.

Produces a C4-inspired system context diagram showing services as
rounded nodes arranged in hierarchical rows by dependency depth,
with directed arrows from consumers to their dependencies.

Renders in GitHub, VS Code, and browsers without external dependencies.
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
    arrow_marker_def,
    esc,
    render_bezier_edge,
    simple_name,
    svg_background,
    svg_open,
    svg_title,
)
from .traversal import service_dependency_edges

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

logger = logging.getLogger(__name__)

# ── Layout constants ──

NODE_W = 200
NODE_H = 40
NODE_PAD_X = 12
H_GAP = 40
V_GAP = 80
TITLE_AREA_H = 48
ARROW_COLOR = "#57606a"


# ── Data holders ──


class _ServiceNode:
    """A service rendered as a rounded box."""

    __slots__ = ("name", "level", "x", "y")

    def __init__(self, name: str) -> None:
        self.name = name
        self.level = 0
        self.x = 0.0
        self.y = 0.0


class _DepEdge:
    """A directed dependency: consumer depends on provider."""

    __slots__ = ("consumer", "provider")

    def __init__(self, consumer: str, provider: str) -> None:
        self.consumer = consumer
        self.provider = provider


# ── Level assignment ──


def _assign_levels(
    nodes: dict[str, _ServiceNode],
    edges: list[_DepEdge],
) -> None:
    """Assign hierarchical levels: providers at top, consumers at bottom.

    Services that others depend on (providers) get level 0.
    Services that only consume get the highest level.
    """
    # Build inbound count (how many services depend on me)
    inbound: dict[str, int] = defaultdict(int)
    outbound: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        inbound[edge.provider] += 1
        outbound[edge.consumer].add(edge.provider)

    # Compute depth as max distance from a "root" provider
    # Root providers: services with inbound deps but no outbound, OR highest inbound
    # Simpler: level = max depth of dependency chain going outward
    levels: dict[str, int] = {}
    computing: set[str] = set()

    def _get_depth(name: str) -> int:
        if name in levels:
            return levels[name]
        if name in computing:
            return 0  # cycle
        computing.add(name)

        deps = outbound.get(name, set())
        if not deps:
            levels[name] = 0
        else:
            levels[name] = max(_get_depth(d) for d in deps) + 1

        computing.discard(name)
        return levels[name]

    for name in nodes:
        _get_depth(name)

    # Reverse so providers (level 0 = no outbound) are at TOP
    # and deep consumers are at bottom
    # Actually _get_depth already does this: leaf providers = 0, consumers = higher
    # But we want providers at top. Invert: max_level - level
    max_level = max(levels.values()) if levels else 0
    for name, node in nodes.items():
        node.level = max_level - levels.get(name, 0)


# ── Layout ──


def _layout_nodes(nodes: list[_ServiceNode]) -> tuple[float, float]:
    """Arrange nodes in rows by level, centered horizontally.

    Returns (total_width, total_height).
    """
    if not nodes:
        return float(SVG_PAD * 2 + NODE_W), float(SVG_PAD * 2 + NODE_H)

    by_level: dict[int, list[_ServiceNode]] = defaultdict(list)
    for node in nodes:
        by_level[node.level].append(node)

    sorted_levels = sorted(by_level.keys())
    max_per_level = max(len(by_level[lvl]) for lvl in sorted_levels)

    total_width = SVG_PAD * 2 + max_per_level * NODE_W + max(0, max_per_level - 1) * H_GAP
    total_width = max(total_width, 400.0)

    y = SVG_PAD + TITLE_AREA_H

    for level in sorted_levels:
        level_nodes = by_level[level]
        row_width = len(level_nodes) * NODE_W + max(0, len(level_nodes) - 1) * H_GAP
        x_start = (total_width - row_width) / 2

        for i, node in enumerate(level_nodes):
            node.x = x_start + i * (NODE_W + H_GAP)
            node.y = y

        y += NODE_H + V_GAP

    total_height = y - V_GAP + SVG_PAD
    return total_width, max(total_height, 200.0)


# ── SVG rendering ──


def _svg_styles() -> str:
    return f"""<style>
  .svc-name {{ font: bold 12px {FONT}; fill: {HEADER_FG}; }}
</style>"""


def _render_node(node: _ServiceNode) -> str:
    """Render a service node as a rounded box with centered text."""
    cx = node.x + NODE_W / 2
    cy = node.y + NODE_H / 2 + 4
    return (
        f'<rect x="{node.x}" y="{node.y}" width="{NODE_W}" '
        f'height="{NODE_H}" rx="{CORNER_R + 2}" '
        f'fill="{HEADER_BG}" stroke="{CARD_STROKE}" stroke-width="1"/>\n'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'class="svc-name">{esc(node.name)}</text>'
    )


def _render_dep_arrow(
    edge: _DepEdge,
    node_map: dict[str, _ServiceNode],
) -> str:
    """Render a dependency arrow from consumer to provider."""
    consumer = node_map.get(edge.consumer)
    provider = node_map.get(edge.provider)
    if consumer is None or provider is None:
        return ""

    # Consumer is below provider — arrow from consumer top to provider bottom
    sx = consumer.x + NODE_W / 2
    sy = consumer.y
    tx = provider.x + NODE_W / 2
    ty = provider.y + NODE_H

    return render_bezier_edge(
        sx, sy, tx, ty,
        stroke=ARROW_COLOR,
        stroke_width=1.5,
        marker_end="dep-arrow",
    )


# ── Public API ──


def build_system_context_svg(app: Application) -> str:
    """Build an SVG system context diagram.

    Shows services as rounded nodes arranged by dependency depth,
    with arrows from consumers to their dependencies.

    Args:
        app: Fully resolved Application model.

    Returns:
        SVG XML string.
    """
    # Collect nodes
    nodes: dict[str, _ServiceNode] = {}
    for service in app.services.values():
        sname = simple_name(str(service.name))
        nodes[sname] = _ServiceNode(sname)

    # Collect edges
    raw_edges = service_dependency_edges(app)
    edges: list[_DepEdge] = []
    for from_name, to_name in raw_edges:
        from_simple = simple_name(from_name)
        to_simple = simple_name(to_name)
        if from_simple in nodes and to_simple in nodes:
            edges.append(_DepEdge(from_simple, to_simple))

    if not nodes:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 60" '
            'width="100%"><text x="20" y="30" font-size="14">'
            'No services found.</text></svg>'
        )

    # Assign levels and layout
    _assign_levels(nodes, edges)
    node_list = list(nodes.values())
    width, height = _layout_nodes(node_list)

    # Assemble SVG
    parts: list[str] = [
        svg_open(width, height),
        _svg_styles(),
        f"<defs>{arrow_marker_def('dep-arrow', ARROW_COLOR)}</defs>",
        svg_background(width, height),
        svg_title(SVG_PAD, SVG_PAD + 16, "System Context", "Service dependency graph"),
    ]

    # Arrows first (below nodes)
    for edge in edges:
        arrow_svg = _render_dep_arrow(edge, nodes)
        if arrow_svg:
            parts.append(arrow_svg)

    # Nodes
    for node in node_list:
        parts.append(_render_node(node))

    parts.append("</svg>")

    svc_count = len(nodes)
    dep_count = len(edges)
    logger.info(
        "system_context_built services=%d dependencies=%d",
        svc_count, dep_count,
    )

    return "\n".join(parts)
