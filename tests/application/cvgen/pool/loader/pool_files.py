"""A valid pool document and the helper that writes one to disk."""

import textwrap
from pathlib import Path

VALID_POOL_YAML = textwrap.dedent("""
    experiences:
      - company: Trybe
        title: "Senior Software Developer"
        period: "Jan 2023 -- Jul 2026"
        location: "Belo Horizonte, Brazil"
        bullets:
          - id: trybe-ic-evaluations
            angles: [backend]
            latex: 'Contributed to \\textbf{38M+ evaluations}'
      - company: IGTI
        id: igti-prose
        title: "Professor"
        period: "Jan 2018 -- Dec 2019"
        location: "Belo Horizonte, Brazil"
        prose: "Taught ML in MBA programs."
        angles: [ai, education]
    open_source:
      - id: oss-moonlighter
        angles: [ai, backend]
        latex: '\\textbf{moonlighter} pipeline'
    summary_facts:
      - "Years of experience: compute from career_started"
""")


def write_pool_file(tmp_path: Path, content: str) -> Path:
    pool_file = tmp_path / "cv-pool.yaml"
    pool_file.write_text(content)
    return pool_file
