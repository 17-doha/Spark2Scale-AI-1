"""
Render a Business Model Canvas dict to a PNG using the classic Osterwalder
9-block layout.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")  # headless — no display needed
import matplotlib.patches as patches
import matplotlib.pyplot as plt


# Layout on a 10-wide × 6-tall grid (origin bottom-left, matplotlib convention).
# Each tuple: (x, y, width, height, display_title, canvas_key).
BOXES = [
    (0, 2, 2, 4, "Key Partnerships",        "key_partnerships"),
    (2, 4, 2, 2, "Key Activities",          "key_activities"),
    (2, 2, 2, 2, "Key Resources",           "key_resources"),
    (4, 2, 2, 4, "Value Proposition",       "value_proposition"),
    (6, 4, 2, 2, "Customer Relationships",  "customer_relationships"),
    (6, 2, 2, 2, "Channels",                "channels"),
    (8, 2, 2, 4, "Customer Segments",       "customer_segments"),
    (0, 0, 5, 2, "Cost Structure",          "cost_structure"),
    (5, 0, 5, 2, "Revenue Streams",         "revenue_streams"),
]

# Shared Spark2Scale palette (mirrors app/utils/pdf_generator.py).
COLOR_PRIMARY = "#576238"   # Olive
COLOR_ACCENT = "#ffd95d"    # Mustard
COLOR_BG = "#F0EADC"        # Cream
COLOR_TEXT = "#2c3e50"      # Dark Slate

TITLE_BG = COLOR_PRIMARY
TITLE_FG = COLOR_ACCENT
BODY_BG = "#FAF6EC"         # slightly lighter cream so blocks pop off the page
BORDER = COLOR_PRIMARY
BULLET_FG = COLOR_TEXT
PAGE_BG = COLOR_BG


def _wrap_bullets(items: List[str], width_chars: int) -> str:
    if not items:
        return "(no data)"
    lines: List[str] = []
    for item in items:
        wrapped = textwrap.wrap(str(item), width=width_chars) or [""]
        lines.append(f"• {wrapped[0]}")
        lines.extend(f"   {w}" for w in wrapped[1:])
    return "\n".join(lines)


def render_bmc_image(canvas: Dict[str, List[str]], idea_name: str, out_path: Path) -> Path:
    """Draw the BMC grid and save as PNG. Returns the path written."""
    # Reserve a header band of HEADER_H units above the canvas (y = 6 .. 6 + HEADER_H).
    HEADER_H = 1.2
    CANVAS_TOP = 6.0
    fig, ax = plt.subplots(figsize=(20, 13))
    fig.patch.set_facecolor(PAGE_BG)
    ax.set_facecolor(PAGE_BG)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, CANVAS_TOP + HEADER_H)
    ax.set_aspect("equal")
    ax.axis("off")

    # Heading — two centered lines: "Business Model Canvas", then the idea name.
    pretty_idea = " ".join(w.capitalize() for w in (idea_name or "").split())
    header_center_y = CANVAS_TOP + HEADER_H / 2
    ax.text(
        5, header_center_y + 0.30,
        "Business Model Canvas",
        ha="center", va="center",
        fontsize=22, fontweight="bold",
        color=COLOR_PRIMARY,
    )
    ax.text(
        5, header_center_y - 0.25,
        pretty_idea,
        ha="center", va="center",
        fontsize=15, fontweight="bold",
        color=COLOR_TEXT,
    )

    for x, y, w, h, title, key in BOXES:
        # Outer rectangle
        ax.add_patch(patches.Rectangle(
            (x, y), w, h,
            linewidth=1.4, edgecolor=BORDER, facecolor=BODY_BG,
        ))
        # Title bar
        title_h = 0.35
        ax.add_patch(patches.Rectangle(
            (x, y + h - title_h), w, title_h,
            linewidth=0, facecolor=TITLE_BG,
        ))
        # Mustard accent strip just below the title bar
        accent_h = 0.05
        ax.add_patch(patches.Rectangle(
            (x, y + h - title_h - accent_h), w, accent_h,
            linewidth=0, facecolor=COLOR_ACCENT,
        ))
        ax.text(
            x + w / 2, y + h - title_h / 2,
            title,  # already in Title Case in BOXES
            ha="center", va="center",
            fontsize=11, fontweight="bold", color=TITLE_FG,
        )

        # Body text — wrap to roughly fit the box width.
        # 18 chars per unit-width is a reasonable fit at this figsize.
        wrap_width = max(int(w * 18), 12)
        body = _wrap_bullets(canvas.get(key) or [], wrap_width)
        ax.text(
            x + 0.1, y + h - title_h - accent_h - 0.15,
            body,
            ha="left", va="top",
            fontsize=8.5, color=BULLET_FG, family="DejaVu Sans",
            wrap=True,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=PAGE_BG)
    plt.close(fig)
    return out_path
