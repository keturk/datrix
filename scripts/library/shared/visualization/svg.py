"""SVG diagram builders for Datrix visualizations.

Produces self-contained SVG that renders in VS Code, GitHub, and browsers.

Diagrams:
- Event flow: vertical service cards with cross-service arrows.
- System context: C4-inspired graph of services and dependencies.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from datrix_common.paths import ServicePaths

from .traversal import all_subscriptions_with_context

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

# ── Layout constants ──

CARD_WIDTH = 660
CARD_PAD_X = 16
CARD_PAD_Y = 12
HEADER_H = 34
ROW_H = 26
SECTION_LABEL_H = 22
CARD_GAP = 44
SVG_PAD = 20
ROUTE_WIDTH = 100
ARROW_STAGGER = 12

# Column positions within a card (relative to card left edge)
COL_EVENT_X = CARD_PAD_X
COL_EVENT_W = 220
COL_ARROW_X = COL_EVENT_X + COL_EVENT_W + 8
COL_HANDLER_X = COL_ARROW_X + 40
COL_HANDLER_W = 220

# Topic container padding (events nested inside topic rect)
TOPIC_PAD_TOP = 4
TOPIC_PAD_BOTTOM = 6
EVENT_INDENT = 8

# ── Colors ──

HEADER_BG = "#24292f"
HEADER_FG = "#ffffff"
CARD_BG = "#ffffff"
CARD_STROKE = "#d0d7de"
TOPIC_BG = "#ddf4ff"
TOPIC_FG = "#0550ae"
TOPIC_STROKE = "#54aeff"
EVENT_BG = "#f6f8fa"
EVENT_FG = "#1f2328"
EVENT_STROKE = "#d0d7de"
SELF_HANDLER_BG = "#dafbe1"
SELF_HANDLER_FG = "#116329"
SELF_HANDLER_STROKE = "#4ac26b"
INCOMING_BG = "#fff8c5"
INCOMING_FG = "#7d4e00"
INCOMING_STROKE = "#d4a72c"
ARROW_SELF_COLOR = "#656d76"
ARROW_CROSS_COLOR = "#cf222e"
ARROW_CROSS_LABEL_COLOR = "#a40e26"
DIVIDER_COLOR = "#d8dee4"
FONT = '"Segoe UI", system-ui, -apple-system, sans-serif'
CORNER_R = 8


# ── Data holders ──


class _EventRow:
    """A published event with optional in-service handler."""

    __slots__ = ("name", "handler_name", "y_center")

    def __init__(self, name: str) -> None:
        self.name = name
        self.handler_name = ""
        self.y_center = 0.0


class _IncomingRow:
    """An incoming cross-service handler."""

    __slots__ = ("event_name", "source_service", "y_center")

    def __init__(self, event_name: str, source_service: str) -> None:
        self.event_name = event_name
        self.source_service = source_service
        self.y_center = 0.0


class _TopicGroup:
    """A topic with its published events."""

    __slots__ = ("name", "events")

    def __init__(self, name: str) -> None:
        self.name = name
        self.events: list[_EventRow] = []


class _ServiceCard:
    """A service card with topics and incoming handlers."""

    __slots__ = ("name", "topics", "incoming", "y_top", "height")

    def __init__(self, name: str) -> None:
        self.name = name
        self.topics: list[_TopicGroup] = []
        self.incoming: list[_IncomingRow] = []
        self.y_top = 0.0
        self.height = 0.0


class _CrossArrow:
    """A cross-service subscription arrow."""

    __slots__ = ("source_service", "event_name", "target_service", "source_y", "target_y")

    def __init__(self, source_service: str, event_name: str, target_service: str) -> None:
        self.source_service = source_service
        self.event_name = event_name
        self.target_service = target_service
        self.source_y = 0.0
        self.target_y = 0.0


# ── Data collection ──


def _simple_name(service_name: str) -> str:
    """Extract simple service name from qualified name."""
    return ServicePaths(service_name).simple_name


def _collect_data(
    app: Application,
) -> tuple[list[_ServiceCard], list[_CrossArrow]]:
    """Collect event flow data from the Application model.

    Returns:
        (service_cards, cross_arrows)
    """
    cards: dict[str, _ServiceCard] = {}
    event_to_service: dict[str, str] = {}

    # Phase 1: Collect published events
    for service in app.services.values():
        sname = _simple_name(str(service.name))
        card = _ServiceCard(sname)

        for pubsub_block in service.pubsub_blocks.values():
            for topic in pubsub_block.topics.values():
                topic_group = _TopicGroup(str(topic.name))
                for event in topic.events.values():
                    ename = str(event.name)
                    topic_group.events.append(_EventRow(ename))
                    event_to_service[ename] = sname
                if topic_group.events:
                    card.topics.append(topic_group)

        if card.topics:
            cards[sname] = card

    # Phase 2: Identify handlers (in-service and cross-service)
    cross_arrows: list[_CrossArrow] = []
    seen_incoming: set[str] = set()

    for service, _block, subscription in all_subscriptions_with_context(app):
        subscriber_name = _simple_name(str(service.name))

        for handler in subscription.handlers:
            raw_event_name = handler.event_name()
            if not raw_event_name:
                continue
            event_name = str(raw_event_name)
            publisher_name = event_to_service.get(event_name)
            if publisher_name is None:
                continue

            if publisher_name == subscriber_name:
                # In-service handler: mark the event row
                card = cards.get(subscriber_name)
                if card is not None:
                    for topic in card.topics:
                        for event_row in topic.events:
                            if event_row.name == event_name and not event_row.handler_name:
                                event_row.handler_name = f"on {event_name}"
                                break
            else:
                # Cross-service handler
                incoming_key = f"{subscriber_name}:{event_name}"
                if incoming_key in seen_incoming:
                    continue
                seen_incoming.add(incoming_key)

                card = cards.get(subscriber_name)
                if card is None:
                    card = _ServiceCard(subscriber_name)
                    cards[subscriber_name] = card
                card.incoming.append(_IncomingRow(event_name, publisher_name))
                cross_arrows.append(
                    _CrossArrow(publisher_name, event_name, subscriber_name)
                )

    return list(cards.values()), cross_arrows


# ── Layout calculation ──


def _calculate_layout(cards: list[_ServiceCard]) -> float:
    """Calculate Y positions for all cards and rows.

    Returns:
        Total SVG height.
    """
    y = SVG_PAD

    for card in cards:
        card.y_top = y
        content_y = y + HEADER_H + CARD_PAD_Y

        for topic in card.topics:
            content_y += TOPIC_PAD_TOP
            content_y += SECTION_LABEL_H
            for event_row in topic.events:
                event_row.y_center = content_y + ROW_H / 2
                content_y += ROW_H
            content_y += TOPIC_PAD_BOTTOM
            content_y += 6

        if card.incoming:
            # Divider + "Subscribes to" label
            content_y += 6
            content_y += SECTION_LABEL_H
            for incoming_row in card.incoming:
                incoming_row.y_center = content_y + ROW_H / 2
                content_y += ROW_H

        content_y += CARD_PAD_Y
        card.height = content_y - card.y_top
        y = content_y + CARD_GAP

    total = y - CARD_GAP + SVG_PAD
    return max(total, 200.0)


# ── SVG rendering ──


def _esc(text: str) -> str:
    """Escape text for SVG/XML."""
    return html.escape(text, quote=True)


def _svg_styles() -> str:
    """Render the <style> block."""
    return f"""<style>
  .header-text {{ font: bold 13px {FONT}; fill: {HEADER_FG}; }}
  .topic-text {{ font: bold 11px {FONT}; fill: {TOPIC_FG}; }}
  .event-text {{ font: 11px {FONT}; fill: {EVENT_FG}; }}
  .handler-text {{ font: 11px {FONT}; fill: {SELF_HANDLER_FG}; }}
  .incoming-text {{ font: 11px {FONT}; fill: {INCOMING_FG}; }}
  .section-label {{ font: bold 10px {FONT}; fill: #656d76; text-transform: uppercase; letter-spacing: 0.5px; }}
  .cross-label {{ font: italic 10px {FONT}; fill: {ARROW_CROSS_LABEL_COLOR}; }}
  .arrow-self {{ stroke: {ARROW_SELF_COLOR}; fill: none; stroke-width: 1.5; marker-end: url(#arrow-self); }}
  .arrow-cross {{ stroke: {ARROW_CROSS_COLOR}; fill: none; stroke-width: 1.5; stroke-dasharray: 6,3; marker-end: url(#arrow-cross); }}
</style>"""


def _svg_defs() -> str:
    """Render arrowhead markers."""
    return f"""<defs>
  <marker id="arrow-self" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{ARROW_SELF_COLOR}"/>
  </marker>
  <marker id="arrow-cross" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{ARROW_CROSS_COLOR}"/>
  </marker>
</defs>"""


def _render_card(card: _ServiceCard, card_x: float) -> str:
    """Render a single service card."""
    parts: list[str] = []

    # Card background
    parts.append(
        f'<rect x="{card_x}" y="{card.y_top}" width="{CARD_WIDTH}" '
        f'height="{card.height}" rx="{CORNER_R}" '
        f'fill="{CARD_BG}" stroke="{CARD_STROKE}" stroke-width="1"/>'
    )

    # Header bar
    parts.append(
        f'<rect x="{card_x}" y="{card.y_top}" width="{CARD_WIDTH}" '
        f'height="{HEADER_H}" rx="{CORNER_R}" fill="{HEADER_BG}"/>'
    )
    # Square off bottom corners of header
    parts.append(
        f'<rect x="{card_x}" y="{card.y_top + HEADER_H - CORNER_R}" '
        f'width="{CARD_WIDTH}" height="{CORNER_R}" fill="{HEADER_BG}"/>'
    )
    # Header text
    parts.append(
        f'<text x="{card_x + CARD_PAD_X}" '
        f'y="{card.y_top + HEADER_H / 2 + 5}" class="header-text">'
        f'{_esc(card.name)}</text>'
    )

    # Published events
    content_y = card.y_top + HEADER_H + CARD_PAD_Y

    for topic in card.topics:
        container_x = card_x + COL_EVENT_X
        container_y = content_y
        n_events = len(topic.events)
        container_h = (
            TOPIC_PAD_TOP + SECTION_LABEL_H + n_events * ROW_H + TOPIC_PAD_BOTTOM
        )

        # Topic container rectangle
        parts.append(
            f'<rect x="{container_x}" y="{container_y}" '
            f'width="{COL_EVENT_W}" height="{container_h}" rx="6" '
            f'fill="{TOPIC_BG}" stroke="{TOPIC_STROKE}" stroke-width="0.5"/>'
        )

        content_y += TOPIC_PAD_TOP

        # Topic name (inside container, at top)
        parts.append(
            f'<text x="{container_x + 10}" y="{content_y + 14}" '
            f'class="topic-text">{_esc(topic.name)}</text>'
        )
        content_y += SECTION_LABEL_H

        event_x = container_x + EVENT_INDENT
        event_w = COL_EVENT_W - EVENT_INDENT * 2

        for event_row in topic.events:
            ey = content_y

            # Event box (nested inside topic container)
            parts.append(
                f'<rect x="{event_x}" y="{ey + 2}" width="{event_w}" '
                f'height="{ROW_H - 4}" rx="4" '
                f'fill="{EVENT_BG}" stroke="{EVENT_STROKE}" stroke-width="0.5"/>'
            )
            parts.append(
                f'<text x="{event_x + 8}" y="{ey + ROW_H / 2 + 4}" '
                f'class="event-text">{_esc(event_row.name)}</text>'
            )

            # In-service handler (if any)
            if event_row.handler_name:
                hx = card_x + COL_HANDLER_X
                # Arrow from event to handler
                arrow_start_x = event_x + event_w
                arrow_end_x = hx
                arrow_y = ey + ROW_H / 2
                parts.append(
                    f'<line x1="{arrow_start_x + 2}" y1="{arrow_y}" '
                    f'x2="{arrow_end_x - 2}" y2="{arrow_y}" class="arrow-self"/>'
                )
                # Handler box
                parts.append(
                    f'<rect x="{hx}" y="{ey + 2}" width="{COL_HANDLER_W}" '
                    f'height="{ROW_H - 4}" rx="4" '
                    f'fill="{SELF_HANDLER_BG}" stroke="{SELF_HANDLER_STROKE}" '
                    f'stroke-width="0.5"/>'
                )
                parts.append(
                    f'<text x="{hx + 8}" y="{ey + ROW_H / 2 + 4}" '
                    f'class="handler-text">{_esc(event_row.handler_name)}</text>'
                )

            content_y += ROW_H

        content_y += TOPIC_PAD_BOTTOM
        content_y += 6

    # Incoming handlers section
    if card.incoming:
        # Divider line
        div_y = content_y + 3
        parts.append(
            f'<line x1="{card_x + CARD_PAD_X}" y1="{div_y}" '
            f'x2="{card_x + CARD_WIDTH - CARD_PAD_X}" y2="{div_y}" '
            f'stroke="{DIVIDER_COLOR}" stroke-width="1" stroke-dasharray="4,3"/>'
        )
        content_y += 6

        # Section label
        parts.append(
            f'<text x="{card_x + CARD_PAD_X}" y="{content_y + 14}" '
            f'class="section-label">Subscribes to</text>'
        )
        content_y += SECTION_LABEL_H

        for incoming_row in card.incoming:
            iy = content_y
            ix = card_x + COL_EVENT_X

            # Incoming handler box
            label = f"on {incoming_row.event_name}"
            parts.append(
                f'<rect x="{ix}" y="{iy + 2}" width="{COL_EVENT_W}" '
                f'height="{ROW_H - 4}" rx="4" '
                f'fill="{INCOMING_BG}" stroke="{INCOMING_STROKE}" '
                f'stroke-width="0.5"/>'
            )
            parts.append(
                f'<text x="{ix + 8}" y="{iy + ROW_H / 2 + 4}" '
                f'class="incoming-text">{_esc(label)}</text>'
            )

            content_y += ROW_H

    return "\n".join(parts)


def _render_cross_arrow(
    arrow: _CrossArrow,
    route_x: float,
    card_x: float,
    stagger_offset: float,
) -> str:
    """Render a cross-service arrow as an SVG path.

    Arrow routes from the source event's right edge through a vertical
    channel and terminates at the target card's right border.
    """
    if arrow.source_y <= 0 or arrow.target_y <= 0:
        return ""

    rx = route_x + stagger_offset
    start_x = card_x + CARD_WIDTH
    end_x = card_x + COL_EVENT_X + COL_EVENT_W
    r = 6.0  # corner radius for the path

    sy = arrow.source_y
    ty = arrow.target_y

    if abs(sy - ty) < r * 2:
        # Nearly same Y — straight horizontal through the channel
        path = (
            f"M {start_x} {sy} "
            f"L {rx} {sy} "
            f"L {rx} {ty} "
            f"L {end_x} {ty}"
        )
    elif sy < ty:
        # Arrow goes downward
        path = (
            f"M {start_x} {sy} "
            f"L {rx - r} {sy} "
            f"Q {rx} {sy} {rx} {sy + r} "
            f"L {rx} {ty - r} "
            f"Q {rx} {ty} {rx - r} {ty} "
            f"L {end_x} {ty}"
        )
    else:
        # Arrow goes upward
        path = (
            f"M {start_x} {sy} "
            f"L {rx - r} {sy} "
            f"Q {rx} {sy} {rx} {sy - r} "
            f"L {rx} {ty + r} "
            f"Q {rx} {ty} {rx - r} {ty} "
            f"L {end_x} {ty}"
        )

    # Combined label: ServiceName.EventName near the arrow's target endpoint
    source_label = f"{arrow.source_service}.{arrow.event_name}"

    return (
        f'<path d="{path}" class="arrow-cross"/>\n'
        f'<text x="{end_x + 4}" y="{ty - 6}" class="cross-label">'
        f'{_esc(source_label)}</text>'
    )


# ── Public API ──


def build_event_flow_svg(app: Application) -> str:
    """Build an SVG event flow diagram.

    Produces a self-contained SVG string showing service cards stacked
    vertically with cross-service arrows routed through a right channel.

    Args:
        app: Fully resolved Application model.

    Returns:
        SVG XML string.
    """
    cards, cross_arrows = _collect_data(app)

    if not cards:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 60"><text x="20" y="30" font-size="14">No event flows found.</text></svg>'

    total_height = _calculate_layout(cards)
    card_x = SVG_PAD

    # Width depends on how many cross arrows need staggering
    cross_arrow_count = len(cross_arrows)
    route_channel_width = ROUTE_WIDTH + max(0, cross_arrow_count - 1) * ARROW_STAGGER + SVG_PAD
    total_width = SVG_PAD + CARD_WIDTH + route_channel_width

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {total_width:.0f} {total_height:.0f}">'
    )
    parts.append(_svg_styles())
    parts.append(_svg_defs())

    # White background
    parts.append(
        f'<rect width="{total_width:.0f}" height="{total_height:.0f}" fill="white"/>'
    )

    # Render service cards
    for card in cards:
        parts.append(_render_card(card, card_x))

    # Resolve arrow Y positions from source events
    card_map: dict[str, _ServiceCard] = {c.name: c for c in cards}
    for arrow in cross_arrows:
        source_card = card_map.get(arrow.source_service)
        target_card = card_map.get(arrow.target_service)
        if source_card is None or target_card is None:
            continue
        for topic in source_card.topics:
            for event_row in topic.events:
                if event_row.name == arrow.event_name:
                    arrow.source_y = event_row.y_center
                    break
        for incoming in target_card.incoming:
            if incoming.event_name == arrow.event_name:
                arrow.target_y = incoming.y_center
                break

    # Render cross-service arrows (staggered to avoid overlap)
    route_base_x = card_x + CARD_WIDTH + SVG_PAD
    for i, arrow in enumerate(cross_arrows):
        stagger = i * ARROW_STAGGER
        parts.append(
            _render_cross_arrow(arrow, route_base_x, card_x, stagger)
        )

    parts.append("</svg>")
    return "\n".join(parts)

