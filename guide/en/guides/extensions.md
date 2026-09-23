🇺🇸 [English](extensions.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/guides/extensions/)

# Extensions: adding a new ATS scanner

Every built-in ATS integration (Greenhouse, Lever, Ashby, Recruitee, Workable, SmartRecruiters, InHire) and portal feed (RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring, Gupy) is a normal part of this repo — but moonlighter also supports **scanner extensions**: separate, independently installed Python packages that register a new job-listing source without forking or modifying this repo at all.

This is how LinkedIn scanning is distributed — not because the mechanism is LinkedIn-specific, but because LinkedIn's own Terms of Service explicitly and unambiguously prohibit automation (see [DISCLAIMER.md](https://github.com/albertosca/moonlighter/blob/main/DISCLAIMER.md)), so that integration ships as an opt-in extension instead of bundled code anyone who clones this repo gets by default.

Browser-driven form filling and submission is not part of this repo at all (see [how it works](../index.md)) and is not an extension point — `prepare_application` composes answers for you to paste yourself, for any ATS.

## How an extension works

An extension is a normal Python package that:

1. Depends on `moonlighter-core` and `moonlighter-scan`, pinned to a released tag of this repo.
2. Ships its own module implementing a `BaseScanner` subclass (see [`packages/scan/moonlighter/discovery/sources/base.py`](https://github.com/albertosca/moonlighter/blob/main/packages/scan/moonlighter/discovery/sources/base.py)).
3. Declares itself via `entry_points` in its own `pyproject.toml` — no code in this repo ever imports or names the extension:

    ```toml
    [project.entry-points."moonlighter.scanners"]
    my_platform = "my_package.my_module:MyScanner"

    # Optional: a browser-based staleness check for a source with no listing API
    [project.entry-points."moonlighter.staleness_checkers"]
    my_platform = "my_package.my_module:check_staleness"
    ```

    A browser-based scanner (like `moonlighter.scanners` entries typically are) needs `moonlighter-core[browser]` — see [Requirements](../getting-started/install.md#requirements); a pure-HTTP scanner needs nothing extra.

4. Must be present in the **same** Python environment moonlighter runs from, so its entry points are discoverable at runtime. If you installed moonlighter via `uvx moonlighter`, there's no persistent environment to add a package to — use one of:
    - `uvx --with my-extension-package moonlighter` — ephemeral, per invocation
    - `uv tool install moonlighter --with my-extension-package` — persistent tool install

    If you're developing on this repo directly, `uv add --editable`/`pip install` your extension package into the same environment works as before. At runtime, `moonlighter.core.plugins.discover_entry_points`/`discover_entry_points_by_name` enumerate whatever's registered under each group — an environment with no extensions installed behaves exactly as before (empty list/dict, nothing breaks).

Because the top-level `moonlighter` package is a [PEP 420 namespace package](https://peps.python.org/pep-0420/) (no `__init__.py` at that level), an extension can even contribute its own top-level subpackage (e.g. `moonlighter/my_extension/`) that coexists with `moonlighter.core`/`moonlighter.discovery`/etc. Just don't place files *inside* an existing subpackage like `moonlighter/discovery/sources/`: that is a regular (non-namespace) package owned entirely by this repo's own distributions, and a second distribution writing to the same path silently collides at install time. Give your extension its own top-level directory instead.

## Real example

The private `moonlighter-linkedin` extension (not published, for the reason above) follows exactly this pattern for scanning — its `LinkedInScanner` lives in its own `moonlighter/linkedin_ext/` package, registered via the `moonlighter.scanners` entry point group above. If you're building your own scanner extension, that's the reference shape to copy.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
