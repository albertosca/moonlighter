from moonlighter.core.llm import codex_profile


def test_the_profile_also_grants_the_directory_the_symlink_resolves_to(monkeypatch):
    monkeypatch.setattr(
        codex_profile.os.path, "realpath", lambda path: "/opt/Caskroom/codex/1/bin/codex"
    )
    joined = " ".join(codex_profile._codex_permission_args("/opt/bin/codex"))
    assert '"/opt/bin"="read"' in joined
    assert '"/opt/Caskroom/codex/1/bin"="read"' in joined


def test_the_permission_args_are_pinned_with_both_binary_directories(monkeypatch):
    monkeypatch.setattr(
        codex_profile.os.path, "realpath", lambda path: "/opt/Caskroom/codex/1/bin/codex"
    )
    assert codex_profile._codex_permission_args("/opt/bin/codex") == [
        "-c",
        'default_permissions="moonlighter-locked"',
        "-c",
        (
            'permissions.moonlighter-locked.filesystem={":minimal"="read",":root"="deny",'
            '"/opt/bin"="read","/opt/Caskroom/codex/1/bin"="read",":workspace_roots"={"."="read"}}'
        ),
        "-c",
        "permissions.moonlighter-locked.network={enabled=false}",
    ]
