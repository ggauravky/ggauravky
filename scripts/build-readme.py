"""Build README.md from templates/README.template.md and data/profile.json (single source of truth)."""

from __future__ import annotations

import re
import sys

from profile_theme import ROOT, STREAK_END, STREAK_START, esc, load_profile, picture, streak_block

TEMPLATE = ROOT / "templates" / "README.template.md"
README = ROOT / "README.md"
LINK_LABELS = {
    "portfolio": "Portfolio",
    "linkedin": "LinkedIn",
    "github": "GitHub",
    "email": "Email",
    "leetcode": "LeetCode",
    "geeksforgeeks": "GeeksforGeeks",
}
SEP = "&nbsp;&nbsp;·&nbsp;&nbsp;"


def link_row(links: dict, keys: tuple[str, ...]) -> str:
    return SEP.join(f'<a href="{esc(links[k])}">{LINK_LABELS[k]}&nbsp;↗</a>' for k in keys if k in links)


def projects(p: dict) -> str:
    blocks: list[str] = []
    for proj in p["featuredProjects"]:
        links = []
        if proj.get("live"):
            links.append(f"[Live ↗]({proj['live']})")
        links.append(f"[Source ↗]({proj['repository']})")
        alt = f"{proj['name']} — {proj['category']}. {proj['summary']} Stack: {', '.join(proj['stack'])}."
        plate = picture("projects/" + proj["slug"], alt)
        blocks.append(plate + "\n\n" + " · ".join(links))
    return "\n\n<br />\n\n".join(blocks)


def existing_streak_block() -> str | None:
    """Keep whatever state update-streak.py last chose (healthy or fallback)."""
    if not README.exists():
        return None
    match = re.search(re.escape(STREAK_START) + r".*?" + re.escape(STREAK_END), README.read_text(encoding="utf-8"), re.S)
    return match.group(0) if match else None


def render(p: dict) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    journey_alt = "; ".join(
        [f"Now: {p['role']['title']} at {p['role']['company']}"]
        + [f"{e['credential']}, {e['institution']}" for e in p["education"]]
    )
    scalars = {
        "name": p["name"],
        "title": p["title"],
        "location": p["location"],
        "handle": p["handle"],
        "stack_labels": ", ".join(s["label"] for s in p.get("stack", [])),
        "journey_alt": journey_alt,
    }
    for key, value in scalars.items():
        text = text.replace("{{" + key + "}}", value)
    text = re.sub(
        r"\{\{picture:([a-z/\-]+)\|([^|]*)\|([0-9%]+)\}\}",
        lambda m: picture(m.group(1), m.group(2), m.group(3)),
        text,
    )
    blocks = {
        "link_row": link_row(p["links"], ("portfolio", "linkedin", "email", "github")),
        "streak_block": existing_streak_block() or streak_block(),
        "summary": p.get("summary", ""),
        "capabilities": "\n".join(
            f"- **{c['name']}** — {c['detail']} <sub>{c['tools']}</sub>" for c in p.get("capabilities", [])
        ),
        "projects": projects(p),
        "focus": "\n".join(f"- {item}" for item in p.get("focus", [])),
        "connect_row": link_row(p["links"], ("linkedin", "portfolio", "email", "leetcode", "geeksforgeeks")),
    }
    for key, value in blocks.items():
        text = text.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{[^}]+\}\}", text)
    if leftover:
        raise RuntimeError(f"unresolved template placeholders: {leftover}")
    return text


def main() -> int:
    output = render(load_profile())
    if README.exists() and README.read_text(encoding="utf-8") == output:
        print("README.md already current")
        return 0
    README.write_text(output, encoding="utf-8", newline="\n")
    print("README.md rebuilt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
