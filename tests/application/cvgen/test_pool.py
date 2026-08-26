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


def test_pool_with_no_experiences_raises(tmp_path):
    broken = textwrap.dedent("""
        open_source: []
        summary_facts: []
    """)
    with pytest.raises(PoolError, match="no 'experiences'"):
        load_pool(_write(tmp_path, broken))
