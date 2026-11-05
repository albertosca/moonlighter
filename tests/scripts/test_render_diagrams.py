import re
from pathlib import Path

import pytest
import render_diagrams

_DIAGRAM_SOURCES = Path(__file__).resolve().parents[2] / "assets/diagrams/src"


def test_tokens_are_replaced_per_theme():
    out = render_diagrams.render(
        '<line stroke="{{fg}}"/><path fill="{{accent}}"/>', render_diagrams.THEMES["dark"]
    )
    assert (
        out
        == f'<line stroke="{render_diagrams.THEMES["dark"]["fg"]}"/><path fill="{render_diagrams.THEMES["dark"]["accent"]}"/>'
    )


def test_amber_is_the_same_in_both_themes():
    assert (
        render_diagrams.THEMES["light"]["accent"]
        == render_diagrams.THEMES["dark"]["accent"]
        == "#E3A23B"
    )


def test_an_unknown_token_fails_loudly():
    with pytest.raises(KeyError, match="colour"):
        render_diagrams.render("{{colour}}", render_diagrams.THEMES["light"])


def test_every_shipped_source_renders_in_both_themes():
    sources = sorted(_DIAGRAM_SOURCES.glob("*.svg"))
    assert sources, "no diagram sources found"
    for source in sources:
        for theme in render_diagrams.THEMES.values():
            out = render_diagrams.render(source.read_text(), theme)
            assert "{{" not in out
            assert "<script" not in out
            assert "<style" not in out
            assert "foreignObject" not in out


def test_no_text_is_painted_in_a_low_contrast_token():
    # On the light ground muted measures 2.11:1 and accent 1.95:1 (WCAG asks
    # 4.5:1 for text). The amber stays on strokes; text uses the ink.
    low_contrast_text = re.compile(r'<text[^>]*fill="\{\{(?:muted|accent)\}\}"')
    sources = sorted(_DIAGRAM_SOURCES.glob("*.svg"))
    offenders = [source.name for source in sources if low_contrast_text.search(source.read_text())]
    assert offenders == []
