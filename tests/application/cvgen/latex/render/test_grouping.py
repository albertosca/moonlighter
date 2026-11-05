from moonlighter.application.cvgen.latex.render import render_cv
from moonlighter.application.cvgen.pool.loader import CVPool, PoolBullet, PoolExperience
from tests.application.cvgen.latex.render.sample_render import TEMPLATE, make_selection

GROUPED_POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Senior Software Developer",
            period="Jan 2023 -- Jul 2026",
            location="BH, Brazil",
            bullets=(PoolBullet("t-ic", ("backend",), "IC work"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
        PoolExperience(
            company="Trybe",
            title="Engineering Manager",
            period="Sep 2019 -- Dec 2022",
            location="BH, Brazil",
            bullets=(PoolBullet("t-em", ("leadership",), "EM work"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
        PoolExperience(
            company="AppProva",
            title="Full Stack Engineer / Tech Lead",
            period="Jun 2017 -- Sep 2019",
            location="BH, Brazil",
            bullets=(PoolBullet("a-1", ("backend",), "Built X"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
    ),
    open_source=(),
    summary_facts=(),
)


class TestGrouping:
    def test_consecutive_roles_at_one_company_render_as_one_block(self):
        # moderncv banking's own multi-role form: company, overall span and
        # location on the first entry's bold line, each role's own period in
        # the first argument (the italic line); following roles omit company,
        # span and location so the bold line is skipped.
        tex = render_cv(TEMPLATE, make_selection(bullets=("t-ic", "t-em", "a-1")), GROUPED_POOL)
        assert (
            r"\cventry{Jan 2023 -- Jul 2026}{Senior Software Developer}{Trybe}"
            r"{Sep 2019 -- Jul 2026}{BH, Brazil}{" in tex
        )
        assert r"\cventry{Sep 2019 -- Dec 2022}{Engineering Manager}{}{}{}{" in tex
        assert tex.count("{Trybe}") == 1

    def test_a_single_role_company_keeps_the_plain_form(self):
        tex = render_cv(TEMPLATE, make_selection(bullets=("t-ic", "t-em", "a-1")), GROUPED_POOL)
        assert (
            r"\cventry{}{Full Stack Engineer / Tech Lead}{AppProva}{Jun 2017 -- Sep 2019}"
            r"{BH, Brazil}{" in tex
        )

    def test_grouping_needs_adjacency(self):
        # Trybe, AppProva, Trybe: the two Trybe entries are not one block.
        shuffled = CVPool(
            experiences=(
                GROUPED_POOL.experiences[0],
                GROUPED_POOL.experiences[2],
                GROUPED_POOL.experiences[1],
            ),
            open_source=(),
            summary_facts=(),
        )
        tex = render_cv(TEMPLATE, make_selection(bullets=("t-ic", "t-em", "a-1")), shuffled)
        assert tex.count("{Trybe}") == 2
        assert "{}{}{}{" not in tex

    def test_period_bounds_handles_a_period_without_a_dash(self):
        # A grouped role's period lacking "--" (e.g. a single year) must not
        # crash _period_bounds -- it stands as both its own start and end.
        pool = CVPool(
            experiences=(
                PoolExperience(
                    company="SoloCo",
                    title="Engineer",
                    period="Jan 2020 -- Dec 2021",
                    location="Remote",
                    bullets=(PoolBullet("s-1", ("backend",), "Did X"),),
                    prose=None,
                    prose_id=None,
                    angles=(),
                ),
                PoolExperience(
                    company="SoloCo",
                    title="Intern",
                    period="2019",
                    location="Remote",
                    bullets=(PoolBullet("s-2", ("backend",), "Did Y"),),
                    prose=None,
                    prose_id=None,
                    angles=(),
                ),
            ),
            open_source=(),
            summary_facts=(),
        )
        tex = render_cv(TEMPLATE, make_selection(bullets=("s-1", "s-2")), pool)
        assert r"\cventry{Jan 2020 -- Dec 2021}{Engineer}{SoloCo}{2019 -- Dec 2021}{Remote}{" in tex
        assert r"\cventry{2019}{Intern}{}{}{}{" in tex
