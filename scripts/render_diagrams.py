"""Renders each diagram source (assets/diagrams/src/*.svg, with {{token}} colours) into a
light and a dark SVG. Two files instead of CSS media queries: an SVG shown through
<img> on GitHub does not inherit the page's colours, and <picture> swaps files by the
reader's colour scheme.

Usage:
    python scripts/render_diagrams.py
"""

import re
import sys
from pathlib import Path

THEMES: dict[str, dict[str, str]] = {
    "light": {"fg": "#1F2B47", "muted": "#9AA8C4", "accent": "#E3A23B", "ground": "#EEF1F6"},
    "dark": {"fg": "#EEF1F6", "muted": "#9AA8C4", "accent": "#E3A23B", "ground": "#1F2B47"},
}
_TOKEN = re.compile(r"\{\{(\w+)\}\}")
_ROOT = Path(__file__).resolve().parents[1] / "assets" / "diagrams"


def render(template: str, theme: dict[str, str]) -> str:
    def value(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in theme:
            raise KeyError(f"unknown colour token: {token}")
        return theme[token]

    return _TOKEN.sub(value, template)


def main(argv: list[str]) -> int:
    for source in sorted((_ROOT / "src").glob("*.svg")):
        for name, theme in THEMES.items():
            (_ROOT / f"{source.stem}-{name}.svg").write_text(render(source.read_text(), theme))
            print(f"wrote {source.stem}-{name}.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
