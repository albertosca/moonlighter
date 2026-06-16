import os
import yaml

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "brave_path": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "browser_session_dir": "~/.candidatador/browser-session",
    "screenshots_dir": "~/.candidatador/screenshots",
    "db_path": "~/.candidatador/candidatador.db",
    "score_threshold": 6.5,
    "llm_model": "claude-sonnet-4-6",
    "eval_model": "claude-haiku-4-5-20251001",
    "slow_mo_ms": 300,
    "title_blocklist": [],
    # CV por empresa. Caminhos relativos à raiz do projeto; match case-insensitive.
    # 'default' usado quando a empresa não tem entrada. Pode ser sobrescrito no
    # config.yaml local. Se o arquivo escolhido não existir, confirm_apply aborta.
    "cv": {
        "default": "profile/general/CV-updated.pdf",
        "by_company": {
            "nubank": "profile/nubank/cv-nu-staff.pdf",
            "airbnb": "profile/airbnb/cv-airbnb.pdf",
        },
    },
}

_PATH_KEYS = ("browser_session_dir", "screenshots_dir", "db_path")
_LEARNED_BLOCKLIST_PATH = os.path.join(_PROJECT_ROOT, "blocklist_learned.yaml")


def load_config(config_path: str = None) -> dict:
    """
    Load configuration from YAML file, merging with defaults.

    Expands home directory (~) paths for designated path keys.

    Args:
        config_path: Path to config.yaml file

    Returns:
        dict with merged config (defaults + overrides)
    """
    if config_path is None:
        config_path = os.path.join(_PROJECT_ROOT, "config.yaml")
    config = dict(DEFAULTS)
    if os.path.exists(config_path):
        with open(config_path) as f:
            user = yaml.safe_load(f) or {}
            config.update(user)
    for key in _PATH_KEYS:
        config[key] = os.path.expanduser(str(config[key]))

    # Merge learned blocklist (blocklist_learned.yaml) into title_blocklist
    if os.path.exists(_LEARNED_BLOCKLIST_PATH):
        with open(_LEARNED_BLOCKLIST_PATH) as f:
            learned = yaml.safe_load(f) or {}
        learned_patterns = learned.get("title_blocklist", [])
        if learned_patterns:
            manual = config.get("title_blocklist", [])
            merged = list(dict.fromkeys(manual + learned_patterns))  # dedup, manual first
            config["title_blocklist"] = merged

    return config


def load_profile(profile_path: str = None) -> dict:
    """
    Load profile from YAML file.

    Args:
        profile_path: Path to profile.yaml file

    Returns:
        dict with profile data (skills, experience, preferences, criteria, etc.)
    """
    if profile_path is None:
        profile_path = os.path.join(_PROJECT_ROOT, "profile", "profile.yaml")
    with open(profile_path) as f:
        return yaml.safe_load(f) or {}


def load_company_list(path: str = None, phase: str | None = None) -> dict:
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
    if path is None:
        path = os.path.join(_PROJECT_ROOT, "company_list.yaml")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

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
