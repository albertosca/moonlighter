"""Renderização de tabelas para as respostas das tools MCP."""

import io

from rich import box
from rich.console import Console
from rich.table import Table

from candidatador.db import Job


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
        score_str = f"{job.score:.1f}" if job.score is not None else "—"
        if job.salary_min and job.salary_max:
            sal = f"${job.salary_min // 1000}–{job.salary_max // 1000}k"
            if job.salary_source == "llm_estimate":
                sal += " *"
        elif job.salary_min:
            sal = f"${job.salary_min // 1000}k+"
        else:
            sal = "n/d"
        posted = job.posted_at.strftime("%d/%m") if job.posted_at else "—"
        caveats_list = job.get_caveats()
        caveat_str = caveats_list[0][:30] if caveats_list else "—"
        table.add_row(
            str(job.id),
            f"{job.company} / {job.title}",
            score_str,
            sal,
            posted,
            job.remote_type or "—",
            caveat_str,
        )
    console.print(table)
    return buf.getvalue()
