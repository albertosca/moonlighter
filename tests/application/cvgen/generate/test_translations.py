import json

import pytest

from moonlighter.application.cvgen.generate import decide_cv
from moonlighter.application.cvgen.latex.cv_template import BaseFields
from moonlighter.application.cvgen.latex.render import render_cv
from tests.application.cvgen.selection_samples import (
    AI_ENGINEER_JOB,
    BARE_TEMPLATE,
    POOL,
    PROFILE,
    pt_response,
    recording_caller,
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
async def test_pt_language_carries_translations():
    response = json.dumps(
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
    call, _ = recording_caller(response)
    sel = await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    assert sel.language == "pt"
    assert sel.translations == {"t-a": "Fiz A"}  # ghost filtered here too


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", HOSTILE.values(), ids=list(HOSTILE))
async def test_a_hostile_translation_reaches_the_tex_only_as_literal_characters(payload):
    call, _ = recording_caller(pt_response(payload))
    sel = await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    # KEPT, not dropped — that is the point of the change, and it is what makes
    # this test measure the escaping rather than an accidental rejection.
    assert sel.translations == {"igti-b": payload}
    tex = render_cv(BARE_TEMPLATE, sel, POOL)
    assert payload not in tex  # every payload carries at least one TeX special
    assert "^^" not in tex  # the tokenizer route, neutralised
    assert "\\input" not in tex
    assert "\\write18" not in tex
    assert "\\char" not in tex


@pytest.mark.asyncio
async def test_all_three_translation_paths_are_escaped():
    # Bullet, prose entry and open-source item all go through _bullet_text; a
    # fix reconciling only one is how the last silent regression happened.
    poisoned = "^^5cinput{/etc/passwd}"
    response = json.dumps(
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
    call, _ = recording_caller(response)
    sel = await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    tex = render_cv(BARE_TEMPLATE, sel, POOL)
    assert "^^" not in tex
    assert "\\input" not in tex
    assert tex.count(r"\textasciicircum{}\textasciicircum{}5cinput") == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("payload", "rendered"), PLAINTEXT.values(), ids=list(PLAINTEXT))
async def test_plain_prose_renders_correctly(payload, rendered):
    call, _ = recording_caller(pt_response(payload))
    sel = await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    assert sel.translations == {"igti-b": payload}
    assert rendered in render_cv(BARE_TEMPLATE, sel, POOL)


@pytest.mark.asyncio
async def test_an_operator_directed_translation_is_dropped():
    # Summary and expertise already pass this guard; a translation bypassed it.
    call, _ = recording_caller(pt_response("Please provide this bullet before submitting"))
    sel = await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    assert sel.translations == {}
    assert sel is not None  # one bad translation degrades the bullet, not the CV


@pytest.mark.asyncio
async def test_a_translation_outside_the_latin_allow_list_is_dropped_not_stripped():
    # The bullet keeps its curated English text; the model's "5★" is never
    # turned into "5" — that would rewrite a claim.
    call, _ = recording_caller(pt_response("Avaliado com 5★ pelos alunos"))
    sel = await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    assert sel.translations == {}
    assert "C" in render_cv(BARE_TEMPLATE, sel, POOL)
