"""The MCP server's composition root: lifespan wiring, tool registration and the entry point."""

import contextlib
import sys
from collections.abc import AsyncIterator

from mcp.server.mcpserver import MCPServer

from moonlighter.app_context import AppContext, WatchedFile
from moonlighter.core.cli import emit
from moonlighter.core.config.company_list import load_company_list
from moonlighter.core.config.loading import load_config, load_profile
from moonlighter.core.config.paths import moonlighter_home
from moonlighter.core.config.permissions import harden_permissions
from moonlighter.core.config.validation import validate_config
from moonlighter.core.db import init_db
from moonlighter.core.doctor import doctor_payload
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.log import setup as setup_logging
from moonlighter.init import main as init_main
from moonlighter.mcp_tools import (
    answer_bank,
    applications,
    cv_pool,
    email_tracking,
    jobs,
    scanning,
)
from moonlighter.startup import validate_startup


@contextlib.asynccontextmanager
async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
    """MCPServer lifespan: loads+validates config, inits DB, hardens permissions, runs startup checks.

    Yields the AppContext. Raises ConfigError before yielding on an invalid config,
    refusing to boot.
    """
    setup_logging()
    home = moonlighter_home()
    config_file = WatchedFile(home / "config.yaml")
    profile_file = WatchedFile(home / "profile.yaml")
    config = load_config()
    validate_config(config)  # raises ConfigError -> server refuses to boot
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = {}
    companies = load_company_list()
    init_db()
    permission_warnings = harden_permissions()
    startup_warnings = validate_startup(config, profile)
    for message in permission_warnings:
        print(f"⚠️  {message}", file=sys.stderr, flush=True)  # noqa: T201 - the boot report is for the human on stderr; stdout carries the MCP protocol
    for warning in startup_warnings:
        prefix = "🚫" if warning.level == "error" else "⚠️ "
        print(f"{prefix} {warning.message}", file=sys.stderr, flush=True)  # noqa: T201 - the boot report is for the human on stderr; stdout carries the MCP protocol
    llm_caller = make_caller(config)
    yield AppContext(
        config=config,
        profile=profile,
        companies=companies,
        llm_caller=llm_caller,
        startup_warnings=startup_warnings,
        permission_warnings=permission_warnings,
        config_file=config_file,
        profile_file=profile_file,
    )


mcp = MCPServer("moonlighter", lifespan=lifespan)

# The order is part of what a client sees in tools/list.
_TOOLS = (
    scanning.scan_and_evaluate,
    scanning.scan_company,
    scanning.add_job,
    scanning.verify_job,
    scanning.archive_stale_jobs,
    jobs.list_jobs,
    jobs.get_job,
    applications.prepare_application,
    applications.prepare_application_from_paste,
    applications.get_pipeline,
    jobs.reopen_job,
    applications.update_status,
    answer_bank.list_answer_bank,
    answer_bank.forget_answer,
    email_tracking.setup_email,
    cv_pool.bootstrap_cv_pool,
    cv_pool.skip_cv_bootstrap,
    email_tracking.sync_email_responses,
)
for _tool in _TOOLS:
    mcp.add_tool(_tool)
del _tool


_USAGE = """usage: moonlighter [init | doctor | -h]

  (no arguments)  start the MCP server on stdio (what Claude Code runs)
  init            interactive first-run setup: writes config.yaml
  doctor          where the state lives and whether the config loads, as JSON
"""


def _dispatch(argv: list[str]) -> int | None:
    """Everything `moonlighter <word>` can do besides serving MCP.

    None means "no subcommand: run the server". `init` stays where it was (it is
    interactive); `doctor` and help are the two things a script or a human
    may ask a stdio server binary before deciding to run it.
    """
    if not argv:
        return None
    if argv[0] in ("-h", "--help"):
        sys.stdout.write(_USAGE)
        return 0
    if argv[0] == "doctor":
        payload, code = doctor_payload()
        return emit(payload, code)
    return None


def main() -> None:  # pragma: no cover - MCP server entry point (boundary)
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_main()
        return
    code = _dispatch(sys.argv[1:])
    if code is not None:
        sys.exit(code)
    mcp.run()


if __name__ == "__main__":
    main()
