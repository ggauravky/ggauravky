"""Compose a monochrome tech-stack row (light + dark) from Simple Icons glyphs.

skillicons.dev renders fixed brand-coloured tiles (several of them blue) with no colour
parameters, which breaks the single-accent palette. Simple Icons (CC0) publishes plain
24x24 paths; we fetch them, validate them, and re-ink them in the profile's ink colour.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

from profile_theme import GENERATED_DIR, MODES, MONO, PALETTE, esc, load_profile, svg_open, write_if_changed

CDN = "https://cdn.simpleicons.org"
WIDTH = 820
PER_ROW = 9
ICON = 26
ROW_H = 74


def fetch_path(slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+", slug):
        raise ValueError(f"invalid simple-icons slug {slug!r}")
    request = urllib.request.Request(f"{CDN}/{slug}", headers={"User-Agent": "profile-stack-snapshot/2.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        text = response.read().decode("utf-8", errors="replace")
    paths = re.findall(r'<path[^>]*\sd="([^"]+)"', text)
    if 'viewBox="0 0 24 24"' not in text or len(paths) != 1:
        raise RuntimeError(f"unexpected icon payload for {slug}")
    d = paths[0]
    if not re.fullmatch(r"[0-9MmLlHhVvCcSsQqTtAaZz.,\-\s eE]+", d):
        raise RuntimeError(f"icon path for {slug} contains unexpected characters")
    return d


def render(items: list[tuple[str, str]], mode: str) -> str:
    c = PALETTE[mode]
    rows = (len(items) + PER_ROW - 1) // PER_ROW
    col = WIDTH / PER_ROW
    height = rows * ROW_H
    out: list[str] = []
    for i, (label, d) in enumerate(items):
        cx = (i % PER_ROW) * col + col / 2
        y = (i // PER_ROW) * ROW_H + 8
        scale = ICON / 24
        out.append(
            f'<g><title>{esc(label)}</title>'
            f'<path transform="translate({cx - ICON / 2:.1f} {y}) scale({scale:.4f})" fill="{c["ink"]}" d="{d}"/>'
            f'<text x="{cx:.1f}" y="{y + ICON + 20}" text-anchor="middle" font-family="{MONO}" font-size="10" fill="{c["muted"]}">{esc(label)}</text></g>'
        )
    names = ", ".join(label for label, _ in items)
    return svg_open(WIDTH, height, "Tech stack", f"Tools used day to day: {names}.") + "  " + "".join(out) + "\n</svg>\n"


def main() -> int:
    stack = load_profile().get("stack", [])
    items: list[tuple[str, str]] = []
    for entry in stack:
        try:
            items.append((entry["label"], fetch_path(entry["slug"])))
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
            print(f"skipping {entry.get('slug')}: {exc}")
    if len(items) < max(1, len(stack) // 2):
        existing = all((GENERATED_DIR / f"stack-{m}.svg").exists() for m in MODES)
        print(f"only {len(items)}/{len(stack)} icons fetched; {'keeping previous snapshot' if existing else 'no snapshot yet'}")
        return 0 if existing else 1
    for mode in MODES:
        changed = write_if_changed(GENERATED_DIR / f"stack-{mode}.svg", render(items, mode))
        print(f"stack-{mode}.svg: {'updated' if changed else 'already current'} ({len(items)} icons)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
