"""The exception every configuration check raises."""


class ConfigError(Exception):
    """Raised when config.yaml has an unknown key or a value of the wrong type."""
