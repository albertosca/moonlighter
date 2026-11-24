"""pre_populate_answers with the default config, for tests that only vary fields and profile."""

from typing import Any

from moonlighter.application.answers.matching import field_map
from moonlighter.core.config.loading import build_config
from moonlighter.core.config.model import Config

DEFAULT_CONFIG = build_config({})


def pre_populate_answers(
    fields: list[str],
    profile: dict[str, Any],
    config: Config = DEFAULT_CONFIG,
    **job: str | None,
) -> dict[str, str]:
    return field_map.pre_populate_answers(fields, profile, config, **job)
