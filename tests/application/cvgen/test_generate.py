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
    # Translations are asked for as plaintext, not LaTeX: the render escapes
    # them, so a model emitting markup would only produce visible backslashes.
    assert "no LaTeX" in calls["prefix"] and "**bold**" in calls["prefix"]
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


# --- translation values are PROSE, not markup: escaped, never validated ------
# The prompt asks for translations in the same **bold** plaintext dialect the
# summary already uses, and render._bullet_text runs them through escape_latex.
# A model-authored string therefore reaches the .tex as literal characters and
# can never become a command, whatever the untrusted posting steered it into.

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


# Every string below is a route to a TeX control sequence, and each one defeated
# at least one earlier attempt at validating translations as markup. They are
# kept here as the corpus that proves the design change: the translation is no
# longer inspected at all, it is ESCAPED, so each of these reaches the .tex as
# literal characters. '^^hh' is the reason validation kept losing — TeX turns it
# into the byte hh during TOKENIZATION, so '^^5c' IS a backslash and no literal
# backslash ever appears in the string.
HOSTILE = {
    "plain latex commands": "\\input{/etc/passwd} \\write18{id}",
    "command inside a bold argument": "\\textbf{\\input{/etc/passwd}}",
    "bare caret hex": "^^5cinput{/etc/passwd}",
    "caret hex, any command": "^^5cnewpage",
    "caret hex inside a bold span": "\\textbf{^^5cinput^^7b/etc/passwd^^7d}",
    "caret hex inside an italic span": "\\textit{^^5cinput^^7b/etc/passwd^^7d}",
    "space-delimited filename, no braces": "\\textbf{^^5cinput /etc/passwd }",
    "uppercase hex": "\\textbf{^^5CINPUT^^7b/etc/passwd^^7d}",
    "raw 0x1c after the carets": "\\textbf{^^\x1cinput^^7b/etc/passwd^^7d}",
    "payload split across two spans": "\\textbf{^^5cin}\\textit{put^^7b/etc/passwd^^7d}",
    "char92 as the backslash": "\\textbf{^^5cchar92 relax}",
    "unbalanced brace": "Fiz A}",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", HOSTILE.values(), ids=list(HOSTILE))
async def test_a_hostile_translation_reaches_the_tex_only_as_literal_characters(payload):
    call, _ = _caller(_pt_response(payload))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    # KEPT, not dropped — that is the point of the change, and it is what makes
    # this test measure the escaping rather than an accidental rejection.
    assert sel.translations == {"igti-b": payload}
    tex = render_cv(TEMPLATE, sel, POOL)
    assert payload not in tex  # every payload carries at least one TeX special
    assert "^^" not in tex  # the tokenizer route, neutralised
    assert "\\input" not in tex and "\\write18" not in tex and "\\char" not in tex


@pytest.mark.asyncio
async def test_all_three_translation_paths_are_escaped():
    # Bullet, prose entry and open-source item all go through _bullet_text; a
    # fix reconciling only one is how the last silent regression happened.
    poisoned = "^^5cinput{/etc/passwd}"
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Resumo",
            "technical_expertise": "Elixir",
            "bullets": ["igti-b"],
            "open_source": ["oss-m"],
            "bullets_translated": {
                "igti-b": poisoned,
                "trybe-prose": poisoned,
                "oss-m": poisoned,
            },
        }
    )
    call, _ = _caller(resp)
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    tex = render_cv(TEMPLATE, sel, POOL)
    assert "^^" not in tex and "\\input" not in tex
    assert tex.count(r"\textasciicircum{}\textasciicircum{}5cinput") == 3


# Plaintext the markup-validating grammar used to reject, costing a legitimate
# PT translation its bullet. As prose run through escape_latex they are simply
# correct — which is the practical dividend of the design change.
PLAINTEXT = {
    "a percentage": ("Reduziu 30% do tempo", r"Reduziu 30\% do tempo"),
    "an ampersand": ("P&D e testes", r"P\&D e testes"),
    "an underscore": ("job_id do sistema", r"job\_id do sistema"),
    "accents": ("Liderou a adoção de IA", "Liderou a adoção de IA"),
    "an en-dash range": ("Liderou (2019--2023)", "Liderou (2019--2023)"),
    "bold emphasis": ("Fiz **C** com Elixir", r"Fiz \textbf{C} com Elixir"),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,rendered", PLAINTEXT.values(), ids=list(PLAINTEXT))
async def test_plain_prose_renders_correctly(payload, rendered):
    call, _ = _caller(_pt_response(payload))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.translations == {"igti-b": payload}
    assert rendered in render_cv(TEMPLATE, sel, POOL)


# --- any shape the model emits degrades; nothing reaches the operator as an
# --- error line instead of the sheet (the module's own contract).
SHAPES = {
    "bullets_translated as a list": ({"bullets_translated": ["\\input{/x}"]}, "translations", {}),
    "bullets_translated as a string": (
        {"bullets_translated": "tudo traduzido"},
        "translations",
        {},
    ),
    "bullets_translated as a number": ({"bullets_translated": 7}, "translations", {}),
    "bullets as an int": ({"bullets": 3}, "bullets", ()),
    "bullets as a string": ({"bullets": "igti-b"}, "bullets", ()),
    "open_source as an int": ({"open_source": 7}, "open_source", ()),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("override,field,expected", SHAPES.values(), ids=list(SHAPES))
async def test_a_wrong_typed_field_degrades_instead_of_raising(override, field, expected):
    # A posting is untrusted input that steers the model's OUTPUT SHAPE, not
    # just its words. decide_cv raising here means prepare_application answers
    # with a traceback line instead of the whole sheet — the operator loses the
    # application, not just the tailored CV.
    resp = json.loads(_pt_response("Fiz C"))
    resp.update(override)
    call, _ = _caller(json.dumps(resp))
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel is not None and getattr(sel, field) == expected
    render_cv(TEMPLATE, sel, POOL)  # and the render still works on it


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
