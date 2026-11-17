"""The two settings behind the no-response rule: their defaults and their type."""

import pytest

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.validation import validate_config


def test_the_no_response_rule_defaults_to_45_days_behind_a_7_day_sync():
    assert (DEFAULTS["no_response_after_days"], DEFAULTS["email_sync_max_age_days"]) == (45, 7)


@pytest.mark.parametrize("key", ["no_response_after_days", "email_sync_max_age_days"])
def test_the_no_response_settings_take_an_integer(key):
    validate_config({key: 30})
    with pytest.raises(ConfigError, match=key):
        validate_config({key: "30"})
