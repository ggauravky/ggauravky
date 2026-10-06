"""Generate a branded, static contribution calendar from GitHub's public activity page."""

from __future__ import annotations

import datetime as dt
import html
import json
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "generated" / "contribution.svg"


class ContributionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.days: dict[dt.date, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "td":
            return
        values = dict(attrs)
        date_value = values.get("data-date")
        level_value = values.get("data-level")
        if not date_value or level_value is None:
            return
        try:
            self.days[dt.date.fromisoformat(date_value)] = min(4, max(0, int(level_value)))
        except (ValueError, TypeError):
            return


def get_username() -> str:
    profile = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    return profile["handle"]


def fetch_days(username: str) -> dict[dt.date, int]:
    url = f"https://github.com/users/{username}/contributions"
    request = urllib.request.Request(url, headers={"User-Agent": "ggauravky-profile-generator/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"GitHub returned HTTP {response.status}")
        parser = ContributionParser()
        parser.feed(response.read().decode("utf-8", errors="replace"))
    if len(parser.days) < 300:
        raise RuntimeError(f"Contribution response contained only {len(parser.days)} calendar days")
    return parser.days


def sunday_index(day: dt.date) -> int:
    return (day.weekday() + 1) % 7


def render_svg(username: str, days: dict[dt.date, int]) -> str:
    first = min(days)
    start = first - dt.timedelta(days=sunday_index(first))
    palette = ("#101A3D", "#163466", "#2054A7", "#247BFF", "#FF354F")
    cell = 11
    gap = 3
    x0 = 194
    y0 = 108
    rects: list[str] = []
    for day, level in sorted(days.items()):
        week = (day - start).days // 7
        weekday = sunday_index(day)
        if week > 53:
            continue
        x = x0 + week * (cell + gap)
        y = y0 + weekday * (cell + gap)
        rects.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{palette[level]}"><title>{day.isoformat()} · contribution level {level}</title></rect>'
        )

    month_labels: list[str] = []
    seen: set[tuple[int, int]] = set()
    for day in sorted(days):
        key = (day.year, day.month)
        if key in seen or day.day > 7:
            continue
        seen.add(key)
        week = (day - start).days // 7
        x = x0 + week * (cell + gap)
        if x <= 925:
            month_labels.append(
                f'<text x="{x}" y="94" fill="#66718F" font-family="ui-monospace,Consolas,monospace" font-size="11">{day.strftime("%b").upper()}</text>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="250" viewBox="0 0 1000 250" role="img" aria-labelledby="title desc">
  <title id="title">{html.escape(username)} public GitHub contribution history</title>
  <desc id="desc">A static calendar of public GitHub contribution intensity across the past year, generated from GitHub's public activity data.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#070B16"/><stop offset="1" stop-color="#0B1225"/></linearGradient>
    <linearGradient id="line" x1="0" x2="1"><stop stop-color="#247BFF"/><stop offset="1" stop-color="#FF354F"/></linearGradient>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#7896D2" stroke-opacity=".05"/></pattern>
  </defs>
  <rect x="1" y="1" width="998" height="248" rx="26" fill="url(#bg)" stroke="#7896D2" stroke-opacity=".22"/>
  <rect x="1" y="1" width="998" height="248" rx="26" fill="url(#grid)"/>
  <path d="M26 1H300M700 249H974" stroke="url(#line)" stroke-width="3"/>
  <text x="42" y="48" fill="#3B8CFF" font-family="ui-monospace,Consolas,monospace" font-size="14" letter-spacing="2">PUBLIC BUILD LOG / PAST 12 MONTHS</text>
  <text x="42" y="76" fill="#A3B0D4" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="15">Contribution intensity, generated from GitHub's public calendar.</text>
  <g>{''.join(month_labels)}{''.join(rects)}</g>
  <g font-family="ui-monospace,Consolas,monospace" font-size="11">
    <text x="42" y="124" fill="#66718F">SUN</text><text x="42" y="166" fill="#66718F">WED</text><text x="42" y="208" fill="#66718F">SAT</text>
    <text x="760" y="225" fill="#66718F">LESS</text>
    <rect x="800" y="214" width="11" height="11" rx="2.5" fill="#101A3D"/><rect x="818" y="214" width="11" height="11" rx="2.5" fill="#163466"/><rect x="836" y="214" width="11" height="11" rx="2.5" fill="#2054A7"/><rect x="854" y="214" width="11" height="11" rx="2.5" fill="#247BFF"/><rect x="872" y="214" width="11" height="11" rx="2.5" fill="#FF354F"/>
    <text x="892" y="225" fill="#66718F">MORE</text>
  </g>
</svg>'''


def main() -> int:
    username = get_username()
    try:
        days = fetch_days(username)
        svg = render_svg(username, days)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
        if OUTPUT.exists():
            print(f"Keeping existing contribution asset after refresh issue: {exc}")
            return 0
        print(f"Unable to create the initial contribution asset: {exc}", file=sys.stderr)
        return 1

    payload = svg.encode("utf-8")
    if OUTPUT.exists() and OUTPUT.read_bytes() == payload:
        print("Contribution asset is already current")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(payload)
    print(f"Updated {OUTPUT.relative_to(ROOT)} with {len(days)} calendar days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
