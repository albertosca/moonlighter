import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from candidatador.core.config import browser_executable


@dataclass
class StartupWarning:
    level: Literal["error", "warn"]
    message: str


def validate_startup(
    config: dict[str, Any],
    profile: dict[str, Any],
    cv_path: str | None = None,
) -> list[StartupWarning]:
    """Inspeciona o ambiente e devolve os avisos/erros de configuração. Lista vazia =
    tudo ok. 'error' = funcionalidade crítica indisponível.
    cv_path: se None, procura em <project_root>/profile/cv.pdf."""
    cv = cv_path or str(Path(__file__).parent.parent / "profile" / "cv.pdf")
    checks = [
        _check_profile(profile),
        _check_api_key(config),
        _check_cv(cv),
        _check_browser(config),
    ]
    return [warning for warning in checks if warning is not None]


def _check_profile(profile: dict[str, Any]) -> StartupWarning | None:
    """Profile vazio → avaliações LLM inúteis."""
    if profile:
        return None
    return StartupWarning(
        "warn",
        "profile/profile.yaml está vazio. "
        "Preencha skills, experiências e critérios para avaliações LLM úteis.",
    )


def _check_api_key(config: dict[str, Any]) -> StartupWarning | None:
    """API key ausente → toda avaliação LLM retorna score=0.0. Só é necessária no
    backend 'api'; com llm_backend='cli' usa-se o `claude` CLI."""
    if config.get("llm_backend") == "cli" or os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return StartupWarning(
        "error",
        "ANTHROPIC_API_KEY não encontrada no ambiente. "
        "scan_and_evaluate e apply_jobs não funcionarão.",
    )


def _check_cv(cv_path: str) -> StartupWarning | None:
    """CV ausente → confirm_apply vai falhar."""
    if Path(cv_path).exists():
        return None
    return StartupWarning(
        "warn",
        "Arquivo cv.pdf não encontrado. "
        "confirm_apply vai falhar. Adicione seu currículo ao diretório correto.",
    )


def _check_browser(config: dict[str, Any]) -> StartupWarning | None:
    """Browser ausente → LinkedIn scan e candidaturas via browser não funcionam."""
    browser_path = browser_executable(config)
    if not browser_path or Path(browser_path).exists():
        return None
    return StartupWarning(
        "warn",
        f"Browser não encontrado em {browser_path}. "
        "Scan LinkedIn e candidaturas via browser não funcionarão. "
        "Instale o browser (Chrome/Chromium/Brave) ou ajuste browser_path em config.yaml.",
    )
