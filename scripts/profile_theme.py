"""Shared palette, typography and helpers for every generated profile asset.

One near-monochrome base (graphite ink on a transparent ground) plus exactly one
accent hue: ember. Every SVG generator and every third-party colour parameter
reads from here so the whole profile stays on a single system.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "data" / "profile.json"
GENERATED_DIR = ROOT / "assets" / "generated"
SECTIONS_DIR = ROOT / "assets" / "sections"
PROJECTS_DIR = ROOT / "assets" / "projects"

MODES = ("light", "dark")

PALETTE: dict[str, dict[str, str]] = {
    "light": {
        "ink": "#1C1B19",
        "muted": "#6E6A63",
        "faint": "#A39E95",
        "rule": "#DCD8D0",
        "accent": "#D9531E",
        # Contribution ramp: rule grey -> ember, same hue throughout.
        "ramp0": "#EBE8E2",
        "ramp1": "#F2C9B4",
        "ramp2": "#E99A72",
        "ramp3": "#DE6B37",
        "ramp4": "#B8410F",
    },
    "dark": {
        "ink": "#ECE9E3",
        "muted": "#9C978E",
        "faint": "#6B675F",
        "rule": "#383530",
        "accent": "#E8663A",
        "ramp0": "#2A2825",
        "ramp1": "#5C3221",
        "ramp2": "#93431F",
        "ramp3": "#C9551F",
        "ramp4": "#F07A4A",
    },
}

SERIF = "'Iowan Old Style','Charter','Georgia','Times New Roman',serif"
SANS = "-apple-system,'Segoe UI','Helvetica Neue',Arial,sans-serif"
MONO = "ui-monospace,'SFMono-Regular','Cascadia Mono',Consolas,monospace"


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_open(width: int, height: int, title: str, desc: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">\n'
        f'  <title id="t">{esc(title)}</title>\n  <desc id="d">{esc(desc)}</desc>\n'
    )


def write_if_changed(path: Path, text: str) -> bool:
    payload = text.encode("utf-8")
    if path.exists() and path.read_bytes() == payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return True


def compact(n: int) -> str:
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    if n >= 1_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n:,}"


STREAK_START = "<!-- streak:start -->"
STREAK_END = "<!-- streak:end -->"
STREAK_ALT = "GitHub contribution streak — total contributions, current streak and longest streak"
STREAK_FALLBACK_ALT = "GitHub activity is refreshing; the contribution calendar below remains current"


def picture(asset: str, alt: str, width: str = "100%") -> str:
    """Light/dark <picture> pointing only at committed local assets (./assets/<asset>-{mode}.svg)."""
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="./assets/{asset}-dark.svg" />\n'
        f'  <img src="./assets/{asset}-light.svg" alt="{esc(alt)}" width="{width}" />\n'
        "</picture>"
    )


def streak_block(prefix: str = "streak", alt: str = STREAK_ALT) -> str:
    """The single, uniquely-marked README block that update-streak.py pattern-matches."""
    return f"{STREAK_START}\n{picture(f'generated/{prefix}', alt, '560')}\n{STREAK_END}"
