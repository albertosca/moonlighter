from unittest.mock import patch

from moonlighter.core.config import permissions
from moonlighter.core.config.permissions import harden_permissions


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
    a warning, not an exception.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "profile.yaml").write_text("x")
    (tmp_path / "browser-session").mkdir()

    with patch.object(permissions.Path, "chmod", side_effect=OSError("read-only fs")):
        warnings = permissions.harden_permissions()

    assert len(warnings) >= 2
    assert any("profile.yaml" in warning or "permiss" in warning.lower() for warning in warnings)
    assert any("browser-session" in warning or "permiss" in warning.lower() for warning in warnings)


def test_every_sensitive_file_and_directory_is_restricted_and_nothing_else(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    files = ("moonlighter.db", "profile.yaml", "config.yaml", "app.log", "blocklist_learned.yaml")
    directories = ("browser-session", "screenshots")
    for name in (*files, "cv.pdf"):
        (tmp_path / name).write_text("x")
        (tmp_path / name).chmod(0o644)
    for name in directories:
        (tmp_path / name).mkdir()
        (tmp_path / name).chmod(0o755)
    assert harden_permissions() == []
    modes = {path.name: oct(path.stat().st_mode)[-3:] for path in tmp_path.iterdir()}
    assert modes == {
        **dict.fromkeys(files, "600"),
        **dict.fromkeys(directories, "700"),
        "cv.pdf": "644",
    }


def test_each_warning_names_the_path_and_the_error_files_before_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "browser-session").mkdir()
    (tmp_path / "profile.yaml").write_text("x")
    with patch.object(permissions.Path, "chmod", side_effect=OSError("read-only fs")):
        warnings = permissions.harden_permissions()
    assert warnings == [
        f"could not restrict permissions on {tmp_path / 'profile.yaml'}: read-only fs",
        f"could not restrict permissions on {tmp_path / 'browser-session'}: read-only fs",
    ]
