from pathlib import Path

import pytest

from moonlighter.application.cvgen.service import ensure_tailored_cv
from tests.application.cvgen.log_records import logged_warnings
from tests.application.cvgen.sample_tailored_cv import (
    GENERATE_TWO_BULLETS,
    JOB,
    fixed_caller,
    write_pool,
)


@pytest.fixture
def config_with_malformed_pool(config):
    write_pool(config, "experiences:\n  - just a string\n")
    return config


@pytest.fixture
def config_without_english_template(config):
    (Path(config["cv"]["template_dir"]) / "cv-template.en.tex").unlink()
    return config


async def test_a_job_without_an_id_is_named_in_the_warning(config, caplog):
    assert (
        await ensure_tailored_cv(
            {"title": "Eng"}, config, {}, caller=fixed_caller(GENERATE_TWO_BULLETS)
        )
        is None
    )
    assert logged_warnings(caplog) == ["job has no id — using default CV"]


async def test_an_unreadable_pool_warning_carries_the_pool_error(
    config_with_malformed_pool, caplog
):
    config = config_with_malformed_pool
    assert (
        await ensure_tailored_cv(JOB, config, {}, caller=fixed_caller(GENERATE_TWO_BULLETS)) is None
    )
    [message] = logged_warnings(caplog)
    assert message.startswith("cv pool unusable, using default CV — ")
    assert len(message) > len("cv pool unusable, using default CV — ")


async def test_a_missing_english_template_warns_with_its_file_name(
    config_without_english_template, caplog
):
    config = config_without_english_template
    assert (
        await ensure_tailored_cv(JOB, config, {}, caller=fixed_caller(GENERATE_TWO_BULLETS)) is None
    )
    assert logged_warnings(caplog) == [
        "cv.template_dir has no cv-template.en.tex — using default CV"
    ]


async def test_a_spend_limit_during_generation_is_logged_in_full(config, caplog):
    async def refuse(prompt, model, cache_prefix=None):
        raise RuntimeError("You've hit your session limit")

    assert await ensure_tailored_cv(JOB, config, {}, caller=refuse) is None
    assert logged_warnings(caplog) == ["spend limit during cv generation — using default CV"]
