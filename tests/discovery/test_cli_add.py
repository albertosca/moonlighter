"""moonlighter-scan add: the grammar, and the JSON the add_job service turns into."""

from contextlib import contextmanager
from unittest.mock import patch

from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK
from moonlighter.core.config.loading import build_config
from moonlighter.core.db import Job, init_db
from moonlighter.discovery import cli
from moonlighter.discovery.cli import _run, parse_args

ADD_URL = "https://x.com/cli/add/1"


def test_add_parses_url_and_flags():
    arguments = parse_args(
        [
            "add",
            ADD_URL,
            "--company",
            "Acme",
            "--title",
            "Eng",
            "--description",
            "text",
            "--track",
        ]
    )
    assert (
        arguments.command,
        arguments.url,
        arguments.company,
        arguments.title,
        arguments.description,
        arguments.track,
    ) == ("add", ADD_URL, "Acme", "Eng", "text", True)


def test_add_defaults():
    arguments = parse_args(["add", ADD_URL])
    assert (arguments.company, arguments.title, arguments.description, arguments.track) == (
        "",
        "",
        "",
        False,
    )


def test_a_leading_flag_is_still_a_run():
    assert parse_args(["--no-eval"]).command == "run"


@contextmanager
def _adding(*, creates_row):
    async def fake_add_job(url, *_service_arguments, track):
        fake_add_job.track = track
        if creates_row:
            Job.create(source="manual", company="Acme", title="Eng", url=url)
            return "✓ saved"
        return "Provide at least 'company' and 'title' along with the URL."

    with (
        patch.object(cli, "bootstrap", return_value=(build_config({"score_threshold": 6.5}), {})),
        patch.object(cli, "make_caller", return_value=object()),
        patch.object(cli, "add_job", new=fake_add_job),
    ):
        yield fake_add_job


async def test_add_command_returns_the_message_and_the_job(temporary_database):
    init_db()
    with _adding(creates_row=True) as fake:
        payload, code = await _run(parse_args(["add", ADD_URL, "--track"]))
    assert (payload["kind"], payload["message"], payload["job"]["url"], code) == (
        "added",
        "✓ saved",
        ADD_URL,
        EXIT_OK,
    )
    assert fake.track is True


async def test_add_command_when_nothing_was_stored(temporary_database):
    init_db()
    with _adding(creates_row=False):
        payload, code = await _run(parse_args(["add", ADD_URL]))
    assert payload == {
        "kind": "not_added",
        "message": "Provide at least 'company' and 'title' along with the URL.",
        "job": None,
    }
    assert code == EXIT_NOTHING
