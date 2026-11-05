import pytest

from moonlighter.core.config.loading import load_profile


def test_load_profile(tmp_path):
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text("""
skills:
  - name: Elixir/Phoenix
    years: 8
    level: expert
criteria:
  hard_filters:
    - "descarta se exigir .NET"
""")
    profile = load_profile(profile_path=str(profile_file))
    assert profile["skills"][0]["name"] == "Elixir/Phoenix"
    assert len(profile["criteria"]["hard_filters"]) == 1


def test_load_profile_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_profile(profile_path="/nonexistent/profile.yaml")


def test_load_profile_empty_yaml_returns_empty_dict(tmp_path):
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text("")
    profile = load_profile(profile_path=str(profile_file))
    assert profile == {}


def test_load_profile_full_structure(tmp_path):
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text("""
skills:
  - name: Elixir/Phoenix
    years: 8
experience:
  - company: Acme
    role: Senior Dev
preferences:
  remote: true
criteria:
  hard_filters:
    - "descarta se exigir .NET"
""")
    profile = load_profile(profile_path=str(profile_file))
    for key in ("skills", "experience", "preferences", "criteria"):
        assert key in profile, f"key '{key}' missing from profile"
