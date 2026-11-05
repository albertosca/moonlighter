from moonlighter.application.cvgen.pool.loader import (
    CVPool,
    PoolBullet,
    PoolExperience,
    dump_pool,
    load_pool,
)


def test_dump_pool_round_trips_through_load_pool(tmp_path):
    pool = CVPool(
        experiences=(
            PoolExperience(
                company="Acme",
                title="Engineer",
                period="2020 -- present",
                location="Remote",
                bullets=(PoolBullet(id="acme-a", angles=("backend",), latex="Did A"),),
                prose=None,
                prose_id=None,
                angles=(),
            ),
        ),
        open_source=(PoolBullet(id="oss-a", angles=(), latex="Maintainer of X"),),
        summary_facts=("10 years of experience",),
    )
    path = tmp_path / "cv-pool.yaml"
    path.write_text(dump_pool(pool))

    reloaded = load_pool(path)
    assert reloaded == pool


def test_dump_pool_writes_a_prose_experience_without_a_bullets_key():
    pool = CVPool(
        experiences=(
            PoolExperience(
                company="IGTI",
                title="Professor",
                period="2018 -- 2019",
                location="Belo Horizonte",
                bullets=(),
                prose="Taught data science part-time.",
                prose_id="igti-prose",
                angles=("education",),
            ),
        ),
        open_source=(),
        summary_facts=(),
    )
    text = dump_pool(pool)
    assert "prose:" in text
    assert "bullets:" not in text
