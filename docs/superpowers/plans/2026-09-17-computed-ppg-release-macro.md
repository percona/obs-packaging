# Computed PPG_RELEASE Macro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PPG_RELEASE` a tool-computed macro derived from `release.yaml`, so the container image release counter can never drift and resets to 1 by itself when the PG minor version is bumped.

**Architecture:** `PPG_RELEASE` stops being a hand-maintained line in `macros.yaml` and becomes a value injected into the resolved macro dict by `load_macros`. It is computed as one plus the number of tags in `root/<product>/releases/<major>/release.yaml` that belong to the project's current `PG_VERSION`. Because the computation is a pure function of `PG_VERSION` and the `release.yaml` text, the package content check can evaluate the same value at a historical commit and keep comparing like-for-like. Merging a release PR therefore changes the rendered container tags, so the main-branch sync learns to skip pushes whose `root/` changes are entirely under `root/*/releases/`, which keeps the retag from racing the release copy.

**Tech Stack:** Python 3, PyYAML, pytest, black, pyright, GitHub Actions, OBS via osc.

**Spec:** inline, see Background below. No separate design doc exists; this plan is the record of the design discussion held on 2026-09-17.

## Background

`PPG_RELEASE` is the counter part of the Percona product release id, for example the `1` in `18.6-1`. It is referenced by 64 lines across 16 Dockerfiles, where it forms the image tag, the `BuildVersion`, the `version` and `release` labels and the `PPG_VERSION` environment variable. It is additionally referenced by 8 lines in the PG 14 and PG 15 server specs.

Four problems were found on 2026-09-17:

1. `project release` still contains code to bump the macro, but it reads only `source_path / "macros.yaml"`, and commit 146694c8 moved the declaration up into the shared `root/ppg/staging/macros.yaml`. The regex never matches, so the bump silently no-ops. The docs already describe it as dormant.
2. The value it would have written is the counter of the release being cut, not the next one. Since images are built before the cut, that is one release behind.
3. The declaration is shared across majors 14 to 19, so one major's bump would retag every other major's images.
4. There is no mechanism that resets the counter to 1 when `PG_MINOR_VERSION` is bumped, and no check that would catch a forgotten reset.

Deriving the value solves all four at once: a `PG_VERSION` that has never been released has zero matching tags, so the counter is 1 with no human action.

Of the 8 spec references, only the telemetry call-home line has a real effect. The `Release:` field is overridden by OBS, which the root project config states explicitly at `root/project.yaml:189-190` and which is confirmed by the built `percona-postgresql14-14.24-2.6` RPM carrying release `2.6` while the macro is `1`. The `%changelog` header is cosmetic.

## Global Constraints

- **The only intended rendering change is `PPG_RELEASE` moving from `1` to `2` for `staging/17` and `staging/18`.** Every other package must render byte-identically. All staging majors and both cross-major container projects currently render `PPG_RELEASE` as `1`. PG 14, 15, 16 and 19 have no release project, so they compute to `1`. PG 17 has one `17.11-*` tag and PG 18 has one `18.6-*` tag, so both compute to `2`. Tasks 1 to 5 must therefore be verified against that expectation, and Task 3 explicitly records the 17 and 18 change as intended.
- `_macros_changed_since` compares a package's referenced macro values at the last synced commit against the current ones. Any macro present on one side and absent on the other makes every package carrying it compare unequal on every sync forever. The computed macro must be injected on **both** sides.
- The computation must never raise on malformed or missing input. A missing `release.yaml` and an unparsable one both mean "never released", which is `1`.
- An explicit `PPG_RELEASE` in a `macros.yaml` must keep winning over the computed value, so a project can still pin its own counter.
- `black percona_obs/ tests/` and `pyright` must both be clean at the end of every task, per CLAUDE.md.
- Commits use `git commit -s`. No `Co-Authored-By: Claude` trailer and no Claude attribution anywhere, per the user's standing rule.

**User decisions (already made):**
- "What about computing the PPG_RELEASE macro value during the `sync push` command? … We remove the PPG_RELEASE declaration from the macros.yaml files since it's automatically available at runtime." Injection point corrected to `load_macros` during planning, because fifteen call sites load macros and only some go through sync push.
- "We can remove the PPG_RELEASE from the spec files, since they don't add any value." Scoped during planning to the `Release:` field and the `%changelog` header. The call-home line keeps the macro because it is the only honest source for the telemetry version string.
- "write the plan including the main sync skip" — the release-only skip in `sync-main.yml` is in scope.
- The release-only detection in `obs-pr-cleanup.yml` is explicitly **out** of scope: "Don't do anything for now". It needs no change anyway, because the computed macro removes the bump commit that would have broken it.

## File Structure

| File | Responsibility |
|---|---|
| `percona_obs/common.py` | New: `compute_ppg_release`, `inject_computed_macros`, `_read_worktree_file`. Modified: `load_macros` injects computed macros. |
| `percona_obs/git_utils.py` | Modified: `_macros_changed_since` injects the computed macro into the historical side too. |
| `percona_obs/cmd_project.py` | Modified: the dead `PPG_RELEASE` bump is deleted from `cmd_project_release`. |
| `root/ppg/staging/macros.yaml` | Modified: `PPG_RELEASE` declaration removed. |
| `root/ppg/devel/{14..19}/macros.yaml` | Modified: unused `PPG_RELEASE` declarations removed. |
| `root/ppg/staging/containers/macros.yaml`, `root/ppg/staging/extras/containers/macros.yaml` | Modified: the "inherited from" comment is replaced by a note that the value is computed. |
| `root/ppg/staging/{14,15}/percona-postgresql/rpm/percona-postgresql.spec` | Modified: macro dropped from `Release:` and `%changelog`, kept in call-home. |
| `.github/workflows/sync-main.yml` | Modified: release-only pushes skip the sync and the poll. |
| `docs/PERCONA_OBS_TOOL.md` | Modified: replaces the "dormant" paragraph with the computed-macro contract. |
| `root/README.md` | Modified: documents `PPG_RELEASE` as computed in the macros section. |
| `tests/test_computed_macros.py` | New: unit tests for the computation, the injection and the content-check symmetry. |
| `tests/test_macro_resolution.py` | New: tree-wide test that every package referencing `PPG_RELEASE` resolves it. |

---

### Task 1: Compute PPG_RELEASE in the macro loader

**Goal:** `load_macros` returns a `PPG_RELEASE` entry derived from `release.yaml` for any project whose macro chain defines `PG_VERSION`.

**Files:**
- Modify: `percona_obs/common.py` (add near `resolve_macros`/`load_macros`, around lines 262-310)
- Test: `tests/test_computed_macros.py`

**Acceptance Criteria:**
- [ ] `compute_ppg_release` returns `"1"` for `None`, empty, unparsable, or non-matching release data
- [ ] `compute_ppg_release` returns one plus the count of tags matching `<product>/<pg_version>-`
- [ ] `inject_computed_macros` leaves the dict untouched when `PG_VERSION` is absent
- [ ] `inject_computed_macros` leaves an explicitly declared `PPG_RELEASE` untouched
- [ ] `load_macros` on a tree with a `release.yaml` yields the computed value
- [ ] `black` clean, `pyright` reports 0 errors

**Verify:** `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_computed_macros.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_computed_macros.py`:

```python
"""Unit tests for tool-computed macros (percona_obs.common)."""

from pathlib import Path

import pytest

import percona_obs.common as common
from percona_obs.common import compute_ppg_release, inject_computed_macros


RELEASE_YAML = """\
project: ppg:staging:18
releases:
- ppg/18.3-1
- ppg/18.3-2
- ppg/18.4-1
repository: ${PERCONA_OBS_PACKAGING_REPO}
"""


def test_compute_counts_only_matching_pg_version():
    assert compute_ppg_release("ppg", "18.3", RELEASE_YAML) == "3"
    assert compute_ppg_release("ppg", "18.4", RELEASE_YAML) == "2"


def test_compute_resets_to_one_for_unreleased_version():
    # This is the forgot-to-reset case: bumping PG_MINOR_VERSION to 18.5 makes
    # the counter 1 with no human action.
    assert compute_ppg_release("ppg", "18.5", RELEASE_YAML) == "1"


def test_compute_tolerates_missing_and_broken_input():
    assert compute_ppg_release("ppg", "18.4", None) == "1"
    assert compute_ppg_release("ppg", "18.4", "") == "1"
    assert compute_ppg_release("ppg", "18.4", "{{{ not yaml") == "1"
    assert compute_ppg_release("ppg", "18.4", "project: x\n") == "1"


def test_compute_honours_legacy_revision_field():
    assert compute_ppg_release("ppg", "18.4", "revision: ppg/18.4-1\n") == "2"


def test_compute_does_not_match_other_products_or_prefixes():
    data = "releases:\n- psmdb/18.4-1\n- ppg/118.4-1\n"
    assert compute_ppg_release("ppg", "18.4", data) == "1"


def _tree(tmp_path: Path) -> Path:
    """staging/18 project plus a releases/18/release.yaml."""
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "18"
    proj.mkdir(parents=True)
    (root / "ppg" / "staging" / "macros.yaml").write_text("- PG_MAJOR_VERSION: 0\n")
    (proj / "macros.yaml").write_text(
        "- PG_MAJOR_VERSION: 18\n- PG_MINOR_VERSION: 4\n"
        "- PG_VERSION: %!{PG_MAJOR_VERSION}.%!{PG_MINOR_VERSION}\n"
    )
    rel = root / "ppg" / "releases" / "18"
    rel.mkdir(parents=True)
    (rel / "release.yaml").write_text(RELEASE_YAML)
    return root


def test_load_macros_injects_computed_value(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    macros = common.load_macros(root / "ppg" / "staging" / "18")
    assert macros["PG_VERSION"] == "18.4"
    assert macros["PPG_RELEASE"] == "2"


def test_load_macros_resets_on_minor_bump(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    proj = root / "ppg" / "staging" / "18"
    (proj / "macros.yaml").write_text(
        "- PG_MAJOR_VERSION: 18\n- PG_MINOR_VERSION: 5\n"
        "- PG_VERSION: %!{PG_MAJOR_VERSION}.%!{PG_MINOR_VERSION}\n"
    )
    assert common.load_macros(proj)["PPG_RELEASE"] == "1"


def test_load_macros_without_pg_version_has_no_counter(tmp_path, monkeypatch):
    root = tmp_path / "root"
    proj = root / "ppg" / "common" / "deps"
    proj.mkdir(parents=True)
    (proj / "macros.yaml").write_text("- GEOS_VERSION: 3.13.1\n")
    monkeypatch.setattr(common, "REPO_ROOT", root)
    assert "PPG_RELEASE" not in common.load_macros(proj)


def test_explicit_declaration_wins(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    proj = root / "ppg" / "staging" / "18"
    (proj / "macros.yaml").write_text(
        (proj / "macros.yaml").read_text() + "- PPG_RELEASE: 9\n"
    )
    assert common.load_macros(proj)["PPG_RELEASE"] == "9"


def test_inject_is_pure_in_its_reader():
    macros = {"PG_VERSION": "18.4"}
    out = inject_computed_macros(
        macros,
        Path("/repo/root/ppg/staging/18"),
        lambda p: RELEASE_YAML,
        repo_root=Path("/repo/root"),
    )
    assert out["PPG_RELEASE"] == "2"
    assert "PPG_RELEASE" not in macros  # input dict not mutated
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_computed_macros.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_ppg_release'`

- [ ] **Step 3: Implement in `percona_obs/common.py`**

Add immediately after `resolve_macros` and before `load_macros`:

```python
# Macros computed by the tool instead of being declared in a macros.yaml.
#
# Unlike the FILE_MODIFY_DATE built-ins, these ARE placed in the resolved macro
# dict, so every existing consumer — substitution, the package content check,
# the changelog builder — treats them like any declared macro.  That is what
# keeps git_utils._macros_changed_since honest: it recomputes the same value at
# the historical commit instead of seeing the name appear out of nowhere.
_COMPUTED_MACROS = frozenset({"PPG_RELEASE"})


def compute_ppg_release(
    product: str, pg_version: str, release_yaml_text: "str | None"
) -> str:
    """Return the counter of the NEXT release of *pg_version*, as a string.

    The counter is one plus the number of tags in *release_yaml_text* that
    belong to *pg_version*, i.e. tags shaped ``<product>/<pg_version>-<n>``.

    A missing, empty, unparsable or tag-less release.yaml all mean "this PG
    version has never been released", which is 1.  That is what makes the
    counter reset by itself when PG_MINOR_VERSION is bumped: the new
    PG_VERSION matches no existing tag.
    """
    if not release_yaml_text:
        return "1"
    try:
        data = yaml.safe_load(release_yaml_text) or {}
    except yaml.YAMLError:
        return "1"
    if not isinstance(data, dict):
        return "1"
    raw = data.get("releases")
    tags = [str(t) for t in raw] if isinstance(raw, list) else []
    if not tags and data.get("revision"):
        tags = [str(data["revision"])]
    prefix = f"{product}/{pg_version}-"
    return str(sum(1 for t in tags if t.startswith(prefix)) + 1)


def _read_worktree_file(path: Path) -> "str | None":
    """Read *path* from the working tree, or None when it does not exist."""
    try:
        return path.read_text("utf-8")
    except OSError:
        return None


def inject_computed_macros(
    macros: dict[str, str],
    project_path: Path,
    read_file: "Callable[[Path], str | None]",
    repo_root: "Path | None" = None,
) -> dict[str, str]:
    """Return *macros* plus the tool-computed entries, without mutating it.

    Currently only ``PPG_RELEASE``.  *read_file* returns a repo file's contents
    or None; callers pass a working-tree reader or a git-revision reader so the
    identical value can be computed at any commit — see
    ``git_utils._macros_changed_since``.  *repo_root* defaults to the module
    global and exists so tests can point at a fixture tree.

    Nothing is injected when the chain defines no ``PG_VERSION`` (e.g. under
    ``root/ppg/common/deps``): those packages never reference the counter, and
    one that did would still fail with the usual undefined-macro error.  An
    explicitly declared ``PPG_RELEASE`` always wins, so a project can pin its
    own counter.
    """
    root = REPO_ROOT if repo_root is None else repo_root
    pg_version = macros.get("PG_VERSION")
    if not pg_version or "PPG_RELEASE" in macros:
        return macros
    try:
        parts = project_path.relative_to(root).parts
    except ValueError:
        return macros
    if not parts:
        return macros
    product = parts[0]
    major = pg_version.split(".", 1)[0].strip()
    if not major:
        return macros
    release_file = root / product / "releases" / major / "release.yaml"
    return {
        **macros,
        "PPG_RELEASE": compute_ppg_release(
            product, pg_version, read_file(release_file)
        ),
    }
```

Change `load_macros` to inject:

```python
def load_macros(project_path: Path) -> dict[str, str]:
    """Load and resolve macros from macros.yaml files in the directory hierarchy.

    Walks from REPO_ROOT down to *project_path*, collecting the macros.yaml
    files that exist in the working tree, resolves them with ``resolve_macros``,
    then adds the tool-computed macros (see ``inject_computed_macros``).
    """
    resolved = resolve_macros(
        [
            (f, f.read_text("utf-8"))
            for f in _macros_chain_files(project_path)
            if f.exists()
        ]
    )
    return inject_computed_macros(resolved, project_path, _read_worktree_file)
```

Add `Callable` to the typing import at the top of the file if it is not already imported:

```python
from typing import Callable
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_computed_macros.py -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Format, type-check and run the whole suite**

```bash
venv/bin/black percona_obs/ tests/
PYTHONPATH=$PWD venv/bin/pyright
PYTHONPATH=$PWD venv/bin/python -m pytest tests/ -q
```

Expected: black reports files unchanged or reformatted, pyright `0 errors`, full suite passes.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/common.py tests/test_computed_macros.py
git commit -s -m "macros: compute PPG_RELEASE from the release tree

PPG_RELEASE is the counter of the next release of a project's PG_VERSION.
Deriving it from root/<product>/releases/<major>/release.yaml makes it
reset to 1 by itself when PG_MINOR_VERSION is bumped, instead of relying
on someone remembering.  The computation is a pure function of PG_VERSION
and the release.yaml text so it can also be evaluated at a past commit.

An explicit declaration still wins, and a chain without PG_VERSION gets
nothing injected."
```

---

### Task 2: Keep the content check symmetric

**Goal:** `_macros_changed_since` computes `PPG_RELEASE` on the historical side too, so container packages are reported as changed only when the counter genuinely changed.

**Files:**
- Modify: `percona_obs/git_utils.py:300-318`
- Test: `tests/test_computed_macros.py`

**Acceptance Criteria:**
- [ ] With identical release state at both revisions, a package referencing `PPG_RELEASE` is not reported as changed
- [ ] With a new release tag added since the synced commit, it is reported as changed
- [ ] The historical side reads `release.yaml` through `_git_show_at`, not from the working tree
- [ ] `black` clean, `pyright` reports 0 errors

**Verify:** `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_computed_macros.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_computed_macros.py`:

```python
import percona_obs.git_utils as git_utils


def _macros_check_fixture(monkeypatch, tmp_path, then_release: str, now_release: str):
    """Wire _macros_changed_since onto a fixture tree with fake git reads."""
    root = _tree(tmp_path)
    (root / "ppg" / "releases" / "18" / "release.yaml").write_text(now_release)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(git_utils, "_REPO_DIR", root.parent)
    monkeypatch.setattr(git_utils, "_commit_exists", lambda sha: True)
    monkeypatch.setattr(
        git_utils, "_referenced_macros", lambda p: {"PG_VERSION", "PPG_RELEASE"}
    )

    def _show(sha: str, rel_path: str) -> "str | None":
        if rel_path.endswith("releases/18/release.yaml"):
            return then_release
        blob = root.parent / rel_path
        return blob.read_text("utf-8") if blob.exists() else None

    monkeypatch.setattr(git_utils, "_git_show_at", _show)
    return root / "ppg" / "staging" / "18"


def test_macros_unchanged_when_release_state_identical(monkeypatch, tmp_path):
    pkg = _macros_check_fixture(monkeypatch, tmp_path, RELEASE_YAML, RELEASE_YAML)
    assert git_utils._macros_changed_since("abc1234", pkg) is False


def test_macros_changed_when_release_added(monkeypatch, tmp_path):
    after = RELEASE_YAML + "- ppg/18.4-2\n"
    pkg = _macros_check_fixture(monkeypatch, tmp_path, RELEASE_YAML, after)
    assert git_utils._macros_changed_since("abc1234", pkg) is True
```

- [ ] **Step 2: Run the tests to verify the first one fails**

Run: `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_computed_macros.py -k macros_unchanged -v`
Expected: FAIL — the historical side has no `PPG_RELEASE`, so it compares unequal and returns True.

- [ ] **Step 3: Implement in `percona_obs/git_utils.py`**

In `_macros_changed_since`, extend the local import and inject on the historical side. Replace:

```python
    from .common import _macros_chain_files, load_macros, resolve_macros
```

with:

```python
    from .common import (
        _macros_chain_files,
        inject_computed_macros,
        load_macros,
        resolve_macros,
    )
```

and replace:

```python
    try:
        then = resolve_macros(sources)
        now = load_macros(package_path)
    except SystemExit:
        return True
```

with:

```python
    try:
        # Tool-computed macros (PPG_RELEASE) are not in any macros.yaml, so the
        # historical side has to recompute them from the same inputs at the same
        # commit.  Without this the name is present on one side only and every
        # package referencing it compares unequal on every single sync.
        then = inject_computed_macros(
            resolve_macros(sources),
            package_path,
            lambda p: _git_show_at(
                short_sha, p.relative_to(_REPO_DIR).as_posix()
            ),
        )
        now = load_macros(package_path)
    except SystemExit:
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_computed_macros.py -v`
Expected: PASS, 12 tests

- [ ] **Step 5: Format, type-check and run the whole suite**

```bash
venv/bin/black percona_obs/ tests/
PYTHONPATH=$PWD venv/bin/pyright
PYTHONPATH=$PWD venv/bin/python -m pytest tests/ -q
```

Expected: pyright `0 errors`, full suite passes.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/git_utils.py tests/test_computed_macros.py
git commit -s -m "git_utils: recompute PPG_RELEASE at the historical commit

_macros_changed_since builds the 'then' side purely from macros.yaml blobs
at the last synced commit.  A computed macro is absent there and present in
the current side, which would mark every container package changed on every
sync.  Inject the computed macros into the historical side too, reading
release.yaml at that same commit."
```

---

### Task 3: Remove the PPG_RELEASE declarations

**Goal:** The macro exists nowhere in the tree as a declaration, and every package that references it still resolves it.

**Files:**
- Modify: `root/ppg/staging/macros.yaml:27` (delete the line)
- Modify: `root/ppg/devel/14/macros.yaml`, `.../15/`, `.../16/`, `.../17/`, `.../18/`, `.../19/macros.yaml` (delete line 6 in each)
- Modify: `root/ppg/staging/containers/macros.yaml:7-8`, `root/ppg/staging/extras/containers/macros.yaml:8-9` (replace the comment)
- Test: `tests/test_macro_resolution.py`

**Acceptance Criteria:**
- [ ] `grep -rn "PPG_RELEASE" root/ --include=macros.yaml` returns only comment lines
- [ ] Every package directory referencing `%!{PPG_RELEASE}` resolves the macro through `load_macros`
- [ ] Staging majors 14, 15, 16 and 19 and both cross-major container projects resolve to `1`
- [ ] Staging majors 17 and 18 resolve to `2`, which is the intended change: both have shipped a `-1` release, so the next one is `-2`
- [ ] `black` clean, `pyright` reports 0 errors

**Verify:** `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_macro_resolution.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_macro_resolution.py`:

```python
"""Tree-wide checks that every referenced macro resolves.

These run against the real root/ tree, so they catch a declaration removed
without a replacement — the failure mode that would otherwise only show up as
an aborted sync.
"""

from pathlib import Path

import pytest

from percona_obs.common import REPO_ROOT, load_macros
from percona_obs.git_utils import _referenced_macros


def _dirs_referencing_ppg_release() -> "list[Path]":
    hits: set[Path] = set()
    for f in REPO_ROOT.rglob("*"):
        if not f.is_file() or f.name == "macros.yaml":
            continue
        try:
            text = f.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "%!{PPG_RELEASE}" in text:
            # obs/Dockerfile and rpm/*.spec live one level below the package dir
            hits.add(f.parent.parent)
    return sorted(hits)


def test_tree_has_no_ppg_release_declaration():
    declared = []
    for f in REPO_ROOT.rglob("macros.yaml"):
        for line in f.read_text("utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            if line.strip().startswith("- PPG_RELEASE:"):
                declared.append(str(f.relative_to(REPO_ROOT)))
    assert declared == [], f"PPG_RELEASE is now computed, remove: {declared}"


@pytest.mark.parametrize("pkg_dir", _dirs_referencing_ppg_release(), ids=str)
def test_every_referencing_package_resolves_the_macro(pkg_dir):
    macros = load_macros(pkg_dir)
    assert "PPG_RELEASE" in macros
    assert macros["PPG_RELEASE"].isdigit()


def test_referenced_macros_all_resolve():
    for pkg_dir in _dirs_referencing_ppg_release():
        macros = load_macros(pkg_dir)
        missing = _referenced_macros(pkg_dir) - set(macros)
        assert missing == set(), f"{pkg_dir}: unresolved {sorted(missing)}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_macro_resolution.py::test_tree_has_no_ppg_release_declaration -v`
Expected: FAIL listing `ppg/staging/macros.yaml` and the six `ppg/devel/*/macros.yaml`

- [ ] **Step 3: Delete the declarations**

```bash
sed -i '/^- PPG_RELEASE: /d' root/ppg/staging/macros.yaml
for v in 14 15 16 17 18 19; do
  sed -i '/^- PPG_RELEASE: /d' "root/ppg/devel/$v/macros.yaml"
done
grep -rn "PPG_RELEASE" root/ --include=macros.yaml
```

Expected from the final grep: only the two comment lines in the cross-major container projects, which the next step rewrites.

- [ ] **Step 4: Rewrite the two stale comments**

In `root/ppg/staging/containers/macros.yaml`, replace:

```
# PPG_RELEASE is inherited from root/ppg/staging/macros.yaml; override it here only if
# this project needs its own independent release counter.
```

with:

```
# PPG_RELEASE is computed by percona-obs, not declared: it is one plus the number
# of PG_VERSION releases already listed in root/ppg/releases/<major>/release.yaml,
# so it resets to 1 on its own when PG_MINOR_VERSION is bumped.  Declare it here
# only if this project needs its own pinned counter.
```

Apply the identical replacement in `root/ppg/staging/extras/containers/macros.yaml`.

- [ ] **Step 5: Run the tests to verify they pass, and record the rendered values**

```bash
PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_macro_resolution.py -v
PYTHONPATH=$PWD venv/bin/python - <<'EOF'
from percona_obs.common import REPO_ROOT, load_macros
for p in ["ppg/staging/14", "ppg/staging/15", "ppg/staging/16", "ppg/staging/17",
          "ppg/staging/18", "ppg/staging/19", "ppg/staging/containers",
          "ppg/staging/extras/containers"]:
    m = load_macros(REPO_ROOT / p)
    print(f"{p:34} PG_VERSION={m.get('PG_VERSION','-'):7} PPG_RELEASE={m.get('PPG_RELEASE','-')}")
EOF
```

Expected: all tests pass; 14, 15, 16, 19 and both cross-major projects print `PPG_RELEASE=1`; 17 and 18 print `PPG_RELEASE=2`.

If 17 or 18 prints anything other than `2`, stop and re-read `root/ppg/releases/{17,18}/release.yaml` before continuing — the counter must match one plus the number of tags for the current `PG_VERSION`.

- [ ] **Step 6: Commit**

```bash
git add root/ppg/staging/macros.yaml root/ppg/devel/*/macros.yaml \
        root/ppg/staging/containers/macros.yaml \
        root/ppg/staging/extras/containers/macros.yaml \
        tests/test_macro_resolution.py
git commit -s -m "macros: drop the PPG_RELEASE declarations

The value is computed from the release tree now, so the shared staging
declaration goes away along with the six devel ones, which were never
referenced by anything.  The two cross-major container projects keep a
comment explaining where the value comes from.

staging/17 and staging/18 move from 1 to 2 as a result: both have shipped
a -1 release, so the next one is -2 and their images retag accordingly.
Every other project stays at 1."
```

---

### Task 4: Delete the dead bump from project release

**Goal:** `cmd_project_release` no longer contains the no-op `PPG_RELEASE` rewrite, so the release commit is release-only by construction.

**Files:**
- Modify: `percona_obs/cmd_project.py:2091-2099` (the `release_counter` and detection block), `:2109` (the preview line), `:2137-2149` (the write block)
- Test: `tests/test_project_release.py`

**Acceptance Criteria:**
- [ ] No reference to `PPG_RELEASE` or `release_counter` remains anywhere in `percona_obs/`
- [ ] `project release --help` still works and the existing release tests pass
- [ ] `black` clean, `pyright` reports 0 errors

**Verify:** `! grep -rn "PPG_RELEASE\|release_counter" percona_obs/ && PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_project_release.py -q` → grep finds nothing, tests pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_release.py`:

```python
def test_release_no_longer_touches_macros():
    """The PPG_RELEASE bump is gone: the value is computed from release.yaml.

    A release commit that also rewrote a staging macros.yaml would stop being
    release-only, which is what obs-pr-cleanup keys its tag-and-dispatch on.
    """
    source = Path(cmd_project.__file__).read_text("utf-8")
    assert "PPG_RELEASE" not in source
    assert "release_counter" not in source
```

`Path` is already imported at the top of that test module.

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_project_release.py::test_release_no_longer_touches_macros -v`
Expected: FAIL on the first assert

- [ ] **Step 3: Delete the three blocks in `percona_obs/cmd_project.py`**

Delete this block, which sits just after the `commit_msg` assignment:

```python
    release_counter = release_id.rsplit("-", 1)[-1]

    macros_file = source_path / "macros.yaml"
    _macros_text = ""
    _ppg_release_in_macros = False
    if macros_file.is_file():
        _macros_text = macros_file.read_text("utf-8")
        _ppg_release_in_macros = bool(
            re.search(r"^- PPG_RELEASE:\s*\S+", _macros_text, re.MULTILINE)
        )
```

Delete this preview line from the confirmation block:

```python
    if _ppg_release_in_macros:
        print(f"  macros.yaml: PPG_RELEASE → {release_counter}")
```

Delete this write block, which sits just after `committed_paths: list[str] = []`:

```python
    if _ppg_release_in_macros:
        new_text, _ = re.subn(
            r"^(- PPG_RELEASE:)\s*\S+",
            rf"\g<1> {release_counter}",
            _macros_text,
            count=1,
            flags=re.MULTILINE,
        )
        macros_file.write_text(new_text, "utf-8")
        _print_create(str(macros_file.relative_to(_REPO_DIR)))
        committed_paths.append(str(macros_file.relative_to(_REPO_DIR)))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH=$PWD venv/bin/python -m pytest tests/test_project_release.py -q
PYTHONPATH=$PWD venv/bin/pyright
```

Expected: tests pass; pyright `0 errors`. If pyright reports `re` as unused, leave it — `re` is used elsewhere in the module; only remove the import if pyright actually flags it.

- [ ] **Step 5: Commit**

```bash
venv/bin/black percona_obs/ tests/
git add percona_obs/cmd_project.py tests/test_project_release.py
git commit -s -m "project release: drop the dead PPG_RELEASE bump

The rewrite only ever looked at the per-major macros.yaml, so it silently
no-opped from the moment the declaration moved into the shared staging file,
and the value it wrote was the counter just cut rather than the next one.
The counter is computed from release.yaml now, so the whole block goes.

This also keeps the release commit release-only, which is what
obs-pr-cleanup keys its tag-and-dispatch on."
```

---

### Task 5: Drop the dead spec references

**Goal:** The PG 14 and PG 15 server specs stop referencing the macro where it has no effect, and keep it where it does.

**Files:**
- Modify: `root/ppg/staging/14/percona-postgresql/rpm/percona-postgresql.spec:101`, `:103`, `:1593`
- Modify: `root/ppg/staging/15/percona-postgresql/rpm/percona-postgresql.spec:101`, `:103`, `:1621`

**Acceptance Criteria:**
- [ ] `Release:` and the `%changelog` header carry literals, matching how the PG 16, 17 and 18 specs already write them
- [ ] The call-home line still uses `%!{PG_VERSION}-%!{PPG_RELEASE}`
- [ ] The rendered spec is byte-identical to the rendering before the change, so no rebuild is triggered
- [ ] Exactly two `PPG_RELEASE` references remain in `root/`, both call-home lines

**Verify:** the render-diff command in Step 3 prints `identical` for both specs

**Steps:**

- [ ] **Step 1: Capture the current rendering**

```bash
mkdir -p /tmp/spec-before
PYTHONPATH=$PWD venv/bin/python - <<'EOF'
from pathlib import Path
from percona_obs.common import REPO_ROOT, apply_macro_substitution, load_macros
for v in ("14", "15"):
    p = REPO_ROOT / f"ppg/staging/{v}/percona-postgresql/rpm/percona-postgresql.spec"
    out = apply_macro_substitution(p.read_text("utf-8"), load_macros(p.parent.parent), source=p)
    Path(f"/tmp/spec-before/{v}.spec").write_text(out)
EOF
```

- [ ] **Step 2: Edit both specs**

In each of the two spec files apply exactly these three replacements. `PPG_RELEASE` renders as `1` for both majors today, so each replacement is textually equivalent.

Replace `Release:        4200%!{PPG_RELEASE}%{?dist}` with `Release:        42001%{?dist}`

Replace `Release:        %!{PPG_RELEASE}%{?dist}` with `Release:        1%{?dist}`

Replace `* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_VERSION}-%!{PPG_RELEASE}` with `* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_VERSION}-1`

Leave the call-home line untouched:

```
bash /tmp/call-home.sh -f "PRODUCT_FAMILY_POSTGRESQL" -v "%!{PG_VERSION}-%!{PPG_RELEASE}" -d "PACKAGE" &>/dev/null || :
```

- [ ] **Step 3: Verify the rendering is unchanged**

```bash
PYTHONPATH=$PWD venv/bin/python - <<'EOF'
from pathlib import Path
from percona_obs.common import REPO_ROOT, apply_macro_substitution, load_macros
for v in ("14", "15"):
    p = REPO_ROOT / f"ppg/staging/{v}/percona-postgresql/rpm/percona-postgresql.spec"
    out = apply_macro_substitution(p.read_text("utf-8"), load_macros(p.parent.parent), source=p)
    before = Path(f"/tmp/spec-before/{v}.spec").read_text()
    print(v, "identical" if out == before else "CHANGED")
EOF
grep -rn "PPG_RELEASE" root/ | grep -v macros.yaml
```

Expected: both print `identical`; the grep prints exactly two call-home lines plus the Dockerfile references.

- [ ] **Step 4: Commit**

```bash
git add root/ppg/staging/14/percona-postgresql/rpm/percona-postgresql.spec \
        root/ppg/staging/15/percona-postgresql/rpm/percona-postgresql.spec
git commit -s -m "staging:14,15: de-macroize the dead PPG_RELEASE spec uses

OBS overrides the RPM Release field on every RPM repository — the root
project config says so and the built 14.24-2.6 RPM proves it — so the
macro in Release: never reached a binary.  The %changelog header is
cosmetic and the 16/17/18 specs already hardcode it.  Both now carry the
literal that the macro rendered to, so the output is byte-identical.

The call-home line keeps the macro: the telemetry version string is the
one place in these specs where the counter is actually observable."
```

---

### Task 6: Skip release-only pushes in the main sync

**Goal:** A push to main whose `root/` changes are entirely under `root/*/releases/` does not re-sync or poll, so merging a release PR cannot retag staging images while `obs-release.yml` is copying them.

**Files:**
- Modify: `.github/workflows/sync-main.yml` (sync job: add the detect step, add job outputs, gate the sync steps; poll job: gate on the output)

**Acceptance Criteria:**
- [ ] The sync job exposes a `release_only` output
- [ ] The detect step falls back to `false` whenever the before-SHA is missing, all zeros, or not present in the clone, so an unknown range always syncs
- [ ] The sync, cache-prune and report-upload steps are skipped when `release_only` is true
- [ ] The poll job is skipped when `release_only` is true, so it never waits on a missing sync report
- [ ] `actionlint` or a YAML parse of the workflow succeeds

**Verify:** `venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/sync-main.yml')); print('yaml ok')"` → `yaml ok`

**Steps:**

- [ ] **Step 1: Add the job output to the sync job**

In `.github/workflows/sync-main.yml`, inside the `sync:` job and after the `permissions:` block, add:

```yaml
    outputs:
      release_only: ${{ steps.detect.outputs.release_only }}
```

- [ ] **Step 2: Add the detect step**

Insert immediately after the `actions/checkout@v4` step of the `sync` job, before the legacy-history fetch:

```yaml
      # A push whose root/ changes are entirely under root/*/releases/ carries no
      # packaging change, and must NOT be synced.  PPG_RELEASE is computed from
      # release.yaml, so merging a release PR changes the rendered container tags;
      # syncing here would rebuild those images with the NEXT release counter at
      # the same moment obs-release.yml is copying the current ones out of
      # staging, and the release workflow waits for staging to go quiet before it
      # copies.  The retag lands on the next packaging push instead.
      - name: Detect release-only push
        id: detect
        shell: bash
        run: |
          set -euo pipefail
          BEFORE="${{ github.event.before }}"
          SHA="${{ github.sha }}"
          # Unknown range (workflow_dispatch, first push, force push, shallow
          # clone): never skip.
          if [ -z "$BEFORE" ] \
             || [ "$BEFORE" = "0000000000000000000000000000000000000000" ] \
             || ! git cat-file -e "${BEFORE}^{commit}" 2>/dev/null; then
            echo "release_only=false" >> "$GITHUB_OUTPUT"
            echo "unknown before-SHA; syncing"
            exit 0
          fi
          CHANGED=$(git diff --name-only "$BEFORE" "$SHA" -- 'root/**')
          NON_RELEASE=$(echo "$CHANGED" | grep -v '^root/[^/]*/releases/' || true)
          if [ -n "$CHANGED" ] && [ -z "$NON_RELEASE" ]; then
            echo "release_only=true" >> "$GITHUB_OUTPUT"
            echo "release-only push; skipping sync"
          else
            echo "release_only=false" >> "$GITHUB_OUTPUT"
          fi
```

- [ ] **Step 3: Gate the sync steps**

Add `if: steps.detect.outputs.release_only != 'true'` to the `Sync to OBS` step and to the `Upload sync report` step. For the `Prune stale cache entries` step, which currently carries `if: always()`, change the condition to:

```yaml
        if: always() && steps.detect.outputs.release_only != 'true'
```

- [ ] **Step 4: Gate the poll job**

In the `poll:` job, which already has `needs: sync`, add:

```yaml
    if: needs.sync.outputs.release_only != 'true'
```

- [ ] **Step 5: Verify the workflow parses**

```bash
venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/sync-main.yml')); print('yaml ok')"
command -v actionlint >/dev/null && actionlint .github/workflows/sync-main.yml || echo "actionlint not installed, skipped"
```

Expected: `yaml ok`, and actionlint clean if it is installed.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/sync-main.yml
git commit -s -m "sync-main: skip release-only pushes

PPG_RELEASE is computed from release.yaml, so merging a release PR changes
the rendered container image tags even though no packaging file moved.
Syncing that push would rebuild the images with the next release counter
while obs-release.yml is still copying the current ones out of staging —
and the release waits for staging to go quiet first, so it would wait for
exactly those rebuilds and then copy the wrong tags.

Skip the sync and the poll when every changed root/ file is under
root/*/releases/.  The retag lands on the next packaging push.  An unknown
before-SHA never skips."
```

---

### Task 7: Document the computed macro

**Goal:** The tool reference and the packaging README describe `PPG_RELEASE` as computed, and the stale "dormant" paragraph is gone.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md:645-650`
- Modify: `root/README.md` (the macros section)

**Acceptance Criteria:**
- [ ] No text anywhere in `docs/` describes the `PPG_RELEASE` bump as dormant or as something `project release` writes
- [ ] The reference states the derivation rule, the automatic reset on a minor bump, and the release-only skip in the main sync
- [ ] `root/README.md` documents that the macro must not be declared

**Verify:** `grep -rn "dormant" docs/PERCONA_OBS_TOOL.md` → no match

**Steps:**

- [ ] **Step 1: Replace the constraint paragraph in `docs/PERCONA_OBS_TOOL.md`**

Replace:

```
> **Constraint:** the tag+dispatch automation in step 3 only fires for a PR whose
> `root/` changes are **entirely** under `root/*/releases/` (`obs-pr-cleanup.yml`'s
> release-only detection). Do not mix in unrelated `root/` edits — including the
> legacy `PPG_RELEASE` counter bump in a per-major `<staging>/<V>/macros.yaml`, which
> would break release-only detection if it were ever reintroduced there. This is
> currently dormant in practice because `PPG_RELEASE` lives in the shared
> `root/ppg/staging/macros.yaml`, which `project release` does not touch or bump.
```

with:

```
> **Constraint:** the tag+dispatch automation in step 3 only fires for a PR whose
> `root/` changes are **entirely** under `root/*/releases/` (`obs-pr-cleanup.yml`'s
> release-only detection). Do not mix unrelated `root/` edits into a release PR.

### The `PPG_RELEASE` counter

`PPG_RELEASE` is the counter part of a release id, the `1` in `18.6-1`, and it is
what the container image tags are built from. It is **computed, never declared**:
`load_macros` sets it to one plus the number of tags in
`root/<product>/releases/<major>/release.yaml` that belong to the project's current
`PG_VERSION`.

Two consequences follow, and both are deliberate:

- Bumping `PG_MINOR_VERSION` resets the counter to 1 on its own, because the new
  `PG_VERSION` matches no existing tag. There is nothing to remember and nothing to
  edit.
- Merging a release PR raises the counter for that PG version, so the staging
  container images are due to be retagged. `sync-main.yml` deliberately skips a push
  whose `root/` changes are all under `root/*/releases/`, so that retag does not race
  `obs-release.yml` copying the images it just released. The retag happens on the
  next packaging push.

A project that needs its own pinned counter can still declare `PPG_RELEASE` in its
`macros.yaml`; an explicit declaration always wins over the computed value.
```

- [ ] **Step 2: Document it in `root/README.md`**

In the section that describes `macros.yaml` files, add:

```markdown
`PPG_RELEASE` is **not** declared in any `macros.yaml`. `percona-obs` computes it as
one plus the number of releases already listed for the project's `PG_VERSION` in
`root/<product>/releases/<major>/release.yaml`, so it resets to 1 by itself whenever
`PG_MINOR_VERSION` is bumped. Declare it only to pin a project to its own counter.
```

- [ ] **Step 3: Verify**

```bash
grep -rn "dormant" docs/PERCONA_OBS_TOOL.md || echo "no stale text"
grep -rn "PPG_RELEASE" docs/ root/README.md | head
```

Expected: `no stale text`, and the remaining hits describe the computed behaviour.

- [ ] **Step 4: Commit**

```bash
git add docs/PERCONA_OBS_TOOL.md root/README.md
git commit -s -m "docs: describe PPG_RELEASE as a computed macro

Replaces the paragraph that described the counter bump as dormant with the
derivation rule, the automatic reset on a minor bump, and why sync-main
skips release-only pushes."
```

---

## Final verification

Run once every task is committed:

```bash
venv/bin/black percona_obs/ tests/
PYTHONPATH=$PWD venv/bin/pyright
PYTHONPATH=$PWD venv/bin/python -m pytest tests/ -q
grep -rn "PPG_RELEASE" root/ --include=macros.yaml | grep -v '^\s*#' || echo "no declarations"
grep -rn "PPG_RELEASE" percona_obs/ || echo "no tool-side references"
```

Expected: black clean, pyright `0 errors`, full suite green, no declarations, no tool-side references outside `common.py`'s computation.

Then, before opening the PR, confirm against production that the intended retag is the only packaging change:

```bash
PYTHONPATH=$PWD venv/bin/python -m percona_obs -P isv sync push --dry-run ppg:staging:17 2>&1 | tail -20
```

Expected: only the three `staging:17` container packages are listed as changed, coming from the counter moving to 2. Any other package appearing here means the content check lost symmetry, which is Task 2 regressing.

## Out of scope

- The release-only detection in `obs-pr-cleanup.yml`. The user deferred it, and the computed macro removes the bump commit that would have broken it, so it needs no change.
- The hardcoded `17.5-1` in the PG 17 server spec's call-home line, and the absence of a call-home line in the PG 16 and PG 18 server specs. Both are real defects found during this investigation and both deserve their own change.
- The stale packages sitting in the release projects on OBS, which are unrelated to this work.
