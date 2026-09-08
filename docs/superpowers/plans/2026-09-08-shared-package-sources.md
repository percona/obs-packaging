# Shared Package Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep one copy of `percona-pg_stat_monitor` packaging under `root/ppg/staging/_shared/` and have every `ppg:staging:<V>` subproject (14–18) sync it rendered with its own PG major.

**Architecture:** A tier-level `_shared/` directory is invisible to project/package discovery and holds full package directories. Each per-major package directory becomes a git symlink into `_shared/`; `pathlib` follows the link for content but keeps macro resolution lexical, so each subproject renders `%!{PG_MAJOR_VERSION}` from its own `macros.yaml`. `git_utils` change detection is taught to include the symlink target so edits in `_shared/` still trigger syncs, promotes and manifest invalidation.

**Tech Stack:** Python 3.13, pytest (`tests/`), black, pyright, git symlinks.

**Spec:** `docs/superpowers/specs/2026-09-08-shared-package-sources-design.md`

## Global Constraints

- Tooling gate after every code change, in this order: `venv/bin/black percona_obs/` then `venv/bin/pyright` → must report `0 errors`. Then `venv/bin/python -m pytest -q` → all pass (201 tests pass on `main` today).
- Commits use `git commit -s`. No `Co-Authored-By: Claude` lines. Never `git push`, never `gh pr create` (the user does that).
- The shared directory name is exactly `_shared` (constant `SHARED_SOURCE_DIRNAME` in `percona_obs/common.py`). Nothing else in `root/` starts with `_` today.
- Symlink targets are relative (`../_shared/<package>`), never absolute.
- The symlink target used for git pathspecs is computed **lexically** (`os.readlink` + `os.path.normpath`), never with `Path.resolve()`, so a repo checkout that itself lives under a symlink keeps producing in-worktree paths.
- Macro resolution (`load_macros`, `_macros_chain_files`, `_inherited_macros_files`) must keep using the lexical package path (the symlink location), never the target.
- Do not touch `root/ppg/devel/*` copies.

**User decisions (already made):**
- Deduplicate at the sync layer (git tree + `percona-obs`), not via OBS `_link`/`ppg:staging:extensions` (OBS has no Debian macro mechanism; confirmed in obs-build `Build/Deb.pm`).
- Scope is `ppg:staging:*` only; `ppg:devel:*` is left as is.
- Planner's assumption (not yet confirmed by the user): the canonical shared copy is the **staging/18** variant (has the `set_version` `basename` param and `debian/source/lintian-overrides`) **plus** `debian/source/options` (`extend-diff-ignore = rpm/`) from the 14–17 copies. Flag this in the first commit message.

---

### Task 1: Discovery skips `_shared/` and follows symlinked packages

**Goal:** `find_packages`/`find_projects` never treat `_shared/` as a project or package, while a symlinked package directory is discovered under its lexical subproject with that subproject's macros.

**Files:**
- Modify: `percona_obs/common.py:117-145` (`is_package`, `is_project`, `find_packages`) and `percona_obs/common.py:590-602` (`find_projects`)
- Test: `tests/test_shared_source.py` (create)

**Acceptance Criteria:**
- [ ] `SHARED_SOURCE_DIRNAME == "_shared"` and `is_shared_source_dir(path)` exist in `percona_obs/common.py`.
- [ ] `find_packages(root/ppg/staging, "X:ppg:staging")` yields no entry whose project contains `:_shared` and no path under `_shared/`.
- [ ] `find_projects(root/ppg/staging, "X:ppg:staging")` yields no `:_shared` project.
- [ ] A symlinked package `staging/17/pkg -> ../_shared/pkg` is yielded as `("X:ppg:staging:17", root/ppg/staging/17/pkg)` and `load_macros(that_path)["PG_MAJOR_VERSION"] == "17"`.

**Verify:** `venv/bin/python -m pytest tests/test_shared_source.py -q -k discovery` → all pass; `venv/bin/black percona_obs/ && venv/bin/pyright` → `0 errors`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_shared_source.py`:

```python
"""Shared package sources: ``_shared/`` directories and symlinked package dirs.

One copy of a package's packaging lives in ``root/<tier>/_shared/<pkg>/`` and
each per-major subproject holds a relative git symlink to it.  Discovery must
ignore ``_shared/`` itself, follow the symlink for content, and resolve macros
from the symlink's lexical location.  Git change detection must see edits to
the symlink target (git scopes ``diff``/``log``/``status`` to the link blob
otherwise).
"""

import os
import subprocess
from pathlib import Path

import pytest

import percona_obs.common as common
import percona_obs.git_utils as git_utils
from percona_obs.common import (
    SHARED_SOURCE_DIRNAME,
    find_packages,
    find_projects,
    is_shared_source_dir,
    load_macros,
)

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(GIT + list(args), cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def tree(monkeypatch, tmp_path):
    """root/ppg/staging/{_shared/pkg, 14/pkg -> link, 17/pkg -> link} in a git repo.

    Returns (repo, sha) with the initial layout committed.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "root/ppg/staging/macros.yaml", "- PG_STAT_MONITOR_VERSION: 2.4.0\n")
    _write(repo, "root/ppg/staging/14/macros.yaml", "- PG_MAJOR_VERSION: 14\n")
    _write(repo, "root/ppg/staging/17/macros.yaml", "- PG_MAJOR_VERSION: 17\n")
    shared = f"root/ppg/staging/{SHARED_SOURCE_DIRNAME}/pkg"
    _write(repo, f"{shared}/obs/_service", "<services/>\n")
    _write(repo, f"{shared}/debian/pgversions", "%!{PG_MAJOR_VERSION}\n")
    _write(repo, f"{shared}/rpm/pkg.spec", "%global pgmajorversion %!{PG_MAJOR_VERSION}\n")
    for v in ("14", "17"):
        link = repo / f"root/ppg/staging/{v}/pkg"
        os.symlink(f"../{SHARED_SOURCE_DIRNAME}/pkg", link)
    # An ordinary (non-shared) package so discovery still finds real dirs.
    _write(repo, "root/ppg/staging/17/plain/obs/_service", "<services/>\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial")
    sha = _git(repo, "rev-parse", "--short", "HEAD")

    monkeypatch.setattr(common, "REPO_ROOT", repo / "root")
    monkeypatch.setattr(git_utils, "_REPO_DIR", repo)
    monkeypatch.setattr(git_utils, "_REPO_ROOT", repo / "root")
    return repo, sha


# --- discovery ---------------------------------------------------------------


def test_discovery_is_shared_source_dir(tree):
    repo, _ = tree
    assert is_shared_source_dir(repo / "root/ppg/staging" / SHARED_SOURCE_DIRNAME)
    assert not is_shared_source_dir(repo / "root/ppg/staging/17")


def test_discovery_find_packages_skips_shared_and_follows_links(tree):
    repo, _ = tree
    found = list(find_packages(repo / "root/ppg/staging", "X:ppg:staging"))
    projects = {p for p, _ in found}
    assert not any(SHARED_SOURCE_DIRNAME in p for p in projects)
    assert ("X:ppg:staging:14", repo / "root/ppg/staging/14/pkg") in found
    assert ("X:ppg:staging:17", repo / "root/ppg/staging/17/pkg") in found
    assert ("X:ppg:staging:17", repo / "root/ppg/staging/17/plain") in found
    assert not any(SHARED_SOURCE_DIRNAME in path.parts for _, path in found)


def test_discovery_find_projects_skips_shared(tree):
    repo, _ = tree
    names = [name for name, _ in find_projects(repo / "root/ppg/staging", "X:ppg:staging")]
    assert "X:ppg:staging:14" in names
    assert "X:ppg:staging:17" in names
    assert not any(SHARED_SOURCE_DIRNAME in n for n in names)


def test_discovery_symlinked_package_resolves_macros_lexically(tree):
    repo, _ = tree
    assert load_macros(repo / "root/ppg/staging/14/pkg")["PG_MAJOR_VERSION"] == "14"
    assert load_macros(repo / "root/ppg/staging/17/pkg")["PG_MAJOR_VERSION"] == "17"
    # Content is reachable through the link.
    assert (repo / "root/ppg/staging/17/pkg/debian/pgversions").is_file()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_shared_source.py -q -k discovery`
Expected: FAIL at import with `ImportError: cannot import name 'SHARED_SOURCE_DIRNAME'`.

- [ ] **Step 3: Implement the constant, predicate and exclusions**

In `percona_obs/common.py`, directly above `def _is_release_dir` (line ~113), add:

```python
# Directory name (per tier, e.g. root/ppg/staging/_shared/) holding complete
# package directories that per-major subprojects reference via relative git
# symlinks.  It is neither a project nor a package: discovery skips it, and
# each symlink is discovered under its own subproject so %!{VAR} macros render
# from that subproject's macros.yaml chain.
SHARED_SOURCE_DIRNAME = "_shared"


def is_shared_source_dir(path: Path) -> bool:
    """Return True if *path* is a ``_shared/`` source library directory."""
    return path.name == SHARED_SOURCE_DIRNAME
```

In `find_packages`, change the loop body so `_shared` is skipped alongside release dirs:

```python
    for child in sorted(project_path.iterdir()):
        if not child.is_dir():
            continue
        if _is_release_dir(child) or is_shared_source_dir(child):
            continue
        if is_package(child):
            yield obs_project, child
        elif recursive:
            yield from find_packages(child, f"{obs_project}:{child.name}")
```

In `find_projects`, change the child filter:

```python
    for child in sorted(path.iterdir()):
        if (
            child.is_dir()
            and not _is_release_dir(child)
            and not is_shared_source_dir(child)
            and is_project(child)
        ):
            yield from find_projects(child, f"{obs_project}:{child.name}")
```

Update the `find_packages` docstring with one sentence: "``_shared/`` source-library directories are skipped; symlinked package directories are yielded under the subproject that holds the link."

- [ ] **Step 4: Run tests, formatter and type checker**

Run: `venv/bin/python -m pytest tests/test_shared_source.py -q -k discovery`
Expected: 4 passed.
Run: `venv/bin/black percona_obs/ && venv/bin/pyright`
Expected: black reformats or leaves unchanged; pyright `0 errors`.
Run: `venv/bin/python -m pytest -q`
Expected: all pass (201 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add percona_obs/common.py tests/test_shared_source.py
git commit -s -m "common: skip _shared/ source libraries in project/package discovery"
```

---

### Task 2: Git change detection sees through symlinked package dirs

**Goal:** Every git-scoped check in `git_utils` includes the symlink target's path, so an edit under `_shared/` counts as a change (committed or dirty) for each linking package.

**Files:**
- Modify: `percona_obs/git_utils.py:1-6` (imports), `:54-137` (the three `_has_*_since` functions), `:142-162` (`_is_path_dirty`)
- Test: `tests/test_shared_source.py` (extend)

**Acceptance Criteria:**
- [ ] `git_utils._package_pathspecs(Path)` returns `[path]` for a real dir and `[path, lexical_target]` for a symlinked dir; the target is computed with `os.readlink` + `os.path.normpath`, not `Path.resolve()`.
- [ ] After committing an edit to `_shared/pkg/debian/pgversions`, `_has_package_changes_since(sha, staging/17/pkg)`, `_has_package_content_changes_since(sha, staging/17/pkg)` and `_has_non_obs_package_changes_since(sha, staging/17/pkg)` all return `True`.
- [ ] After committing an edit to `_shared/pkg/obs/_service` only, `_has_non_obs_package_changes_since` returns `False` (obs/ under the target is still "obs/").
- [ ] With an uncommitted edit to `_shared/pkg/rpm/pkg.spec`, `_is_path_dirty(staging/17/pkg)` returns `True`.
- [ ] With no edits, all four return `False`.
- [ ] `_macros_changed_since(sha, staging/17/pkg)` still works unchanged (it already walks the link top with `rglob` and resolves macros lexically): bumping `staging/17/macros.yaml` → `True` for the 17 link, `False` for the 14 link.

**Verify:** `venv/bin/python -m pytest tests/test_shared_source.py -q` → all pass; `venv/bin/black percona_obs/ && venv/bin/pyright` → `0 errors`; `venv/bin/python -m pytest -q` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_shared_source.py`:

```python
# --- git change detection ----------------------------------------------------

from percona_obs.git_utils import (  # noqa: E402
    _has_non_obs_package_changes_since,
    _has_package_changes_since,
    _has_package_content_changes_since,
    _is_path_dirty,
    _macros_changed_since,
    _package_pathspecs,
)


def _commit(repo: Path, msg: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def test_git_pathspecs_plain_dir(tree):
    repo, _ = tree
    plain = repo / "root/ppg/staging/17/plain"
    assert _package_pathspecs(plain) == [plain]


def test_git_pathspecs_symlink_adds_lexical_target(tree):
    repo, _ = tree
    link = repo / "root/ppg/staging/17/pkg"
    assert _package_pathspecs(link) == [
        link,
        repo / "root/ppg/staging" / SHARED_SOURCE_DIRNAME / "pkg",
    ]


def test_git_no_change_all_false(tree):
    repo, sha = tree
    link = repo / "root/ppg/staging/17/pkg"
    assert _has_package_changes_since(sha, link) is False
    assert _has_package_content_changes_since(sha, link) is False
    assert _has_non_obs_package_changes_since(sha, link) is False
    assert _is_path_dirty(link) is False


def test_git_committed_shared_debian_edit_is_seen_via_link(tree):
    repo, sha = tree
    _write(repo, f"root/ppg/staging/{SHARED_SOURCE_DIRNAME}/pkg/debian/pgversions", "%!{PG_MAJOR_VERSION}\n# bump\n")
    _commit(repo, "edit shared debian")
    link = repo / "root/ppg/staging/17/pkg"
    assert _has_package_changes_since(sha, link) is True
    assert _has_package_content_changes_since(sha, link) is True
    assert _has_non_obs_package_changes_since(sha, link) is True


def test_git_committed_shared_obs_only_edit_is_obs_only(tree):
    repo, sha = tree
    _write(repo, f"root/ppg/staging/{SHARED_SOURCE_DIRNAME}/pkg/obs/_service", "<services>\n</services>\n")
    _commit(repo, "edit shared obs")
    link = repo / "root/ppg/staging/17/pkg"
    assert _has_package_changes_since(sha, link) is True
    assert _has_non_obs_package_changes_since(sha, link) is False


def test_git_dirty_shared_edit_is_seen_via_link(tree):
    repo, _ = tree
    _write(repo, f"root/ppg/staging/{SHARED_SOURCE_DIRNAME}/pkg/rpm/pkg.spec", "%global pgmajorversion %!{PG_MAJOR_VERSION}\n# dirty\n")
    assert _is_path_dirty(repo / "root/ppg/staging/17/pkg") is True
    assert _is_path_dirty(repo / "root/ppg/staging/17/plain") is False


def test_git_macros_changed_since_is_per_subproject(tree):
    repo, sha = tree
    _write(repo, "root/ppg/staging/17/macros.yaml", "- PG_MAJOR_VERSION: 17\n- PG_STAT_MONITOR_VERSION: 2.5.0\n")
    _commit(repo, "bump 17 only")
    assert _macros_changed_since(sha, repo / "root/ppg/staging/17/pkg") is False  # pkg does not reference PG_STAT_MONITOR_VERSION
    _write(repo, "root/ppg/staging/17/macros.yaml", "- PG_MAJOR_VERSION: 170\n")
    _commit(repo, "change referenced macro on 17")
    assert _macros_changed_since(sha, repo / "root/ppg/staging/17/pkg") is True
    assert _macros_changed_since(sha, repo / "root/ppg/staging/14/pkg") is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_shared_source.py -q -k git`
Expected: FAIL at import with `ImportError: cannot import name '_package_pathspecs'`.

- [ ] **Step 3: Implement `_package_pathspecs` and use it**

In `percona_obs/git_utils.py`, add `import os` to the imports. Directly above `def _has_non_obs_package_changes_since` add:

```python
def _package_pathspecs(package_path: Path) -> list[Path]:
    """Return the git pathspecs that cover *package_path*'s content.

    A package directory may be a relative symlink into a ``_shared/`` source
    library (see ``common.SHARED_SOURCE_DIRNAME``).  git scopes ``diff``,
    ``log`` and ``status`` to the link *blob* in that case, so the lexical
    link target is added as a second pathspec.  The target is computed with
    ``os.readlink`` + ``normpath`` rather than ``Path.resolve()`` so the result
    stays inside the worktree's own path namespace even when the checkout
    itself sits under a symlink.
    """
    paths = [package_path]
    if package_path.is_symlink():
        target = os.path.normpath(package_path.parent / os.readlink(package_path))
        paths.append(Path(target))
    return paths
```

Change the three diff/log functions to pass all pathspecs. In `_has_non_obs_package_changes_since`:

```python
    paths = _package_pathspecs(package_path)
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{short_sha}..HEAD", "--", *map(str, paths)],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        return True  # unknown SHA or git error — safe default
    if not result.stdout.strip():
        return False
    # git diff --name-only outputs paths relative to the repo root with
    # forward slashes on all platforms.
    try:
        obs_prefixes = [str((p / "obs").relative_to(_REPO_DIR)) + "/" for p in paths]
    except ValueError:
        return True
    for line in result.stdout.splitlines():
        path = line.strip()
        if path and not any(path.startswith(prefix) for prefix in obs_prefixes):
            return True
    return False
```

In `_has_package_content_changes_since` replace `str(package_path)` in the argv with `*map(str, _package_pathspecs(package_path))`. In `_has_package_changes_since` do the same for the `git log` argv.

In `_is_path_dirty`, expand each given path:

```python
    if not paths:
        return False
    specs = [str(p) for path in paths for p in _package_pathspecs(path)]
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *specs],
        ...
```

Add one sentence to each touched docstring: "Symlinked package directories also cover their `_shared/` target (see `_package_pathspecs`)."

- [ ] **Step 4: Run tests, formatter and type checker**

Run: `venv/bin/python -m pytest tests/test_shared_source.py -q`
Expected: 11 passed.
Run: `venv/bin/black percona_obs/ && venv/bin/pyright`
Expected: pyright `0 errors`.
Run: `venv/bin/python -m pytest -q`
Expected: all pass (existing `test_macros_changed_since.py`, `test_sync_state.py`, `test_skip_unchanged.py` must stay green: they exercise the same functions on plain dirs).

- [ ] **Step 5: Commit**

```bash
git add percona_obs/git_utils.py tests/test_shared_source.py
git commit -s -m "git_utils: include symlink target in package change detection"
```

---

### Task 3: Move `percona-pg_stat_monitor` into `ppg/staging/_shared/` and link 14–18

**Goal:** One canonical packaging copy under `root/ppg/staging/_shared/percona-pg_stat_monitor/`, with `root/ppg/staging/{14,15,16,17,18}/percona-pg_stat_monitor` as relative symlinks, rendering the right PG major per subproject.

**Files:**
- Create (via `git mv`): `root/ppg/staging/_shared/percona-pg_stat_monitor/` (from `root/ppg/staging/18/percona-pg_stat_monitor/`)
- Create: `root/ppg/staging/_shared/percona-pg_stat_monitor/debian/source/options`
- Delete: `root/ppg/staging/{14,15,16,17}/percona-pg_stat_monitor/` (directories)
- Create: symlinks `root/ppg/staging/{14,15,16,17,18}/percona-pg_stat_monitor -> ../_shared/percona-pg_stat_monitor`

**Acceptance Criteria:**
- [ ] `git ls-files -s root/ppg/staging/1?/percona-pg_stat_monitor` shows five entries with mode `120000` (symlinks), each pointing to `../_shared/percona-pg_stat_monitor`.
- [ ] `diff -r` between the pre-move staging/18 copy and `_shared/` shows only the added `debian/source/options`.
- [ ] Local rendering check (below) produces `debian/pgversions` = `14`, `17`, `18` and `%global pgmajorversion 14/17/18` respectively for the three linked dirs.
- [ ] `venv/bin/python -m pytest -q` still passes; `git status` clean after commit.

**Verify:** the render script in Step 3 prints `14 14 / 17 17 / 18 18`; `git ls-files -s root/ppg/staging/1?/percona-pg_stat_monitor | awk '{print $1}' | sort -u` → `120000`.

**Steps:**

- [ ] **Step 1: Move the canonical copy and unify the drift**

```bash
cd /home/rdias/Work/percona-obs-packaging
mkdir -p root/ppg/staging/_shared
git mv root/ppg/staging/18/percona-pg_stat_monitor root/ppg/staging/_shared/percona-pg_stat_monitor
# 14–17 carried debian/source/options (extend-diff-ignore = rpm/); 18 lacked it. Keep the union.
git mv root/ppg/staging/17/percona-pg_stat_monitor/debian/source/options \
       root/ppg/staging/_shared/percona-pg_stat_monitor/debian/source/options
git rm -r -q root/ppg/staging/14/percona-pg_stat_monitor \
             root/ppg/staging/15/percona-pg_stat_monitor \
             root/ppg/staging/16/percona-pg_stat_monitor \
             root/ppg/staging/17/percona-pg_stat_monitor
```

Then confirm the only content difference to the old copies is the known drift:

```bash
git diff --cached --stat -M | tail -5
git show HEAD:root/ppg/staging/17/percona-pg_stat_monitor/obs/_service | diff - root/ppg/staging/_shared/percona-pg_stat_monitor/obs/_service
```
Expected: the `_service` diff shows only the added `<param name="basename">percona-pg_stat_monitor</param>` lines (the 18 variant).

- [ ] **Step 2: Create the five relative symlinks**

```bash
for v in 14 15 16 17 18; do
  ln -s ../_shared/percona-pg_stat_monitor root/ppg/staging/$v/percona-pg_stat_monitor
  git add root/ppg/staging/$v/percona-pg_stat_monitor
done
git ls-files -s root/ppg/staging/1?/percona-pg_stat_monitor
```
Expected: five lines, mode `120000`.

- [ ] **Step 3: Render locally and check the PG major per subproject**

Write and run this from the repo root (needs no OBS access; `_copy_local_packaging` is the exact function `sync push` uses):

```bash
venv/bin/python - <<'EOF'
import subprocess, tempfile
from pathlib import Path
from percona_obs.common import load_macros
from percona_obs.services import _copy_local_packaging

for v in ("14", "17", "18"):
    pkg = Path(f"root/ppg/staging/{v}/percona-pg_stat_monitor")
    out = Path(tempfile.mkdtemp(prefix=f"render-{v}-"))
    _copy_local_packaging(pkg / "obs", out, pkg_label=v, macros=load_macros(pkg))
    pgv = subprocess.run(
        ["tar", "-xOzf", str(out / "debian.tar.gz"), "debian/pgversions"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    spec = (out / "percona-pg_stat_monitor.spec").read_text()
    major = [l for l in spec.splitlines() if l.startswith("%global pgmajorversion")][0].split()[-1]
    dsc = (out / "debian.dsc").read_text()
    assert f"percona-pg-stat-monitor{v}" in dsc, dsc
    print(v, pgv, major)
EOF
```
Expected output:
```
14 14 14
17 17 17
18 18 18
```

- [ ] **Step 4: Run the full test suite**

Run: `venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A root/ppg/staging
git commit -s -m "ppg:staging: share percona-pg_stat_monitor packaging across 14-18 via _shared/

One canonical copy under root/ppg/staging/_shared/; the per-major package
directories are relative symlinks.  The canonical copy is the former staging/18
variant (set_version basename param, debian/source/lintian-overrides) plus the
debian/source/options file the 14-17 copies carried."
```

---

### Task 4: Document the `_shared/` convention

**Goal:** The tree README, the tool reference and the architecture reference describe `_shared/` and the symlink convention, including the change-detection behaviour and the macro-definition constraint.

**Files:**
- Modify: `root/README.md:126-147` (staging section table and layout block)
- Modify: `docs/PERCONA_OBS_TOOL.md:253-267` ("How unchanged packages are detected")
- Modify: `docs/PACKAGING_HOWTO.md` (new section before "## Quick Reference: File Checklist", line 534)
- Modify: `.github/copilot-instructions.md:311` (change-detection bullet)

**Acceptance Criteria:**
- [ ] `root/README.md` staging table has a `_shared/` row and the layout block shows a symlinked package example.
- [ ] Each doc states: `_shared/` is skipped by discovery; symlinks are relative; macros render from the symlink location; referenced macros must be defined for every linking major; git checks include the target.
- [ ] `grep -n '_shared' root/README.md docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md .github/copilot-instructions.md` returns at least one hit per file.

**Verify:** the grep above → 4 files matched.

**Steps:**

- [ ] **Step 1: root/README.md**

Add to the staging table (after the `tarballs/` row):

```markdown
| `../_shared/<package>/` | Packaging shared by several majors; per-major entries are relative symlinks into it (see below) |
```

Below the `<package>/` tree block add:

```markdown
A package whose packaging is byte-identical across majors (only `%!{PG_MAJOR_VERSION}` differs) is
stored once in `staging/_shared/<package>/` and referenced from each major by a relative git symlink:

```
staging/
├── _shared/
│   └── percona-pg_stat_monitor/      # the only copy: obs/, debian/, rpm/
├── 17/
│   └── percona-pg_stat_monitor -> ../_shared/percona-pg_stat_monitor
└── 18/
    └── percona-pg_stat_monitor -> ../_shared/percona-pg_stat_monitor
```

`_shared/` is never an OBS project or package: `percona-obs` skips it during discovery. Each symlink is
synced as a normal package of the subproject that holds it, and `%!{VAR}` macros are resolved from the
symlink's own directory chain (`staging/17/macros.yaml` for the `17/` entry), so every major still gets
a fully rendered, independent package in OBS. Any macro the shared files reference must therefore be
defined at or above every linking major. Edits under `_shared/` count as changes for every linking
package (change detection follows the link target).
```

- [ ] **Step 2: docs/PERCONA_OBS_TOOL.md**

At the end of "How unchanged packages are detected" add a paragraph:

```markdown
Packages stored under a tier's `_shared/` directory and referenced by symlink (see
`root/README.md`) are checked against both the symlink and its target path, so an edit
to the shared copy invalidates every linking package's fast path.
```

- [ ] **Step 3: docs/PACKAGING_HOWTO.md**

Insert before "## Quick Reference: File Checklist":

```markdown
## Sharing One Package Source Across PG Majors

If the packaging for a package is identical in every `staging/<V>/` except for the PG major
(which enters only via `%!{PG_MAJOR_VERSION}`), keep a single copy:

```sh
git mv root/ppg/staging/18/<pkg> root/ppg/staging/_shared/<pkg>
for v in 14 15 16 17 18; do
  git rm -r -q root/ppg/staging/$v/<pkg> 2>/dev/null || true
  ln -s ../_shared/<pkg> root/ppg/staging/$v/<pkg>
  git add root/ppg/staging/$v/<pkg>
done
```

Rules:

- The symlink target must be relative (`../_shared/<pkg>`).
- Every `%!{VAR}` the shared files use must be defined at or above each linking major
  (`staging/macros.yaml` or every `staging/<V>/macros.yaml`).
- `_shared/` itself is never synced; only the symlinks are, each rendered with its own
  major's macros.
- Do not use this for packages whose `_service` revision or packaging differs per major.
```

- [ ] **Step 4: .github/copilot-instructions.md**

Extend the change-detection bullet at line ~311 with: "For symlinked package directories (`_shared/` sources) the git checks cover the link and its target."

- [ ] **Step 5: Commit**

```bash
git add root/README.md docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md .github/copilot-instructions.md
git commit -s -m "docs: describe _shared/ package sources and symlinked per-major entries"
```

---

## Self-review

- **Spec coverage:** design §1 (Task 1), §2 (Task 3), §3 (Task 2), §4 (Task 4 docs). Out-of-scope items untouched.
- **Placeholders:** none; every code step carries the code.
- **Type consistency:** `SHARED_SOURCE_DIRNAME`, `is_shared_source_dir`, `_package_pathspecs` are named identically in tasks 1, 2 and 4.
- **Risk noted for the user:** the canonical copy choice (staging/18 variant + `options`) is an assumption, called out in the Task 3 commit message.
