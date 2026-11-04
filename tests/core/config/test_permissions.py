from unittest.mock import patch

from moonlighter.core.config import permissions
from moonlighter.core.config.permissions import harden_permissions

# --- harden_permissions (S-07) ---


def test_harden_permissions_chmods_files_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "moonlighter.db").write_text("x")
    (tmp_path / "moonlighter.db").chmod(0o644)
    warnings = harden_permissions()
    assert warnings == []
    assert oct((tmp_path / "moonlighter.db").stat().st_mode)[-3:] == "600"


def test_harden_permissions_chmods_dirs_0700(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "browser-session").mkdir()
    (tmp_path / "browser-session").chmod(0o755)
    harden_permissions()
    assert oct((tmp_path / "browser-session").stat().st_mode)[-3:] == "700"


def test_harden_permissions_skips_missing_files(tmp_path, monkeypatch):
    """No real files in MOONLIGHTER_HOME → nothing to fix, no error."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert harden_permissions() == []


def test_harden_permissions_warns_on_chmod_failure_without_raising(tmp_path, monkeypatch):
    """A permission error must never crash the server's startup — it becomes
    a warning, not an exception."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "profile.yaml").write_text("x")
    (tmp_path / "browser-session").mkdir()

    with patch.object(permissions.Path, "chmod", side_effect=OSError("read-only fs")):
        warnings = permissions.harden_permissions()

    assert len(warnings) >= 2
    assert any("profile.yaml" in warning or "permiss" in warning.lower() for warning in warnings)
    assert any("browser-session" in warning or "permiss" in warning.lower() for warning in warnings)
