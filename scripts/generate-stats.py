"""Snapshot GitHub stats, top languages and a trophy case as on-palette SVGs (light + dark).

Replaces the github-readme-stats / github-profile-trophy widgets: the public trophy
instance returns 402 DEPLOYMENT_DISABLED and the stats instance is rate-limited, and
neither can render the profile's typographic, frameless style. Data comes from the
GitHub GraphQL API (GITHUB_TOKEN in Actions) with an unauthenticated REST fallback.

fetch -> validate -> keep previous snapshot on failure -> write only if changed.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from github_calendar import parse_streak_metrics
from profile_theme import GENERATED_DIR, MODES, MONO, PALETTE, SERIF, compact, esc, load_profile, svg_open, write_if_changed

API = "https://api.github.com"
WIDTH = 820
OUTPUTS = ("stats", "languages", "trophies")

QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
    contributionsCollection { totalCommitContributions restrictedContributionsCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
    }
  }
}
"""


def http_json(url: str, body: dict | None = None) -> dict:
    headers = {"User-Agent": "profile-stats-snapshot/2.0", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_graphql(login: str) -> dict:
    payload = http_json(f"{API}/graphql", {"query": QUERY, "variables": {"login": login}})
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise RuntimeError(f"GraphQL error: {payload.get('errors')}")
    u = payload["data"]["user"]
    langs: dict[str, int] = {}
    for repo in u["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            langs[edge["node"]["name"]] = langs.get(edge["node"]["name"], 0) + edge["size"]
    cc = u["contributionsCollection"]
    return {
        "stars": sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "created": u["createdAt"],
        "languages": langs,
    }


def fetch_rest(login: str) -> dict:
    """Unauthenticated fallback for local runs (primary language weighted by repo size)."""
    user = http_json(f"{API}/users/{login}")
    repos = http_json(f"{API}/users/{login}/repos?per_page=100&type=owner")
    own = [r for r in repos if not r.get("fork")]
    langs: dict[str, int] = {}
    for r in own:
        if r.get("language"):
            langs[r["language"]] = langs.get(r["language"], 0) + max(1, r.get("size", 0)) * 1024
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    q = lambda s: http_json(f"{API}/search/issues?q={urllib.parse.quote(s)}&per_page=1")["total_count"]  # noqa: E731
    commits = http_json(f"{API}/search/commits?q={urllib.parse.quote(f'author:{login} committer-date:>{since}')}&per_page=1")["total_count"]
    return {
        "stars": sum(r.get("stargazers_count", 0) for r in own),
        "commits": commits,
        "prs": q(f"author:{login} type:pr"),
        "issues": q(f"author:{login} type:issue"),
        "contributed": None,
        "repos": len(own),
        "followers": user["followers"],
        "created": user["created_at"],
        "languages": langs,
    }


def validate(data: dict) -> str | None:
    for key in ("stars", "commits", "prs", "issues", "repos", "followers"):
        value = data.get(key)
        if not isinstance(value, int) or value < 0 or value > 10_000_000:
            return f"implausible value for {key}: {value!r}"
    if data["repos"] == 0 or not data["languages"]:
        return "no repositories or languages returned"
    return None


def current_streak() -> int | None:
    path = GENERATED_DIR / "streak-light.svg"
    if not path.exists():
        return None
    metrics = parse_streak_metrics(path.read_text(encoding="utf-8", errors="replace"))
    return metrics["current"] if metrics else None


# --------------------------------------------------------------------------- rendering


def figure_row(items: list[tuple[str, str]], c: dict[str, str], y: int, accent_first: bool = False) -> str:
    col = WIDTH / len(items)
    out: list[str] = []
    for i, (value, label) in enumerate(items):
        x = round(i * col)
        fill = c["accent"] if accent_first and i == 0 else c["ink"]
        out.append(
            f'<text x="{x}" y="{y}" font-family="{SERIF}" font-size="40" fill="{fill}">{esc(value)}</text>'
            f'<text x="{x}" y="{y + 24}" font-family="{MONO}" font-size="11" fill="{c["muted"]}">{esc(label)}</text>'
        )
        if i:
            out.append(f'<line x1="{x - 14}" y1="{y - 34}" x2="{x - 14}" y2="{y + 28}" stroke="{c["rule"]}" stroke-width="1"/>')
    return "".join(out)


def render_stats(data: dict, mode: str) -> str:
    c = PALETTE[mode]
    items = [
        (compact(data["commits"]), "commits, past year"),
        (compact(data["prs"]), "pull requests"),
        (compact(data["stars"]), "stars earned"),
        (compact(data["repos"]), "public repositories"),
    ]
    if data.get("contributed") is not None:
        items.append((compact(data["contributed"]), "repos contributed to"))
    else:
        items.append((compact(data["issues"]), "issues opened"))
    desc = "; ".join(f"{v} {l}" for v, l in items)
    return (
        svg_open(WIDTH, 96, "GitHub stats", desc)
        + "  "
        + figure_row(items, c, 56)
        + "\n</svg>\n"
    )


def render_languages(data: dict, mode: str) -> str:
    c = PALETTE[mode]
    tones = [c["accent"], c["ramp4"], c["ramp3"], c["ramp2"], c["ramp1"], c["faint"]]
    ranked = sorted(data["languages"].items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:5]
    rest = sum(v for _, v in ranked[5:])
    if rest:
        top.append(("Other", rest))
    total = sum(v for _, v in top) or 1
    bar: list[str] = []
    legend: list[str] = []
    x = 0.0
    for i, (name, size) in enumerate(top):
        w = WIDTH * size / total
        bar.append(f'<rect x="{x:.1f}" y="18" width="{max(w - 2, 1):.1f}" height="6" fill="{tones[i]}"/>')
        x += w
        lx = (i % 3) * (WIDTH / 3)
        ly = 58 + (i // 3) * 26
        legend.append(
            f'<rect x="{lx:.0f}" y="{ly - 8}" width="8" height="8" fill="{tones[i]}"/>'
            f'<text x="{lx + 16:.0f}" y="{ly}" font-family="{MONO}" font-size="12" fill="{c["ink"]}">{esc(name)}</text>'
            f'<text x="{lx + 200:.0f}" y="{ly}" font-family="{MONO}" font-size="12" fill="{c["muted"]}" text-anchor="end">{100 * size / total:.1f}%</text>'
        )
    desc = ", ".join(f"{n} {100 * s / total:.1f}%" for n, s in top)
    height = 58 + ((len(top) - 1) // 3) * 26 + 14
    return (
        svg_open(WIDTH, height, "Most used languages", f"Share of code by bytes across public repositories: {desc}")
        + f'  <text x="0" y="8" font-family="{MONO}" font-size="11" fill="{c["muted"]}">languages by bytes, public repositories</text>\n'
        + f"  {''.join(bar)}\n  {''.join(legend)}\n</svg>\n"
    )


TIERS = ("I", "II", "III", "IV", "V")


def tier(value: int, thresholds: tuple[int, ...]) -> int:
    return sum(1 for t in thresholds if value >= t)


def render_trophies(data: dict, streak: int | None, mode: str) -> str:
    c = PALETTE[mode]
    years = max(0, (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data["created"].replace("Z", "+00:00"))).days)
    marks: list[tuple[str, str, int]] = []
    if streak is not None:
        marks.append((f"{streak}", "day streak", tier(streak, (7, 30, 100, 365, 730))))
    marks += [
        (compact(data["commits"]), "commits / year", tier(data["commits"], (50, 200, 500, 1000, 2500))),
        (compact(data["prs"]), "pull requests", tier(data["prs"], (5, 25, 75, 150, 500))),
        (compact(data["stars"]), "stars", tier(data["stars"], (5, 25, 75, 200, 1000))),
        (compact(data["repos"]), "repositories", tier(data["repos"], (5, 15, 30, 50, 100))),
        (compact(data["followers"]), "followers", tier(data["followers"], (10, 50, 150, 500, 2000))),
    ]
    marks = marks[:6]
    col = WIDTH / len(marks)
    out: list[str] = []
    for i, (value, label, level) in enumerate(marks):
        x = round(i * col)
        ticks = "".join(
            f'<rect x="{x + k * 10}" y="16" width="6" height="6" fill="{c["accent"] if k < level else c["rule"]}"/>'
            for k in range(5)
        )
        tier_name = f"tier {TIERS[level - 1]}" if level else "unranked"
        out.append(
            ticks
            + f'<text x="{x + 56}" y="23" font-family="{MONO}" font-size="10" fill="{c["faint"]}">{tier_name}</text>'
            + f'<text x="{x}" y="66" font-family="{SERIF}" font-size="34" fill="{c["accent"]}">{esc(value)}</text>'
            + f'<text x="{x}" y="88" font-family="{MONO}" font-size="11" fill="{c["muted"]}">{esc(label)}</text>'
        )
    desc = "; ".join(f"{v} {l} (tier {lvl} of 5)" for v, l, lvl in marks) + f"; on GitHub {years // 365 or 1} year(s)"
    return svg_open(WIDTH, 100, "Trophy case", desc) + "  " + "".join(out) + "\n</svg>\n"


def main() -> int:
    login = load_profile()["handle"]
    data: dict | None = None
    errors: list[str] = []
    fetchers = (fetch_graphql, fetch_rest) if os.environ.get("GITHUB_TOKEN") else (fetch_rest,)
    for fetcher in fetchers:
        try:
            candidate = fetcher(login)
            problem = validate(candidate)
            if problem is None:
                data = candidate
                break
            errors.append(f"{fetcher.__name__}: {problem}")
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, KeyError, ValueError) as exc:
            errors.append(f"{fetcher.__name__}: {exc}")

    if data is None:
        existing = all((GENERATED_DIR / f"{o}-{m}.svg").exists() for o in OUTPUTS for m in MODES)
        print(f"stats refresh rejected ({'; '.join(errors)}); {'keeping previous snapshots' if existing else 'no snapshot yet'}")
        return 0 if existing else 1

    streak = current_streak()
    for mode in MODES:
        for name, svg in (
            ("stats", render_stats(data, mode)),
            ("languages", render_languages(data, mode)),
            ("trophies", render_trophies(data, streak, mode)),
        ):
            changed = write_if_changed(GENERATED_DIR / f"{name}-{mode}.svg", svg)
            print(f"{name}-{mode}.svg: {'updated' if changed else 'already current'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
