"""The one error the CV-pool bootstrap raises.

It lives apart from the drafting code and the orchestration code so neither
has to import the other.
"""


class BootstrapError(Exception):
    """The bootstrap could not produce a usable draft.

    Named precisely so the MCP tool / CLI subcommand can report why, instead
    of a bare crash.
    """
