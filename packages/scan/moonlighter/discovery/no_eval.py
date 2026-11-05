"""The marker that puts a scan in --no-eval mode."""


class NoEval:
    """--no-eval mode marker.

    It is distinct from any accidental `None` default elsewhere: a stray unset
    caller can never compare equal to this.
    """


NO_EVAL = NoEval()
