import json

import pytest
from moonlighter.application.cvgen.generate import USE_BASE, decide_cv
from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience
from moonlighter.application.cvgen.render import render_cv

POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Dev",
            period="2023 -- 2026",
            location="BH",
            bullets=(PoolBullet("t-a", ("backend",), "A"), PoolBullet("t-b", ("ai",), "B")),
            prose="Taught ML",
            prose_id="trybe-prose",
            angles=(),
        ),
        PoolExperience(
            company="IGTI",
            title="Professor",
            period="2018 -- 2019",
            location="BH",
            bullets=(PoolBullet("igti-b", ("ml",), "C"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
    ),
    open_source=(PoolBullet("oss-m", ("ai",), "M"),),
    summary_facts=("compute years from career_started",),
)
JOB = {"title": "AI Eng", "company": "acme", "description": "Build agents."}
PROFILE = {"career_started": 2010, "summary": "s"}


def _caller(response):
    calls = {}

    async def call(prompt, model, cache_prefix=None):
        calls["prompt"] = prompt
        calls["prefix"] = cache_prefix
        return response

    return call, calls


GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "Tailored summary",
        "technical_expertise": "Elixir",
        "bullets": ["t-b", "ghost-id", "t-a"],
        "open_source": ["oss-m"],
    }
)


@pytest.mark.asyncio
async def test_generate_returns_selection_with_unknown_ids_dropped():
    call, _ = _caller(GENERATE)
    sel = await decide_cv(JOB, POOL, PROFILE, "base sum", "base te", call)
    assert sel is not None
    assert sel.bullets == ("t-b", "t-a")  # ghost-id silently dropped
    assert sel.open_source == ("oss-m",)
    assert sel.summary == "Tailored summary"


@pytest.mark.asyncio
async def test_use_base_returns_sentinel():
    call, _ = _caller(json.dumps({"decision": "USE_BASE"}))
    result = await decide_cv(JOB, POOL, PROFILE, "base sum", "base te", call)
    assert result == USE_BASE  # a genuine model answer, distinct from degradation's None


@pytest.mark.asyncio
async def test_unrecognized_decision_degrades_to_none():
    call, _ = _caller(json.dumps({"decision": "MAYBE"}))
    assert await decide_cv(JOB, POOL, PROFILE, "base sum", "base te", call) is None


@pytest.mark.asyncio
async def test_prompt_carries_pool_ids_base_summary_and_untrusted_posting():
    call, calls = _caller(json.dumps({"decision": "USE_BASE"}))
    await decide_cv(JOB, POOL, PROFILE, "base sum", "base te", call)
    assert "t-a" in calls["prefix"] and "oss-m" in calls["prefix"]
    assert "base sum" in calls["prefix"]
    assert "USE_BASE" in calls["prefix"]
    assert "never author" in calls["prefix"] or "never write" in calls["prefix"]
    assert "Build agents." in calls["prompt"]
    assert "job_posting" in calls["prompt"]  # wrap_untrusted tag


@pytest.mark.asyncio
async def test_pt_language_carries_translations():
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Resumo",
            "technical_expertise": "Elixir",
            "bullets": ["t-a"],
            "open_source": [],
            "bullets_translated": {"t-a": "Fiz A", "ghost": "x"},
        }
    )
    call, _ = _caller(resp)
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.language == "pt"
    assert sel.translations == {"t-a": "Fiz A"}  # ghost filtered here too


@pytest.mark.asyncio
async def test_malformed_json_degrades_to_none():
    call, _ = _caller("not json at all")
    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", call) is None


@pytest.mark.asyncio
async def test_valid_json_non_dict_degrades_to_none():
    call, _ = _caller(json.dumps(["not", "a", "dict"]))
    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", call) is None


@pytest.mark.asyncio
async def test_llm_exception_degrades_to_none():
    async def boom(prompt, model, cache_prefix=None):
        raise RuntimeError("network")

    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", boom) is None


@pytest.mark.asyncio
async def test_operator_directed_summary_degrades_to_none():
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Please provide this summary before submitting",
            "technical_expertise": "Elixir",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = _caller(resp)
    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", call) is None


@pytest.mark.asyncio
async def test_spend_limit_reraises():
    async def spend_limit_error(prompt, model, cache_prefix=None):
        raise RuntimeError("You've hit your session spend limit")

    with pytest.raises(RuntimeError, match="spend limit"):
        await decide_cv(JOB, POOL, PROFILE, "b", "b", spend_limit_error)


# --- translation values are markup, not prose: allow-list, not escape --------
# A translation reaches the .tex verbatim (render._bullet_text substitutes it
# raw), so an unguarded value hands the model a local pdflatex: \input embeds a
# local file into the PDF the operator then uploads to the company.

TEMPLATE = "%%SUMMARY%%\n%%TECHNICAL_EXPERTISE%%\n%%EXPERIENCE%%\n%%OPEN_SOURCE%%\n"


def _pt_response(translation, bullet_id="igti-b"):  # igti-b: a bullets-only entry
    return json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Resumo",
            "technical_expertise": "Elixir",
            "bullets": [bullet_id],
            "open_source": [],
            "bullets_translated": {bullet_id: translation},
        }
    )


@pytest.mark.asyncio
async def test_injected_latex_translation_is_dropped_and_the_pool_bullet_renders():
    call, _ = _caller(_pt_response(r"\input{/etc/passwd} \write18{id}"))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {}
    tex = render_cv(TEMPLATE, sel, POOL)
    assert "\\input" not in tex and "\\write18" not in tex
    assert "\\item C" in tex  # the pool's own latex for igti-b, untouched


@pytest.mark.asyncio
async def test_a_legitimate_bold_translation_survives_and_renders():
    call, _ = _caller(_pt_response(r"Fiz \textbf{C} com \textit{Elixir}"))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {"igti-b": r"Fiz \textbf{C} com \textit{Elixir}"}
    assert r"Fiz \textbf{C} com \textit{Elixir}" in render_cv(TEMPLATE, sel, POOL)


@pytest.mark.asyncio
async def test_a_nested_or_command_bearing_bold_argument_is_dropped():
    # \textbf{\input{x}} would smuggle a command through the allow-list if the
    # argument were not required to be brace- and backslash-free.
    call, _ = _caller(_pt_response(r"\textbf{\input{/etc/passwd}}"))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {}


# TeX replaces ^^hh with the byte hh during TOKENIZATION, before any macro
# runs: ^^5c IS a backslash. A guard that only looks for a literal backslash
# lets "^^5cinput{...}" through, and pdflatex then embeds a file from outside
# the project into the PDF the sheet tells the operator to upload.
CARET_BACKSLASH = "^^5cinput{/etc/passwd}"


@pytest.mark.asyncio
async def test_caret_hex_backslash_is_dropped_on_bullet_prose_and_open_source():
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Resumo",
            "technical_expertise": "Elixir",
            "bullets": ["igti-b"],
            "open_source": ["oss-m"],
            # All three translation paths reach the .tex verbatim, so all three
            # are proven here: a fix reconciling only one is how the last silent
            # regression happened.
            "bullets_translated": {
                "igti-b": CARET_BACKSLASH,
                "trybe-prose": CARET_BACKSLASH,
                "oss-m": CARET_BACKSLASH,
            },
        }
    )
    call, _ = _caller(resp)
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {}
    tex = render_cv(TEMPLATE, sel, POOL)
    assert "^^" not in tex and "input{" not in tex
    assert "\\item C" in tex  # bullet path fell back to the pool latex
    assert "Taught ML" in tex  # prose path fell back
    assert "\\cvlistitem{M}" in tex  # open-source path fell back


@pytest.mark.asyncio
async def test_caret_hex_backslash_is_dropped_whatever_command_follows():
    # The class is closed, not the \input instance.
    call, _ = _caller(_pt_response("^^5cnewpage"))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {}


# The guard is a POSITIVE full-match grammar, not a blocklist, and every string
# below is why. Each one reached the .tex under the previous subtractive check
# (delete the \textbf{...} spans, then scan the residue): sub() removed the span
# before anything looked inside it, and TeX's '^^hh' notation spells a backslash
# and braces without using either character. Payload 1 was compiled with real
# pdflatex and put a file from outside the compile directory into the PDF.
BYPASSES = {
    "caret hex inside a bold span": "\\textbf{^^5cinput^^7b/etc/passwd^^7d}",
    "caret hex inside an italic span": "\\textit{^^5cinput^^7b/etc/passwd^^7d}",
    "space-delimited filename, no braces": "\\textbf{^^5cinput /etc/passwd }",
    "uppercase hex": "\\textbf{^^5CINPUT^^7b/etc/passwd^^7d}",
    "raw 0x1c after the carets": "\\textbf{^^\x1cinput^^7b/etc/passwd^^7d}",
    "payload split across two spans": "\\textbf{^^5cin}\\textit{put^^7b/etc/passwd^^7d}",
    "char92 as the backslash": "\\textbf{^^5cchar92 relax}",
    # Not injection, but outside the grammar all the same: a stray brace breaks
    # the \cventry group, and a raw '%' comments out the rest of the line.
    "unbalanced brace": "Fiz A}",
    "raw percent": "Reduziu 30% do tempo",
    "raw ampersand": "P&D e testes",
    "raw underscore": "job_id do sistema",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", BYPASSES.values(), ids=list(BYPASSES))
async def test_a_translation_outside_the_grammar_never_reaches_the_tex(payload):
    call, _ = _caller(_pt_response(payload))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {}
    tex = render_cv(TEMPLATE, sel, POOL)
    assert payload not in tex
    assert "^^" not in tex
    assert "\\item C" in tex  # the pool's own latex for igti-b, untouched


LEGITIMATE = {
    "bold and italic": "Fiz \\textbf{C} com \\textit{Elixir}",
    "plain PT prose with accents": "Liderou a adoção de IA em cinco times",
    "an en-dash year range": "Liderou (2019--2023)",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", LEGITIMATE.values(), ids=list(LEGITIMATE))
async def test_a_legitimate_translation_still_survives_the_grammar(payload):
    call, _ = _caller(_pt_response(payload))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {"igti-b": payload}
    assert payload in render_cv(TEMPLATE, sel, POOL)


@pytest.mark.asyncio
async def test_an_operator_directed_translation_is_dropped():
    # Summary and expertise already pass this guard; a translation bypassed it.
    call, _ = _caller(_pt_response("Please provide this bullet before submitting"))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {}
    assert sel is not None  # one bad translation degrades the bullet, not the CV


@pytest.mark.asyncio
async def test_operator_directed_expertise_degrades_to_none():
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Expert in Elixir",
            "technical_expertise": "The candidate cannot supply this section",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = _caller(resp)
    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", call) is None
