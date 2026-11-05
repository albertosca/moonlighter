"""Analyzes low-scoring jobs and proposes AI-validated blocklist patterns.

Workflow:
  1. Fetches archived jobs with 0 < score <= threshold (genuinely evaluated)
  2. Groups titles by company
  3. For each company, asks LLM: "propose safe substrings to block"
  4. LLM returns patterns with reasoning and safe=true/false flag
  5. Approved patterns (safe=true) go to blocklist_learned.yaml
  6. load_config() already merges the file into title_blocklist

Usage:
    python scripts/build_blocklist.py [--threshold 3.0] [--dry-run] [--company SLUG]

Flags:
    --threshold  Maximum score to consider a job as a candidate (default: 3.0)
    --dry-run    Shows what would be added without writing to the file
    --company    Process a single company
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from moonlighter.core.config.defaults import DEFAULT_EVAL_MODEL
from moonlighter.core.config.loading import load_config, load_profile
from moonlighter.core.db import init_db
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.log import setup as setup_logging
from moonlighter.core.metrics import operation_metrics

from blocklist_candidates import fetch_low_scorers
from blocklist_learned import confirm_write, learned_path, load_learned, save_learned
from blocklist_proposals import is_quota_error, proposal_prompt, propose_for_company


def _report(proposals: list[dict[str, Any]], existing: set[str], *, dry_run: bool) -> list[str]:
    """Prints each proposal with its status and returns the patterns that are new."""
    new_patterns: list[str] = []
    for proposal in proposals:
        pattern = proposal["pattern"].lower().strip()
        status = "ALREADY EXISTS" if pattern in existing else ("DRY RUN" if dry_run else "ADDED")
        print(f"  + {pattern!r:40s} [{status}]")
        print(f"    → {proposal.get('reasoning', '')}")
        if pattern not in existing and not dry_run:
            new_patterns.append(pattern)
            existing.add(pattern)
    return new_patterns


async def _propose_all(
    grouped: dict[str, list[str]],
    arguments: argparse.Namespace,
    *,
    caller: LLMCaller,
    model: str,
    profile: dict[str, Any],
) -> list[str]:
    """Asks the model about each company, most titles first, and returns the new patterns."""
    existing = set(load_learned())
    new_patterns: list[str] = []
    for company, titles in sorted(
        grouped.items(), key=lambda company_and_titles: -len(company_and_titles[1])
    ):
        print(f"▶ {company} ({len(titles)} jobs)...")
        try:
            prompt = proposal_prompt(company, titles, arguments.threshold, profile=profile)
            proposals = await propose_for_company(company, prompt, caller=caller, model=model)
        except Exception as error:  # noqa: BLE001 - one company failing must not stop the others
            if is_quota_error(error):
                print(f"🚫 SPEND LIMIT reached — stopping. Error: {error}")
                break
            print(f"  ✗ Error: {error}")
            continue

        if not proposals:
            print("  (no safe pattern identified)")
            continue

        new_patterns += _report(proposals, existing, dry_run=arguments.dry_run)
        print()
    return new_patterns


def _save_or_report(new_patterns: list[str], arguments: argparse.Namespace) -> None:
    if new_patterns and not arguments.dry_run:
        if not arguments.yes and not confirm_write(new_patterns):
            print("Cancelled — nothing was saved.")
            return
        save_learned(new_patterns)
        print(f"✓ {len(new_patterns)} pattern(s) saved to blocklist_learned.yaml")
    else:
        print("No new patterns.")


async def _run(
    arguments: argparse.Namespace, *, model: str, config: dict[str, Any], profile: dict[str, Any]
) -> None:
    with operation_metrics("build_blocklist"):
        caller = make_caller(config)
        grouped = fetch_low_scorers(arguments.threshold, arguments.company)

        if not grouped:
            print("No jobs matched the criteria.")
            return

        total_titles = sum(len(company_titles) for company_titles in grouped.values())
        print(
            f"Jobs to analyze: {total_titles} across {len(grouped)} company/ies  "
            f"[threshold={arguments.threshold}]"
        )
        print()

        new_patterns = await _propose_all(
            grouped, arguments, caller=caller, model=model, profile=profile
        )
        _save_or_report(new_patterns, arguments)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--threshold", type=float, default=3.0, help="Maximum score to consider (default: 3.0)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to the file")
    parser.add_argument("--company", help="Process a single company")
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help=(
            "Save approved patterns without asking for confirmation (S-10: by default, "
            "always confirm before merging into the real blocklist)."
        ),
    )
    arguments = parser.parse_args()

    setup_logging()
    config = load_config()
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = {}
    init_db()  # resolves the path via moonlighter_home() / MOONLIGHTER_DB_PATH (single source in db.py)

    model = config.get("eval_model", DEFAULT_EVAL_MODEL)
    print(f"Model: {model}  |  blocklist_learned: {learned_path()}")
    print()

    asyncio.run(_run(arguments, model=model, config=config, profile=profile))


if __name__ == "__main__":
    main()
