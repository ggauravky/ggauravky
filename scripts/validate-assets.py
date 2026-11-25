"""Quality gate for the profile: run locally and in CI before anything is committed.

Fails on: unparseable SVG XML; embedded base64 images; blue hues anywhere in assets,
profile data or workflow colour args; stroked rounded-rect "card" frames; camo/proxy
hosts; anything other than exactly one streak block; README images that are not
committed local files.
"""

from __future__ import annotations

import colorsys
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SVG_NS = "{http://www.w3.org/2000/svg}"
HEX = re.compile(r"(?<![0-9A-Za-z&])#?([0-9A-Fa-f]{6})(?![0-9A-Za-z])")
CAMO = re.compile(r"camo\.githubusercontent\.com|githubusercontent\.com/[0-9a-f]{40}", re.I)
OPTIONAL_UNTIL_FIRST_RUN = ("assets/generated/snake-",)


def is_blue(hex6: str) -> bool:
    r, g, b = (int(hex6[i : i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return 190 <= h * 360 <= 260 and s > 0.15 and 0.08 < l < 0.95


def check_colors(path: Path, text: str, errors: list[str], strict_hex: bool) -> None:
    candidates = re.findall(r"#([0-9A-Fa-f]{6})\b", text) if strict_hex else [m.group(1) for m in HEX.finditer(text)]
    blues = sorted({h.upper() for h in candidates if is_blue(h)})
    if blues:
        errors.append(f"{path.relative_to(ROOT)}: blue colour(s) {', '.join('#' + b for b in blues)}")


def check_svg(path: Path, errors: list[str]) -> None:
    rel = path.relative_to(ROOT)
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        errors.append(f"{rel}: invalid XML ({exc})")
        return
    if re.search(r"data:image/[a-z+]+;base64,", text) or re.search(r"[A-Za-z0-9+/]{2048,}={0,2}", text):
        errors.append(f"{rel}: embedded base64 payload")
    if path.stat().st_size > 600_000:
        errors.append(f"{rel}: {path.stat().st_size} bytes is too heavy")
    for el in root.iter(f"{SVG_NS}image"):
        errors.append(f"{rel}: raster <image> element is not allowed (no photos)")
        break
    for rect in root.iter(f"{SVG_NS}rect"):
        stroke = rect.get("stroke")
        if stroke and stroke != "none" and rect.get("stroke-opacity", "1") not in ("0", "0.0") and float(rect.get("width", 0) or 0) > 40 and float(rect.get("height", 0) or 0) > 20:
            errors.append(f"{rel}: stroked container rect (boxed card pattern)")
            break
    # Streak card comes from a third party; it is the one SVG we check by computed hex only.
    check_colors(path, text, errors, strict_hex=True)


def check_readme(errors: list[str]) -> None:
    text = README.read_text(encoding="utf-8")
    if len(re.findall(r"<!-- streak:start -->.*?<!-- streak:end -->", text, re.S)) != 1:
        errors.append("README.md: must contain exactly one streak block")
    if text.count("<!-- streak:start -->") != 1 or text.count("<!-- streak:end -->") != 1:
        errors.append("README.md: duplicate streak markers")
    if CAMO.search(text):
        errors.append("README.md: camo/proxy URL found")
    for src in re.findall(r'(?:src|srcset)="([^"]+)"', text):
        if not src.startswith("./assets/"):
            errors.append(f"README.md: image source is not a committed local asset: {src}")
            continue
        target = ROOT / src[2:]
        if not target.exists():
            msg = f"README.md: image file missing: {src}"
            if src[2:].startswith(OPTIONAL_UNTIL_FIRST_RUN):
                print(f"warning: {msg} (produced by the snake workflow)")
            else:
                errors.append(msg)
    if re.search(r"\{\{[^}]+\}\}", text):
        errors.append("README.md: unresolved template placeholder")


def main() -> int:
    errors: list[str] = []
    svgs = sorted((ROOT / "assets").rglob("*.svg"))
    for svg in svgs:
        check_svg(svg, errors)
    for raster in (ROOT / "assets").rglob("*"):
        if raster.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            errors.append(f"{raster.relative_to(ROOT)}: raster image asset (no photos)")
    profile = ROOT / "data" / "profile.json"
    ptext = profile.read_text(encoding="utf-8")
    if CAMO.search(ptext):
        errors.append("data/profile.json: camo/proxy URL configured")
    check_colors(profile, ptext, errors, strict_hex=False)
    check_colors(ROOT / "scripts" / "profile_theme.py", (ROOT / "scripts" / "profile_theme.py").read_text(encoding="utf-8"), errors, True)
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        check_colors(wf, wf.read_text(encoding="utf-8"), errors, strict_hex=True)
    check_readme(errors)
    if errors:
        print("Validation failed:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK: {len(svgs)} SVGs valid; README, profile data and workflows pass all checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
