import asyncio
import logging
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _scan():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import scan

    return scan


def test_scan_runner_scopes_and_delegates(monkeypatch, caplog):
    scan = _scan()

    async def fake_scan(keywords, phase, config, profile, caller):
        return f"scanned {phase}:{keywords}"

    monkeypatch.setattr(scan.scan_service, "scan_and_evaluate", fake_scan)
    monkeypatch.setattr(scan, "load_config", lambda: {"score_threshold": 6.5})
    monkeypatch.setattr(scan, "validate_config", lambda c: None)
    monkeypatch.setattr(scan, "load_profile", lambda: {})
    monkeypatch.setattr(scan, "init_db", lambda: None)
    monkeypatch.setattr(scan, "make_caller", lambda c: None)

    with caplog.at_level(logging.INFO):
        out = asyncio.run(scan._run("kw", "phase2"))

    assert out == "scanned phase2:kw"
    assert any("op=scan_and_evaluate" in r.getMessage() for r in caplog.records)
