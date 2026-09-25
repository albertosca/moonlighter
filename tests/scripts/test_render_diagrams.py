import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _rd():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import render_diagrams

    return render_diagrams


def test_tokens_are_replaced_per_theme():
    rd = _rd()
    out = rd.render('<line stroke="{{fg}}"/><path fill="{{accent}}"/>', rd.THEMES["dark"])
    assert (
        out
        == f'<line stroke="{rd.THEMES["dark"]["fg"]}"/><path fill="{rd.THEMES["dark"]["accent"]}"/>'
    )


def test_amber_is_the_same_in_both_themes():
    rd = _rd()
    assert rd.THEMES["light"]["accent"] == rd.THEMES["dark"]["accent"] == "#E3A23B"


def test_an_unknown_token_fails_loudly():
    with pytest.raises(KeyError, match="colour"):
        _rd().render("{{colour}}", _rd().THEMES["light"])


def test_every_shipped_source_renders_in_both_themes():
    rd = _rd()
    sources = sorted((_SCRIPTS_DIR.parent / "assets/diagrams/src").glob("*.svg"))
    assert sources, "no diagram sources found"
    for source in sources:
        for theme in rd.THEMES.values():
            out = rd.render(source.read_text(), theme)
            assert (
                "{{" not in out
                and "<script" not in out
                and "<style" not in out
                and "foreignObject" not in out
            )


def test_no_text_is_painted_in_a_low_contrast_token():
    # On the light ground muted measures 2.11:1 and accent 1.95:1 (WCAG asks
    # 4.5:1 for text). The amber stays on strokes; text uses the ink.
    import re

    low_contrast_text = re.compile(r'<text[^>]*fill="\{\{(?:muted|accent)\}\}"')
    sources = sorted((_SCRIPTS_DIR.parent / "assets/diagrams/src").glob("*.svg"))
    offenders = [source.name for source in sources if low_contrast_text.search(source.read_text())]
    assert offenders == []
