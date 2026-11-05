import textwrap

import pytest
from moonlighter.application.cvgen.pool import PoolError, load_pool

from tests.application.cvgen.pool.pool_files import write_pool_file


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
        load_pool(write_pool_file(tmp_path, broken))


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
        load_pool(write_pool_file(tmp_path, broken))


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
        load_pool(write_pool_file(tmp_path, broken))


def test_experience_missing_field_raises(tmp_path):
    broken = textwrap.dedent("""
        experiences:
          - title: T
            period: P
            location: L
            prose: "Some prose"
    """)
    with pytest.raises(PoolError, match="experience missing 'company'"):
        load_pool(write_pool_file(tmp_path, broken))


def test_non_mapping_experience_raises_pool_error(tmp_path):
    # The pool is hand-curated YAML: a stray '-' turns an entry into a bare
    # string. raw.get() would raise AttributeError, which escapes the caller's
    # `except PoolError` and takes the whole MCP tool call down.
    broken = textwrap.dedent("""
        experiences:
          - just a string
    """)
    with pytest.raises(PoolError, match="experience is not a mapping"):
        load_pool(write_pool_file(tmp_path, broken))


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
        load_pool(write_pool_file(tmp_path, broken))
