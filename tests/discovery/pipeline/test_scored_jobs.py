"""A scan saves every scored field and scores with the configured model."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import init_db
from moonlighter.discovery.pipeline import evaluate_and_store

from tests.discovery.scan_fakes import BatchRecorder, evaluation_result, make_raw_job, store_config


async def test_evaluated_jobs_persist_every_scored_field(temporary_database):
    init_db()
    batch = AsyncMock(
        return_value=[evaluation_result(8.0, caveats=["visa"]), evaluation_result(2.0)]
    )
    with patch("moonlighter.discovery.pipeline.evaluate_jobs_batch", new=batch):
        saved, _ = await evaluate_and_store(
            [make_raw_job(1), make_raw_job(2)], store_config(), {}, caller=MagicMock()
        )
    first, second = saved
    assert first.caveats == '["visa"]'
    assert first.description == "A detailed job description that goes on."
    assert (first.salary_min, first.salary_max) == (150000, 200000)
    assert (first.salary_currency, first.salary_source) == ("USD", "llm_estimate")
    assert (first.score, first.score_notes, first.status) == (8.0, "match", "new")
    assert (second.score, second.status) == (2.0, "archived")


async def test_evaluation_model_comes_from_eval_model_then_llm_model_then_the_default(
    temporary_database,
):
    init_db()
    recorder = BatchRecorder()
    with patch("moonlighter.discovery.pipeline.evaluate_jobs_batch", new=recorder):
        for index, extra in enumerate(
            [
                {"eval_model": "from-eval", "llm_model": "from-llm"},
                {"llm_model": "from-llm"},
                {},
            ]
        ):
            await evaluate_and_store(
                [make_raw_job(100 + index)], store_config(**extra), {}, caller=MagicMock()
            )
    assert recorder.models == ["from-eval", "from-llm", "claude-haiku-4-5-20251001"]
