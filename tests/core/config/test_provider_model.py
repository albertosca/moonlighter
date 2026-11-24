"""`provider/model`: the only model form `opencode run -m` accepts."""

import pytest

from moonlighter.core.config.backends import is_provider_model


@pytest.mark.parametrize(
    "model", ["anthropic/claude-sonnet-5-5", "fake/echo", "openrouter/meta/llama-4"]
)
def test_a_provider_and_a_model_are_accepted(model):
    assert is_provider_model(model)


@pytest.mark.parametrize("model", ["", "gpt-5", "/echo", "fake/", " / ", "  ", 5, None])
def test_anything_without_both_sides_is_refused(model):
    assert not is_provider_model(model)


@pytest.mark.parametrize(
    "model", [" anthropic/x", "anthropic/x ", "anthropic /x", "anthropic/ x", "a/b\n"]
)
def test_whitespace_is_refused_because_it_reaches_opencode_as_typed(model):
    assert not is_provider_model(model)
