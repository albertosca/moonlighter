"""The Config TypedDicts and the runtime _CONFIG_SCHEMA describe the same keys and types.

Two schemas by decision (spec 2026-11-23, decision 3): the runtime one keeps its
error messages and its bool-is-not-int rule, the TypedDict gives mypy the shape.
This test is what keeps them in step.
"""

import types
from collections.abc import Mapping
from typing import Any, get_args, get_origin, get_type_hints, is_typeddict

import pytest

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.model import Config
from moonlighter.core.config.validation import _CONFIG_SCHEMA, _NESTED_SCHEMAS

_LOAD_TIME_KEYS = {"browser_session_dir", "screenshots_dir"}
# Indexed with a variable below; mypy refuses a non-literal key on the TypedDict itself.
_DEFAULTS: Mapping[str, Any] = DEFAULTS


def _runtime_tuple(annotation: Any) -> tuple[type, ...]:
    if annotation is float:
        return (int, float)
    if is_typeddict(annotation):
        return (dict,)
    origin = get_origin(annotation)
    if origin is types.UnionType:
        return tuple(
            member for argument in get_args(annotation) for member in _runtime_tuple(argument)
        )
    if origin is not None:
        return (origin,)
    return (annotation,)


def _schema_of(typed_mapping: Any) -> dict[str, tuple[type, ...]]:
    return {key: _runtime_tuple(value) for key, value in get_type_hints(typed_mapping).items()}


def test_config_matches_the_runtime_schema():
    assert _schema_of(Config) == _CONFIG_SCHEMA


@pytest.mark.parametrize("block", sorted(_NESTED_SCHEMAS))
def test_each_nested_block_matches_its_runtime_schema(block):
    assert _schema_of(get_type_hints(Config)[block]) == _NESTED_SCHEMAS[block]


def test_required_keys_are_the_ones_loading_guarantees():
    assert Config.__required_keys__ == set(_DEFAULTS) | _LOAD_TIME_KEYS


@pytest.mark.parametrize("block", sorted(_NESTED_SCHEMAS))
def test_each_nested_block_requires_exactly_its_defaults(block):
    assert get_type_hints(Config)[block].__required_keys__ == set(_DEFAULTS[block])
