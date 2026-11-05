"""Shared inputs for the tests of the CV renderer."""

import textwrap

from moonlighter.application.cvgen.render import CVSelection

TEMPLATE = textwrap.dedent(r"""
    \section{Professional Summary}
    \cvlistitem{%%SUMMARY%%}
    \cvlistitem{%%TECHNICAL_EXPERTISE%%}
    %%EXPERIENCE%%
    %%OPEN_SOURCE%%
    \section{Education}
""")


def make_selection(**overrides):
    base = {
        "language": "en",
        "summary": "A summary",
        "technical_expertise": "Elixir, React",
        "bullets": ("t-b", "t-a", "igti-prose"),
        "open_source": (),
        "translations": {},
    }
    base.update(overrides)
    return CVSelection(**base)
