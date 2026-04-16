"""SVG CQRS data flow builder.

Produces a left-to-right pipeline diagram showing the CQRS data flow:
Commands → Events → Projections → Views ← Queries.

Each column contains vertically stacked items, connected by horizontal
arrows. If multiple services have CQRS blocks, each gets its own
titled section.

Renders in GitHub, VS Code, and browsers without external dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .svg_common import (
    CARD_BG,
    CARD_STROKE,
    CORNER_R,
    FONT,
    SVG_PAD,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    arrow_marker_def,
    esc,
    simple_name,
    svg_background,
    svg_open,
    svg_title,
)
from .traversal import all_cqrs_with_service

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

logger = logging.getLogger(__name__)

# ── Layout constants ──

ITEM_W = 160
ITEM_H = 30
COL_GAP = 40
ROW_GAP = 12
SECTION_GAP = 50
TITLE_AREA_H = 48
SERVICE_LABEL_H = 28

# ── Colors per column ──

CMD_BG = "#f6f8fa"
CMD_STROKE = "#d0d7de"
CMD_FG = TEXT_PRIMARY

EVENT_BG = "#ddf4ff"
EVENT_STROKE = "#54aeff"
EVENT_FG = "#0550ae"

PROJ_BG = "#fff8c5"
PROJ_STROKE = "#d4a72c"
PROJ_FG = "#7d4e00"

VIEW_BG = "#dafbe1"
VIEW_STROKE = "#4ac26b"
VIEW_FG = "#116329"

QUERY_BG = "#f6f8fa"
QUERY_STROKE = "#d0d7de"
QUERY_FG = TEXT_PRIMARY

ARROW_COLOR = "#57606a"

COLUMN_STYLES: list[tuple[str, str, str, str]] = [
    # (column_label, bg, stroke, fg)
    ("Commands", CMD_BG, CMD_STROKE, CMD_FG),
    ("Events", EVENT_BG, EVENT_STROKE, EVENT_FG),
    ("Projections", PROJ_BG, PROJ_STROKE, PROJ_FG),
    ("Views", VIEW_BG, VIEW_STROKE, VIEW_FG),
    ("Queries", QUERY_BG, QUERY_STROKE, QUERY_FG),
]


# ── Data holders ──


class _CqrsItem:
    """A single item (command, event, projection, view, or query)."""

    __slots__ = ("name", "col", "x", "y")

    def __init__(self, name: str, col: int) -> None:
        self.name = name
        self.col = col  # 0=commands, 1=events, 2=projections, 3=views, 4=queries
        self.x = 0.0
        self.y = 0.0


class _CqrsArrow:
    """A directed arrow between two items."""

    __slots__ = ("source_name", "source_col", "target_name", "target_col")

    def __init__(
        self, source_name: str, source_col: int,
        target_name: str, target_col: int,
    ) -> None:
        self.source_name = source_name
        self.source_col = source_col
        self.target_name = target_name
        self.target_col = target_col


class _CqrsSection:
    """A per-service CQRS section."""

    __slots__ = ("service_name", "items", "arrows", "y_offset", "height")

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.items: list[_CqrsItem] = []
        self.arrows: list[_CqrsArrow] = []
        self.y_offset = 0.0
        self.height = 0.0


# ── Data collection ──


def _collect_data(app: Application) -> list[_CqrsSection]:
    """Collect CQRS data for all services with CQRS blocks."""
    sections: list[_CqrsSection] = []

    for service, cqrs_block in all_cqrs_with_service(app):
        sname = simple_name(str(service.name))
        section = _CqrsSection(sname)

        # Commands (col 0)
        for cmd_name in cqrs_block.commands:
            section.items.append(_CqrsItem(str(cmd_name), 0))

        # Views (col 3)
        for view_name in cqrs_block.views:
            section.items.append(_CqrsItem(str(view_name), 3))

        # Queries (col 4) — link to views
        for query_name in cqrs_block.queries:
            section.items.append(_CqrsItem(str(query_name), 4))
            # Heuristic: query → all views in this block
            for view_name in cqrs_block.views:
                section.arrows.append(_CqrsArrow(
                    str(query_name), 4, str(view_name), 3,
                ))

        # Projections (col 2) — link events → projections → views
        for proj_name, projection in cqrs_block.projections.items():
            section.items.append(_CqrsItem(str(proj_name), 2))

            # Events → projection
            for raw_event_name in projection.handled_event_names():
                event_name = str(raw_event_name)
                # Add event item (col 1) if not already present
                existing_events = {
                    i.name for i in section.items if i.col == 1
                }
                if event_name not in existing_events:
                    section.items.append(_CqrsItem(event_name, 1))
                section.arrows.append(_CqrsArrow(
                    event_name, 1, str(proj_name), 2,
                ))

            # Projection → views
            for raw_view_name in projection.target_view_names():
                section.arrows.append(_CqrsArrow(
                    str(proj_name), 2, str(raw_view_name), 3,
                ))

        if section.items:
            sections.append(section)

    return sections


# ── Layout ──


def _layout_sections(sections: list[_CqrsSection]) -> tuple[float, float]:
    """Position items in column layout for each section.

    Returns (total_width, total_height).
    """
    num_cols = 5
    total_col_width = num_cols * ITEM_W + (num_cols - 1) * COL_GAP
    total_width = SVG_PAD * 2 + total_col_width
    total_width = max(total_width, 400.0)

    y = SVG_PAD + TITLE_AREA_H

    for section in sections:
        section.y_offset = y
        y += SERVICE_LABEL_H

        # Group items by column
        by_col: dict[int, list[_CqrsItem]] = {}
        for item in section.items:
            by_col.setdefault(item.col, []).append(item)

        # Find tallest column
        max_items = max(
            (len(by_col.get(c, [])) for c in range(num_cols)),
            default=0,
        )
        section_content_h = max(max_items * (ITEM_H + ROW_GAP) - ROW_GAP, ITEM_H)

        # Position items
        for col_idx in range(num_cols):
            col_items = by_col.get(col_idx, [])
            col_x = SVG_PAD + col_idx * (ITEM_W + COL_GAP)
            col_y = y

            for item in col_items:
                item.x = col_x
                item.y = col_y
                col_y += ITEM_H + ROW_GAP

        section.height = SERVICE_LABEL_H + section_content_h
        y += section_content_h + SECTION_GAP

    total_height = y - SECTION_GAP + SVG_PAD
    return total_width, max(total_height, 200.0)


# ── SVG rendering ──


def _svg_styles() -> str:
    return f"""<style>
  .item-text {{ font: 11px {FONT}; }}
  .col-label {{ font: bold 10px {FONT}; fill: {TEXT_SECONDARY}; text-transform: uppercase; letter-spacing: 0.5px; }}
  .svc-label {{ font: bold 13px {FONT}; fill: {TEXT_PRIMARY}; }}
</style>"""


def _render_column_labels(y: float) -> str:
    """Render column header labels at the given Y position."""
    parts: list[str] = []
    for col_idx, (label, _bg, _stroke, _fg) in enumerate(COLUMN_STYLES):
        x = SVG_PAD + col_idx * (ITEM_W + COL_GAP) + ITEM_W / 2
        parts.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" '
            f'class="col-label">{esc(label)}</text>'
        )
    return "\n".join(parts)


def _render_item(item: _CqrsItem) -> str:
    """Render a CQRS item as a colored rounded box."""
    _label, bg, stroke, fg = COLUMN_STYLES[item.col]
    cx = item.x + ITEM_W / 2
    cy = item.y + ITEM_H / 2 + 4
    return (
        f'<rect x="{item.x}" y="{item.y}" width="{ITEM_W}" '
        f'height="{ITEM_H}" rx="{CORNER_R}" '
        f'fill="{bg}" stroke="{stroke}" stroke-width="1"/>\n'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'style="fill: {fg};" class="item-text">{esc(item.name)}</text>'
    )


def _render_arrow(
    arrow: _CqrsArrow,
    item_map: dict[tuple[str, int], _CqrsItem],
) -> str:
    """Render an arrow between two CQRS items."""
    source = item_map.get((arrow.source_name, arrow.source_col))
    target = item_map.get((arrow.target_name, arrow.target_col))
    if source is None or target is None:
        return ""

    if source.col < target.col:
        # Left-to-right: right edge of source → left edge of target
        sx = source.x + ITEM_W
        sy = source.y + ITEM_H / 2
        tx = target.x
        ty = target.y + ITEM_H / 2
    else:
        # Right-to-left: left edge of source → right edge of target
        sx = source.x
        sy = source.y + ITEM_H / 2
        tx = target.x + ITEM_W
        ty = target.y + ITEM_H / 2

    # Horizontal arrow with slight vertical curve
    mid_x = (sx + tx) / 2
    path = (
        f"M {sx:.1f} {sy:.1f} "
        f"C {mid_x:.1f} {sy:.1f} {mid_x:.1f} {ty:.1f} "
        f"{tx:.1f} {ty:.1f}"
    )

    return (
        f'<path d="{path}" stroke="{ARROW_COLOR}" fill="none" '
        f'stroke-width="1.5" marker-end="url(#cqrs-arrow)"/>'
    )


# ── Public API ──


def build_cqrs_svg(app: Application) -> str | None:
    """Build an SVG CQRS data flow diagram.

    Shows the CQRS pipeline (commands → events → projections → views ← queries)
    for each service that has a CQRS block.

    Args:
        app: Fully resolved Application model.

    Returns:
        SVG XML string, or None if no services have CQRS blocks.
    """
    sections = _collect_data(app)

    if not sections:
        return None

    width, height = _layout_sections(sections)

    parts: list[str] = [
        svg_open(width, height),
        _svg_styles(),
        f"<defs>{arrow_marker_def('cqrs-arrow', ARROW_COLOR)}</defs>",
        svg_background(width, height),
        svg_title(SVG_PAD, SVG_PAD + 16, "CQRS Data Flow"),
    ]

    # Column headers (static, at top of diagram below title)
    parts.append(_render_column_labels(SVG_PAD + TITLE_AREA_H - 6))

    for section in sections:
        # Section service label
        parts.append(
            f'<text x="{SVG_PAD}" y="{section.y_offset + 16}" '
            f'class="svc-label">{esc(section.service_name)}</text>'
        )

        # Build item lookup
        item_map: dict[tuple[str, int], _CqrsItem] = {
            (i.name, i.col): i for i in section.items
        }

        # Arrows first (below items)
        for arrow in section.arrows:
            arrow_svg = _render_arrow(arrow, item_map)
            if arrow_svg:
                parts.append(arrow_svg)

        # Items
        for item in section.items:
            parts.append(_render_item(item))

    parts.append("</svg>")

    svc_count = len(sections)
    logger.info("cqrs_built services=%d", svc_count)

    return "\n".join(parts)
