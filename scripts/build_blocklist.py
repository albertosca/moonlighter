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
import json
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from moonlighter.core.config import load_config, load_profile, moonlighter_home
from moonlighter.core.db import Job, init_db
from moonlighter.core.llm import make_caller
from moonlighter.core.log import setup as setup_logging
from moonlighter.core.metrics import operation_metrics
from moonlighter.core.parsing import extract_json


def _make_proposal_prompt(company: str, threshold: float, titles_block: str, profile: dict) -> str:
    name = profile.get("name", "the candidate")
    level = profile.get("level", "senior software engineer")
    skills = ", ".join((profile.get("top_skills") or [])[:4]) or "software engineering"
    return f"""\
You are building a job title blocklist for {name}, a {level} specializing in {skills}.

The following job titles at **{company}** were evaluated and scored {threshold} or below out of 10 \
— meaning they are clearly irrelevant for them:

{titles_block}

Your task: propose minimal, safe **substring patterns** (lowercase) to block future titles like these \
before they reach the LLM evaluator.

A pattern is SAFE only if you are confident that **every possible job title containing it** would be \
irrelevant for a senior software engineer. When in doubt, mark safe=false.

Examples of UNSAFE patterns (too broad):
- "analista" alone → "analista de segurança" could be relevant
- "gerente" alone → "Engineering Manager" might appear in PT-BR as "Gerente de Engenharia"
- "especialista" alone → "Especialista de Plataforma" could be a tech role

Examples of SAFE patterns:
- "gerente de relacionamento" → always a banking relationship manager, never engineering
- "banco de talentos" → always a talent pool post, not a real opening
- "estagiár" → always an intern position

Return a JSON array (no markdown):
[
  {{
    "pattern": "lowercase substring to match",
    "examples": ["example title 1", "example title 2"],
    "safe": true,
    "reasoning": "one sentence explaining why all matching titles would be irrelevant"
  }}
]

Return [] if no safe patterns can be identified.\
"""


QUOTA_MARKERS = (
    "spend limit",
    "quota",
    "rate limit",
    "too many requests",
    "overloaded",
    "429",
    "usage limit",
)


def _learned_path() -> Path:
    return moonlighter_home() / "blocklist_learned.yaml"


def _load_learned() -> list[str]:
    path = _learned_path()
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    return data.get("title_blocklist", [])


def _save_learned(patterns: list[str]) -> None:
    path = _learned_path()
    existing = _load_learned()
    merged = list(dict.fromkeys(existing + patterns))  # dedup, preserve order
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump({"title_blocklist": merged}, allow_unicode=True, default_flow_style=False)
    )


def _confirm_write(patterns: list[str]) -> bool:
    """Ask for explicit confirmation before merging LLM-proposed patterns into
    the real blocklist (S-10) — an over-broad hallucinated pattern silently
    filters out good jobs; the user's silence must NEVER count as consent."""
    print(f"\n{len(patterns)} new pattern(s) about to be saved:")
    for p in patterns:
        print(f"  - {p!r}")
    answer = input("Confirm save? [y/N] ").strip().lower()
    return answer in ("y", "yes", "s", "sim")


def _fetch_low_scorers(threshold: float, company: str | None) -> dict[str, list[str]]:
    """Returns {company: [title, ...]} for archived jobs with 0 < score <= threshold."""
    query = (
        Job.select(Job.company, Job.title)
        .where(
            Job.score > 0,
            Job.score <= threshold,
            Job.status == "archived",
            Job.score_notes.is_null(False),
            ~Job.score_notes.startswith("evaluation error"),
            ~Job.score_notes.startswith("title filtered"),
            ~Job.score_notes.startswith("reevaluate_error"),
        )
        .order_by(Job.company, Job.title)
    )
    if company:
        query = query.where(Job.company == company)

    grouped: dict[str, list[str]] = {}
    for job in query:
        grouped.setdefault(job.company, []).append(job.title)
    return grouped


async def _propose_for_company(
    company: str, titles: list[str], threshold: float, caller, model: str, profile: dict
) -> list[dict]:
    titles_block = "\n".join(f"- {t}" for t in titles[:80])  # cap at 80 to avoid huge context
    prompt = _make_proposal_prompt(company, threshold, titles_block, profile)
    try:
        raw = await caller(prompt, model)
        extracted = extract_json(raw)
        proposals = json.loads(extracted)
        if not isinstance(proposals, list):
            return []
        return [
            p
            for p in proposals
            if isinstance(p, dict) and p.get("safe") is True and p.get("pattern")
        ]
    except Exception as e:
        err = str(e).lower()
        if any(m in err for m in QUOTA_MARKERS):
            raise
        print(f"  ⚠️  Error processing {company}: {e}")
        return []


async def _run(
    threshold: float,
    company_filter: str | None,
    dry_run: bool,
    model: str,
    config: dict,
    profile: dict,
    assume_yes: bool,
) -> None:
    with operation_metrics("build_blocklist"):
        caller = make_caller(config)
        grouped = _fetch_low_scorers(threshold, company_filter)

        if not grouped:
            print("No jobs matched the criteria.")
            return

        total_titles = sum(len(v) for v in grouped.values())
        print(
            f"Jobs to analyze: {total_titles} across {len(grouped)} company/ies  [threshold={threshold}]"
        )
        print()

        existing = set(_load_learned())
        all_new: list[str] = []

        for company, titles in sorted(grouped.items(), key=lambda x: -len(x[1])):
            print(f"▶ {company} ({len(titles)} jobs)...")
            try:
                proposals = await _propose_for_company(
                    company, titles, threshold, caller, model, profile
                )
            except Exception as e:
                if any(m in str(e).lower() for m in QUOTA_MARKERS):
                    print(f"🚫 SPEND LIMIT reached — stopping. Error: {e}")
                    break
                print(f"  ✗ Error: {e}")
                continue

            if not proposals:
                print("  (no safe pattern identified)")
                continue

            for p in proposals:
                pattern = p["pattern"].lower().strip()
                status = (
                    "ALREADY EXISTS" if pattern in existing else ("DRY RUN" if dry_run else "ADDED")
                )
                print(f"  + {pattern!r:40s} [{status}]")
                print(f"    → {p.get('reasoning', '')}")
                if pattern not in existing and not dry_run:
                    all_new.append(pattern)
                    existing.add(pattern)
            print()

        if all_new and not dry_run:
            if not assume_yes and not _confirm_write(all_new):
                print("Cancelled — nothing was saved.")
                return
            _save_learned(all_new)
            print(f"✓ {len(all_new)} pattern(s) saved to blocklist_learned.yaml")
        elif dry_run and all_new:
            print(f"[DRY RUN] {len(all_new)} pattern(s) would be added.")
        else:
            print("No new patterns.")


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
    args = parser.parse_args()

    setup_logging()
    config = load_config()
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = {}
    init_db()  # resolve o path via moonlighter_home() / MOONLIGHTER_DB_PATH (fonte única em db.py)

    model = config.get("eval_model", "claude-haiku-4-5-20251001")
    learned_path = moonlighter_home() / "blocklist_learned.yaml"
    print(f"Model: {model}  |  blocklist_learned: {learned_path}")
    print()

    asyncio.run(_run(args.threshold, args.company, args.dry_run, model, config, profile, args.yes))


if __name__ == "__main__":
    main()
