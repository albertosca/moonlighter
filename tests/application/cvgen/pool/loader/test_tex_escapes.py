import textwrap

import pytest

from moonlighter.application.cvgen.pool.loader import PoolError, load_pool
from tests.application.cvgen.pool.loader.pool_files import VALID_POOL_YAML, write_pool_file


@pytest.mark.parametrize(
    ("field", "value"),
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
        load_pool(write_pool_file(tmp_path, broken))


def test_single_backslash_escapes_the_special(tmp_path):
    # \& = escaped ampersand (safe)
    is_ok = VALID_POOL_YAML.replace('title: "Professor"', 'title: "R\\\\&D"')
    pool = load_pool(write_pool_file(tmp_path, is_ok))
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
        load_pool(write_pool_file(tmp_path, broken))


def test_triple_backslash_escapes_after_line_break(tmp_path):
    # \\\& = line break + escaped ampersand (safe)
    is_ok = VALID_POOL_YAML.replace('title: "Professor"', 'title: "R\\\\\\\\\\\\&D"')
    pool = load_pool(write_pool_file(tmp_path, is_ok))
    assert pool.experiences[1].title == r"R\\\&D"


def test_escaped_specials_in_a_fixed_field_are_fine(tmp_path):
    is_ok = VALID_POOL_YAML.replace(
        'title: "Professor"', 'title: "R\\\\&D \\\\& 100\\\\% Professor"'
    )
    pool = load_pool(write_pool_file(tmp_path, is_ok))
    assert pool.experiences[1].title == r"R\&D \& 100\% Professor"
