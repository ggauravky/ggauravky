"""Fetch the streak card from its ORIGIN, validate it, and commit light/dark snapshots.

Root cause this guards against: the configured URL used to be a
camo.githubusercontent.com proxy link. Camo caches the first response it got for
hours, independent of how often this job runs, so the pipeline kept re-saving a
stale card that said "Current Streak 0". We now:

* only ever fetch the direct origin (camo/githubusercontent hosts are refused),
* parse the numbers and reject a 0 current streak unless GitHub's own public
  calendar confirms the streak really broke,
* keep the README pointing at the committed local snapshot, never a live URL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from github_calendar import fetch_days, parse_streak_metrics
from profile_theme import (
    GENERATED_DIR,
    MODES,
    PALETTE,
    ROOT,
    STREAK_ALT,
    STREAK_END,
    STREAK_FALLBACK_ALT,
    STREAK_START,
    load_profile,
    streak_block,
    write_if_changed,
)

README_PATH = ROOT / "README.md"
START_MARKER = STREAK_START
END_MARKER = STREAK_END
MAX_TRANSIENT_FAILURES = 2
BLOCKED_HOST_SUFFIXES = ("githubusercontent.com",)
BLOCKED_HOST_PREFIXES = ("camo.",)


class CamoConfigured(RuntimeError):
    pass


def snapshot_path(mode: str) -> Path:
    return GENERATED_DIR / f"streak-{mode}.svg"


def fallback_path(mode: str) -> Path:
    return GENERATED_DIR / f"streak-fallback-{mode}.svg"


def assert_not_camo(url: str) -> None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if not host:
        raise CamoConfigured(f"streak URL has no host: {url!r}")
    if host.endswith(BLOCKED_HOST_SUFFIXES) or host.startswith(BLOCKED_HOST_PREFIXES):
        raise CamoConfigured(
            f"refusing proxied streak URL host {host!r}: configure the direct origin "
            "(e.g. https://streak-stats.demolab.com), never a camo-rewritten link"
        )


def build_url(profile: dict, mode: str) -> str:
    activity = profile["githubActivity"]
    origin = activity["streakOriginUrl"]
    assert_not_camo(origin)
    c = {k: v.lstrip("#") for k, v in PALETTE[mode].items()}
    params = {
        "user": profile["handle"],
        "background": "00000000",
        "border": c["rule"],
        "stroke": c["rule"],
        "ring": c["accent"],
        "fire": c["accent"],
        "currStreakNum": c["ink"],
        "currStreakLabel": c["accent"],
        "sideNums": c["ink"],
        "sideLabels": c["muted"],
        "dates": c["faint"],
        **activity.get("streakParams", {}),
    }
    return f"{origin.rstrip('/')}/?{urllib.parse.urlencode(params)}"


parse_metrics = parse_streak_metrics


def validate_streak_svg(payload: bytes, content_type: str) -> tuple[dict[str, int] | None, str]:
    if "svg" not in content_type.lower():
        return None, f"unexpected content type: {content_type or 'missing'}"
    if len(payload) < 1_000:
        return None, "response is suspiciously small"
    text = payload.decode("utf-8", errors="replace")
    lowered = text.lower()
    if "<svg" not in lowered or "<html" in lowered:
        return None, "response is not an SVG"
    for phrase in ("rate limit", "service unavailable", "undefined", ">null<", ">nan<", "something went wrong"):
        if phrase in lowered:
            return None, f"response contains an invalid-data marker ({phrase})"
    if not all(label in text for label in ("Total Contributions", "Current Streak", "Longest Streak")):
        return None, "expected streak labels are missing"
    metrics = parse_metrics(text)
    if metrics is None:
        return None, "metric values are missing"
    return metrics, "valid streak SVG"


def streak_really_broke(handle: str) -> bool:
    """True only if GitHub's own calendar shows no contributions yesterday AND today (UTC)."""
    try:
        days = fetch_days(handle)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
        print(f"calendar cross-check unavailable ({exc}); treating 0 as a glitch")
        return False
    today = max(days)
    yesterday = today - dt.timedelta(days=1)
    return days.get(today, 0) == 0 and days.get(yesterday, 0) == 0


def sanity_check(metrics: dict[str, int], handle: str, previous: dict[str, int] | None) -> tuple[bool, str]:
    if metrics["total"] <= 0 and metrics["longest"] <= 0 and metrics["current"] <= 0:
        return False, "card reports all-zero metrics"
    if metrics["current"] > metrics["longest"]:
        return False, "current streak exceeds longest streak"
    if metrics["current"] == 0 and (metrics["total"] > 0 or metrics["longest"] > 0):
        if not streak_really_broke(handle):
            return False, (
                f"card says current streak 0 while total={metrics['total']} and longest={metrics['longest']}, "
                "but the public calendar shows recent activity — transient glitch, keeping last good snapshot"
            )
    if previous and previous["current"] > 1 and 0 < metrics["current"] < previous["current"] - 1:
        if not streak_really_broke(handle):
            return False, f"current streak regressed {previous['current']} -> {metrics['current']} without a calendar gap"
    return True, "metrics are plausible"


def fetch(url: str) -> tuple[bytes | None, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "profile-streak-snapshot/2.0", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read(), response.headers.get("Content-Type", ""), "ok"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, "", f"transient request failure: {exc}"


HEALTHY_ALT = STREAK_ALT
FALLBACK_ALT = STREAK_FALLBACK_ALT


def replace_streak_block(block: str) -> bool:
    if not README_PATH.exists():
        return False
    readme = README_PATH.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)
    if len(pattern.findall(readme)) != 1:
        raise RuntimeError("README must contain exactly one isolated streak block")
    updated = pattern.sub(lambda _: block, readme)
    if updated == readme:
        return False
    README_PATH.write_text(updated, encoding="utf-8", newline="\n")
    return True


def read_failure_count(state_path: Path) -> int:
    try:
        return max(0, int(state_path.read_text(encoding="ascii").strip()))
    except (FileNotFoundError, ValueError):
        return 0


def previous_metrics() -> dict[str, int] | None:
    path = snapshot_path("light")
    if not path.exists():
        return None
    return parse_metrics(path.read_text(encoding="utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".cache" / "streak")
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.state_dir / "failures.txt"

    profile = load_profile()
    try:
        urls = {mode: build_url(profile, mode) for mode in MODES}
    except CamoConfigured as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    previous = previous_metrics()
    payloads: dict[str, bytes] = {}
    reason = ""
    for mode, url in urls.items():
        payload, content_type, reason = fetch(url)
        if payload is None:
            break
        metrics, reason = validate_streak_svg(payload, content_type)
        if metrics is None:
            break
        ok, reason = sanity_check(metrics, profile["handle"], previous)
        if not ok:
            break
        print(f"{mode}: total={metrics['total']} current={metrics['current']} longest={metrics['longest']}")
        payloads[mode] = payload

    if len(payloads) == len(MODES):
        changed = [write_if_changed(snapshot_path(m), p.decode("utf-8")) for m, p in payloads.items()]
        readme_changed = replace_streak_block(streak_block("streak", HEALTHY_ALT))
        state_path.write_text("0\n", encoding="ascii")
        print(f"healthy: snapshots_changed={any(changed)} readme_changed={readme_changed}")
        return 0

    failures = read_failure_count(state_path) + 1
    state_path.write_text(f"{failures}\n", encoding="ascii")
    print(f"rejected ({failures}/{MAX_TRANSIENT_FAILURES}): {reason}")
    if snapshot_path("light").exists() and snapshot_path("dark").exists():
        # Keep the last known-good snapshot exactly as it is.
        replace_streak_block(streak_block("streak", HEALTHY_ALT))
        return 0
    if failures >= MAX_TRANSIENT_FAILURES:
        replace_streak_block(streak_block("streak-fallback", FALLBACK_ALT))
        print("no snapshot exists yet; showing fallback card")
    return 0


if __name__ == "__main__":
    sys.exit(main())
