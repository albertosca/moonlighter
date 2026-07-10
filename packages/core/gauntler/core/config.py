import os
from pathlib import Path
from typing import Any

import yaml


def gauntler_home() -> Path:
    return Path(os.environ.get("GAUNTLER_HOME", "~/.gauntler")).expanduser()


def _learned_blocklist_path() -> Path:
    return gauntler_home() / "blocklist_learned.yaml"


def browser_executable(config: dict[str, Any]) -> str:
    """Caminho do executável do browser. Lê 'browser_path'; cai para 'brave_path'
    (chave legada) se browser_path estiver vazio."""
    path: str = config.get("browser_path") or config.get("brave_path", "")
    return path


DEFAULTS = {
    # Caminho do executável do browser (Chrome/Chromium/Brave). Vazio por padrão:
    # configure browser_path no config.yaml. Aceita brave_path (legado) como fallback.
    "browser_path": "",
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
    # CV por empresa. Caminhos relativos a GAUNTLER_HOME; match case-insensitive.
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

_PATH_KEYS = ("browser_session_dir", "screenshots_dir")


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
        Path(config_path) if config_path is not None else gauntler_home() / "config.yaml"
    )
    home = gauntler_home()
    config: dict[str, Any] = {
        **DEFAULTS,
        "browser_session_dir": str(home / "browser-session"),
        "screenshots_dir": str(home / "screenshots"),
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
        Path(profile_path) if profile_path is not None else gauntler_home() / "profile.yaml"
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
    path = Path(path) if path is not None else gauntler_home() / "company_list.yaml"
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


_HARDEN_FILES = ("gauntler.db", "profile.yaml", "config.yaml", "app.log", "blocklist_learned.yaml")
_HARDEN_DIRS = ("browser-session", "screenshots")


def harden_permissions() -> list[str]:
    """Set 0600/0700 on the sensitive files/subdirectories under ~/.gauntler
    (S-07): gauntler.db, profile.yaml and config.yaml carry full PII;
    browser-session/ holds cookies equivalent to LinkedIn credentials.
    Best-effort and never raises — a permission error becomes a warning,
    since the server must stay up even on an unusual filesystem/ACL setup."""
    home = gauntler_home()
    warnings: list[str] = []
    for name in _HARDEN_FILES:
        path = home / name
        if path.exists():
            try:
                path.chmod(0o600)
            except OSError as e:
                warnings.append(f"could not restrict permissions on {path}: {e}")
    for name in _HARDEN_DIRS:
        path = home / name
        if path.exists():
            try:
                path.chmod(0o700)
            except OSError as e:
                warnings.append(f"could not restrict permissions on {path}: {e}")
    return warnings
