"""Tests for the CV-pool bootstrap (draft_pool, fill_template, bootstrap_cv_pool)."""

import importlib.resources


def test_the_example_template_and_pool_ship_as_package_data():
    # Proves the files are reachable the way fill_template()/draft_pool() (Task 6)
    # will read them -- importlib.resources, not a hardcoded filesystem path that
    # only works from a repo checkout. This is the packaging gap the spec's
    # mid-planning correction exists to close.
    templates = importlib.resources.files("moonlighter.application.cvgen.templates")
    pool_text = (templates / "cv-pool.example.yaml").read_text()
    template_text = (templates / "cv-template.en.example.tex").read_text()
    assert "experiences:" in pool_text
    assert "{{NAME_FIRST}}" in template_text
    assert "%%SUMMARY%%" in template_text
