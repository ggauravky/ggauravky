"""Render a static, on-palette contribution calendar (light + dark) from GitHub's public calendar."""

from __future__ import annotations

import datetime as dt
import sys
import urllib.error

from github_calendar import fetch_days
from profile_theme import GENERATED_DIR, MODES, MONO, PALETTE, load_profile, svg_open, write_if_changed

CELL = 11
GAP = 3
X0 = 40
Y0 = 34
WIDTH = 820
HEIGHT = 170


def sunday_index(day: dt.date) -> int:
    return (day.weekday() + 1) % 7


def render_svg(username: str, days: dict[dt.date, int], mode: str) -> str:
    c = PALETTE[mode]
    ramp = [c[f"ramp{i}"] for i in range(5)]
    first = min(days)
    start = first - dt.timedelta(days=sunday_index(first))

    cells: list[str] = []
    for day, level in sorted(days.items()):
        week = (day - start).days // 7
        if week > 53:
            continue
        x = X0 + week * (CELL + GAP)
        y = Y0 + sunday_index(day) * (CELL + GAP)
        cells.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{ramp[level]}">'
            f"<title>{day.isoformat()} · level {level}</title></rect>"
        )

    months: list[str] = []
    seen: set[tuple[int, int]] = set()
    for day in sorted(days):
        key = (day.year, day.month)
        if key in seen or day.day > 7:
            continue
        seen.add(key)
        x = X0 + ((day - start).days // 7) * (CELL + GAP)
        if x <= WIDTH - 40:
            months.append(f'<text x="{x}" y="22">{day.strftime("%b")}</text>')

    active = sum(1 for v in days.values() if v > 0)
    legend_x = WIDTH - 40 - 5 * (CELL + 4) - 34
    legend = "".join(
        f'<rect x="{legend_x + 30 + i * (CELL + 4)}" y="{HEIGHT - 22}" width="{CELL}" height="{CELL}" rx="2" fill="{ramp[i]}"/>'
        for i in range(5)
    )
    return (
        svg_open(
            WIDTH,
            HEIGHT,
            f"{username} public GitHub contribution calendar",
            f"Contribution intensity for the past year: {active} active days of {len(days)}.",
        )
        + f'  <g font-family="{MONO}" font-size="10" fill="{c["muted"]}">{"".join(months)}\n'
        + f'    <text x="0" y="{Y0 + 1 * (CELL + GAP) + 9}">Mon</text>'
        + f'<text x="0" y="{Y0 + 3 * (CELL + GAP) + 9}">Wed</text>'
        + f'<text x="0" y="{Y0 + 5 * (CELL + GAP) + 9}">Fri</text>\n'
        + f'    <text x="{X0}" y="{HEIGHT - 12}">{active} active days in the last year</text>\n'
        + f'    <text x="{legend_x}" y="{HEIGHT - 12}">less</text>{legend}'
        + f'<text x="{legend_x + 30 + 5 * (CELL + 4) + 4}" y="{HEIGHT - 12}">more</text>\n  </g>\n'
        + f'  <g>{"".join(cells)}</g>\n</svg>\n'
    )


def main() -> int:
    username = load_profile()["handle"]
    try:
        days = fetch_days(username)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
        if all((GENERATED_DIR / f"contribution-{m}.svg").exists() for m in MODES):
            print(f"Keeping existing contribution assets after refresh issue: {exc}")
            return 0
        print(f"Unable to create the initial contribution assets: {exc}", file=sys.stderr)
        return 1
    for mode in MODES:
        changed = write_if_changed(GENERATED_DIR / f"contribution-{mode}.svg", render_svg(username, days, mode))
        print(f"contribution-{mode}.svg: {'updated' if changed else 'already current'} ({len(days)} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
