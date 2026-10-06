"""Maintain the isolated README streak block and a last-known-good snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "data" / "profile.json"
README_PATH = ROOT / "README.md"
GENERATED_DIR = ROOT / "assets" / "generated"
LAST_GOOD_PATH = GENERATED_DIR / "streak-last-good.svg"
FALLBACK_PATH = GENERATED_DIR / "streak-fallback.svg"
START_MARKER = "<!-- streak:start -->"
END_MARKER = "<!-- streak:end -->"
MAX_TRANSIENT_FAILURES = 2


def read_primary_url() -> str:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return profile["githubActivity"]["streakPrimaryUrl"]


def validate_streak_svg(payload: bytes, content_type: str = "image/svg+xml") -> tuple[bool, str]:
    if "svg" not in content_type.lower() and "image" not in content_type.lower():
        return False, f"unexpected content type: {content_type or 'missing'}"
    if len(payload) < 1_000:
        return False, "response is suspiciously small"
    text = payload.decode("utf-8", errors="replace")
    lowered = text.lower()
    if "<svg" not in lowered or "<html" in lowered:
        return False, "response is not an SVG"
    invalid_phrases = ("rate limit", "service unavailable", "undefined", ">null<", ">nan<")
    if any(phrase in lowered for phrase in invalid_phrases):
        return False, "response contains an invalid-data marker"
    required_labels = ("Total Contributions", "Current Streak", "Longest Streak")
    if not all(label in text for label in required_labels):
        return False, "expected streak labels are missing"
    numeric_text = re.findall(r">\s*[0-9][0-9,]*\s*<", text)
    if len(numeric_text) < 3:
        return False, "metric value groups are missing"
    return True, "valid streak SVG"


def fetch_primary(url: str) -> tuple[bytes | None, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "ggauravky-profile-health/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
            valid, reason = validate_streak_svg(payload, content_type)
            return (payload if valid else None), reason
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"transient request failure: {exc}"


def streak_block(source: str, alt: str) -> str:
    return (
        f"{START_MARKER}\n"
        '<p align="center">\n'
        f'  <img src="{source}" alt="{alt}" width="620" />\n'
        "</p>\n"
        f"{END_MARKER}"
    )


def replace_streak_block(block: str) -> bool:
    readme = README_PATH.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)
    if len(pattern.findall(readme)) != 1:
        raise RuntimeError("README must contain exactly one isolated streak block")
    updated = pattern.sub(lambda _: block, readme)
    if updated == readme:
        return False
    README_PATH.write_text(updated, encoding="utf-8", newline="\n")
    return True


def write_if_changed(path: Path, payload: bytes) -> bool:
    if path.exists() and path.read_bytes() == payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return True


def read_failure_count(state_path: Path) -> int:
    try:
        return max(0, int(state_path.read_text(encoding="ascii").strip()))
    except (FileNotFoundError, ValueError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".cache" / "streak")
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.state_dir / "failures.txt"

    primary_url = read_primary_url()
    payload, reason = fetch_primary(primary_url)

    if payload is not None:
        asset_changed = write_if_changed(LAST_GOOD_PATH, payload)
        readme_changed = replace_streak_block(
            streak_block(
                primary_url,
                "Gaurav Kumar Yadav GitHub contribution streak — total contributions, current streak and longest streak",
            )
        )
        state_path.write_text("0\n", encoding="ascii")
        print(f"healthy: {reason}; snapshot_changed={asset_changed}; readme_changed={readme_changed}")
        return 0

    failures = read_failure_count(state_path) + 1
    state_path.write_text(f"{failures}\n", encoding="ascii")
    if failures < MAX_TRANSIENT_FAILURES:
        print(f"deferred fallback after transient failure {failures}/{MAX_TRANSIENT_FAILURES}: {reason}")
        return 0

    if LAST_GOOD_PATH.exists():
        fallback_source = "./assets/generated/streak-last-good.svg"
        fallback_alt = "Gaurav Kumar Yadav GitHub contribution streak — last known good snapshot"
    else:
        fallback_source = "./assets/generated/streak-fallback.svg"
        fallback_alt = "GitHub activity is refreshing; Gaurav's contribution timeline remains available below"

    readme_changed = replace_streak_block(streak_block(fallback_source, fallback_alt))
    print(f"fallback active after {failures} consecutive failures: {reason}; readme_changed={readme_changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
