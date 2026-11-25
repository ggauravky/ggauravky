"""Render the static, typographic README sections (light + dark) from data/profile.json.

Editorial system: transparent ground, graphite ink, a single ember accent, hairline
rules and whitespace instead of containers. No photos, no gradients, no framed cards.
"""

from __future__ import annotations

import sys

from profile_theme import (
    GENERATED_DIR,
    MODES,
    MONO,
    PALETTE,
    PROJECTS_DIR,
    SANS,
    SECTIONS_DIR,
    SERIF,
    esc,
    load_profile,
    svg_open,
    write_if_changed,
)

W = 820


def wrap(text: str, limit: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > limit:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def tspans(lines: list[str], x: int, first_y: int, leading: int) -> str:
    return "".join(
        f'<tspan x="{x}" y="{first_y + i * leading}">{esc(line)}</tspan>' for i, line in enumerate(lines)
    )


def masthead(p: dict, mode: str) -> str:
    c = PALETTE[mode]
    pos = wrap(p["positioning"], 70)
    h = 196 + 26 * (len(pos) - 1)
    return (
        svg_open(W, h, f"{p['name']} — {p['title']}", f"{p['positioning']} Based in {p['location']}.")
        + f'  <text x="0" y="20" font-family="{MONO}" font-size="12" fill="{c["muted"]}">@{esc(p["handle"])}  ·  {esc(p["location"])}</text>\n'
        + f'  <text x="-3" y="88" font-family="{SERIF}" font-size="58" fill="{c["ink"]}">{esc(p["name"])}</text>\n'
        + f'  <rect x="0" y="110" width="56" height="3" fill="{c["accent"]}"/>\n'
        + f'  <text x="72" y="116" font-family="{SANS}" font-size="17" fill="{c["ink"]}">{esc(p["title"])}</text>\n'
        + f'  <text font-family="{SERIF}" font-size="19" fill="{c["muted"]}" font-style="italic">{tspans(pos, 0, 160, 26)}</text>\n'
        + "</svg>\n"
    )


def journey(p: dict, mode: str) -> str:
    c = PALETTE[mode]
    stops = [("Now", p["role"]["title"], p["role"]["company"])]
    stops += [("Education", e["credential"], e["institution"]) for e in p["education"]]
    col = W / len(stops)
    out: list[str] = [f'<line x1="0" y1="30.5" x2="{W}" y2="30.5" stroke="{c["rule"]}" stroke-width="1"/>']
    for i, (kicker, head, sub) in enumerate(stops):
        x = round(i * col)
        fill = c["accent"] if i == 0 else c["ink"]
        out.append(
            f'<circle cx="{x + 5}" cy="30.5" r="5" fill="{fill}"/>'
            f'<text x="{x}" y="12" font-family="{MONO}" font-size="11" fill="{c["muted"]}">{esc(kicker.lower())}</text>'
            f'<text font-family="{SERIF}" font-size="19" fill="{c["ink"]}">{tspans(wrap(head, 26), x, 66, 24)}</text>'
            f'<text x="{x}" y="{66 + 24 * len(wrap(head, 26)) + 2}" font-family="{SANS}" font-size="14" fill="{c["muted"]}">{esc(sub)}</text>'
        )
    desc = "; ".join(f"{k}: {h}, {s}" for k, h, s in stops)
    return svg_open(W, 140, "Experience and education", desc) + "  " + "".join(out) + "\n</svg>\n"


def colophon(p: dict, mode: str) -> str:
    c = PALETTE[mode]
    rows = [
        ("name", p["name"]),
        ("role", p["title"]),
        ("base", p["location"]),
        ("builds", "web · apis · data · ai"),
        ("handle", f"@{p['handle']}"),
    ]
    out: list[str] = []
    for i, (k, v) in enumerate(rows):
        y = 34 + i * 28
        out.append(
            f'<text x="0" y="{y}" font-family="{MONO}" font-size="11" fill="{c["muted"]}">{esc(k)}</text>'
            f'<text x="120" y="{y}" font-family="{SANS}" font-size="15" fill="{c["ink"]}">{esc(v)}</text>'
        )
    mono = p.get("monogram", "")
    out.append(
        f'<text x="{W}" y="118" text-anchor="end" font-family="{SERIF}" font-size="88" fill="{c["accent"]}">{esc(mono)}</text>'
        f'<line x1="0" y1="{34 + len(rows) * 28 - 6}.5" x2="{W}" y2="{34 + len(rows) * 28 - 6}.5" stroke="{c["rule"]}"/>'
    )
    desc = "; ".join(f"{k}: {v}" for k, v in rows)
    return svg_open(W, 34 + len(rows) * 28, "Developer identity", desc) + "  " + "".join(out) + "\n</svg>\n"


def project(p: dict, index: int, mode: str) -> str:
    c = PALETTE[mode]
    summary = wrap(proj_summary(p), 62)
    hl_y = 96 + 24 * len(summary) + 22
    status = "live + source" if p.get("live") else "source"
    out = [
        f'<text x="0" y="14" font-family="{MONO}" font-size="11" fill="{c["accent"]}">{index:02d}</text>',
        f'<text x="30" y="14" font-family="{MONO}" font-size="11" fill="{c["muted"]}">{esc(p["category"].lower())}</text>',
        f'<text x="{W}" y="14" text-anchor="end" font-family="{MONO}" font-size="11" fill="{c["faint"]}">{status}</text>',
        f'<text x="-2" y="64" font-family="{SERIF}" font-size="40" fill="{c["ink"]}">{esc(p["name"])}</text>',
        f'<text font-family="{SANS}" font-size="16" fill="{c["ink"]}">{tspans(summary, 0, 96, 24)}</text>',
        f'<text x="0" y="{hl_y}" font-family="{SERIF}" font-size="15" font-style="italic" fill="{c["muted"]}">{esc(p["signal"])}</text>',
    ]
    col = W / max(1, len(p["highlights"]))
    for i, h in enumerate(p["highlights"]):
        x = round(i * col)
        out.append(
            f'<rect x="{x}" y="{hl_y + 26}" width="18" height="2" fill="{c["accent"]}"/>'
            f'<text x="{x}" y="{hl_y + 48}" font-family="{MONO}" font-size="12" fill="{c["ink"]}">{esc(h)}</text>'
        )
    stack_y = hl_y + 82
    out.append(f'<line x1="0" y1="{stack_y - 16}.5" x2="{W}" y2="{stack_y - 16}.5" stroke="{c["rule"]}"/>')
    out.append(
        f'<text x="0" y="{stack_y + 4}" font-family="{MONO}" font-size="11" fill="{c["muted"]}">{esc("  ·  ".join(p["stack"]).lower())}</text>'
    )
    desc = f"{p['name']}: {p['category']}. {proj_summary(p)} {p['signal']} Stack: {', '.join(p['stack'])}."
    return svg_open(W, stack_y + 12, f"Project {index:02d} — {p['name']}", desc) + "  " + "".join(out) + "\n</svg>\n"


def proj_summary(p: dict) -> str:
    return p.get("summary") or p["category"]


def streak_fallback(mode: str) -> str:
    c = PALETTE[mode]
    return (
        svg_open(560, 90, "GitHub streak refreshing", "The streak snapshot is refreshing; the contribution calendar below is current.")
        + f'  <text x="280" y="40" text-anchor="middle" font-family="{SERIF}" font-size="22" fill="{c["ink"]}">Streak snapshot refreshing</text>\n'
        + f'  <rect x="252" y="56" width="56" height="2" fill="{c["accent"]}"/>\n'
        + f'  <text x="280" y="80" text-anchor="middle" font-family="{MONO}" font-size="11" fill="{c["muted"]}">the calendar below is live data</text>\n'
        + "</svg>\n"
    )


def main() -> int:
    p = load_profile()
    written = 0
    for mode in MODES:
        written += write_if_changed(SECTIONS_DIR / f"masthead-{mode}.svg", masthead(p, mode))
        written += write_if_changed(SECTIONS_DIR / f"journey-{mode}.svg", journey(p, mode))
        written += write_if_changed(SECTIONS_DIR / f"colophon-{mode}.svg", colophon(p, mode))
        written += write_if_changed(GENERATED_DIR / f"streak-fallback-{mode}.svg", streak_fallback(mode))
        for i, proj in enumerate(p["featuredProjects"], start=1):
            written += write_if_changed(PROJECTS_DIR / f"{proj['slug']}-{mode}.svg", project(proj, i, mode))
    print(f"sections rendered; {written} file(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
