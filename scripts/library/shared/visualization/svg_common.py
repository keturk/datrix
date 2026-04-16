"""Shared SVG building blocks for Datrix visualization diagrams.

Provides colors, fonts, escape helpers, and reusable SVG fragment
renderers so that individual diagram builders stay DRY.
"""

from __future__ import annotations

import html

from datrix_common.paths import ServicePaths

# ── Colors (GitHub-inspired palette) ──

HEADER_BG = "#24292f"
HEADER_FG = "#ffffff"
CARD_BG = "#ffffff"
CARD_STROKE = "#d0d7de"
CARD_SHADOW = "rgba(0,0,0,0.08)"
TEXT_PRIMARY = "#1f2328"
TEXT_SECONDARY = "#656d76"
TEXT_MUTED = "#8b949e"
ACCENT_RED = "#cf222e"
ACCENT_BLUE = "#0550ae"
ACCENT_GREEN = "#116329"
DIVIDER_COLOR = "#d8dee4"

# ── Typography ──

FONT = '"Segoe UI", system-ui, -apple-system, sans-serif'

# ── Layout defaults ──

SVG_PAD = 28
CORNER_R = 6


# ── Text escaping ──


def esc(text: str) -> str:
    """Escape text for SVG/XML content."""
    return html.escape(text, quote=True)


# ── Service name helper ──


def simple_name(service_name: str) -> str:
    """Extract short service name from a qualified name.

    Example: ``"curvaero.AviationDataService"`` → ``"AviationDataService"``
    """
    return ServicePaths(service_name).simple_name


# ── SVG document helpers ──


def svg_open(width: float, height: float) -> str:
    """Return the opening ``<svg>`` tag with viewBox."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" width="100%">'
    )


def svg_background(width: float, height: float) -> str:
    """Return a white background rect covering the full SVG."""
    return f'<rect width="{width:.0f}" height="{height:.0f}" fill="white"/>'


def svg_title(
    x: float,
    y: float,
    title: str,
    subtitle: str = "",
) -> str:
    """Render a title and optional subtitle."""
    parts: list[str] = [
        f'<text x="{x}" y="{y}" '
        f'style="font: bold 16px {FONT}; fill: {TEXT_PRIMARY};">'
        f'{esc(title)}</text>',
    ]
    if subtitle:
        parts.append(
            f'<text x="{x}" y="{y + 16}" '
            f'style="font: 11px {FONT}; fill: {TEXT_SECONDARY};">'
            f'{esc(subtitle)}</text>'
        )
    return "\n".join(parts)


# ── Reusable defs ──


def shadow_filter_def() -> str:
    """Return a ``<filter>`` for card drop shadows."""
    return (
        f'<filter id="shadow" x="-4%" y="-4%" width="108%" height="112%">'
        f'<feDropShadow dx="0" dy="1" stdDeviation="3" '
        f'flood-color="{CARD_SHADOW}"/></filter>'
    )


def arrow_marker_def(
    marker_id: str,
    fill_color: str,
) -> str:
    """Return a triangle arrowhead ``<marker>``."""
    return (
        f'<marker id="{esc(marker_id)}" viewBox="0 0 10 10" '
        f'refX="9" refY="5" markerWidth="6" markerHeight="6" '
        f'orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{fill_color}"/>'
        f'</marker>'
    )


# ── Card / node rendering fragments ──


def render_card_header(
    x: float,
    y: float,
    width: float,
    header_h: float,
    name: str,
    *,
    bg: str = HEADER_BG,
    fg: str = HEADER_FG,
    corner_r: float = CORNER_R,
    font_size: int = 13,
) -> str:
    """Render the dark header bar of a card (top-rounded, bottom-squared)."""
    return (
        # Rounded-top header rect
        f'<rect x="{x}" y="{y}" width="{width}" '
        f'height="{header_h}" rx="{corner_r}" fill="{bg}"/>\n'
        # Square off bottom corners
        f'<rect x="{x}" y="{y + header_h - corner_r}" '
        f'width="{width}" height="{corner_r}" fill="{bg}"/>\n'
        # Name text
        f'<text x="{x + 12}" y="{y + header_h / 2 + 5}" '
        f'style="font: bold {font_size}px {FONT}; fill: {fg};">'
        f'{esc(name)}</text>'
    )


def render_rounded_box(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fill: str = CARD_BG,
    stroke: str = CARD_STROKE,
    corner_r: float = CORNER_R,
    shadow: bool = False,
) -> str:
    """Render a rounded rectangle (card body, node, etc.)."""
    extra = ' filter="url(#shadow)"' if shadow else ""
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="{corner_r}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="1"{extra}/>'
    )


def render_bezier_edge(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    *,
    stroke: str = TEXT_MUTED,
    stroke_width: float = 1.5,
    dash: str = "",
    marker_end: str = "",
) -> str:
    """Render a cubic bezier from (sx,sy) to (tx,ty).

    Auto-selects vertical or horizontal control points based on
    which axis has the greater delta.
    """
    dx = abs(tx - sx)
    dy = abs(ty - sy)

    if dy >= dx:
        # Vertical orientation
        mid_y = (sy + ty) / 2
        path = (
            f"M {sx:.1f} {sy:.1f} "
            f"C {sx:.1f} {mid_y:.1f} {tx:.1f} {mid_y:.1f} "
            f"{tx:.1f} {ty:.1f}"
        )
    else:
        # Horizontal orientation
        mid_x = (sx + tx) / 2
        path = (
            f"M {sx:.1f} {sy:.1f} "
            f"C {mid_x:.1f} {sy:.1f} {mid_x:.1f} {ty:.1f} "
            f"{tx:.1f} {ty:.1f}"
        )

    style_parts = [
        f'stroke="{stroke}"',
        "fill=\"none\"",
        f'stroke-width="{stroke_width}"',
    ]
    if dash:
        style_parts.append(f'stroke-dasharray="{dash}"')
    if marker_end:
        style_parts.append(f'marker-end="url(#{esc(marker_end)})"')

    return f'<path d="{path}" {" ".join(style_parts)}/>'
