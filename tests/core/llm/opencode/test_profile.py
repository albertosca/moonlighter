"""The locked `opencode run` call: config, environment, argv and the files a call writes."""

import json
import stat

from moonlighter.core.llm.opencode_profile import (
    AGENT_NAME,
    locked_config,
    opencode_environment,
    opencode_run_argv,
    write_call_files,
)

DENY_ALL = [{"action": "*", "resource": "*", "effect": "deny"}]
LOCKED_VARIABLES = {
    "OPENCODE_DISABLE_CLAUDE_CODE": "1",
    "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1",
    "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_FILEWATCHER": "1",
}


def _keys(value: object) -> set[str]:
    """Every key anywhere in a nested dict/list."""
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _keys(child)}
    return set()


def test_every_permission_is_denied_at_the_top_and_in_the_agent():
    config = locked_config()
    assert config["permissions"] == DENY_ALL
    assert config["agents"][AGENT_NAME]["permissions"] == DENY_ALL


def test_the_only_agent_is_the_primary_call_agent():
    agents = locked_config()["agents"]
    assert list(agents) == ["moonlighter-call"]
    assert agents["moonlighter-call"]["mode"] == "primary"


def test_steps_is_never_set_because_it_injects_text_into_the_answer():
    assert "steps" not in _keys(locked_config())


def test_sharing_and_automations_are_off():
    config = locked_config()
    assert config["share"] == "disabled"
    assert config["automations"] is False


def test_the_policies_deny_tools_mcp_skills_plugins_and_web_search():
    policies = locked_config()["policies"]
    assert {policy["action"] for policy in policies} == {
        "tool.use",
        "mcp.use",
        "skill.use",
        "plugin.use",
        "websearch.use",
    }
    assert all(policy["effect"] == "deny" and policy["resource"] == "*" for policy in policies)


def test_each_call_gets_its_own_config():
    first = locked_config()
    first["agents"][AGENT_NAME]["permissions"].clear()
    first["permissions"].clear()
    assert locked_config()["agents"][AGENT_NAME]["permissions"] == DENY_ALL
    assert locked_config()["permissions"] == DENY_ALL


def test_the_environment_drops_the_pointers_to_the_persons_config(tmp_path):
    inherited = {
        "OPENCODE_CONFIG": "/home/me/opencode.json",
        "OPENCODE_CONFIG_CONTENT": "{}",
        "OPENCODE_CONFIG_DIR": "/home/me/.config/opencode",
        "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
        "OPENAI_API_KEY": "sk-test",
        "PATH": "/usr/bin",
    }
    environment = opencode_environment(inherited, tmp_path / "config")
    for pointer in (
        "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_CONTENT",
        "OPENCODE_DISABLE_PROJECT_CONFIG",
    ):
        assert pointer not in environment
    assert environment["OPENCODE_CONFIG_DIR"] == str(tmp_path / "config")
    assert environment["OPENAI_API_KEY"] == "sk-test"
    assert environment["PATH"] == "/usr/bin"
    assert LOCKED_VARIABLES.items() <= environment.items()


def test_the_environment_leaves_the_inherited_mapping_alone(tmp_path):
    inherited = {"OPENCODE_CONFIG": "x"}
    opencode_environment(inherited, tmp_path)
    assert inherited == {"OPENCODE_CONFIG": "x"}


def test_the_argv_names_the_agent_and_the_model_and_never_the_prompt():
    assert opencode_run_argv("/opt/bin/opencode", "fake/echo") == [
        "/opt/bin/opencode",
        "run",
        "--standalone",
        "--archived",
        "--title",
        "call",
        "--agent",
        "moonlighter-call",
        "-m",
        "fake/echo",
        "--format",
        "json",
    ]


def test_the_call_files_are_the_locked_config_and_an_empty_private_config_directory(tmp_path):
    config_directory = write_call_files(tmp_path)
    assert json.loads((tmp_path / "opencode.json").read_text()) == locked_config()
    assert config_directory == tmp_path / "config"
    assert list(config_directory.iterdir()) == []
    assert stat.S_IMODE(config_directory.stat().st_mode) == 0o700
