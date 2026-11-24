"""The fixed moment and config the no-response rule tests run against."""

from datetime import datetime, timedelta

from moonlighter.core.config.loading import build_config

NOW = datetime(2026, 11, 17, 10, 0)  # noqa: DTZ001 - the database stores naive local time
CONFIG = build_config({"no_response_after_days": 45, "email_sync_max_age_days": 7})
ONE_YEAR_AGO = NOW - timedelta(days=365)
