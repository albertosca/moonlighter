"""Table rendering for MCP tool responses."""

import io

from moonlighter.core.db import Job
from rich import box
from rich.console import Console
from rich.table import Table


def render_jobs_table(jobs: list[Job], badges: dict[int, str] | None = None) -> str:
    buf = io.StringIO()
    console = Console(file=buf, width=120)
    table = Table(box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Company / Title", min_width=28)
    table.add_column("Score", width=7)
    table.add_column("Salary", width=14)
    table.add_column("Posted", width=11)
    table.add_column("Remote", width=8)
    table.add_column("Caveats", min_width=20)

    for job in jobs:
        badge = (badges or {}).get(job.id)
        company_cell = f"{job.company} / {job.title}"
        if badge:
            company_cell += f"\n{badge}"
        table.add_row(
            str(job.id),
            company_cell,
            f"{job.score:.1f}" if job.score is not None else "—",
            _salary_cell(job),
            job.posted_at.strftime("%b %d") if job.posted_at else "—",
            job.remote_type or "—",
            _caveat_cell(job),
        )
    console.print(table)
    return buf.getvalue()


def _salary_cell(job: Job) -> str:
    if job.salary_min and job.salary_max:
        cell = f"${job.salary_min // 1000}–{job.salary_max // 1000}k"
        return f"{cell} *" if job.salary_source == "llm_estimate" else cell
    if job.salary_min:
        return f"${job.salary_min // 1000}k+"
    return "n/a"


def _caveat_cell(job: Job) -> str:
    caveats = job.get_caveats()
    return caveats[0][:30] if caveats else "—"
