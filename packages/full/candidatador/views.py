"""Renderização de tabelas para as respostas das tools MCP."""

import io

from candidatador.core.db import Job
from rich import box
from rich.console import Console
from rich.table import Table


def render_jobs_table(jobs: list[Job]) -> str:
    buf = io.StringIO()
    console = Console(file=buf, width=120)
    table = Table(box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Empresa / Cargo", min_width=28)
    table.add_column("Score", width=7)
    table.add_column("Salário", width=14)
    table.add_column("Publicada", width=11)
    table.add_column("Remoto", width=8)
    table.add_column("Caveats", min_width=20)

    for job in jobs:
        table.add_row(
            str(job.id),
            f"{job.company} / {job.title}",
            f"{job.score:.1f}" if job.score is not None else "—",
            _salary_cell(job),
            job.posted_at.strftime("%d/%m") if job.posted_at else "—",
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
    return "n/d"


def _caveat_cell(job: Job) -> str:
    caveats = job.get_caveats()
    return caveats[0][:30] if caveats else "—"
