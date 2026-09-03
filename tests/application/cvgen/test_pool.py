import textwrap
from pathlib import Path

import pytest
from moonlighter.application.cvgen.pool import CVPool, PoolError, load_pool

VALID = textwrap.dedent("""
    experiences:
      - company: Trybe
        title: "Senior Software Developer"
        period: "Jan 2023 -- Jul 2026"
        location: "Belo Horizonte, Brazil"
        bullets:
          - id: trybe-ic-evaluations
            angles: [backend]
            latex: 'Contributed to \\textbf{38M+ evaluations}'
      - company: IGTI
        id: igti-prose
        title: "Professor"
        period: "Jan 2018 -- Dec 2019"
        location: "Belo Horizonte, Brazil"
        prose: "Taught ML in MBA programs."
        angles: [ai, education]
    open_source:
      - id: oss-moonlighter
        angles: [ai, backend]
        latex: '\\textbf{moonlighter} pipeline'
    summary_facts:
      - "Years of experience: compute from career_started"
""")


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "cv-pool.yaml"
    p.write_text(content)
    return p


def test_loads_a_valid_pool(tmp_path):
    pool = load_pool(_write(tmp_path, VALID))
    assert isinstance(pool, CVPool)
    assert pool.experiences[0].bullets[0].id == "trybe-ic-evaluations"
    assert pool.experiences[1].prose == "Taught ML in MBA programs."
    assert pool.experiences[1].prose_id == "igti-prose"
    assert pool.open_source[0].id == "oss-moonlighter"
    assert "Years of experience: compute from career_started" in pool.summary_facts


def test_bullet_ids_cover_bullets_open_source_and_prose(tmp_path):
    pool = load_pool(_write(tmp_path, VALID))
    assert pool.bullet_ids() == {"trybe-ic-evaluations", "oss-moonlighter", "igti-prose"}


def test_missing_file_raises_pool_error(tmp_path):
    with pytest.raises(PoolError, match="not found"):
        load_pool(tmp_path / "nope.yaml")


def test_duplicate_ids_raise(tmp_path):
    dup = VALID.replace("oss-moonlighter", "trybe-ic-evaluations")
    with pytest.raises(PoolError, match="duplicate"):
        load_pool(_write(tmp_path, dup))


def test_experience_without_bullets_or_prose_raises(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: T
            period: P
            location: L
    """)
    with pytest.raises(PoolError, match="bullets or prose"):
        load_pool(_write(tmp_path, broken))


def test_unparseable_yaml_raises(tmp_path):
    with pytest.raises(PoolError, match="parse"):
        load_pool(_write(tmp_path, "experiences: ["))


def test_bullet_missing_id_raises(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: T
            period: P
            location: L
            bullets:
              - latex: 'some latex'
    """)
    with pytest.raises(PoolError, match="bullet missing 'id'"):
        load_pool(_write(tmp_path, broken))


def test_bullet_missing_latex_raises(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: T
            period: P
            location: L
            bullets:
              - id: test-id
    """)
    with pytest.raises(PoolError, match="bullet missing 'latex'"):
        load_pool(_write(tmp_path, broken))


def test_open_source_bullet_missing_id_raises(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: T
            period: P
            location: L
            prose: "Some prose"
        open_source:
          - latex: 'some latex'
    """)
    with pytest.raises(PoolError, match="bullet missing 'id'"):
        load_pool(_write(tmp_path, broken))


def test_experience_missing_field_raises(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - title: T
            period: P
            location: L
            prose: "Some prose"
    """)
    with pytest.raises(PoolError, match="experience missing 'company'"):
        load_pool(_write(tmp_path, broken))


def test_non_mapping_experience_raises_pool_error(tmp_path):
    # The pool is hand-curated YAML: a stray '-' turns an entry into a bare
    # string. raw.get() would raise AttributeError, which escapes the caller's
    # `except PoolError` and takes the whole MCP tool call down.
    broken = textwrap.dedent("""
        experiences:
          - just a string
    """)
    with pytest.raises(PoolError, match="experience is not a mapping"):
        load_pool(_write(tmp_path, broken))


def test_non_mapping_bullet_raises_pool_error(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: T
            period: P
            location: L
            bullets:
              - just a string
    """)
    with pytest.raises(PoolError, match="bullet is not a mapping"):
        load_pool(_write(tmp_path, broken))


def test_pool_with_no_experiences_raises(tmp_path):
    broken = textwrap.dedent("""
        open_source: []
        summary_facts: []
    """)
    with pytest.raises(PoolError, match="no 'experiences'"):
        load_pool(_write(tmp_path, broken))


def test_prose_ids_lists_only_prose_entries(tmp_path):
    pool = load_pool(_write(tmp_path, VALID))
    assert pool.prose_ids() == {"igti-prose"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "R&D Engineer"),
        ("title", "Professor (ML/DL MBA) & Coordination Board"),
        ("company", "100% Digital"),
        ("location", "Belo_Horizonte"),
        ("period", "Jan 2023 -- Jul 2026 #remote"),
    ],
)
def test_unescaped_tex_special_in_a_fixed_field_raises(tmp_path, field, value):
    # Fixed fields go into \cventry{} verbatim. The seed draft carried "R&D
    # Engineer": every generation compiled to "Missing } inserted", was
    # discarded, and the application silently used the default CV at one LLM
    # call per prepare. Found by compiling, not by reading; caught here now.
    broken = textwrap.dedent(f"""
        experiences:
          - company: X
            title: T
            period: P
            location: L
            {field}: "{value}"
            prose: "Some prose"
    """)
    with pytest.raises(PoolError, match=f"unescaped .* in '{field}'"):
        load_pool(_write(tmp_path, broken))


def test_single_backslash_escapes_the_special(tmp_path):
    # \& = escaped ampersand (safe)
    ok = VALID.replace('title: "Professor"', 'title: "R\\\\&D"')
    pool = load_pool(_write(tmp_path, ok))
    assert pool.experiences[1].title == r"R\&D"


def test_double_backslash_leaves_special_unescaped(tmp_path):
    # \\& = line break + unescaped ampersand (breaks LaTeX, must be caught)
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: "R\\\\\\\\&D"
            period: P
            location: L
            prose: "Some prose"
    """)
    with pytest.raises(PoolError, match="unescaped"):
        load_pool(_write(tmp_path, broken))


def test_triple_backslash_escapes_after_line_break(tmp_path):
    # \\\& = line break + escaped ampersand (safe)
    ok = VALID.replace('title: "Professor"', 'title: "R\\\\\\\\\\\\&D"')
    pool = load_pool(_write(tmp_path, ok))
    assert pool.experiences[1].title == r"R\\\&D"


def test_escaped_specials_in_a_fixed_field_are_fine(tmp_path):
    ok = VALID.replace('title: "Professor"', 'title: "R\\\\&D \\\\& 100\\\\% Professor"')
    pool = load_pool(_write(tmp_path, ok))
    assert pool.experiences[1].title == r"R\&D \& 100\% Professor"


def test_an_experience_with_both_prose_and_bullets_raises(tmp_path):
    # render's prose branch returns early, so the bullets were silently dropped
    # while their ids were still advertised to the model.
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: T
            period: P
            location: L
            prose: "Some prose"
            bullets:
              - id: x-a
                angles: [backend]
                latex: 'A'
    """)
    with pytest.raises(PoolError, match="both prose and bullets"):
        load_pool(_write(tmp_path, broken))
