# Claude Code Instructions

Full project context is in [`.github/copilot-instructions.md`](.github/copilot-instructions.md). Read it before working on any task.

## Development Workflow

The CLI entry point is `percona-obs` (bash wrapper, no file extension).
The Python implementation lives in the `percona_obs/` package.
The virtualenv is at `venv/` — use it for all tooling commands.

**If `venv/` does not exist, create it and install dependencies before doing anything else:**

```sh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

**After every code change, always run both tools in this order:**

```sh
venv/bin/black percona_obs/     # format
venv/bin/pyright                # type-check
```

Both must pass (black: "N files reformatted" or "N files left unchanged"; pyright: "0 errors") before considering the task done.

## Git Commits

Always use `git commit -s` (signed-off-by). Do not add `Co-Authored-By: Claude` lines.

## Reading the source

**Before working on any task that involves the `percona_obs/` package, read the relevant source files first.** Do not propose or make changes to code you have not read. The key files are listed in the table below — read the ones that are in scope for the task before suggesting anything.

## Implementation Planning

**Before changing any code, always write an implementation plan and show it to the user for approval.** Only proceed with code changes after the user has explicitly approved the plan. This applies to all non-trivial changes (new features, refactors, multi-file edits).

## Key Files

| File | Purpose |
|---|---|
| `percona-obs` | Bash wrapper — invokes `python -m percona_obs` |
| `percona_obs/` | Python package — all implementation lives here |
| `percona_obs/cli.py` | Argument parser and `main()` entry point |
| `percona_obs/cmd_sync.py` | `sync` command implementation |
| `percona_obs/cmd_build.py` | `build trigger` / `build status` implementation |
| `percona_obs/cmd_profile.py` | `profile` command implementation |
| `percona_obs/obs_api.py` | OBS API wrappers |
| `percona_obs/common.py` | Shared constants, colour helpers, data utilities |
| `percona_obs/targets.py` | Target resolution helpers |
| `percona_obs/services.py` | Local OBS service execution + caching |
| `percona_obs/git_utils.py` | Git helpers |
| `requirements.txt` | Runtime + dev dependencies (`osc`, `pyyaml`, `black`, `pyright`) |
| `pyrightconfig.json` | Pyright config pointing at `venv/` and `percona_obs/` |
| `root/` | All packaging content (project hierarchy mirrors OBS) |
| `root/README.md` | Packaging tree structure — how `root/` maps to OBS projects |
| `docs/PERCONA_OBS_TOOL.md` | `percona-obs` tool reference (profiles, sync, branching) |
| `docs/PACKAGING_HOWTO.md` | Step-by-step guide for adding a new package from scratch |
| `docs/HOWTO_IMPORT_PACKAGES_FROM_PERCONA_PACKAGING.md` | Step-by-step guide for importing from `percona/postgres-packaging` |
| `.github/copilot-instructions.md` | Full project and architecture reference |
