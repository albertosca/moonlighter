"""The learned blocklist file: the patterns build_blocklist saved, merged into title_blocklist.

load_config() reads blocklist_learned.yaml from the moonlighter home on every run.
"""

from pathlib import Path

import yaml

from moonlighter.core.config.paths import moonlighter_home


def learned_path() -> Path:
    return moonlighter_home() / "blocklist_learned.yaml"


def load_learned() -> list[str]:
    path = learned_path()
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    return list(data.get("title_blocklist", []))


def save_learned(patterns: list[str]) -> None:
    path = learned_path()
    existing = load_learned()
    merged = list(dict.fromkeys(existing + patterns))  # dedup, preserve order
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump({"title_blocklist": merged}, allow_unicode=True, default_flow_style=False)
    )


def confirm_write(patterns: list[str]) -> bool:
    """Asks for explicit confirmation before merging model-proposed patterns into the blocklist.

    S-10: an over-broad hallucinated pattern silently filters out good jobs, so the user's
    silence must NEVER count as consent.
    """
    print(f"\n{len(patterns)} new pattern(s) about to be saved:")
    for pattern in patterns:
        print(f"  - {pattern!r}")
    answer = input("Confirm save? [y/N] ").strip().lower()
    return answer in ("y", "yes", "s", "sim")
