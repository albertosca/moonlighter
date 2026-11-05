"""The portal category config keys must be strings."""

import pytest

from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.validation import validate_config


@pytest.mark.parametrize("key", ["remotive_category", "wwr_category"])
def test_category_config_keys_are_strings(key):
    validate_config({key: "design"})
    with pytest.raises(ConfigError, match=key):
        validate_config({key: 3})
