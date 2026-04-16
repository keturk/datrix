"""SVG service map builder with shared infrastructure.

Produces a two-tier diagram:
- Top tier: service nodes arranged in rows with HTTP dependency arrows.
- Bottom tier: shared infrastructure nodes (RDBMS, cache, MQ, NoSQL, storage)
  with connection lines from services to their infrastructure.

Shared infrastructure is grouped by identity key (engine + host + port)
so that services connecting to the same server share a single node.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from .svg_common import (
    CARD_STROKE,
    CORNER_R,
    FONT,
    HEADER_BG,
    HEADER_FG,
    SVG_PAD,
    TEXT_MUTED,
    TEXT_SECONDARY,
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

SVC_NODE_W = 180
SVC_NODE_H = 36
SVC_H_GAP = 30
SVC_V_GAP = 20
SVC_MAX_PER_ROW = 7

INFRA_NODE_W = 200
INFRA_NODE_H = 36
INFRA_H_GAP = 30

TIER_GAP = 60        # gap between service tier and infra tier
TITLE_AREA_H = 48

# ── Colors ──

RDBMS_BG = "#ddf4ff"
RDBMS_STROKE = "#54aeff"
CACHE_BG = "#dafbe1"
CACHE_STROKE = "#4ac26b"
MQ_BG = "#fff8c5"
MQ_STROKE = "#d4a72c"
NOSQL_BG = "#fbefff"
NOSQL_STROKE = "#c297db"
STORAGE_BG = "#e8f5e9"
STORAGE_STROKE = "#66bb6a"

INFRA_LINE_COLOR = "#b0b8c0"
HTTP_ARROW_COLOR = "#57606a"


# ── Data holders ──


class _SvcNode:
    """A service in the service tier."""

    __slots__ = ("name", "x", "y")

    def __init__(self, name: str) -> None:
        self.name = name
        self.x = 0.0
        self.y = 0.0


class _InfraNode:
    """A shared infrastructure node in the infra tier."""

    __slots__ = ("node_id", "label", "bg", "stroke", "x", "y", "connections")

    def __init__(
        self, node_id: str, label: str, bg: str, stroke: str,
    ) -> None:
        self.node_id = node_id
        self.label = label
        self.bg = bg
        self.stroke = stroke
        self.x = 0.0
        self.y = 0.0
        self.connections: list[tuple[str, str]] = []  # (service_name, edge_label)


class _HttpEdge:
    """An HTTP dependency between two services."""

    __slots__ = ("consumer", "provider")

    def __init__(self, consumer: str, provider: str) -> None:
        self.consumer = consumer
        self.provider = provider


# ── Data collection ──


def _brokers_identity(brokers: list[str] | str | None) -> str:
    """Produce a stable string for a pubsub brokers config value."""
    if brokers is None:
        return ""
    if isinstance(brokers, str):
        return brokers
    if isinstance(brokers, list):
        return ",".join(str(b) for b in sorted(str(b) for b in brokers))
    return str(brokers)


def _collect_data(
    app: Application,
) -> tuple[list[_SvcNode], list[_InfraNode], list[_HttpEdge]]:
    """Collect services, infrastructure, and HTTP edges."""
    svc_nodes: dict[str, _SvcNode] = {}
    infra_groups: dict[tuple[str, ...], _InfraNode] = {}
    infra_counter = 0

    def _get_infra(
        key: tuple[str, ...],
        engine_label: str,
        bg: str,
        stroke: str,
    ) -> _InfraNode:
        nonlocal infra_counter
        if key not in infra_groups:
            infra_counter += 1
            # Build display label with host:port if available
            host_port = _host_port_label(key)
            label = f"{engine_label}{host_port}"
            infra_groups[key] = _InfraNode(
                f"infra_{infra_counter}", label, bg, stroke,
            )
        return infra_groups[key]

    for service in app.services.values():
        sname = simple_name(str(service.name))
        svc_nodes[sname] = _SvcNode(sname)

        # RDBMS blocks
        for block_name, rdbms_block in service.rdbms_blocks.items():
            if rdbms_block._config is not None:
                cfg = rdbms_block.config
                engine_label = str(cfg.engine.canonical_name)
                key: tuple[str, ...] = (engine_label, cfg.host or "", str(cfg.port or ""))
                db_name = cfg.database or str(block_name)
            else:
                engine_label = "PostgreSQL"
                key = (engine_label, sname, str(block_name))
                db_name = str(block_name)
            node = _get_infra(key, engine_label, RDBMS_BG, RDBMS_STROKE)
            node.connections.append((sname, db_name))

        # Cache block
        if service.cache_block is not None:
            if service.cache_block._config is not None:
                cfg_cache = service.cache_block.config
                engine_label = str(cfg_cache.engine.canonical_name)
                key = (engine_label, cfg_cache.host or "", str(cfg_cache.port or ""))
            else:
                engine_label = "Redis"
                key = (engine_label, sname, "cache")
            node = _get_infra(key, engine_label, CACHE_BG, CACHE_STROKE)
            node.connections.append((sname, ""))

        # Pubsub blocks
        for block_name, pubsub_block in service.pubsub_blocks.items():
            if pubsub_block._config is not None:
                cfg_mq = pubsub_block.config
                engine_label = str(cfg_mq.engine.canonical_name)
                brokers_str = _brokers_identity(cfg_mq.brokers)
                key = (engine_label, brokers_str, str(cfg_mq.port or ""))
            else:
                engine_label = "MQ"
                key = (engine_label, sname, str(block_name))
            node = _get_infra(key, engine_label, MQ_BG, MQ_STROKE)
            node.connections.append((sname, str(block_name)))

        # NoSQL blocks
        for block_name, nosql_block in service.nosql_blocks.items():
            if nosql_block._config is not None:
                cfg_nosql = nosql_block.config
                engine_label = str(cfg_nosql.engine.canonical_name)
                key = (engine_label, str(cfg_nosql.host or ""), str(cfg_nosql.port or ""))
            else:
                engine_label = "NoSQL"
                key = (engine_label, sname, str(block_name))
            node = _get_infra(key, engine_label, NOSQL_BG, NOSQL_STROKE)
            node.connections.append((sname, str(block_name)))

        # Storage blocks
        for block_name in service.storage_blocks:
            # Storage is always per-service
            infra_counter += 1
            storage_key: tuple[str, ...] = ("Storage", sname, str(block_name))
            node = _get_infra(
                storage_key, f"Storage: {block_name}", STORAGE_BG, STORAGE_STROKE,
            )
            node.connections.append((sname, ""))

    # HTTP edges
    raw_edges = service_dependency_edges(app)
    http_edges: list[_HttpEdge] = []
    for from_name, to_name in raw_edges:
        from_simple = simple_name(from_name)
        to_simple = simple_name(to_name)
        if from_simple in svc_nodes and to_simple in svc_nodes:
            http_edges.append(_HttpEdge(from_simple, to_simple))

    return list(svc_nodes.values()), list(infra_groups.values()), http_edges


def _host_port_label(key: tuple[str, ...]) -> str:
    """Extract host:port suffix for display. Returns '' or ' (host:port)'."""
    if len(key) < 3:
        return ""
    host = key[1]
    port = key[2]
    if not host or (host != "localhost" and "." not in host and ":" not in host):
        return ""
    if ":" in host:
        return f" ({host})"
    if port:
        return f" ({host}:{port})"
    return f" ({host})"


# ── Layout ──


def _layout(
    svc_nodes: list[_SvcNode],
    infra_nodes: list[_InfraNode],
) -> tuple[float, float, float]:
    """Position service and infra nodes. Returns (width, height, infra_y)."""
    if not svc_nodes:
        return 400.0, 200.0, 100.0

    # Service tier: arrange in rows
    per_row = min(SVC_MAX_PER_ROW, len(svc_nodes))
    num_rows = (len(svc_nodes) + per_row - 1) // per_row

    svc_tier_width = per_row * SVC_NODE_W + max(0, per_row - 1) * SVC_H_GAP

    # Infra tier width
    infra_per_row = min(len(infra_nodes), max(4, per_row))
    infra_tier_width = infra_per_row * INFRA_NODE_W + max(0, infra_per_row - 1) * INFRA_H_GAP

    total_width = SVG_PAD * 2 + max(svc_tier_width, infra_tier_width)
    total_width = max(total_width, 500.0)

    # Position service nodes
    y = SVG_PAD + TITLE_AREA_H
    for row_idx in range(num_rows):
        start = row_idx * per_row
        end = min(start + per_row, len(svc_nodes))
        row_nodes = svc_nodes[start:end]
        row_width = len(row_nodes) * SVC_NODE_W + max(0, len(row_nodes) - 1) * SVC_H_GAP
        x_start = (total_width - row_width) / 2

        for i, node in enumerate(row_nodes):
            node.x = x_start + i * (SVC_NODE_W + SVC_H_GAP)
            node.y = y

        y += SVC_NODE_H + SVC_V_GAP

    svc_bottom = y - SVC_V_GAP + SVC_NODE_H

    # Position infra nodes
    infra_y = svc_bottom + TIER_GAP
    infra_rows = (len(infra_nodes) + infra_per_row - 1) // infra_per_row if infra_nodes else 0

    for row_idx in range(infra_rows):
        start = row_idx * infra_per_row
        end = min(start + infra_per_row, len(infra_nodes))
        row_nodes = infra_nodes[start:end]
        row_width = len(row_nodes) * INFRA_NODE_W + max(0, len(row_nodes) - 1) * INFRA_H_GAP
        x_start = (total_width - row_width) / 2

        for i, node in enumerate(row_nodes):
            node.x = x_start + i * (INFRA_NODE_W + INFRA_H_GAP)
            node.y = infra_y + row_idx * (INFRA_NODE_H + SVC_V_GAP)

    infra_bottom = infra_y
    if infra_nodes:
        infra_bottom = max(n.y + INFRA_NODE_H for n in infra_nodes)

    total_height = infra_bottom + SVG_PAD
    return total_width, max(total_height, 200.0), infra_y


# ── SVG rendering ──


def _svg_styles() -> str:
    return f"""<style>
  .svc-label {{ font: bold 11px {FONT}; fill: {HEADER_FG}; }}
  .infra-label {{ font: bold 11px {FONT}; fill: #1f2328; }}
  .section-label {{ font: bold 10px {FONT}; fill: {TEXT_SECONDARY}; text-transform: uppercase; letter-spacing: 0.5px; }}
</style>"""


def _render_svc_node(node: _SvcNode) -> str:
    cx = node.x + SVC_NODE_W / 2
    cy = node.y + SVC_NODE_H / 2 + 4
    return (
        f'<rect x="{node.x}" y="{node.y}" width="{SVC_NODE_W}" '
        f'height="{SVC_NODE_H}" rx="{CORNER_R + 2}" '
        f'fill="{HEADER_BG}" stroke="{CARD_STROKE}" stroke-width="1"/>\n'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'class="svc-label">{esc(node.name)}</text>'
    )


def _render_infra_node(node: _InfraNode) -> str:
    cx = node.x + INFRA_NODE_W / 2
    cy = node.y + INFRA_NODE_H / 2 + 4
    return (
        f'<rect x="{node.x}" y="{node.y}" width="{INFRA_NODE_W}" '
        f'height="{INFRA_NODE_H}" rx="{CORNER_R}" '
        f'fill="{node.bg}" stroke="{node.stroke}" stroke-width="1"/>\n'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'class="infra-label">{esc(node.label)}</text>'
    )


def _render_infra_connections(
    infra_nodes: list[_InfraNode],
    svc_map: dict[str, _SvcNode],
) -> str:
    """Render thin lines from services to their infrastructure."""
    parts: list[str] = []
    for infra_node in infra_nodes:
        ix = infra_node.x + INFRA_NODE_W / 2
        iy = infra_node.y

        for svc_name, _label in infra_node.connections:
            svc_node = svc_map.get(svc_name)
            if svc_node is None:
                continue
            sx = svc_node.x + SVC_NODE_W / 2
            sy = svc_node.y + SVC_NODE_H

            parts.append(render_bezier_edge(
                sx, sy, ix, iy,
                stroke=INFRA_LINE_COLOR,
                stroke_width=1.0,
            ))

    return "\n".join(parts)


def _render_http_arrows(
    edges: list[_HttpEdge],
    svc_map: dict[str, _SvcNode],
) -> str:
    """Render HTTP dependency arrows between service nodes."""
    parts: list[str] = []
    for edge in edges:
        consumer = svc_map.get(edge.consumer)
        provider = svc_map.get(edge.provider)
        if consumer is None or provider is None:
            continue

        # Determine anchor points based on relative position
        if abs(consumer.y - provider.y) > SVC_NODE_H / 2:
            # Different rows: connect bottom/top
            if consumer.y > provider.y:
                sx = consumer.x + SVC_NODE_W / 2
                sy = consumer.y
                tx = provider.x + SVC_NODE_W / 2
                ty = provider.y + SVC_NODE_H
            else:
                sx = consumer.x + SVC_NODE_W / 2
                sy = consumer.y + SVC_NODE_H
                tx = provider.x + SVC_NODE_W / 2
                ty = provider.y
        else:
            # Same row: connect sides
            if consumer.x < provider.x:
                sx = consumer.x + SVC_NODE_W
                sy = consumer.y + SVC_NODE_H / 2
                tx = provider.x
                ty = provider.y + SVC_NODE_H / 2
            else:
                sx = consumer.x
                sy = consumer.y + SVC_NODE_H / 2
                tx = provider.x + SVC_NODE_W
                ty = provider.y + SVC_NODE_H / 2

        parts.append(render_bezier_edge(
            sx, sy, tx, ty,
            stroke=HTTP_ARROW_COLOR,
            stroke_width=1.0,
            marker_end="http-arrow",
        ))

    return "\n".join(parts)


# ── Public API ──


def build_service_map_svg(app: Application) -> str:
    """Build an SVG service map with shared infrastructure.

    Shows services as dark rounded boxes in the top tier,
    infrastructure as colored boxes in the bottom tier,
    with connection lines and HTTP dependency arrows.

    Args:
        app: Fully resolved Application model.

    Returns:
        SVG XML string.
    """
    svc_nodes, infra_nodes, http_edges = _collect_data(app)

    if not svc_nodes:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 60">'
            '<text x="20" y="30" font-size="14">'
            'No services found.</text></svg>'
        )

    width, height, infra_y = _layout(svc_nodes, infra_nodes)
    svc_map = {n.name: n for n in svc_nodes}

    parts: list[str] = [
        svg_open(width, height),
        _svg_styles(),
        f"<defs>{arrow_marker_def('http-arrow', HTTP_ARROW_COLOR)}</defs>",
        svg_background(width, height),
        svg_title(SVG_PAD, SVG_PAD + 16, "Service Map", "Services and shared infrastructure"),
    ]

    # Section labels
    svc_label_y = SVG_PAD + TITLE_AREA_H - 10
    parts.append(
        f'<text x="{SVG_PAD}" y="{svc_label_y}" '
        f'class="section-label">Services</text>'
    )
    if infra_nodes:
        parts.append(
            f'<text x="{SVG_PAD}" y="{infra_y - 10}" '
            f'class="section-label">Infrastructure</text>'
        )

    # Infrastructure connection lines (drawn first, below everything)
    parts.append(_render_infra_connections(infra_nodes, svc_map))

    # HTTP arrows
    parts.append(_render_http_arrows(http_edges, svc_map))

    # Service nodes
    for node in svc_nodes:
        parts.append(_render_svc_node(node))

    # Infrastructure nodes
    for node in infra_nodes:
        parts.append(_render_infra_node(node))

    parts.append("</svg>")

    logger.info(
        "service_map_built services=%d infra_nodes=%d http_edges=%d",
        len(svc_nodes), len(infra_nodes), len(http_edges),
    )

    return "\n".join(parts)
