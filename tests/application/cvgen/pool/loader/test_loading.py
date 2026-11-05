import textwrap

import pytest
from moonlighter.application.cvgen.pool.loader import CVPool, PoolError, load_pool

from tests.application.cvgen.pool.loader.pool_files import VALID_POOL_YAML, write_pool_file


def test_loads_a_valid_pool(tmp_path):
    pool = load_pool(write_pool_file(tmp_path, VALID_POOL_YAML))
    assert isinstance(pool, CVPool)
    assert pool.experiences[0].bullets[0].id == "trybe-ic-evaluations"
    assert pool.experiences[1].prose == "Taught ML in MBA programs."
    assert pool.experiences[1].prose_id == "igti-prose"
    assert pool.open_source[0].id == "oss-moonlighter"
    assert "Years of experience: compute from career_started" in pool.summary_facts


def test_bullet_ids_cover_bullets_open_source_and_prose(tmp_path):
    pool = load_pool(write_pool_file(tmp_path, VALID_POOL_YAML))
    assert pool.bullet_ids() == {"trybe-ic-evaluations", "oss-moonlighter", "igti-prose"}


def test_missing_file_raises_pool_error(tmp_path):
    with pytest.raises(PoolError, match="not found"):
        load_pool(tmp_path / "nope.yaml")


def test_duplicate_ids_raise(tmp_path):
    dup = VALID_POOL_YAML.replace("oss-moonlighter", "trybe-ic-evaluations")
    with pytest.raises(PoolError, match="duplicate"):
        load_pool(write_pool_file(tmp_path, dup))


def test_experience_without_bullets_or_prose_raises(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - company: X
            title: T
            period: P
            location: L
    """)
    with pytest.raises(PoolError, match="bullets or prose"):
        load_pool(write_pool_file(tmp_path, broken))


def test_unparseable_yaml_raises(tmp_path):
    with pytest.raises(PoolError, match="parse"):
        load_pool(write_pool_file(tmp_path, "experiences: ["))


def test_pool_with_no_experiences_raises(tmp_path):
    broken = textwrap.dedent("""
        open_source: []
        summary_facts: []
    """)
    with pytest.raises(PoolError, match="no 'experiences'"):
        load_pool(write_pool_file(tmp_path, broken))


def test_prose_ids_lists_only_prose_entries(tmp_path):
    pool = load_pool(write_pool_file(tmp_path, VALID_POOL_YAML))
    assert pool.prose_ids() == {"igti-prose"}


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
        load_pool(write_pool_file(tmp_path, broken))
