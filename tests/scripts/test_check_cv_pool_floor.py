import textwrap
from unittest.mock import patch

import check_cv_pool_floor
from moonlighter.application.cvgen.pool import load_pool

POOL_YAML = textwrap.dedent("""\
    experiences:
      - company: Trybe
        title: Dev
        period: "2023 -- 2026"
        location: BH
        bullets:
          - id: t-a
            angles: [backend]
            latex: 'Did A'
          - id: t-b
            angles: [backend]
            latex: 'Did B'
      - company: AppProva
        title: Eng
        period: "2017 -- 2019"
        location: BH
        bullets:
          - id: a-a
            angles: [backend]
            latex: 'Did C'
    """)
TEMPLATE = (
    "%%BASE_SUMMARY: The base summary line\n"
    "%%BASE_EXPERTISE: Elixir, React\n"
    "\\cvlistitem{%%SUMMARY%%}\n\\cvlistitem{%%TECHNICAL_EXPERTISE%%}\n"
    "%%EXPERIENCE%%\n%%OPEN_SOURCE%%\n"
)


def _pool(tmp_path):
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    return load_pool(pool_path)


def test_check_reports_the_real_page_count_when_pdflatex_is_available(tmp_path):
    pool = _pool(tmp_path)
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(
            check_cv_pool_floor,
            "compile_pdf",
            side_effect=lambda tex: tex.with_suffix(".pdf"),
        ),
        patch.object(check_cv_pool_floor, "page_count", return_value=1),
    ):
        assert check_cv_pool_floor.check(pool, TEMPLATE) == 1


def test_check_reports_a_floor_that_overflows(tmp_path):
    # The whole point of the script: the floor itself — not any one job's
    # selection — is what's measured here.
    pool = _pool(tmp_path)
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(
            check_cv_pool_floor,
            "compile_pdf",
            side_effect=lambda tex: tex.with_suffix(".pdf"),
        ),
        patch.object(check_cv_pool_floor, "page_count", return_value=2),
    ):
        assert check_cv_pool_floor.check(pool, TEMPLATE) == 2


def test_check_is_none_without_pdflatex(tmp_path):
    pool = _pool(tmp_path)
    with patch.object(check_cv_pool_floor, "latex_available", return_value=False):
        assert check_cv_pool_floor.check(pool, TEMPLATE) is None


def test_check_is_none_when_the_floor_itself_fails_to_compile(tmp_path):
    # A broken template (or a pool bullet with unescaped LaTeX that somehow
    # slipped past load_pool's guard) fails the same way a real generation
    # would — reported as "could not check", not crashed.
    pool = _pool(tmp_path)
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(check_cv_pool_floor, "compile_pdf", return_value=None),
    ):
        assert check_cv_pool_floor.check(pool, TEMPLATE) is None


def test_check_renders_every_experience_via_the_first_bullet_fallback(tmp_path):
    # Proves the floor selection is genuinely empty (bullets=()), not
    # accidentally selecting every bullet — render_cv's own fallback is what
    # produces "one bullet per experience", the exact thing being measured.
    pool = _pool(tmp_path)
    seen = {}

    def spy_compile(tex):
        seen["tex"] = tex.read_text()
        return tex.with_suffix(".pdf")

    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(check_cv_pool_floor, "compile_pdf", side_effect=spy_compile),
        patch.object(check_cv_pool_floor, "page_count", return_value=1),
    ):
        check_cv_pool_floor.check(pool, TEMPLATE)
    assert "Did A" in seen["tex"]  # Trybe's first bullet
    assert "Did B" not in seen["tex"]  # not the second — proves it's the floor
    assert "Did C" in seen["tex"]  # AppProva's only bullet


def test_main_prints_ok_and_exits_zero_when_the_floor_fits(tmp_path, capsys):
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    (template_directory / "cv-template.en.tex").write_text(TEMPLATE)
    config = {"cv": {"pool": str(pool_path), "template_dir": str(template_directory)}}
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(
            check_cv_pool_floor,
            "compile_pdf",
            side_effect=lambda tex: tex.with_suffix(".pdf"),
        ),
        patch.object(check_cv_pool_floor, "page_count", return_value=1),
    ):
        assert check_cv_pool_floor.main(config) == 0
    assert "1 page" in capsys.readouterr().out.lower()


def test_main_prints_a_warning_and_exits_nonzero_when_the_floor_overflows(tmp_path, capsys):
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    (template_directory / "cv-template.en.tex").write_text(TEMPLATE)
    config = {"cv": {"pool": str(pool_path), "template_dir": str(template_directory)}}
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(
            check_cv_pool_floor,
            "compile_pdf",
            side_effect=lambda tex: tex.with_suffix(".pdf"),
        ),
        patch.object(check_cv_pool_floor, "page_count", return_value=3),
    ):
        assert check_cv_pool_floor.main(config) != 0
    out = capsys.readouterr().out
    assert "3 pages" in out.lower() or "3" in out


def test_main_reports_when_the_check_could_not_run(tmp_path, capsys):
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    (template_directory / "cv-template.en.tex").write_text(TEMPLATE)
    config = {"cv": {"pool": str(pool_path), "template_dir": str(template_directory)}}
    with patch.object(check_cv_pool_floor, "latex_available", return_value=False):
        assert check_cv_pool_floor.main(config) != 0
    assert "pdflatex" in capsys.readouterr().out.lower()


def test_main_reports_when_no_pool_is_configured(tmp_path, capsys):
    assert check_cv_pool_floor.main({"cv": {}}) != 0
    assert "cv.pool" in capsys.readouterr().out


def test_main_reports_when_no_template_dir_is_configured(tmp_path, capsys):
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    assert check_cv_pool_floor.main({"cv": {"pool": str(pool_path)}}) != 0
    assert "template" in capsys.readouterr().out.lower()
