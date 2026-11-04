"""The marker for a form field left to the operator instead of a guess."""

# Sentinel for a form field the LLM did not (or should not) answer, stopping in front
# of the operator instead of guessing. This is a constant, not a config key: every
# producer (field_map.py's salary rule, work_auth.py's authorization and sponsorship
# rule, both reached through pre_populate_answers) and every consumer
# (assisted/composer.py, which turns the marker into a visible gap) must agree on the
# exact same string, or an unanswered field silently degrades into whatever literal
# text was configured — typed into a real form field and submitted, with no operator
# stop. There is no way to make that divergence safe by configuration; the fix is for
# the string to have exactly one source of truth.
NEEDS_REVIEW_SENTINEL = "__NEEDS_REVIEW__"
