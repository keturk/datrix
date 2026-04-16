"""SVG data store topology builder.

Produces a grid of service cards, each listing its data stores
(RDBMS, NoSQL, cache, MQ, storage, jobs) with color-coded type
indicators. Each service is an isolated card — no cross-service
connections.

Renders in GitHub, VS Code, and browsers without external dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .svg_common import (
    CARD_BG,
    CARD_SHADOW,
    CARD_STROKE,
    CORNER_R,
    FONT,
    HEADER_BG,
    HEADER_FG,
    SVG_PAD,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    esc,
    render_card_header,
    render_rounded_box,
    shadow_filter_def,
    simple_name,
    svg_background,
    svg_open,
    svg_title,
)

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

logger = logging.getLogger(__name__)

# ── Layout constants ──

CARD_W = 280
CARD_PAD_X = 14
HEADER_H = 32
ITEM_ROW_H = 24
ITEM_PAD_Y = 8
H_GAP = 24
V_GAP = 24
TITLE_AREA_H = 48
CARDS_PER_ROW = 4

# ── Store type styling ──

STORE_STYLES: dict[str, tuple[str, str]] = {
    # type_key → (dot_color, label_prefix)
    "rdbms": ("#0550ae", ""),
    "nosql": ("#8250df", ""),
    "cache": ("#116329", ""),
    "mq": ("#7d4e00", ""),
    "storage": ("#0e8a16", ""),
    "jobs": ("#57606a", "Jobs"),
}

DOT_RADIUS = 4


# ── Data holders ──


class _StoreItem:
    """A data store entry inside a service card."""

    __slots__ = ("label", "store_type")

    def __init__(self, label: str, store_type: str) -> None:
        self.label = label
        self.store_type = store_type


class _ServiceCard:
    """A service card with its data stores."""

    __slots__ = ("name", "items", "x", "y", "height")

    def __init__(self, name: str, items: list[_StoreItem]) -> None:
        self.name = name
        self.items = items
        self.x = 0.0
        self.y = 0.0
        content_h = max(len(items) * ITEM_ROW_H, ITEM_ROW_H)
        self.height = float(HEADER_H + ITEM_PAD_Y * 2 + content_h)


# ── Data collection ──


def _collect_data(app: Application) -> list[_ServiceCard]:
    """Collect per-service data store listings."""
    cards: list[_ServiceCard] = []

    for service in app.services.values():
        sname = simple_name(str(service.name))
        items: list[_StoreItem] = []

        # RDBMS blocks
        for block_name, rdbms_block in service.rdbms_blocks.items():
            engine_label = "PostgreSQL"
            if getattr(rdbms_block, "_config", None) is not None:
                engine_label = str(rdbms_block.config.engine.canonical_name)
            entity_count = len(rdbms_block.entities)
            items.append(_StoreItem(
                f"{block_name} / {engine_label} ({entity_count} entities)",
                "rdbms",
            ))

        # NoSQL blocks
        for block_name in service.nosql_blocks:
            items.append(_StoreItem(f"{block_name} / NoSQL", "nosql"))

        # Cache block
        if service.cache_block is not None:
            engine_label = "Redis"
            if getattr(service.cache_block, "_config", None) is not None:
                engine_label = str(service.cache_block.config.engine.canonical_name)
            items.append(_StoreItem(engine_label, "cache"))

        # Pubsub blocks
        for block_name in service.pubsub_blocks:
            items.append(_StoreItem(f"{block_name} / MQ", "mq"))

        # Storage blocks
        for block_name in service.storage_blocks:
            items.append(_StoreItem(f"{block_name} / Storage", "storage"))

        # Jobs block
        if service.jobs_block is not None:
            items.append(_StoreItem("Jobs", "jobs"))

        if items:
            cards.append(_ServiceCard(sname, items))

    return cards


# ── Layout ──


def _layout_cards(cards: list[_ServiceCard]) -> tuple[float, float]:
    """Arrange cards in a grid. Returns (total_width, total_height)."""
    if not cards:
        return 400.0, 200.0

    per_row = min(CARDS_PER_ROW, len(cards))
    total_width = SVG_PAD * 2 + per_row * CARD_W + max(0, per_row - 1) * H_GAP
    total_width = max(total_width, 400.0)

    num_rows = (len(cards) + per_row - 1) // per_row
    y = SVG_PAD + TITLE_AREA_H

    for row_idx in range(num_rows):
        start = row_idx * per_row
        end = min(start + per_row, len(cards))
        row_cards = cards[start:end]

        row_width = len(row_cards) * CARD_W + max(0, len(row_cards) - 1) * H_GAP
        x_start = (total_width - row_width) / 2

        max_height = 0.0
        for i, card in enumerate(row_cards):
            card.x = x_start + i * (CARD_W + H_GAP)
            card.y = y
            max_height = max(max_height, card.height)

        y += max_height + V_GAP

    total_height = y - V_GAP + SVG_PAD
    return total_width, max(total_height, 200.0)


# ── SVG rendering ──


def _svg_styles() -> str:
    return f"""<style>
  .store-label {{ font: 11px {FONT}; fill: {TEXT_PRIMARY}; }}
</style>"""


def _render_card(card: _ServiceCard) -> str:
    """Render a service card with its data store items."""
    parts: list[str] = []

    # Card body with shadow
    parts.append(render_rounded_box(
        card.x, card.y, CARD_W, card.height,
        shadow=True,
    ))

    # Header
    parts.append(render_card_header(
        card.x, card.y, CARD_W, HEADER_H, card.name,
    ))

    # Store items
    item_y = card.y + HEADER_H + ITEM_PAD_Y

    for item in card.items:
        iy_text = item_y + ITEM_ROW_H / 2 + 4
        dot_color, _ = STORE_STYLES.get(item.store_type, ("#57606a", ""))

        # Color dot
        dot_cx = card.x + CARD_PAD_X + DOT_RADIUS
        dot_cy = item_y + ITEM_ROW_H / 2
        parts.append(
            f'<circle cx="{dot_cx}" cy="{dot_cy}" r="{DOT_RADIUS}" '
            f'fill="{dot_color}"/>'
        )

        # Label
        label_x = dot_cx + DOT_RADIUS + 8
        parts.append(
            f'<text x="{label_x}" y="{iy_text}" '
            f'class="store-label">{esc(item.label)}</text>'
        )

        # Divider
        if item is not card.items[-1]:
            div_y = item_y + ITEM_ROW_H
            parts.append(
                f'<line x1="{card.x + CARD_PAD_X}" y1="{div_y}" '
                f'x2="{card.x + CARD_W - CARD_PAD_X}" y2="{div_y}" '
                f'stroke="#f0f0f0" stroke-width="0.5"/>'
            )

        item_y += ITEM_ROW_H

    return "\n".join(parts)


# ── Public API ──


def build_infrastructure_svg(app: Application) -> str:
    """Build an SVG data store topology diagram.

    Shows each service as a card listing its data stores with
    color-coded type indicators, arranged in a grid.

    Args:
        app: Fully resolved Application model.

    Returns:
        SVG XML string.
    """
    cards = _collect_data(app)

    if not cards:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 60" '
            'width="100%"><text x="20" y="30" font-size="14">'
            'No data stores found.</text></svg>'
        )

    width, height = _layout_cards(cards)

    parts: list[str] = [
        svg_open(width, height),
        _svg_styles(),
        f"<defs>{shadow_filter_def()}</defs>",
        svg_background(width, height),
        svg_title(SVG_PAD, SVG_PAD + 16, "Data Store Topology"),
    ]

    for card in cards:
        parts.append(_render_card(card))

    parts.append("</svg>")

    logger.info(
        "infrastructure_built services=%d",
        len(cards),
    )

    return "\n".join(parts)
