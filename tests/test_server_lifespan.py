import pytest
from gauntler.core.config import ConfigError
from gauntler.server import AppContext, lifespan, mcp


async def test_lifespan_yields_populated_appcontext(tmp_db):
    async with lifespan(mcp) as ctx:
        assert isinstance(ctx, AppContext)
        assert isinstance(ctx.config, dict)
        assert ctx.llm_caller is not None
        assert isinstance(ctx.startup_warnings, list)


async def test_lifespan_rejects_invalid_config(tmp_db, monkeypatch):
    import gauntler.server as server

    bad = {"scan_concurrency": "five"}  # will fail validate_config
    monkeypatch.setattr(server, "load_config", lambda: bad)
    with pytest.raises(ConfigError):
        async with lifespan(mcp):
            pass  # must raise before yielding
