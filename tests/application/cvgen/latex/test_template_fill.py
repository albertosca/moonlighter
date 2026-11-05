from moonlighter.application.cvgen.latex.template_fill import fill_template

from tests.application.cvgen.log_records import logged_warnings


def test_fill_template_substitutes_contact_and_education_placeholders():
    profile = {
        "name": "Jane Marie Doe",
        "headline": "Senior Engineer",
        "email": "jane@example.com",
        "phone": "+1 555 0100",
        "linkedin": "https://www.linkedin.com/in/janedoe/",
        "education": [
            {"degree": "BSc Computer Science", "school": "Example University", "year": 2014}
        ],
    }
    filled = fill_template(profile)
    assert "{{" not in filled  # every {{...}} placeholder was substituted
    assert "%%SUMMARY%%" in filled  # the per-job markers survive untouched
    assert r"\firstname{Jane Marie}" in filled
    assert r"\familyname{Doe}" in filled
    assert r"\email{jane@example.com}" in filled
    assert r"\social[linkedin]{janedoe}" in filled
    assert "BSc Computer Science" in filled
    assert "Example University" in filled


def test_fill_template_handles_a_missing_optional_field():
    filled = fill_template({"name": "Jane Doe"})
    assert "{{" not in filled
    assert r"\phone[mobile]{}" in filled


def test_fill_template_escapes_tex_specials_in_contact_and_education_fields():
    # pool.py's own module docstring records this exact bug class already
    # happening once: an unescaped '&' in a hand-curated "R&D Engineer" title
    # broke every pdflatex compile silently. NAME_FIRST/NAME_LAST/HEADLINE/
    # PHONE/EMAIL and the education fields all substitute into ordinary
    # text-mode LaTeX macros (\firstname{}, \title{}, \phone[mobile]{},
    # \email{}, \cventry{...}) -- not verbatim -- so a profile.yaml field
    # containing a TeX special must come out escaped, not raw. A bare '%' is
    # the sharpest case: unescaped, it is LaTeX's comment character and
    # silently truncates the rest of the line with no compile error at all.
    profile = {
        "name": "Anne & Marie Doe",
        "headline": "Full-Stack Engineer (Node.js & React, 100% remote)",
        "phone": "+1 555 0100 #2",
        "email": "jane_doe@example.com",
        "education": [
            {"degree": "R&D Engineering", "school": "50% Scholarship University", "year": 2014}
        ],
    }
    filled = fill_template(profile)
    assert r"\firstname{Anne \& Marie}" in filled
    assert r"\familyname{Doe}" in filled
    assert r"\title{Full-Stack Engineer (Node.js \& React, 100\% remote)}" in filled
    assert r"\phone[mobile]{+1 555 0100 \#2}" in filled
    assert r"\email{jane\_doe@example.com}" in filled
    assert r"R\&D Engineering" in filled
    assert r"50\% Scholarship University" in filled


def test_fill_template_drops_a_linkedin_value_that_is_not_a_real_slug():
    # LINKEDIN_USERNAME is the one substitution fill_template leaves
    # UNESCAPED, justified by "it's a slug, never free text" -- so the
    # pattern has to enforce that, and "anything but /?#" did not. A '%' is
    # LaTeX's comment character: unescaped inside \social[linkedin]{...} it
    # eats the closing brace and the rest of the line, with no compile error
    # at the point of the mistake. A value that is not a slug now yields
    # nothing at all rather than something unsafe.
    filled = fill_template(
        {"name": "Jane Doe", "linkedin": "https://www.linkedin.com/in/jane%doe}\\evil"}
    )
    assert r"\social[linkedin]{}" in filled
    assert "%doe" not in filled
    assert "evil" not in filled
    # And a legitimate slug is still lossless, hyphen and digits included.
    is_ok = fill_template({"name": "Jane Doe", "linkedin": "https://linkedin.com/in/jane-doe-42"})
    assert r"\social[linkedin]{jane-doe-42}" in is_ok


def test_fill_template_skips_a_malformed_education_entry_that_is_not_a_mapping():
    # profile.yaml is hand-edited: a stray '-' under "education" (the same
    # mistake pool.py's own _bullet/_experience guard against) makes an entry
    # a bare string instead of a mapping -- fill_template must skip it rather
    # than crash the whole bootstrap on one malformed line.
    profile = {
        "name": "Jane Doe",
        "education": [
            "not a mapping",
            {"degree": "BSc Computer Science", "school": "Example University", "year": 2014},
        ],
    }
    filled = fill_template(profile)
    assert "{{" not in filled
    assert "BSc Computer Science" in filled
    assert "not a mapping" not in filled


def test_an_unrecognisable_linkedin_value_is_announced(caplog):
    filled = fill_template({"name": "A B", "linkedin": "not a profile url"})
    assert "{{LINKEDIN_USERNAME}}" not in filled
    assert logged_warnings(caplog) == [
        (
            "bootstrap: profile.yaml's linkedin value is not a recognizable profile URL "
            "— leaving the CV's LinkedIn field empty"
        )
    ]
