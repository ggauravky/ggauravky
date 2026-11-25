"""Fetch GitHub's public contribution calendar (shared by the calendar and streak guard)."""

from __future__ import annotations

import datetime as dt
import re
import urllib.request
from html.parser import HTMLParser


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


def fetch_days(username: str) -> dict[dt.date, int]:
    """Return {date: level 0-4} for the past year, or raise on a bad response."""
    url = f"https://github.com/users/{username}/contributions"
    request = urllib.request.Request(url, headers={"User-Agent": "profile-readme-generator/2.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"GitHub returned HTTP {response.status}")
        parser = ContributionParser()
        parser.feed(response.read().decode("utf-8", errors="replace"))
    if len(parser.days) < 300:
        raise RuntimeError(f"Contribution response contained only {len(parser.days)} calendar days")
    return parser.days


def parse_streak_metrics(svg_text: str) -> dict[str, int] | None:
    """Read total / current / longest from a streak-stats card's visible text (document order)."""
    tokens = [t.strip() for t in re.findall(r">([^<>]+)<", svg_text) if t.strip()]
    numbers = [int(t.replace(",", "")) for t in tokens if re.fullmatch(r"[0-9][0-9,]*", t)]
    if len(numbers) != 3:
        return None
    return {"total": numbers[0], "current": numbers[1], "longest": numbers[2]}
