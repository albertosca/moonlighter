import pytest

from moonlighter.core.llm.spend_limit import is_spend_limit


class _CustomAPIError(Exception):
    """Stand-in for a real SDK exception type (e.g. anthropic.RateLimitError)."""


IS_SPEND_LIMIT_CASES = [
    # (exception, expected, case id)
    (Exception("spend limit reached"), True, "spend-limit-plain"),
    (Exception("Spend Limit Reached"), True, "spend-limit-mixed-case"),
    (Exception("SPEND LIMIT EXCEEDED FOR ORG"), True, "spend-limit-upper"),
    (Exception("your session limit has been hit"), True, "session-limit"),
    (Exception("quota exceeded for this project"), True, "quota"),
    (Exception("rate limit exceeded, please retry"), True, "rate-limit"),
    (Exception("too many requests in a short period"), True, "too-many-requests"),
    (Exception("the API is currently overloaded"), True, "overloaded"),
    (Exception("HTTP 429 returned by upstream"), True, "429-in-http-status"),
    (Exception("usage limit for this key was reached"), True, "usage-limit"),
    # Marker embedded deep inside a longer, unrelated-looking message.
    (
        Exception("Traceback (most recent call last): anthropic.RateLimitError: rate limit"),
        True,
        "marker-embedded-in-traceback",
    ),
    # A real SDK-shaped exception type, not just builtin Exception.
    (_CustomAPIError("429 Too Many Requests"), True, "custom-exception-type"),
    # Wrapped exception: __str__ of the outer exception must still surface the marker.
    (
        RuntimeError(f"llm call failed: {ValueError('quota exceeded')}"),
        True,
        "wrapped-exception-str-propagates-marker",
    ),
    # should NOT be classified as spend-limit
    (Exception("connection refused"), False, "unrelated-connection-error"),
    (Exception("invalid api key"), False, "unrelated-auth-error"),
    (Exception("file not found: /tmp/x.json"), False, "unrelated-file-error"),
    (Exception(""), False, "empty-message"),
    (Exception("timeout while waiting for response"), False, "timeout-not-a-marker"),
    (ValueError("malformed JSON in response body"), False, "unrelated-value-error"),
    (KeyError("missing_field"), False, "unrelated-key-error"),
    # Partial/incomplete phrases: only a fragment of a two-word marker present.
    (Exception("spend more time reviewing"), False, "partial-phrase-spend-without-limit"),
    (Exception("limit your expectations"), False, "partial-phrase-limit-without-spend"),
    (Exception("rate this job highly"), False, "partial-phrase-rate-without-limit"),
    # Regression: bare substring matching let "quota" match inside "quotation"
    # and "429" match inside "4290" — a false positive here ABORTS THE WHOLE
    # SCAN, so these must stay False under word-boundary matching.
    (Exception("malformed quotation marks in JSON"), False, "quota-substring-of-quotation"),
    (Exception("connection refused on port 4290"), False, "429-substring-of-4290"),
    (Exception("error 14293 occurred"), False, "429-substring-of-14293"),
    # Real spend-limit phrasings that must keep matching after the word-boundary fix.
    (Exception("quota exceeded"), True, "quota-exceeded-word-boundary"),
    (Exception("429 Too Many Requests"), True, "429-leading-word-boundary"),
    (Exception("error 429"), True, "429-trailing-word-boundary"),
]


@pytest.mark.parametrize(
    ("error", "expected"),
    [(error, expected) for error, expected, _ in IS_SPEND_LIMIT_CASES],
    ids=[case_id for _, _, case_id in IS_SPEND_LIMIT_CASES],
)
def test_is_spend_limit_table(*, error: Exception, expected: bool) -> None:
    assert is_spend_limit(error) is expected
