"""The prompt section that discounts engagement types the candidate does not want."""

from typing import Any

_ENGAGEMENT_SECTION = """## Engagement type
The candidate targets {engagement} positions. When the posting is a different kind of engagement
(for example contract-based, freelance, fixed-term, or hourly-gig work, including "Contract" or
"Freelance" in the title), discount the score: these postings stay in the queue but must rank below
comparable roles of the kind the candidate wants. This is a discount, NOT a hard filter — never cap
the score at 2.0 for engagement type alone. Record the finding in `caveats`, prefixed
"contract-based:".

"""


def engagement_section(profile: dict[str, Any]) -> str:
    """The engagement-type prompt section from `preferences.engagement`.

    Empty when the profile does not say, because an unknown preference is not a default one.
    """
    preferences = profile.get("preferences")
    engagement = preferences.get("engagement") if isinstance(preferences, dict) else None
    if not isinstance(engagement, str) or not engagement.strip():
        return ""
    return _ENGAGEMENT_SECTION.format(engagement=engagement.strip())
