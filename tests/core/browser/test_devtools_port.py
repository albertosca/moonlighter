"""_read_devtools_port takes the port from a real DevToolsActivePort file, no mocks (S-03), and answers None until the file holds one."""

from moonlighter.core import browser


def test_read_devtools_port_parses_first_line(tmp_path):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("54321\n/devtools/browser/abc-123\n")
    assert browser._read_devtools_port(tmp_path) == 54321


def test_read_devtools_port_missing_file_returns_none(tmp_path):
    assert browser._read_devtools_port(tmp_path) is None


def test_read_devtools_port_malformed_content_returns_none(tmp_path):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("not-a-port\n")
    assert browser._read_devtools_port(tmp_path) is None


def test_read_devtools_port_empty_file_returns_none(tmp_path):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("")
    assert browser._read_devtools_port(tmp_path) is None
