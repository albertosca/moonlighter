import json
from unittest.mock import patch

from moonlighter.application.cvgen.latex.page_fit import TailoredCV, _shrunk
from moonlighter.application.cvgen.latex.render import CVSelection
from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.application.cvgen.pool.loader import CVPool, PoolBullet, PoolExperience
from moonlighter.application.cvgen.service import ensure_tailored_cv
from tests.application.cvgen.latex.page_fit.pdf_compilers import compiler_that_reports
from tests.application.cvgen.tailored_cv_samples import JOB, counting_caller, write_pool

PROSE_POOL_YAML = """
experiences:
  - id: p-a
    company: Nubank
    title: Staff
    period: "2020 -- 2023"
    location: SP
    prose: 'Led the platform team.'
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: t-a
        angles: [backend]
        latex: 'Did A'
      - id: t-b
        angles: [backend]
        latex: 'Did B'
      - id: t-c
        angles: [backend]
        latex: 'Did C'
"""


PROSE_GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["p-a", "t-a", "t-b", "t-c"],
        "open_source": [],
    }
)


TWO_EXPERIENCE_POOL_YAML = """
experiences:
  - company: Nubank
    title: Staff
    period: "2020 -- 2023"
    location: SP
    bullets:
      - id: b-1
        angles: [backend]
        latex: 'B one'
      - id: b-2
        angles: [backend]
        latex: 'B two'
      - id: b-3
        angles: [backend]
        latex: 'B three'
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: a-1
        angles: [backend]
        latex: 'A only'
"""


# The model places A's single bullet LAST in its order — a global (non-per-
# experience) counter would treat it as "just the tail element" and drop it
# first, since it only checks whether MORE than one bullet remains selected
# overall, not whether it is A's or B's. The correct per-experience bookkeeping
# must skip it (A only has 1 selected) and keep dropping from B's tail instead.
TWO_EXPERIENCE_GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["b-1", "b-2", "b-3", "a-1"],
        "open_source": [],
    }
)


async def test_a_prose_id_among_selected_bullets_is_never_dropped(config):
    # A prose id shares the "bullets" list with real experience bullets (it
    # carries a translation), but owns no experience of its own —
    # _shrunk's `bid in owner` guard must skip it while counting, not drop it.
    write_pool(config, PROSE_POOL_YAML)
    call, _ = counting_caller(PROSE_GENERATE)
    compile_, attempts = compiler_that_reports([2, 1])
    with (
        patch("moonlighter.application.cvgen.latex.page_fit.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    assert attempts["n"] == 2
    tex = (generated_dir_for(config, 42) / "cv.tex").read_text()
    assert "Led the platform team" in tex  # the prose entry survives the shrink
    assert "Did C" not in tex  # the last experience bullet is what went


async def test_shrunk_bookkeeping_is_per_experience_not_global(config):
    # Reproduces the review finding: owner/selected_per_exp exist so that an
    # experience with few selected bullets (A, here down to its only one) is
    # never touched while another experience (B) still has more than one
    # selected. A constant/global key would instead drop from the END of the
    # whole selection.bullets list regardless of which experience owns it —
    # which here means dropping A's only bullet FIRST, since it sits last in
    # the model's order. Two clearly distinguishable bullet texts per
    # experience make a wrong implementation produce a detectably different
    # final .tex: "A only" would be missing and "B three" would survive.
    write_pool(config, TWO_EXPERIENCE_POOL_YAML)
    call, calls = counting_caller(TWO_EXPERIENCE_GENERATE)
    compile_, attempts = compiler_that_reports([2, 2, 1])
    with (
        patch("moonlighter.application.cvgen.latex.page_fit.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    assert attempts["n"] == 3  # two shrinks were needed to reach one page
    assert calls["n"] == 1  # shrinking never spends another LLM call
    tex = (generated_dir_for(config, 42) / "cv.tex").read_text()
    # A's only bullet must never be touched: dropping it would zero out A's
    # selection while B still had more than one bullet selected.
    assert "A only" in tex
    # Both drops came from B's tail, in the model's order: "B three" first,
    # then "B two" — B still keeps its first bullet.
    assert "B one" in tex
    assert "B two" not in tex
    assert "B three" not in tex


def test_shrunk_keys_on_experience_index_so_a_rehire_keeps_its_own_counter():
    # A rehire: the same company AND the same title twice in the pool, with a
    # gap between the stints. Keyed on company+title the two experiences would
    # share ONE counter (3 selected), so scanning from the tail `_shrunk` would
    # see "3 > 1" and drop b-1 — the second stint's ONLY bullet — instead of
    # dropping from the first stint, which still keeps a bullet after the drop.
    # Keyed on the experience's index the counters are 2 and 1, and b-1 is
    # untouchable.

    def exp(period, *bullets):
        return PoolExperience(
            company="Acme",
            title="Engineer",
            period=period,
            location="SP",
            bullets=tuple(
                PoolBullet(id=index, angles=("backend",), latex=index) for index in bullets
            ),
            prose=None,
            prose_id=None,
            angles=(),
        )

    pool = CVPool(
        experiences=(exp("2018 -- 2020", "a-1", "a-2"), exp("2022 -- 2026", "b-1")),
        open_source=(),
        summary_facts=(),
    )
    selection = CVSelection(
        language="en",
        summary="",
        technical_expertise="",
        bullets=("a-1", "a-2", "b-1"),
        open_source=(),
        translations={},
    )
    shrunk = _shrunk(selection, pool)
    assert shrunk is not None
    assert shrunk.bullets == ("a-1", "b-1")
