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
    "slow_mo_ms": 300,
}

_PATH_KEYS = ("browser_session_dir", "screenshots_dir", "db_path")


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


def load_company_list(path: str = None) -> dict:
    """
    Load company list from YAML file.

    Args:
        path: Path to company_list.yaml file

    Returns:
        dict: {source: [slug, ...]} (e.g., {"greenhouse": ["stripe", "linear"], ...})
    """
    if path is None:
        path = os.path.join(_PROJECT_ROOT, "company_list.yaml")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}
