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


def test_main_writes_a_light_and_a_dark_file_per_source_into_the_diagrams_directory(
    tmp_path, monkeypatch, capsys
):
    source_directory = tmp_path / "src"
    source_directory.mkdir()
    (source_directory / "b.svg").write_text('<rect fill="{{ground}}"/>')
    (source_directory / "a.svg").write_text('<rect stroke="{{fg}}"/>')
    (source_directory / "notes.txt").write_text("{{ignored}}")
    monkeypatch.setattr(render_diagrams, "_DIAGRAMS_DIR", tmp_path)

    assert render_diagrams.main() == 0

    assert capsys.readouterr().out == (
        "wrote a-light.svg\nwrote a-dark.svg\nwrote b-light.svg\nwrote b-dark.svg\n"
    )
    assert sorted(path.name for path in tmp_path.glob("*.svg")) == [
        "a-dark.svg",
        "a-light.svg",
        "b-dark.svg",
        "b-light.svg",
    ]
    assert (tmp_path / "a-light.svg").read_text() == '<rect stroke="#1F2B47"/>'
    assert (tmp_path / "b-dark.svg").read_text() == '<rect fill="#1F2B47"/>'


def test_main_stops_with_an_error_on_an_unknown_token_after_writing_earlier_files(
    tmp_path, monkeypatch
):
    source_directory = tmp_path / "src"
    source_directory.mkdir()
    (source_directory / "a.svg").write_text("{{fg}}")
    (source_directory / "b.svg").write_text("{{nope}}")
    monkeypatch.setattr(render_diagrams, "_DIAGRAMS_DIR", tmp_path)

    with pytest.raises(KeyError, match="nope"):
        render_diagrams.main()

    assert (tmp_path / "a-dark.svg").exists()
    assert not (tmp_path / "b-light.svg").exists()


def test_main_renders_the_sources_in_name_order_whatever_order_the_filesystem_lists_them(
    tmp_path, monkeypatch, capsys
):
    source_directory = tmp_path / "src"
    source_directory.mkdir()
    for name in ("a", "b", "c"):
        (source_directory / f"{name}.svg").write_text("{{fg}}")
    real_glob = Path.glob
    monkeypatch.setattr(
        Path, "glob", lambda self, pattern: iter(sorted(real_glob(self, pattern), reverse=True))
    )
    monkeypatch.setattr(render_diagrams, "_DIAGRAMS_DIR", tmp_path)

    render_diagrams.main()

    assert capsys.readouterr().out.splitlines() == [
        f"wrote {name}-{theme}.svg" for name in ("a", "b", "c") for theme in ("light", "dark")
    ]
