"""Reads markdown text one line at a time, leaving out what sits inside fenced code blocks."""

import re
from collections.abc import Iterator

_FENCE = re.compile(r"^\s*(```|~~~)")


def lines_outside_fences(text: str) -> Iterator[str]:
    """Yields each line of `text` that is neither a fence line nor inside a fenced block.

    A fence opened with backticks can be closed by a tilde line and the other way round, and an unclosed fence runs to the end of the text.
    """
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            yield line
