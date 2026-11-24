"""The llm_backend setting: accepted values, the validated reader and the model checks."""

from collections.abc import Mapping
from typing import Any

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.errors import ConfigError

LLM_BACKENDS = ("cli", "api", "cursor", "codex", "opencode")


def llm_backend(config: Mapping[str, Any]) -> str:
    """The configured LLM backend, validated.

    Single source of truth for every site that branches on the backend -- the
    caller factory and the startup checks -- so a warning can never describe a
    different backend from the one that will actually run. Raises ConfigError
    on anything outside LLM_BACKENDS: an unrecognized value used to fall
    through to 'api' in silence, which turned the typo 'CLI' into a demand for
    an API key the user had no reason to own.
    """
    backend: str = config.get("llm_backend", DEFAULTS["llm_backend"])
    if backend not in LLM_BACKENDS:
        raise ConfigError(
            f"config key 'llm_backend' must be one of {', '.join(LLM_BACKENDS)}, got {backend!r}"
        )
    return backend


def require_codex_models(config: Mapping[str, Any]) -> None:
    """Refuse an llm_model or eval_model the Codex CLI cannot run.

    The Codex CLI runs OpenAI models: a Claude id (the shipped defaults) or an
    empty one would fail on every call, so refuse it at load time instead.
    """
    for key in ("llm_model", "eval_model"):
        model = config.get(key, DEFAULTS[key])
        if not _is_codex_runnable(model):
            raise ConfigError(
                f"config key '{key}' must name a model the Codex CLI can run (for example "
                f"'gpt-6-luna') when llm_backend is 'codex', got {model!r}"
            )


def _is_codex_runnable(model: object) -> bool:
    return (
        isinstance(model, str)
        and bool(model.strip())
        and not model.strip().lower().startswith("claude")
    )


def is_provider_model(model: object) -> bool:
    """`provider/model`, both sides non-blank: the only form `opencode run -m` accepts.

    Whitespace is refused, not stripped: the value reaches `-m` and the startup
    check exactly as typed, so a stray space would pass here and fail there.
    """
    if not isinstance(model, str) or any(character.isspace() for character in model):
        return False
    provider, slash, name = model.partition("/")
    return bool(slash and provider and name)


def require_opencode_models(config: Mapping[str, Any]) -> None:
    """Refuse an llm_model or eval_model that is not `provider/model`.

    `opencode run -m` takes nothing else, and the shipped defaults are bare
    Claude ids: refuse them at load time instead of on every call mid-scan.
    """
    for key in ("llm_model", "eval_model"):
        model = config.get(key, DEFAULTS[key])
        if not is_provider_model(model):
            raise ConfigError(
                f"config key '{key}' must name an opencode model as provider/model (for "
                "example 'anthropic/claude-sonnet-5-5'; `opencode models` lists them) when "
                f"llm_backend is 'opencode', got {model!r}"
            )
