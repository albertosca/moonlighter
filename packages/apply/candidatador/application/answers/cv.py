"""Resolução do arquivo de CV por empresa (a partir de config['cv'])."""

from pathlib import Path
from typing import Any

from candidatador.core.config import candidatador_home


class CVNotFoundError(Exception):
    """O arquivo de CV resolvido para a empresa não existe no disco."""


def resolve_cv_path(company: str, config: dict[str, Any]) -> str:
    """
    Resolve o caminho do CV para a empresa a partir de config['cv'].
    Match por empresa é case-insensitive. Cai no 'default' quando não há
    mapeamento. Caminhos relativos são resolvidos a partir de CANDIDATADOR_HOME.
    Levanta CVNotFoundError se o arquivo escolhido não existir (nunca sobe
    um CV errado em silêncio).
    """
    cv_cfg = config.get("cv", {}) or {}
    by_company = {k.lower(): v for k, v in (cv_cfg.get("by_company", {}) or {}).items()}
    rel = by_company.get((company or "").lower(), cv_cfg.get("default"))
    if not rel:
        raise CVNotFoundError(
            f"Sem CV mapeado para '{company}' e sem 'cv.default' em config. Verifique config.yaml."
        )
    path = Path(rel)
    if not path.is_absolute():
        path = candidatador_home() / path
    if not path.exists():
        raise CVNotFoundError(
            f"CV para '{company}' não encontrado em {path}. Verifique o mapeamento 'cv' na config."
        )
    return str(path)
