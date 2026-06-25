import os
from pathlib import Path
from typing import Any

import yaml


def candidatador_home() -> Path:
    return Path(os.environ.get("CANDIDATADOR_HOME", "~/.candidatador")).expanduser()


def _learned_blocklist_path() -> Path:
    return candidatador_home() / "blocklist_learned.yaml"


DEFAULTS = {
    "brave_path": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "score_threshold": 6.5,
    "llm_model": "claude-sonnet-4-6",
    "eval_model": "claude-haiku-4-5-20251001",
    "slow_mo_ms": 300,
    "title_blocklist": [],
    # Máximo de avaliações LLM em paralelo no scan. Limita o burst de tokens e o
    # desperdício após o spend-limit (irmãs em voo). Com batching (scan_batch_size),
    # é o nº de LOTES em paralelo. Concorrência efetiva = scan_concurrency × scan_batch_size.
    "scan_concurrency": 5,
    # Vagas avaliadas por chamada LLM. O profile vai uma única vez por lote, cortando
    # re-transmissão por fator K. 1 desliga o batching (1 vaga por chamada).
    "scan_batch_size": 5,
    # CV por empresa. Caminhos relativos a CANDIDATADOR_HOME; match case-insensitive.
    # 'default' usado quando a empresa não tem entrada. Pode ser sobrescrito no
    # config.yaml local. Se o arquivo escolhido não existir, confirm_apply aborta.
    "cv": {
        "default": "",
        "by_company": {},
    },
    # Autorização de trabalho país-dependente. O candidato é autorizado a trabalhar
    # apenas no país de cidadania. Quando o país da vaga não é inferível com
    # confiança, o campo vira __NEEDS_REVIEW__ (decisão manual — nunca um chute).
    "work_authorization": {
        "citizenship_country": "",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
        "needs_review_sentinel": "__NEEDS_REVIEW__",
    },
}

_PATH_KEYS = ("browser_session_dir", "screenshots_dir", "db_path")


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load configuration from YAML file, merging with defaults.

    Expands home directory (~) paths for designated path keys.

    Args:
        config_path: Path to config.yaml file

    Returns:
        dict with merged config (defaults + overrides)
    """
    config_path = (
        Path(config_path) if config_path is not None else candidatador_home() / "config.yaml"
    )
    home = candidatador_home()
    config: dict[str, Any] = {
        **DEFAULTS,
        "browser_session_dir": str(home / "browser-session"),
        "screenshots_dir": str(home / "screenshots"),
        "db_path": str(home / "candidatador.db"),
    }
    if config_path.exists():
        user = yaml.safe_load(config_path.read_text()) or {}
        config.update(user)
    for key in _PATH_KEYS:
        config[key] = str(Path(config[key]).expanduser())

    # Merge learned blocklist (blocklist_learned.yaml) into title_blocklist
    learned = _learned_blocklist_path()
    if learned.exists():
        data = yaml.safe_load(learned.read_text()) or {}
        learned_patterns = data.get("title_blocklist", [])
        if learned_patterns:
            manual = config.get("title_blocklist", [])
            merged = list(dict.fromkeys(manual + learned_patterns))  # dedup, manual first
            config["title_blocklist"] = merged

    return config


def load_profile(profile_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load profile from YAML file.

    Args:
        profile_path: Path to profile.yaml file

    Returns:
        dict with profile data (skills, experience, preferences, criteria, etc.)
    """
    profile_path = (
        Path(profile_path) if profile_path is not None else candidatador_home() / "profile.yaml"
    )
    return yaml.safe_load(profile_path.read_text()) or {}


def load_company_list(path: str | Path | None = None, phase: str | None = None) -> dict[str, Any]:
    """Load company list from YAML file, optionally filtered by phase.

    O company_list.yaml organiza slugs por ATS e fase:
        greenhouse:
          phase1: [slug, ...]
          phase2: [slug, ...]

    Args:
        path: Path to company_list.yaml file
        phase: "phase1", "phase2", "phase3", ou None para todas as fases.

    Returns:
        dict: {source: [slug, ...]} (e.g., {"greenhouse": ["nubank", "ifoodcarreiras"]})
    """
    path = Path(path) if path is not None else candidatador_home() / "company_list.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}

    result = {}
    for source, value in raw.items():
        if isinstance(value, list):
            # Formato legado: lista plana sem fases
            result[source] = value
        elif isinstance(value, dict):
            if phase:
                result[source] = value.get(phase, [])
            else:
                # Todas as fases concatenadas
                slugs = []
                for slugs_in_phase in value.values():
                    if isinstance(slugs_in_phase, list):
                        slugs.extend(slugs_in_phase)
                result[source] = slugs
        else:
            result[source] = []
    return result
