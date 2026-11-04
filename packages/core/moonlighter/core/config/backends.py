"""The llm_backend setting: accepted values, the validated reader and the Codex model check."""

from typing import Any

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.errors import ConfigError

LLM_BACKENDS = ("cli", "api", "cursor", "codex")


def llm_backend(config: dict[str, Any]) -> str:
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


def require_codex_models(config: dict[str, Any]) -> None:
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
