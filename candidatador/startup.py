import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass
class StartupWarning:
    level: Literal["error", "warn"]
    message: str


def validate_startup(
    config: dict,
    profile: dict,
    cv_path: Optional[str] = None,
) -> list[StartupWarning]:
    """
    Inspeciona o ambiente e retorna lista de avisos/erros de configuração.
    Nenhum aviso = tudo ok para rodar. Errors = funcionalidade crítica indisponível.
    cv_path: se None, procura em <project_root>/profile/cv.pdf
    """
    warnings: list[StartupWarning] = []

    # Profile vazio → avaliações LLM inúteis
    if not profile:
        warnings.append(StartupWarning(
            level="warn",
            message=(
                "profile/profile.yaml está vazio. "
                "Preencha skills, experiências e critérios para avaliações LLM úteis."
            ),
        ))

    # API key ausente → toda avaliação LLM retorna score=0.0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        warnings.append(StartupWarning(
            level="error",
            message=(
                "ANTHROPIC_API_KEY não encontrada no ambiente. "
                "scan_and_evaluate e apply_jobs não funcionarão."
            ),
        ))

    # CV ausente → confirm_apply vai falhar
    if cv_path is None:
        cv_path = str(Path(__file__).parent.parent / "profile" / "cv.pdf")
    if not Path(cv_path).exists():
        warnings.append(StartupWarning(
            level="warn",
            message=(
                "Arquivo cv.pdf não encontrado. "
                "confirm_apply vai falhar. Adicione seu currículo ao diretório correto."
            ),
        ))

    # Brave ausente → LinkedIn scan e candidaturas via browser não funcionam
    brave_path = config.get("brave_path", "")
    if brave_path and not Path(brave_path).exists():
        warnings.append(StartupWarning(
            level="warn",
            message=(
                f"Brave não encontrado em {brave_path}. "
                "Scan LinkedIn e candidaturas via browser não funcionarão. "
                "Instale o Brave ou ajuste brave_path em config.yaml."
            ),
        ))

    return warnings
