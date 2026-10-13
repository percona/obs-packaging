# Pre-release Flow — Tool PR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the `percona-obs` side of the two-hop release flow (rollout step 1 of the spec): `release.yaml` mapping entries, `sync prerelease`, `sync release --from`, the shared `release_copy` module, and the `project release` changes (source commit, open-release refresh, QA blocks in mirrors).

**Architecture:** Two new small modules (`release_record.py` for `release.yaml` entries, `github_api.py` for the `gh api` lookup of the last synced commit) plus one shared orchestration module (`release_copy.py`) that both hops call. `cmd_sync_release` is refactored onto `release_copy` with unchanged behaviour, then gains `--from`; `cmd_sync_prerelease` is a new thin command. `project release` gains three features in `cmd_project.py`. Workflow changes are a separate plan (rollout step 2); only the one `release.yaml` reader in `obs-pr-cleanup.yml` is touched here so a mapping-form entry cannot break tagging if a release is cut before step 2 lands.

**Tech Stack:** Python 3.11, `osc` library + `osc` CLI, PyYAML, pytest (monkeypatch style, no network), black, pyright, `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md`

## Global Constraints

- Work in the worktree `.claude/worktrees/prerelease-flow` on branch `prerelease-flow` (off `percona/main`). Never touch the primary checkout.
- After every code change run `venv/bin/black percona_obs/` then `venv/bin/pyright` (must report `0 errors`), then `venv/bin/pytest -q`. All three must pass before a task's commit.
- Commits: `git commit -s`. No `Co-Authored-By` lines of any kind (CLAUDE.md rule overrides the session reminder). Never `git push`, never open a PR.
- No OBS or GitHub network access in tests: every `osc.core.*`, `subprocess.run` and `gh` call is monkeypatched.
- `release.yaml` string entries (`- ppg/18.4-1`) must keep working everywhere; the mapping form is `{tag: <tag>, source_commit: <full sha>}`.
- The pre-release source project is addressed through a profile passed as `--branch-from` (same convention as `sync push`), never guessed from the PR root.
- `osc release` keeps the temporary `<releasetarget>` mechanism (`_add_release_targets` / `_remove_release_targets` in a `finally`) for both hops, and additionally passes `--target-project <target>`. Reason: `osc release` documents "It requires defined release targets set to trigger=manual"; `--target-project` only selects among them. The pre-release meta therefore carries release targets only transiently during a copy, which satisfies the spec's intent (a pure mirror at rest).
- The OBS-side copy of `source_commit` is a `source_commit: <sha>` line appended to the pre-release project's `<description>`; it is rewritten at the end of every population because `_apply_project_config` overwrites the description from the mirror first.
- Spec section numbering is referenced below as "spec §N".

**User decisions (already made):**
- Pre-release lives under the PR namespace: `<pr-root>:pr-N:<product>:releases:<major>`.
- Release QA runs every `qa:` lane declared in the staging project and its subprojects (no label filter yet).
- Population and QA are automatic on a release PR (workflow plan), no trigger labels.
- `source_commit` is recorded locally by `project release`; CI never commits back to the PR branch.
- `project release` refreshes an open release id in place when its tag does not exist yet.
- Approach A: two commands (`sync prerelease`, `sync release --from`) on a shared `release_copy.py`.
- Multi-major release PRs are supported; one in-flight release PR per major (enforced in the workflow plan).

---

## File structure

| File | Responsibility |
|---|---|
| `percona_obs/release_record.py` (new) | Parse/dump `release.yaml` `releases:` entries (string and mapping forms, legacy `revision:`). |
| `percona_obs/github_api.py` (new) | `gh api` wrapper: repo slug from a clone URL, head SHA of the last sync-main run whose sync jobs succeeded. |
| `percona_obs/release_copy.py` (new) | Shared hop mechanics: subproject pair collection, mirror meta apply, `osc release` copy of a project tree, verify, orphan report. |
| `percona_obs/obs_api.py` | `publish_override` on `_apply_project_config`; project description marker read/write. |
| `percona_obs/cmd_sync.py` | `cmd_sync_release` refactored onto `release_copy`, then `--from`; new `cmd_sync_prerelease`. |
| `percona_obs/cmd_project.py` | `project release`: QA blocks in mirrors, `source_commit`, open-release refresh. |
| `percona_obs/common.py` | `compute_ppg_release` reads entries through `release_record`. |
| `percona_obs/cli.py` | New `sync prerelease` parser, new flags on `sync release` and `project release`. |
| `.github/workflows/obs-pr-cleanup.yml` | The one-line `release.yaml` reader understands the mapping form. |
| `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md`, `CLAUDE.md` | Command reference and key-file tables. |
| `tests/test_release_record.py`, `tests/test_github_api.py`, `tests/test_release_copy.py`, `tests/test_sync_prerelease.py` (new); `tests/test_sync_release.py`, `tests/test_project_release.py`, `tests/test_computed_macros.py`, `tests/test_obs_api_markers.py` (new) | Unit tests. |

---

### Task 0: Worktree environment and baseline

**Goal:** A working `venv/` in the worktree and a green baseline so later failures are attributable.

**Files:**
- Create: `venv/` (git-ignored) in `.claude/worktrees/prerelease-flow`

**Acceptance Criteria:**
- [ ] `venv/bin/pytest -q` passes on the untouched branch
- [ ] `venv/bin/black --check percona_obs/` and `venv/bin/pyright` pass

**Verify:** `venv/bin/pytest -q && venv/bin/black --check percona_obs/ && venv/bin/pyright` → all green, pyright prints `0 errors`

**Steps:**

- [ ] **Step 1: Create the venv**

```bash
cd /home/rdias/Work/percona-obs-packaging/.claude/worktrees/prerelease-flow
python3 -m venv venv
venv/bin/pip install -q -r requirements.txt
venv/bin/pip install -q pytest
```

- [ ] **Step 2: Run the baseline**

Run: `venv/bin/pytest -q && venv/bin/black --check percona_obs/ && venv/bin/pyright`
Expected: all tests pass, black reports nothing to change, pyright `0 errors`.

No commit (nothing changed).

---

### Task 1: `release_record.py` and mapping-form `release.yaml` entries

**Goal:** One parser for `releases:` entries used by every reader (`compute_ppg_release`, `project release`, `sync release`, the cleanup workflow one-liner), accepting strings, `{tag, source_commit}` mappings and legacy `revision:`.

**Files:**
- Create: `percona_obs/release_record.py`
- Modify: `percona_obs/common.py:319-346` (`compute_ppg_release`)
- Modify: `percona_obs/cmd_project.py:2293-2300` (existing release list)
- Modify: `percona_obs/cmd_sync.py:2628-2635` (release list in `cmd_sync_release`)
- Modify: `.github/workflows/obs-pr-cleanup.yml:138`
- Test: `tests/test_release_record.py`, `tests/test_computed_macros.py`

**Acceptance Criteria:**
- [ ] `parse_release_entries` returns `ReleaseEntry(tag, source_commit)` for both forms and raises `SystemExit` naming an unrecognised entry
- [ ] `compute_ppg_release` counts a mapping entry's tag (`{tag: ppg/18.4-2}` counts for 18.4)
- [ ] `project release` and `sync release` still work with string-only files (existing tests pass)
- [ ] The cleanup one-liner prints the tag for a mapping last entry

**Verify:** `venv/bin/pytest -q tests/test_release_record.py tests/test_computed_macros.py tests/test_project_release.py tests/test_sync_release.py` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests**

`tests/test_release_record.py`:

```python
"""Unit tests for percona_obs.release_record."""

import pytest

from percona_obs.release_record import (
    ReleaseEntry,
    current_release,
    dump_release_entry,
    parse_release_entries,
    release_tags,
)


def test_parse_string_and_mapping_entries():
    data = {
        "releases": [
            "ppg/18.4-1",
            {"tag": "ppg/18.6-1"},
            {"tag": "ppg/18.7-1", "source_commit": "abc123"},
        ]
    }
    assert parse_release_entries(data) == [
        ReleaseEntry("ppg/18.4-1"),
        ReleaseEntry("ppg/18.6-1"),
        ReleaseEntry("ppg/18.7-1", "abc123"),
    ]
    assert release_tags(data) == ["ppg/18.4-1", "ppg/18.6-1", "ppg/18.7-1"]
    assert current_release(data) == ReleaseEntry("ppg/18.7-1", "abc123")


def test_parse_legacy_revision_and_empty():
    assert parse_release_entries({"revision": "ppg/17.9-1"}) == [
        ReleaseEntry("ppg/17.9-1")
    ]
    assert parse_release_entries({}) == []
    assert parse_release_entries("not a dict") == []
    assert current_release({}) is None


def test_parse_rejects_garbage_entry():
    with pytest.raises(SystemExit, match="unrecognised releases entry"):
        parse_release_entries({"releases": [{"source_commit": "x"}]})


def test_dump_round_trip():
    assert dump_release_entry(ReleaseEntry("ppg/18.4-1")) == "ppg/18.4-1"
    assert dump_release_entry(ReleaseEntry("ppg/18.7-1", "abc")) == {
        "tag": "ppg/18.7-1",
        "source_commit": "abc",
    }
```

Append to `tests/test_computed_macros.py`:

```python
MAPPING_RELEASE_YAML = """\
project: ppg:staging:18
releases:
- ppg/18.3-1
- tag: ppg/18.4-1
  source_commit: 9e9d9738c0ffee
"""


def test_compute_counts_mapping_entries():
    assert compute_ppg_release("ppg", "18.4", MAPPING_RELEASE_YAML) == "2"
    assert compute_ppg_release("ppg", "18.3", MAPPING_RELEASE_YAML) == "2"


def test_compute_tolerates_garbage_entries():
    assert compute_ppg_release("ppg", "18.4", "releases: [{x: 1}]\n") == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest -q tests/test_release_record.py tests/test_computed_macros.py`
Expected: FAIL with `ModuleNotFoundError: percona_obs.release_record` and `assert '1' == '2'`.

- [ ] **Step 3: Create `percona_obs/release_record.py`**

```python
"""``release.yaml`` ``releases:`` entries.

Two entry forms coexist: the plain tag string (``- ppg/18.4-1``, all
historical entries) and the mapping form written by ``project release``
since the pre-release flow (``- {tag: ppg/18.7-1, source_commit: <sha>}``).
``source_commit`` is the full SHA of ``main`` whose staging tree the
release's binaries were built from.  The legacy single ``revision:`` field
is still read as a one-element list.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReleaseEntry:
    tag: str
    source_commit: "str | None" = None


def parse_release_entries(data: Any) -> "list[ReleaseEntry]":
    """Return the ``releases:`` list of a loaded release.yaml as entries.

    Raises SystemExit naming the offending item for anything that is neither
    a string nor a mapping with a string ``tag``.
    """
    if not isinstance(data, dict):
        return []
    raw = data.get("releases")
    if not raw and data.get("revision"):
        return [ReleaseEntry(str(data["revision"]))]
    if not isinstance(raw, list):
        return []
    entries: list[ReleaseEntry] = []
    for item in raw:
        if isinstance(item, str):
            entries.append(ReleaseEntry(item))
        elif isinstance(item, dict) and isinstance(item.get("tag"), str):
            sc = item.get("source_commit")
            entries.append(ReleaseEntry(item["tag"], str(sc) if sc else None))
        else:
            raise SystemExit(
                f"error: release.yaml: unrecognised releases entry {item!r} "
                "(expected a tag string or {tag: ..., source_commit: ...})"
            )
    return entries


def release_tags(data: Any) -> "list[str]":
    return [e.tag for e in parse_release_entries(data)]


def current_release(data: Any) -> "ReleaseEntry | None":
    """The last entry is the release in flight (or just shipped)."""
    entries = parse_release_entries(data)
    return entries[-1] if entries else None


def dump_release_entry(entry: ReleaseEntry) -> "str | dict[str, str]":
    """YAML-ready value: a bare tag when there is nothing else to record."""
    if entry.source_commit is None:
        return entry.tag
    return {"tag": entry.tag, "source_commit": entry.source_commit}
```

- [ ] **Step 4: Route the three readers through it**

`percona_obs/common.py`, inside `compute_ppg_release`, replace the block

```python
    raw = data.get("releases")
    tags = [str(t) for t in raw] if isinstance(raw, list) else []
    if not tags and data.get("revision"):
        tags = [str(data["revision"])]
```

with

```python
    from .release_record import release_tags  # local: release_record is leaf

    try:
        tags = release_tags(data)
    except SystemExit:
        return "1"
```

`percona_obs/cmd_project.py` (around line 2293), replace

```python
    existing_releases: list[str] = []
    if not is_first_release:
        existing_data = load_yaml(release_dir / "release.yaml")
        raw = existing_data.get("releases")
        if isinstance(raw, list):
            existing_releases = [str(r) for r in raw]
        elif existing_data.get("revision"):
            existing_releases = [str(existing_data["revision"])]
```

with

```python
    existing_entries: list[ReleaseEntry] = []
    if not is_first_release:
        existing_entries = parse_release_entries(
            load_yaml(release_dir / "release.yaml")
        )
    existing_releases: list[str] = [e.tag for e in existing_entries]
```

and add `from .release_record import ReleaseEntry, parse_release_entries` to the imports. Keep `new_releases_list = existing_releases + [tag]` for now (Task 8 rewrites it).

`percona_obs/cmd_sync.py` in `cmd_sync_release`, replace

```python
    releases_list: list[str] = release_data.get("releases") or []
    if not releases_list and release_data.get("revision"):
        releases_list = [str(release_data["revision"])]
    tag = releases_list[-1] if releases_list else ""
```

with

```python
    releases_list = release_tags(release_data)
    tag = releases_list[-1] if releases_list else ""
```

and import `from .release_record import release_tags`.

`.github/workflows/obs-pr-cleanup.yml` line 138, replace the python one-liner string with:

```
"import sys,yaml; d=yaml.safe_load(sys.stdin); r=d.get('releases') or []; last=r[-1] if r else d.get('revision') or ''; print(last.get('tag','') if isinstance(last, dict) else last)"
```

- [ ] **Step 5: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS, `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/release_record.py percona_obs/common.py percona_obs/cmd_project.py percona_obs/cmd_sync.py .github/workflows/obs-pr-cleanup.yml tests/test_release_record.py tests/test_computed_macros.py
git commit -s -m "release.yaml: accept {tag, source_commit} entries via release_record"
```

---

### Task 2: `github_api.py` — last synced head SHA

**Goal:** Resolve "the commit of `main` whose staging tree OBS currently holds" as the head SHA of the newest completed `sync-main.yml` run on `main` whose sync jobs all concluded `success`, through `gh api`.

**Files:**
- Create: `percona_obs/github_api.py`
- Test: `tests/test_github_api.py`

**Acceptance Criteria:**
- [ ] `repo_slug_from_url` handles `https://github.com/percona/obs-packaging.git`, `https://github.com/percona/obs-packaging`, `git@github.com:percona/obs-packaging.git`
- [ ] `last_synced_head_sha` skips a run whose `percona-obs sync push (...)` job failed even if the run's other jobs passed, and returns the next older qualifying run's `head_sha`
- [ ] A `gh` failure raises `SystemExit` with the stderr text; no qualifying run raises `SystemExit`

**Verify:** `venv/bin/pytest -q tests/test_github_api.py` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests**

`tests/test_github_api.py`:

```python
"""Unit tests for percona_obs.github_api (gh is monkeypatched)."""

import pytest

import percona_obs.github_api as gha


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/percona/obs-packaging.git",
        "https://github.com/percona/obs-packaging",
        "git@github.com:percona/obs-packaging.git",
    ],
)
def test_repo_slug_from_url(url):
    assert gha.repo_slug_from_url(url) == "percona/obs-packaging"


def test_repo_slug_rejects_unknown():
    with pytest.raises(SystemExit, match="cannot derive owner/repo"):
        gha.repo_slug_from_url("file:///tmp/x")


def _fake_api(monkeypatch, runs, jobs_by_run):
    def fake(path):
        if "/workflows/sync-main.yml/runs" in path:
            return {"workflow_runs": runs}
        for run_id, jobs in jobs_by_run.items():
            if f"/runs/{run_id}/jobs" in path:
                return {"jobs": jobs}
        raise AssertionError(path)

    monkeypatch.setattr(gha, "_gh_api_json", fake)


def test_last_synced_skips_runs_with_failed_sync_job(monkeypatch):
    runs = [
        {"id": 3, "head_sha": "c" * 40},
        {"id": 2, "head_sha": "b" * 40},
        {"id": 1, "head_sha": "a" * 40},
    ]
    jobs = {
        3: [
            {"name": "percona-obs sync push (boo)", "conclusion": "success"},
            {"name": "percona-obs sync push (labs)", "conclusion": "failure"},
            {"name": "Wait for OBS builds (boo)", "conclusion": "success"},
        ],
        2: [
            {"name": "percona-obs sync push (boo)", "conclusion": "success"},
            {"name": "percona-obs sync push (labs)", "conclusion": "success"},
            {"name": "Wait for OBS builds (boo)", "conclusion": "failure"},
        ],
    }
    _fake_api(monkeypatch, runs, jobs)
    assert gha.last_synced_head_sha("percona/obs-packaging") == "b" * 40


def test_last_synced_no_qualifying_run(monkeypatch):
    _fake_api(monkeypatch, [{"id": 1, "head_sha": "a" * 40}], {1: []})
    with pytest.raises(SystemExit, match="no completed sync-main.yml run"):
        gha.last_synced_head_sha("percona/obs-packaging")


def test_gh_failure_is_reported(monkeypatch):
    class R:
        returncode = 1
        stdout = ""
        stderr = "gh: not logged in"

    monkeypatch.setattr(gha.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(SystemExit, match="not logged in"):
        gha._gh_api_json("repos/x/y")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest -q tests/test_github_api.py`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `percona_obs/github_api.py`**

```python
"""GitHub REST lookups through the ``gh`` CLI.

Only ``gh`` is used (no token handling in the tool): locally the operator is
logged in, in CI ``GH_TOKEN`` is set.  Every call is a subprocess so tests
monkeypatch ``_gh_api_json``.
"""

import json
import re
import subprocess
from typing import Any

_SLUG_RE = re.compile(r"github\.com[/:]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")

# Job name prefix of sync-main.yml's upload legs ("percona-obs sync push (<instance>)").
SYNC_JOB_PREFIX = "percona-obs sync push"


def repo_slug_from_url(url: str) -> str:
    """``https://github.com/o/r.git`` / ``git@github.com:o/r.git`` → ``o/r``."""
    m = _SLUG_RE.search(url.strip())
    if not m:
        raise SystemExit(f"error: cannot derive owner/repo from {url!r}")
    return m.group(1)


def _gh_api_json(path: str) -> Any:
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"error: gh api {path} failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def last_synced_head_sha(
    repo_slug: str,
    *,
    workflow_file: str = "sync-main.yml",
    branch: str = "main",
    job_prefix: str = SYNC_JOB_PREFIX,
    max_runs: int = 20,
) -> str:
    """Head SHA of the newest completed *workflow_file* run on *branch* whose
    sync jobs (name starting with *job_prefix*) all concluded ``success``.

    The run's own conclusion is ignored on purpose: the build poll job fails
    the run after the upload already happened, and that upload is what OBS
    holds.
    """
    data = _gh_api_json(
        f"repos/{repo_slug}/actions/workflows/{workflow_file}/runs"
        f"?branch={branch}&status=completed&per_page={max_runs}"
    )
    for run in data.get("workflow_runs") or []:
        jobs = (
            _gh_api_json(f"repos/{repo_slug}/actions/runs/{run['id']}/jobs?per_page=100")
            .get("jobs")
            or []
        )
        sync_jobs = [j for j in jobs if str(j.get("name", "")).startswith(job_prefix)]
        if sync_jobs and all(j.get("conclusion") == "success" for j in sync_jobs):
            return str(run["head_sha"])
    raise SystemExit(
        f"error: no completed {workflow_file} run on {branch} of {repo_slug} "
        f"with successful sync jobs in the last {max_runs} runs; "
        "pass --source-commit explicitly"
    )
```

- [ ] **Step 4: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q tests/test_github_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/github_api.py tests/test_github_api.py
git commit -s -m "github_api: look up the last synced main commit via gh"
```

---

### Task 3: `release_copy.py` and `cmd_sync_release` refactor (behaviour unchanged)

**Goal:** Move the copy mechanics out of `cmd_sync.py` into `percona_obs/release_copy.py` and make `cmd_sync_release` a thin orchestration with a single code path for first and update releases. Behaviour must be identical; the existing tests prove it after their monkeypatch targets move.

**Files:**
- Create: `percona_obs/release_copy.py`
- Modify: `percona_obs/cmd_sync.py` (`_collect_release_subprojects`, `_filter_release_repo_names`, `_sync_release_subprojects` removed; `cmd_sync_release` body)
- Test: `tests/test_sync_release.py` (rewired), `tests/test_release_copy.py` (new)

**Acceptance Criteria:**
- [ ] `release_copy.copy_project_binaries` adds release targets, runs `osc release <src> --no-delay --target-project <target>`, removes targets in `finally` even when osc fails
- [ ] `release_copy.release_tree` copies top then each pair, applies each pair's mirror meta before its copy, verifies when `verify_timeout > 0`, warns about orphans
- [ ] `cmd_sync_release` first-release and update paths both run the freeze sequence and the same `release_tree`; all pre-existing `test_sync_release.py` assertions hold

**Verify:** `venv/bin/pytest -q tests/test_sync_release.py tests/test_release_copy.py` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests for the new module**

`tests/test_release_copy.py`:

```python
"""Unit tests for percona_obs.release_copy (OBS and osc monkeypatched)."""

from pathlib import Path

import pytest

import percona_obs.release_copy as rc


def _stub_obs(monkeypatch, calls):
    monkeypatch.setattr(
        rc, "_read_project_release_source", lambda apiurl, prj: ([], None)
    )
    monkeypatch.setattr(
        rc, "filter_release_repo_names", lambda apiurl, names, target: names
    )
    monkeypatch.setattr(
        rc, "_add_release_targets", lambda *a, **k: calls.append(("add", a[1], a[2]))
    )
    monkeypatch.setattr(
        rc,
        "_remove_release_targets",
        lambda *a, **k: calls.append(("remove", a[1], a[2])),
    )
    monkeypatch.setattr(
        rc, "_apply_project_config", lambda *a, **k: calls.append(("meta", a[1])) or (False, True)
    )
    monkeypatch.setattr(rc, "_disable_project_builds", lambda *a, **k: None)
    monkeypatch.setattr(
        rc, "_fetch_obs_subproject_names", lambda apiurl, prefix: set()
    )


def test_copy_project_binaries_uses_target_project_and_restores(monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)
    seen = {}
    monkeypatch.setattr(
        rc.subprocess, "run", lambda cmd, **k: seen.setdefault("cmd", cmd)
    )
    rc.copy_project_binaries("http://obs", "S", "T")
    assert "--target-project" in seen["cmd"] and "T" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("release") + 1] == "S"
    assert calls == [("add", "S", "T"), ("remove", "S", "T")]


def test_copy_project_binaries_restores_on_failure(monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)

    def boom(*a, **k):
        raise RuntimeError("osc failed")

    monkeypatch.setattr(rc.subprocess, "run", boom)
    with pytest.raises(RuntimeError):
        rc.copy_project_binaries("http://obs", "S", "T")
    assert calls[-1] == ("remove", "S", "T")


def test_release_tree_order_and_verify(monkeypatch, tmp_path):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(
        rc.subprocess, "run", lambda cmd, **k: calls.append(("osc", cmd[4]))
    )
    monkeypatch.setattr(
        rc,
        "verify_release_landed",
        lambda apiurl, s, t, timeout_s=600: calls.append(("verify", s, t)),
    )
    pairs = [("containers", tmp_path / "containers")]
    rc.release_tree(
        "http://obs", "S", "T", pairs, "home:Admin", {}, verify_timeout=5
    )
    assert [c for c in calls if c[0] in ("osc", "meta")] == [
        ("osc", "S"),
        ("meta", "T:containers"),
        ("osc", "S:containers"),
    ]
    assert ("verify", "S", "T") in calls
    assert ("verify", "S:containers", "T:containers") in calls


def test_release_tree_publish_override_reaches_meta(monkeypatch, tmp_path):
    seen = {}
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(
        rc,
        "_apply_project_config",
        lambda *a, **k: seen.setdefault("publish", k.get("publish_override"))
        or (False, True),
    )
    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **k: None)
    rc.release_tree(
        "http://obs",
        "S",
        "T",
        [("x", tmp_path)],
        "home:Admin",
        {},
        publish_override=True,
        verify_timeout=0,
    )
    assert seen["publish"] is True


def test_warn_orphans(monkeypatch, capsys):
    monkeypatch.setattr(
        rc,
        "_fetch_obs_subproject_names",
        lambda apiurl, prefix: {"T:containers", "T:containers:ubi9"},
    )
    rc.warn_orphans("http://obs", "T", [("containers", Path("/x"))], "home:Admin")
    out = capsys.readouterr().out
    assert "T:containers:ubi9" in out and "sync delete" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_release_copy.py`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `percona_obs/release_copy.py`**

Move `_collect_release_subprojects` (cmd_sync.py 2440-2480) and `_filter_release_repo_names` (2482-2498) here verbatim under the names `collect_release_subprojects` and `filter_release_repo_names` (docstrings kept), and add the new functions:

```python
"""Shared mechanics of the two release hops.

Hop 1 (``sync prerelease``): staging → per-PR pre-release project.
Hop 2 (``sync release --from``): pre-release → release project.
Both apply mirror project.yaml meta to the target tree, copy binaries with
``osc release`` and verify the copy landed.  The legacy single-hop
``sync release`` (no ``--from``) uses the same primitives.

``osc release`` requires ``<releasetarget trigger="manual">`` entries on the
source, so a copy adds them, runs osc with ``--target-project`` and removes
them again in a ``finally`` — the source meta is unchanged at rest.
"""

import os
import subprocess
import sys
from pathlib import Path

from .common import (
    _REPO_DIR,
    _print_ok,
    _print_pending,
    find_projects,
    resolve_project_path,
)
from .obs_api import (
    _add_release_targets,
    _apply_project_config,
    _disable_project_builds,
    _fetch_obs_project_repository_names,
    _fetch_obs_subproject_names,
    _read_project_release_source,
    _remove_release_targets,
)
from .project_config import project_in_slice
from .release_freeze import verify_release_landed

_OSC_BIN = os.path.join(os.path.dirname(sys.executable), "osc")


# --- moved verbatim from cmd_sync (renamed, no leading underscore) ---
# def collect_release_subprojects(source_project_id, release_path): ...
# def filter_release_repo_names(apiurl, source_repo_names, release_obs_project): ...


def apply_mirror_meta(
    apiurl: str,
    target_obs_project: str,
    mirror_path: Path,
    rootprj: str,
    env_vars: "dict[str, str]",
    *,
    publish_override: "dict[str, bool] | bool | None" = None,
) -> None:
    """Create or update *target_obs_project* from the mirror project.yaml and
    make sure builds are disabled.  Two passes when OBS stripped paths."""
    paths_stripped, _ = _apply_project_config(
        apiurl,
        target_obs_project,
        mirror_path,
        rootprj,
        env_vars=env_vars,
        publish_override=publish_override,
    )
    if paths_stripped:
        _apply_project_config(
            apiurl,
            target_obs_project,
            mirror_path,
            rootprj,
            env_vars=env_vars,
            publish_override=publish_override,
        )
    _disable_project_builds(apiurl, target_obs_project)


def copy_project_binaries(
    apiurl: str, source_obs_project: str, target_obs_project: str
) -> None:
    """``osc release`` every repo of *source* that exists in *target*."""
    repo_elems, _ = _read_project_release_source(apiurl, source_obs_project)
    repo_names = filter_release_repo_names(
        apiurl,
        [r.get("name", "") for r in repo_elems if r.get("name")],
        target_obs_project,
    )
    _add_release_targets(apiurl, source_obs_project, target_obs_project, repo_names)
    try:
        _print_pending(f"releasing {source_obs_project} → {target_obs_project}")
        subprocess.run(
            [
                _OSC_BIN,
                "-A",
                apiurl,
                "release",
                source_obs_project,
                "--no-delay",
                "--target-project",
                target_obs_project,
            ],
            check=True,
        )
    finally:
        _remove_release_targets(apiurl, source_obs_project, target_obs_project)
    _print_ok(f"released  {source_obs_project} → {target_obs_project}")


def warn_orphans(
    apiurl: str,
    target_obs_project: str,
    pairs: "list[tuple[str, Path]]",
    rootprj: str,
) -> None:
    """Report target-tier OBS subprojects with no local mirror (never deleted)."""
    local_names = {name for name, _ in pairs}
    for obs_sub in sorted(_fetch_obs_subproject_names(apiurl, target_obs_project)):
        sub_name = obs_sub[len(target_obs_project) + 1 :]
        if sub_name not in local_names:
            print(
                f"warning: orphaned release subproject on OBS: {obs_sub} "
                "(no local mirror) — remove manually with "
                f"'percona-obs sync delete {obs_sub[len(rootprj) + 1 :]}'",
                flush=True,
            )


def release_tree(
    apiurl: str,
    source_obs_project: str,
    target_obs_project: str,
    pairs: "list[tuple[str, Path]]",
    rootprj: str,
    env_vars: "dict[str, str]",
    *,
    publish_override: "dict[str, bool] | bool | None" = None,
    verify_timeout: int = 600,
) -> None:
    """Copy the top project and every (subproject, mirror) pair, then verify.

    The caller has already applied the top project's meta (that happens
    before any freeze); subproject meta is applied here, right before each
    subproject's copy, exactly as the single-hop release always did.
    """
    copy_project_binaries(apiurl, source_obs_project, target_obs_project)
    for subproject_name, mirror_path in pairs:
        target_sub = f"{target_obs_project}:{subproject_name}"
        apply_mirror_meta(
            apiurl,
            target_sub,
            mirror_path,
            rootprj,
            env_vars,
            publish_override=publish_override,
        )
        copy_project_binaries(
            apiurl, f"{source_obs_project}:{subproject_name}", target_sub
        )
    if verify_timeout > 0:
        verify_release_landed(
            apiurl, source_obs_project, target_obs_project, timeout_s=verify_timeout
        )
        for subproject_name, _ in pairs:
            verify_release_landed(
                apiurl,
                f"{source_obs_project}:{subproject_name}",
                f"{target_obs_project}:{subproject_name}",
                timeout_s=verify_timeout,
            )
    warn_orphans(apiurl, target_obs_project, pairs, rootprj)
```

`_apply_project_config`'s `publish_override` keyword does not exist until Task 4; add it there before running pyright on this task, or do Task 4's Step 3 edit now (it is a 4-line change) — either order, both must land before this task's commit. Simplest: apply Task 4 Step 3 now and still complete Task 4's tests in Task 4.

- [ ] **Step 4: Refactor `cmd_sync_release`**

In `percona_obs/cmd_sync.py`:
1. Delete `_collect_release_subprojects`, `_filter_release_repo_names`, `_sync_release_subprojects`.
2. Add `from .release_copy import apply_mirror_meta, collect_release_subprojects, release_tree`.
3. Replace the call `_collect_release_subprojects(source_project_id, release_path)` with `collect_release_subprojects(...)`.
4. Replace everything from `_print_pending(f"checking release project {release_obs_project}")` to the end of the function with:

```python
    _print_pending(f"checking release project {release_obs_project}")
    project_exists = _obs_project_exists(apiurl, release_obs_project)

    if not args.force:
        _check_source_unchanged_since_tag(source_project_id, tag, args)

    if project_exists:
        # Re-apply the local release project config so repo additions,
        # publish flags and prjconf changes reach OBS on update releases too.
        apply_mirror_meta(
            apiurl, release_obs_project, release_path, args.rootprj, shared_env_vars
        )
    else:
        # First release: snapshot the source topology, builds disabled.
        _create_release_project(apiurl, source_obs_project, release_obs_project)
        _copy_project_conf(apiurl, source_obs_project, release_obs_project)

    _freeze_and_run(
        lambda: release_tree(
            apiurl,
            source_obs_project,
            release_obs_project,
            subproject_pairs,
            args.rootprj,
            shared_env_vars,
            verify_timeout=args.verify_timeout,
        )
    )

    suffix = f" (update: {tag})" if project_exists and tag else ""
    _print_ok(f"release  {source_obs_project} → {release_obs_project}{suffix}")
```

and extract the duplicated divergence check into a module-level helper placed right above `cmd_sync_release`:

```python
def _check_source_unchanged_since_tag(source_project_id: str, tag: str, args) -> None:
    """Abort when the source project's tree changed since *tag* (legacy
    single-hop release only; ``--skip-tag-check`` skips, no tag = nothing)."""
    if not tag:
        return
    if getattr(args, "skip_tag_check", False):
        _print_same(f"skipping tag divergence check for {tag} (--skip-tag-check)")
        return
    source_path = resolve_project_path(source_project_id)
    _print_pending(f"checking for changes in {source_project_id} since tag {tag}")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{tag}..HEAD", "--", str(source_path)],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(f"error: git diff failed — is the tag '{tag}' present locally?")
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    if changed:
        print(
            f"error: source project {source_project_id} has changed since tag {tag}:",
            file=sys.stderr,
        )
        for f in changed:
            print(f"  {f}", file=sys.stderr)
        raise SystemExit(
            "The source project has diverged from the release tag. "
            "Use --force to skip this check."
        )
```

Remove the now-unused imports from cmd_sync (`_add_release_targets`, `_remove_release_targets`, `_read_project_release_source`, `_fetch_obs_project_repository_names`, `_disable_project_builds` if no other use, `verify_release_landed`) — pyright/black will not flag unused imports, so grep each name before removing: `grep -n "<name>" percona_obs/cmd_sync.py`.

- [ ] **Step 5: Rewire `tests/test_sync_release.py`**

- Change the import line to `from percona_obs.release_copy import collect_release_subprojects` and `import percona_obs.release_copy as rc`; drop `_sync_release_subprojects`.
- `test_collect_pairs_and_missing`, `test_collect_release_subprojects_respects_slice`: call `collect_release_subprojects`, patch `rc.resolve_project_path` (not `cmd_sync.`).
- `test_missing_mirror_is_hard_error` and `test_orphan_reporting` tested `_sync_release_subprojects`; replace them with:

```python
def test_missing_mirror_is_hard_error(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    _wire_release_update_path(monkeypatch, src, rel)
    args = _Args(project="ppg:releases:17", rootprj="home:Admin")
    with pytest.raises(SystemExit, match="tarballs"):
        cmd_sync.cmd_sync_release(args)
```

(the orphan behaviour is now covered by `tests/test_release_copy.py::test_warn_orphans`).
- In `_wire_release_update_path` and `_wire_release_first_path`, keep the `cmd_sync.*` patches for `resolve_project_path`, `_REPO_DIR`, `osc.conf.config`, `_obs_project_exists`, `_create_release_project`, `_copy_project_conf`, and patch the moved touchpoints on `rc`: `rc._apply_project_config → (False, None)`, `rc._disable_project_builds`, `rc._read_project_release_source → ([], None)`, `rc.filter_release_repo_names → names`, `rc._add_release_targets`, `rc._remove_release_targets`, `rc._fetch_obs_subproject_names → set()`, `rc.resolve_project_path` (same lambda as cmd_sync's).
- Every `monkeypatch.setattr(cmd_sync.subprocess, "run", ...)` that intercepts `osc release` becomes `rc.subprocess`; `cmd_sync.subprocess.run` is still used by the git divergence check, which `_Args.skip_tag_check = True` bypasses.
- Every `monkeypatch.setattr(cmd_sync, "verify_release_landed", ...)` becomes `rc`.
- `test_filter_release_repo_names_warns_and_drops`: import/patch on `rc` (`rc._fetch_obs_project_repository_names`).

- [ ] **Step 6: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS, `0 errors`. In particular `test_freeze_order_and_restore_on_failure` still sees `["drain", "green", "freeze", ..., "restore"]`.

- [ ] **Step 7: Commit**

```bash
git add percona_obs/release_copy.py percona_obs/cmd_sync.py percona_obs/obs_api.py tests/test_sync_release.py tests/test_release_copy.py
git commit -s -m "sync release: move copy mechanics into release_copy, one code path"
```

---

### Task 4: `obs_api` — publish override and description marker

**Goal:** Two small OBS-side primitives the new hops need: force-publish on a project built from a mirror, and a `source_commit:` marker in a project description.

**Files:**
- Modify: `percona_obs/obs_api.py:1215-1280` (`_apply_project_config`), new functions after `_disable_project_builds`
- Test: `tests/test_obs_api_markers.py`

**Acceptance Criteria:**
- [ ] `_apply_project_config(..., publish_override=True)` emits `<publish><enable/></publish>` regardless of the mirror's `publish:`; `None` keeps today's behaviour
- [ ] `set_project_description_marker` appends `source_commit: <sha>` once (replacing an existing marker line) and pushes the meta
- [ ] `read_project_description_marker` returns the value or `None`

**Verify:** `venv/bin/pytest -q tests/test_obs_api_markers.py` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests**

`tests/test_obs_api_markers.py`:

```python
"""Unit tests for the project description marker and publish override (percona_obs.obs_api)."""

from pathlib import Path

import percona_obs.obs_api as obs_api

_META = (
    '<project name="P"><title>t</title><description>Mirror of X\n'
    "source_commit: old</description><repository name=\"r\"/></project>"
)


def test_marker_round_trip(monkeypatch):
    pushed = {}
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: _META)
    monkeypatch.setattr(
        obs_api, "_edit_project_meta", lambda a, p, meta, force: pushed.setdefault("meta", meta) or False
    )
    obs_api.set_project_description_marker("http://obs", "P", "source_commit", "new")
    assert pushed["meta"].count("source_commit:") == 1
    assert "source_commit: new" in pushed["meta"]
    assert "Mirror of X" in pushed["meta"]

    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: pushed["meta"])
    assert obs_api.read_project_description_marker("http://obs", "P", "source_commit") == "new"
    assert obs_api.read_project_description_marker("http://obs", "P", "other") is None


def test_publish_override_forces_enable(monkeypatch, tmp_path):
    (tmp_path / "project.yaml").write_text(
        "publish: {r: false}\nrepositories:\n  - name: r\n    archs: [x86_64]\n    paths: []\n"
    )
    seen = {}
    monkeypatch.setattr(
        obs_api,
        "build_project_meta",
        lambda *a, **k: seen.setdefault("publish", k.get("publish")) or "<project/>",
    )
    import urllib.error

    def not_found(*a, **k):
        raise urllib.error.HTTPError("u", 404, "nf", {}, None)

    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", not_found)
    monkeypatch.setattr(obs_api.osc.core, "show_project_conf", not_found)
    monkeypatch.setattr(obs_api, "_fetch_root_project_managed_elements", lambda a, r: [])
    monkeypatch.setattr(obs_api, "_inject_obs_managed_elements", lambda m, e: m)
    obs_api._apply_project_config(
        "http://obs", "root:P", tmp_path, "root", dry_run=True, publish_override=True
    )
    assert seen["publish"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_obs_api_markers.py`
Expected: FAIL (`AttributeError: set_project_description_marker`, `TypeError: unexpected keyword publish_override`).

- [ ] **Step 3: Implement**

In `_apply_project_config`, add the keyword parameter `publish_override: "dict[str, bool] | bool | None" = None` after `existing_branch_projects`, extend the docstring with "``publish_override`` replaces the mirror's ``publish:`` flags (the pre-release forces publishing on so QA always has repositories)", and change the `build_project_meta(...)` call to pass

```python
        publish=(
            publish_override
            if publish_override is not None
            else project_config.get("publish")
        ),
```

Add after `_disable_project_builds`:

```python
def set_project_description_marker(
    apiurl: str, obs_project_name: str, key: str, value: str
) -> None:
    """Append (or replace) a ``<key>: <value>`` line in the project description.

    Used to pin ``source_commit`` on a pre-release project so the final hop
    can check it without git.  ``_apply_project_config`` rewrites the
    description from the mirror, so callers set the marker last.
    """
    raw = _decode_obs_response(osc.core.show_project_meta(apiurl, obs_project_name))
    root = ET.fromstring(raw)
    desc = root.find("description")
    if desc is None:
        desc = ET.SubElement(root, "description")
    kept = [
        line
        for line in (desc.text or "").splitlines()
        if not line.startswith(f"{key}: ")
    ]
    desc.text = "\n".join([*kept, f"{key}: {value}"]).strip()
    ET.indent(root, space="  ")
    _edit_project_meta(
        apiurl, obs_project_name, ET.tostring(root, encoding="unicode"), force=False
    )
    _print_update(f"project meta  {obs_project_name}  ({key}: {value})")


def read_project_description_marker(
    apiurl: str, obs_project_name: str, key: str
) -> "str | None":
    raw = _decode_obs_response(osc.core.show_project_meta(apiurl, obs_project_name))
    desc = ET.fromstring(raw).findtext("description") or ""
    for line in desc.splitlines():
        if line.startswith(f"{key}: "):
            return line[len(key) + 2 :].strip() or None
    return None
```

- [ ] **Step 4: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/obs_api.py tests/test_obs_api_markers.py
git commit -s -m "obs_api: publish override and project description markers"
```

---

### Task 5: `sync prerelease` (hop 1)

**Goal:** New command that, under the PR profile, checks the `source_commit` record against the last synced `main`, creates/re-applies the pre-release tree from the mirrors (publish forced on), freezes staging, copies, verifies, restores, and pins `source_commit` in the pre-release description.

**Files:**
- Modify: `percona_obs/cmd_sync.py` (new `cmd_sync_prerelease`, helpers `_scope_local_paths`, `_changed_files_between`)
- Modify: `percona_obs/cli.py` (new `sync prerelease` parser after `sync release`)
- Test: `tests/test_sync_prerelease.py`

**Acceptance Criteria:**
- [ ] Without a mapping entry carrying `source_commit`, the command fails with "has no source_commit"
- [ ] A non-empty diff of scope paths between `source_commit` and the synced head aborts before `wait_for_quiesce` is called, listing the files
- [ ] Order of operations: record check → top meta (publish True) → drain → green → freeze → copy tree → restore → marker; marker is not written when the copy raised
- [ ] `--dry-run` runs the record check and the green check, writes nothing
- [ ] `--synced-commit` bypasses `gh`; `--force` bypasses the record check only

**Verify:** `venv/bin/pytest -q tests/test_sync_prerelease.py` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests**

`tests/test_sync_prerelease.py`:

```python
"""Unit tests for `sync prerelease` (percona_obs.cmd_sync.cmd_sync_prerelease).

OBS, osc, git and gh are all monkeypatched; the staging/release trees come
from tests.test_sync_release._mk_tree.
"""

import pytest

import percona_obs.cmd_sync as cmd_sync
import percona_obs.release_copy as rc
from tests.test_sync_release import _REPO_YAML, _mk_tree

SHA = "a" * 40


class _Args:
    def __init__(self, **kw):
        self.project = "ppg:releases:17"
        self.rootprj = "home:Admin:PR:pr-5"
        self.branch_from = "main"
        self.synced_commit = SHA
        self.source_commit = None
        self.force = False
        self.dry_run = False
        self.no_freeze = False
        self.freeze_timeout = 1
        self.verify_timeout = 0
        self.env_overrides = None
        self.profile = None
        self.__dict__.update(kw)


def _tree_with_record(tmp_path, monkeypatch, source_commit=SHA):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    entry = (
        f"  - tag: ppg/17.11-1\n    source_commit: {source_commit}\n"
        if source_commit
        else "  - ppg/17.11-1\n"
    )
    (rel / "release.yaml").write_text(f"project: ppg:staging:17\nreleases:\n{entry}")
    return src, rel


def _wire(monkeypatch, src, rel, calls):
    monkeypatch.setattr(
        cmd_sync, "resolve_project_path", lambda pid: src if pid == "ppg:staging:17" else rel
    )
    monkeypatch.setattr(
        rc, "resolve_project_path", lambda pid: src if pid == "ppg:staging:17" else rel
    )
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", rel.parents[2])
    monkeypatch.setattr(cmd_sync.osc.conf, "config", {"apiurl": "http://obs"})
    monkeypatch.setattr(
        cmd_sync, "_load_profile", lambda name: {"rootprj": "home:Admin", "apiurl": "http://obs"}
    )
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: True)
    monkeypatch.setattr(cmd_sync, "_changed_files_between", lambda *a, **k: [])
    monkeypatch.setattr(
        cmd_sync,
        "apply_mirror_meta",
        lambda apiurl, prj, path, rootprj, env, publish_override=None: calls.append(
            ("meta", prj, publish_override)
        ),
    )
    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", lambda *a, **k: calls.append("drain"))
    monkeypatch.setattr(cmd_sync, "assert_all_green", lambda *a, **k: calls.append("green") or [])
    monkeypatch.setattr(cmd_sync, "freeze_builds", lambda *a, **k: calls.append("freeze") or {"p": "<x/>"})
    monkeypatch.setattr(cmd_sync, "freeze_packages", lambda *a, **k: {})
    monkeypatch.setattr(cmd_sync, "restore_packages", lambda *a, **k: None)
    monkeypatch.setattr(cmd_sync, "restore_builds", lambda *a, **k: calls.append("restore"))
    monkeypatch.setattr(
        cmd_sync, "release_tree", lambda *a, **k: calls.append(("copy", a[1], a[2], k.get("publish_override")))
    )
    monkeypatch.setattr(
        cmd_sync,
        "set_project_description_marker",
        lambda apiurl, prj, key, value: calls.append(("marker", prj, value)),
    )


def test_requires_source_commit(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch, source_commit=None)
    _wire(monkeypatch, src, rel, [])
    with pytest.raises(SystemExit, match="has no source_commit"):
        cmd_sync.cmd_sync_prerelease(_Args())


def test_record_mismatch_aborts_before_drain(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    monkeypatch.setattr(
        cmd_sync, "_changed_files_between", lambda *a, **k: ["root/ppg/staging/17/x/rpm/x.spec"]
    )
    with pytest.raises(SystemExit, match="staging changed since the cut"):
        cmd_sync.cmd_sync_prerelease(_Args())
    assert "drain" not in calls


def test_happy_path_order(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    cmd_sync.cmd_sync_prerelease(_Args())
    assert calls[0] == ("meta", "home:Admin:PR:pr-5:ppg:releases:17", True)
    assert calls[1:4] == ["drain", "green", "freeze"]
    assert calls[4] == ("copy", "home:Admin:ppg:staging:17", "home:Admin:PR:pr-5:ppg:releases:17", True)
    assert calls[5] == "restore"
    assert calls[6] == ("marker", "home:Admin:PR:pr-5:ppg:releases:17", SHA)


def test_marker_not_written_when_copy_fails(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)

    def boom(*a, **k):
        raise RuntimeError("osc")

    monkeypatch.setattr(cmd_sync, "release_tree", boom)
    with pytest.raises(RuntimeError):
        cmd_sync.cmd_sync_prerelease(_Args())
    assert "restore" in calls and not any(c[0] == "marker" for c in calls if isinstance(c, tuple))


def test_dry_run_checks_only(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    (rel / "CHANGELOG.md").write_text("# Changelog\n\n## [17.11-1] - 2026-01-01\n")
    calls = []
    _wire(monkeypatch, src, rel, calls)
    monkeypatch.setattr(
        cmd_sync.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})()
    )
    cmd_sync.cmd_sync_prerelease(_Args(dry_run=True))
    assert calls == ["green"]


def test_scope_local_paths_maps_obs_names_back(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    monkeypatch.setattr(cmd_sync, "resolve_project_path", lambda pid: src.parents[2] / pid.replace(":", "/"))
    paths = cmd_sync._scope_local_paths(
        src,
        ["home:Admin:ppg:staging:17", "home:Admin:ppg:staging:17:containers"],
        {"home:Admin:ppg:common:deps": {"geos"}},
        "home:Admin",
    )
    assert src in paths
    assert src.parents[2] / "ppg/common/deps/geos" in paths
    assert any(p.name == "macros.yaml" for p in paths)
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_sync_prerelease.py`
Expected: FAIL with `AttributeError: cmd_sync_prerelease`.

- [ ] **Step 3: Implement in `percona_obs/cmd_sync.py`**

Add imports: `from .common import _macros_chain_files` (extend the existing `from .common import (...)` block), `from .obs_api import set_project_description_marker`, `from .release_record import current_release, release_tags` (merge with Task 1's import), `from .github_api import last_synced_head_sha, repo_slug_from_url`.

Add the helpers and the command right after `cmd_sync_release`:

```python
def _scope_local_paths(
    source_path: Path,
    freeze_scope: "list[str]",
    freeze_packages_map: "dict[str, set[str]]",
    rootprj: str,
) -> "list[Path]":
    """Local git paths whose content decides the released binaries: the
    source tree, its macros chain, every whole-frozen project and every
    aggregate-frozen package."""
    paths: list[Path] = [source_path, *_macros_chain_files(source_path)]
    for prj in freeze_scope:
        p = resolve_project_path(prj[len(rootprj) + 1 :])
        if p.is_dir() and p not in paths:
            paths.append(p)
    for prj, pkgs in freeze_packages_map.items():
        base = resolve_project_path(prj[len(rootprj) + 1 :])
        paths.extend(base / pkg for pkg in sorted(pkgs))
    return paths


def _changed_files_between(a: str, b: str, paths: "list[Path]") -> "list[str]":
    """``git diff --name-only a b -- paths`` (both commits must exist locally)."""
    for sha in (a, b):
        r = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=_REPO_DIR, capture_output=True
        )
        if r.returncode != 0:
            raise SystemExit(
                f"error: commit {sha} is not available locally; "
                "fetch the repository (full history) and retry"
            )
    rel = [str(p.relative_to(_REPO_DIR)) if p.is_absolute() else str(p) for p in paths]
    r = subprocess.run(
        ["git", "diff", "--name-only", a, b, "--", *rel],
        cwd=_REPO_DIR,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"error: git diff {a} {b} failed: {r.stderr.strip()}")
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def cmd_sync_prerelease(args) -> None:
    """Hop 1: copy a staging project tree into this PR's pre-release project.

    Runs with the PR profile (``-P pr-N``); ``--branch-from`` names the
    profile of the production instance that holds staging.  Steps (spec §2):
    record check, pre-release meta from the mirrors with publish forced on,
    drain/green/freeze staging, osc release, verify, restore, pin
    ``source_commit`` in the pre-release description.
    """
    release_path = resolve_project_path(args.project)
    release_file = release_path / "release.yaml"
    if not release_file.is_file():
        raise SystemExit(
            f"error: release.yaml not found at {release_path.relative_to(_REPO_DIR)}"
        )
    env_vars = parse_env_overrides(args.env_overrides) if args.env_overrides else {}
    release_data = load_yaml_with_env(release_file, env_vars)
    source_project_id = release_data.get("project")
    if not source_project_id:
        raise SystemExit(f"error: release.yaml missing 'project' field: {release_file}")
    entry = current_release(release_data)
    if entry is None:
        raise SystemExit("error: release.yaml has no releases: entries")
    source_commit = args.source_commit or entry.source_commit
    if not source_commit:
        raise SystemExit(
            f"error: release {entry.tag} has no source_commit in release.yaml; "
            "re-run 'percona-obs project release' (or pass --source-commit)"
        )

    branch_profile = _load_profile(args.branch_from)
    source_rootprj = branch_profile.get("rootprj", "")
    if not source_rootprj:
        raise SystemExit(f"error: profile {args.branch_from!r} has no rootprj")
    apiurl: str = osc.conf.config["apiurl"]
    source_obs_project = f"{source_rootprj}:{source_project_id}"
    prerelease_obs_project = f"{args.rootprj}:{args.project}"
    source_path = resolve_project_path(source_project_id)
    # Mirror paths are rewritten to the PR root through ${OBS_ROOTPRJ}.
    shared_env_vars = {**env_vars, **auto_rootprj_env(args.rootprj)}
    # The freeze scope lives on the production root.
    source_env_vars = {**env_vars, **auto_rootprj_env(source_rootprj)}

    subproject_pairs, missing_mirrors = collect_release_subprojects(
        source_project_id, release_path
    )
    source_sub_obs_projects = [
        f"{source_obs_project}:{name}" for name, _ in subproject_pairs
    ]
    freeze_scope, freeze_packages_map = _build_freeze_scope(
        source_obs_project,
        source_sub_obs_projects,
        source_path,
        source_project_id,
        source_rootprj,
        source_env_vars,
    )
    quiesce_scope = freeze_scope + sorted(freeze_packages_map)

    # --- record check (spec §2, step 2) ---
    if not args.force:
        synced = args.synced_commit or last_synced_head_sha(
            repo_slug_from_url(
                shared_env_vars.get("PERCONA_OBS_PACKAGING_REPO")
                or _load_profile_env(args.branch_from).get("PERCONA_OBS_PACKAGING_REPO", "")
            )
        )
        changed = _changed_files_between(
            source_commit,
            synced,
            _scope_local_paths(source_path, freeze_scope, freeze_packages_map, source_rootprj),
        )
        if changed:
            listing = "\n".join(f"  {f}" for f in changed[:50])
            raise SystemExit(
                f"error: staging changed since the cut ({source_commit[:12]} → "
                f"{synced[:12]}):\n{listing}\n"
                "Re-run 'percona-obs project release' on a rebased branch."
            )
        _print_same(f"source record {source_commit[:12]} matches synced main {synced[:12]}")

    if missing_mirrors:
        listing = "\n".join(f"  {source_project_id}:{n}" for n in sorted(missing_mirrors))
        raise SystemExit(
            f"error: staging subprojects have no release mirror:\n{listing}\n"
            "Re-run 'percona-obs project release' to regenerate the release tree."
        )

    if args.dry_run:
        failures: list[str] = []
        release_id = entry.tag.split("/")[-1]
        changelog_file = release_path / "CHANGELOG.md"
        if not changelog_file.is_file():
            failures.append("CHANGELOG.md is missing")
        elif f"## [{release_id}]" not in changelog_file.read_text("utf-8"):
            failures.append(f"CHANGELOG.md has no '## [{release_id}]' section")
        r = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{entry.tag}"],
            capture_output=True,
            cwd=_REPO_DIR,
        )
        if r.returncode == 0:
            failures.append(f"tag {entry.tag} already exists")
        if not _obs_project_exists(apiurl, source_obs_project):
            failures.append(f"source project {source_obs_project} not found on OBS")
        else:
            failures.extend(
                f"not green: {p}"
                for p in assert_all_green(apiurl, quiesce_scope, packages=freeze_packages_map)
            )
        if failures:
            for f in failures:
                print(f"  ✗ {f}", file=sys.stderr)
            raise SystemExit("error: prerelease dry-run failed")
        _print_ok(f"prerelease dry-run passed for {entry.tag}  (dry run)")
        return

    # Top-level pre-release meta from the mirror, publish forced on (spec §1).
    apply_mirror_meta(
        apiurl,
        prerelease_obs_project,
        release_path,
        args.rootprj,
        shared_env_vars,
        publish_override=True,
    )

    snapshots: dict[str, str] = {}
    pkg_snapshots: dict[tuple[str, str], str] = {}
    if not args.no_freeze:
        _print_pending(f"draining scheduler for {len(quiesce_scope)} project(s)")
        wait_for_quiesce(
            apiurl, quiesce_scope, timeout_s=args.freeze_timeout, packages=freeze_packages_map
        )
        problems = assert_all_green(apiurl, quiesce_scope, packages=freeze_packages_map)
        if problems:
            listing = "\n".join(f"  {p}" for p in problems[:50])
            raise SystemExit(f"error: source projects are not fully green:\n{listing}")
        snapshots = freeze_builds(apiurl, freeze_scope)
        try:
            pkg_snapshots = freeze_packages(apiurl, freeze_packages_map)
        except Exception:
            restore_builds(apiurl, snapshots)
            raise
    try:
        release_tree(
            apiurl,
            source_obs_project,
            prerelease_obs_project,
            subproject_pairs,
            args.rootprj,
            shared_env_vars,
            publish_override=True,
            verify_timeout=args.verify_timeout,
        )
    finally:
        if pkg_snapshots:
            restore_packages(apiurl, pkg_snapshots)
        if snapshots:
            restore_builds(apiurl, snapshots)

    set_project_description_marker(
        apiurl, prerelease_obs_project, "source_commit", source_commit
    )
    for name, _ in subproject_pairs:
        set_project_description_marker(
            apiurl, f"{prerelease_obs_project}:{name}", "source_commit", source_commit
        )
    _print_ok(f"prerelease  {source_obs_project} → {prerelease_obs_project} ({entry.tag})")
```

`_load_profile_env` is already imported in cmd_sync from `.cmd_profile` (check the import block at line 18; add it if absent). If the test's `_Args` has no `PERCONA_OBS_PACKAGING_REPO`, the `--synced-commit` path short-circuits before `gh`, so the lookup is never reached in tests.

Note: `_freeze_and_run` is a closure inside `cmd_sync_release`; the freeze block above duplicates its ~20 lines. Extract it instead: move `_freeze_and_run`'s body to a module-level

```python
def _run_frozen(apiurl, quiesce_scope, freeze_scope, freeze_packages_map, args, action) -> None:
```

used by both commands (same body, `args.no_freeze` / `args.freeze_timeout` read from `args`), and have `cmd_sync_release` call it. Then the prerelease command's freeze block becomes `_run_frozen(apiurl, quiesce_scope, freeze_scope, freeze_packages_map, args, lambda: release_tree(...))`. The tests in `tests/test_sync_release.py` patch `cmd_sync.wait_for_quiesce` etc., which still works at module level.

- [ ] **Step 4: Wire the CLI**

In `percona_obs/cli.py`, after `sync_release_parser.set_defaults(...)`:

```python
    sync_prerelease_parser = sync_subparsers.add_parser(
        "prerelease",
        help="Hop 1 of a release: copy a staging tree into this PR's pre-release project.",
    )
    sync_prerelease_parser.add_argument(
        "project", help="Release project identifier (e.g. ppg:releases:18)."
    )
    sync_prerelease_parser.add_argument(
        "--branch-from",
        required=True,
        metavar="PROFILE",
        dest="branch_from",
        help="Profile of the production instance holding the staging source.",
    )
    sync_prerelease_parser.add_argument(
        "--synced-commit",
        metavar="SHA",
        default=None,
        dest="synced_commit",
        help="Head SHA of the last successful sync-main run (default: looked up with gh).",
    )
    sync_prerelease_parser.add_argument(
        "--source-commit",
        metavar="SHA",
        default=None,
        dest="source_commit",
        help="Override the source_commit recorded in release.yaml.",
    )
    sync_prerelease_parser.add_argument(
        "--force", action="store_true", default=False,
        help="Skip the source_commit record check.",
    )
    sync_prerelease_parser.add_argument(
        "--no-freeze", action="store_true", default=False,
        help="Skip the drain/green-check/build-freeze sequence around osc release.",
    )
    sync_prerelease_parser.add_argument(
        "--freeze-timeout", type=int, default=3600, dest="freeze_timeout",
        help="Seconds to wait for the source scheduler to drain (default: 3600).",
    )
    sync_prerelease_parser.add_argument(
        "--verify-timeout", type=int, default=600, dest="verify_timeout",
        help="Seconds to wait for copied packages to land (default: 600; 0 disables).",
    )
    sync_prerelease_parser.add_argument(
        "--dry-run", action="store_true", default=False, dest="dry_run",
        help="Run the record check, mirror/changelog/tag checks and the green check only.",
    )
    sync_prerelease_parser.set_defaults(func=cmd_sync_prerelease)
```

and add `cmd_sync_prerelease` to the `from .cmd_sync import (...)` list.

- [ ] **Step 5: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS. Also `venv/bin/python -m percona_obs sync prerelease --help` prints the new flags.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/cmd_sync.py percona_obs/cli.py tests/test_sync_prerelease.py
git commit -s -m "sync prerelease: hop 1, staging to the PR pre-release project"
```

---

### Task 6: `sync release --from <pre-release>` (hop 2)

**Goal:** With `--from`, `sync release` skips the freeze and the git divergence check, verifies the pre-release's `source_commit` marker against the tagged `release.yaml`, applies the mirror meta to the release tree and copies from the pre-release.

**Files:**
- Modify: `percona_obs/cmd_sync.py` (`cmd_sync_release`)
- Modify: `percona_obs/cli.py` (`--from` on `sync release`)
- Test: `tests/test_sync_release.py`

**Acceptance Criteria:**
- [ ] `--from X`: no `wait_for_quiesce`/`freeze_builds` call, no git diff, `release_tree(apiurl, "X", <release project>, ...)` called once, meta applied from mirrors for a new release project too (not `_create_release_project`)
- [ ] Marker mismatch → `SystemExit("source_commit mismatch")` before any meta write; `--force` skips the check
- [ ] Without `--from` behaviour is Task 3's

**Verify:** `venv/bin/pytest -q tests/test_sync_release.py -k from_prerelease` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_sync_release.py`)

```python
def _args_from(rel, **kw):
    a = _Args(project="ppg:releases:17", rootprj="home:Admin")
    a.from_project = "home:Admin:PR:pr-5:ppg:releases:17"
    a.__dict__.update(kw)
    return a


def _mapping_release_yaml(rel, sha="b" * 40):
    (rel / "release.yaml").write_text(
        f"project: ppg:staging:17\nreleases:\n  - tag: ppg/17.11-1\n    source_commit: {sha}\n"
    )


def test_from_prerelease_skips_freeze_and_copies_from_it(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text("build: false\n" + _REPO_YAML.format(name="ssl3"))
    _mapping_release_yaml(rel)
    _wire_release_update_path(monkeypatch, src, rel)
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: False)
    monkeypatch.setattr(cmd_sync, "read_project_description_marker", lambda a, p, k: "b" * 40)
    fail = lambda *a, **k: pytest.fail("freeze must be skipped with --from")
    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", fail)
    monkeypatch.setattr(cmd_sync, "freeze_builds", fail)
    monkeypatch.setattr(cmd_sync, "_create_release_project", fail)
    metas, copies = [], []
    monkeypatch.setattr(cmd_sync, "apply_mirror_meta", lambda a, prj, *r, **k: metas.append(prj))
    monkeypatch.setattr(cmd_sync, "release_tree", lambda a, s, t, *r, **k: copies.append((s, t)))
    cmd_sync.cmd_sync_release(_args_from(rel))
    assert metas == ["home:Admin:ppg:releases:17"]
    assert copies == [("home:Admin:PR:pr-5:ppg:releases:17", "home:Admin:ppg:releases:17")]


def test_from_prerelease_marker_mismatch(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text("build: false\n" + _REPO_YAML.format(name="ssl3"))
    _mapping_release_yaml(rel)
    _wire_release_update_path(monkeypatch, src, rel)
    monkeypatch.setattr(cmd_sync, "read_project_description_marker", lambda a, p, k: "c" * 40)
    monkeypatch.setattr(cmd_sync, "apply_mirror_meta", lambda *a, **k: pytest.fail("no meta on mismatch"))
    with pytest.raises(SystemExit, match="source_commit mismatch"):
        cmd_sync.cmd_sync_release(_args_from(rel))
```

Also add `self.from_project = None` to `_Args.__init__`.

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_sync_release.py -k from_prerelease`
Expected: FAIL (freeze called / no mismatch error).

- [ ] **Step 3: Implement**

Import `read_project_description_marker` from `.obs_api` and `current_release` from `.release_record` in cmd_sync. In `cmd_sync_release`, right after `project_exists = _obs_project_exists(...)` (Task 3's layout), insert the `--from` branch before the legacy path:

```python
    from_project: "str | None" = getattr(args, "from_project", None)
    if from_project:
        # Hop 2 (spec §2): no staging involvement, no freeze, no git check.
        entry = current_release(release_data)
        if entry is None:
            raise SystemExit("error: release.yaml has no releases: entries")
        if not args.force:
            marker = read_project_description_marker(apiurl, from_project, "source_commit")
            if marker != entry.source_commit:
                raise SystemExit(
                    f"error: source_commit mismatch: {from_project} was populated from "
                    f"{marker or '<none>'} but release.yaml {entry.tag} records "
                    f"{entry.source_commit or '<none>'}; repopulate the pre-release "
                    "or cut a new release"
                )
        apply_mirror_meta(
            apiurl, release_obs_project, release_path, args.rootprj, shared_env_vars
        )
        release_tree(
            apiurl,
            from_project,
            release_obs_project,
            subproject_pairs,
            args.rootprj,
            shared_env_vars,
            verify_timeout=args.verify_timeout,
        )
        _print_ok(f"release  {from_project} → {release_obs_project} ({entry.tag})")
        return
```

The `--dry-run` block earlier in the function stays as is for both modes (its green check reads staging, which is still a sensible pre-merge signal; with `--from` it is informational).

- [ ] **Step 4: CLI flag**

In `cli.py`, on `sync_release_parser`:

```python
    sync_release_parser.add_argument(
        "--from",
        metavar="OBS_PROJECT",
        default=None,
        dest="from_project",
        help="Hop 2: copy from this pre-release OBS project (full name, e.g. "
        "isv:percona:PR:pr-12:ppg:releases:18) instead of from staging; "
        "no freeze, no git divergence check.",
    )
```

- [ ] **Step 5: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/cmd_sync.py percona_obs/cli.py tests/test_sync_release.py
git commit -s -m "sync release --from: hop 2, pre-release to the release project"
```

---

### Task 7: `project release` carries rendered `qa:` blocks into the mirrors

**Goal:** Every mirror `project.yaml` (top and subprojects) gets the staging project's `qa:` block with `%!{…}` macros rendered and `<product>:staging:<major>` references rewritten to the release project, leaving `${…}` env tokens intact.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`_write_release_tree`, new `_rewrite_qa_project_refs`, `cmd_project_release` top-level `project_data`)
- Test: `tests/test_project_release.py`

**Acceptance Criteria:**
- [ ] A staging subproject with `qa: [{pipeline: p, parameters: {OBS_PROJECT: "${OBS_ROOTPRJ}:ppg:staging:17:containers", VERSION: "ppg-%!{PG_VERSION}"}}]` and a `macros.yaml` defining `PG_VERSION: 17.11` yields a mirror `qa:` with `OBS_PROJECT: "${OBS_ROOTPRJ}:ppg:releases:17:containers"` and `VERSION: ppg-17.11`
- [ ] A staging project without `qa:` yields a mirror without `qa:`
- [ ] The top-level mirror gets the top-level staging `qa:` the same way

**Verify:** `venv/bin/pytest -q tests/test_project_release.py -k qa` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project_release.py`)

```python
def test_rewrite_qa_project_refs_recurses_and_keeps_env_tokens():
    from percona_obs.cmd_project import _rewrite_qa_project_refs

    qa = [
        {
            "pipeline": "p",
            "parameters": {
                "OBS_PROJECT": "${OBS_ROOTPRJ}:ppg:staging:17:containers",
                "PLATFORMS": ["ppg:staging:17", "other"],
            },
        }
    ]
    out = _rewrite_qa_project_refs(qa, "ppg:staging:17", "ppg:releases:17")
    assert out[0]["parameters"]["OBS_PROJECT"] == "${OBS_ROOTPRJ}:ppg:releases:17:containers"
    assert out[0]["parameters"]["PLATFORMS"] == ["ppg:releases:17", "other"]
    assert qa[0]["parameters"]["PLATFORMS"][0] == "ppg:staging:17"  # input untouched


def test_write_release_tree_carries_rendered_qa_blocks(tmp_path, monkeypatch):
    import percona_obs.common as common

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    (tmp_path / "root/macros.yaml").write_text("- PG_VERSION: 17.11\n")
    (src / "containers" / "project.yaml").write_text(
        (src / "containers" / "project.yaml").read_text()
        + "qa:\n  - pipeline: p\n    parameters:\n"
        "      OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:staging:17:containers\n"
        "      VERSION: ppg-%!{PG_VERSION}\n"
    )
    rel = tmp_path / "root/ppg/releases/17"
    _write_release_tree(
        rel, {"build": False, "repositories": []}, src, "ppg:staging:17", "ppg:releases:17", "ppg", "17"
    )
    containers = yaml.safe_load((rel / "containers" / "project.yaml").read_text())
    assert containers["qa"][0]["parameters"] == {
        "OBS_PROJECT": "${OBS_ROOTPRJ}:ppg:releases:17:containers",
        "VERSION": "ppg-17.11",
    }
    tarballs = yaml.safe_load((rel / "tarballs" / "project.yaml").read_text())
    assert "qa" not in tarballs
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_project_release.py -k qa`
Expected: FAIL (`ImportError: _rewrite_qa_project_refs`).

- [ ] **Step 3: Implement**

Add above `_write_release_tree`:

```python
def _rewrite_qa_project_refs(value, source_project_id: str, release_project_id: str):
    """Deep-copy a loaded ``qa:`` value replacing ``<source>``/``<source>:…``
    project references inside strings with the release project.  Macros are
    already rendered by the loader; ``${VAR}`` tokens are left as they are."""
    if isinstance(value, str):
        if value == source_project_id:
            return release_project_id
        return re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(source_project_id)}(?=:|$|[^A-Za-z0-9_:])",
            release_project_id,
            value,
        )
    if isinstance(value, list):
        return [_rewrite_qa_project_refs(v, source_project_id, release_project_id) for v in value]
    if isinstance(value, dict):
        return {
            k: _rewrite_qa_project_refs(v, source_project_id, release_project_id)
            for k, v in value.items()
        }
    return value
```

In `_write_release_tree`, after the `for key in ("debuginfo", "publish", "project-config")` loop add:

```python
        if source_sub_config.get("qa") is not None:
            sub_data["qa"] = _rewrite_qa_project_refs(
                source_sub_config["qa"], source_project_id, release_project
            )
```

(`_load_project_config_with_inheritance(sub_path, repo_filter=...)` is called without env vars, so `%!{…}` is rendered and `${…}` survives — that is the behaviour the test pins.)

In `cmd_project_release`, right after `project_data` is built, add the top-level block, loading the top project *without* env vars so the `${OBS_ROOTPRJ}` token survives:

```python
    top_cfg_no_env = _load_project_config_with_inheritance(
        source_path, repo_filter=RepositoryFilter.EMPTY
    )
    if top_cfg_no_env.get("qa") is not None:
        project_data["qa"] = _rewrite_qa_project_refs(
            top_cfg_no_env["qa"], args.project, release_project
        )
```

`RepositoryFilter` is already imported in cmd_project (it is used at line 2329); confirm with `grep -n "RepositoryFilter" percona_obs/cmd_project.py`.

- [ ] **Step 4: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS. Also run `venv/bin/python -m percona_obs project verify --offline` from the worktree to confirm a `qa:` key in a release mirror is not rejected (release trees are skipped by the QA validators).

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_project.py tests/test_project_release.py
git commit -s -m "project release: carry rendered qa: blocks into the release mirrors"
```

---

### Task 8: `project release` — `source_commit` and open-release refresh

**Goal:** `project release` records `source_commit` (last synced `main` via `gh`, or `--source-commit`) in a mapping entry, refuses a SHA that is not an ancestor of HEAD, and when the last entry's tag has no git tag yet it refreshes that release in place (same id, CHANGELOG section replaced, mirrors regenerated, `source_commit` updated).

**Files:**
- Modify: `percona_obs/cmd_project.py` (`cmd_project_release`, new helpers `_resolve_source_commit`, `_tag_exists_locally`, `_replace_changelog_section`)
- Modify: `percona_obs/cli.py` (`--source-commit` on `project release`)
- Test: `tests/test_project_release.py`

**Acceptance Criteria:**
- [ ] `_replace_changelog_section(text, "18.6-1", new)` replaces exactly the `## [18.6-1]` section and keeps the others; when absent it prepends like the update path does today
- [ ] `_resolve_source_commit` returns the override when given, else the `gh` lookup; raises when the SHA is not an ancestor of HEAD
- [ ] With last entry `ppg/18.6-1` and no local tag, the derived id is `18.6-1` (refresh) and `release.yaml` ends with `{tag: ppg/18.6-1, source_commit: <sha>}` as the only `18.6-1` entry
- [ ] With the local tag present, a new id is derived and appended as a mapping entry; older entries keep their original form

**Verify:** `venv/bin/pytest -q tests/test_project_release.py -k "refresh or source_commit or changelog_section"` → PASS

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project_release.py`)

```python
def test_replace_changelog_section():
    from percona_obs.cmd_project import _replace_changelog_section

    text = "# Changelog\n\n## [18.6-1] - 2026-01-01\n\n### Added\n- a\n\n## [18.4-1] - 2025-12-01\n\n### Added\n- b\n"
    out = _replace_changelog_section(text, "18.6-1", "## [18.6-1] - 2026-02-02\n\n### Added\n- c\n")
    assert "- a" not in out and "- c" in out and "- b" in out
    assert out.index("[18.6-1]") < out.index("[18.4-1]")
    # absent → prepended above the first section
    out2 = _replace_changelog_section(text, "18.7-1", "## [18.7-1] - x\n")
    assert out2.index("[18.7-1]") < out2.index("[18.6-1]")


def test_resolve_source_commit_override_and_ancestor(monkeypatch):
    from percona_obs import cmd_project as cp

    monkeypatch.setattr(cp, "_is_ancestor_of_head", lambda sha: sha == "good")
    assert cp._resolve_source_commit("good", "https://github.com/o/r.git") == "good"
    with pytest.raises(SystemExit, match="not an ancestor of HEAD"):
        cp._resolve_source_commit("bad", "https://github.com/o/r.git")
    monkeypatch.setattr(cp, "last_synced_head_sha", lambda slug: "good")
    assert cp._resolve_source_commit(None, "https://github.com/o/r.git") == "good"
    with pytest.raises(SystemExit, match="PERCONA_OBS_PACKAGING_REPO"):
        cp._resolve_source_commit(None, "")


def test_open_release_is_refreshed_in_place(monkeypatch):
    from percona_obs import cmd_project as cp
    from percona_obs.release_record import ReleaseEntry

    monkeypatch.setattr(cp, "_tag_exists_locally", lambda tag: False)
    entries = [ReleaseEntry("ppg/18.4-1"), ReleaseEntry("ppg/18.6-1", "old")]
    rid, new_entries, prev = cp._plan_release_entries(entries, None, lambda: "18.6-2", "ppg", "newsha")
    assert rid == "18.6-1"
    assert new_entries == [ReleaseEntry("ppg/18.4-1"), ReleaseEntry("ppg/18.6-1", "newsha")]
    assert prev == "18.4-1"


def test_shipped_release_appends_next_id(monkeypatch):
    from percona_obs import cmd_project as cp
    from percona_obs.release_record import ReleaseEntry

    monkeypatch.setattr(cp, "_tag_exists_locally", lambda tag: True)
    entries = [ReleaseEntry("ppg/18.6-1", "old")]
    rid, new_entries, prev = cp._plan_release_entries(entries, None, lambda: "18.6-2", "ppg", "newsha")
    assert rid == "18.6-2"
    assert new_entries == [ReleaseEntry("ppg/18.6-1", "old"), ReleaseEntry("ppg/18.6-2", "newsha")]
    assert prev == "18.6-1"


def test_explicit_release_id_wins_over_refresh(monkeypatch):
    from percona_obs import cmd_project as cp
    from percona_obs.release_record import ReleaseEntry

    monkeypatch.setattr(cp, "_tag_exists_locally", lambda tag: False)
    entries = [ReleaseEntry("ppg/18.6-1")]
    with pytest.raises(SystemExit, match="already present"):
        cp._plan_release_entries(entries, "18.6-1", lambda: "x", "ppg", "s")
    rid, new_entries, _ = cp._plan_release_entries(entries, "18.6-9", lambda: "x", "ppg", "s")
    assert rid == "18.6-9" and new_entries[-1] == ReleaseEntry("ppg/18.6-9", "s")
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_project_release.py -k "refresh or source_commit or changelog_section or appends_next or explicit_release_id"`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implement the helpers** (place above `cmd_project_release`)

```python
def _tag_exists_locally(tag: str) -> bool:
    r = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
        capture_output=True,
        cwd=_REPO_DIR,
    )
    return r.returncode == 0


def _is_ancestor_of_head(sha: str) -> bool:
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
        capture_output=True,
        cwd=_REPO_DIR,
    )
    return r.returncode == 0


def _resolve_source_commit(override: "str | None", repo_url: str) -> str:
    """The commit of main whose staging tree the release is cut from.

    Default: head SHA of the last sync-main run with successful sync jobs
    (``gh api``), so the record names what OBS actually holds.  Must be an
    ancestor of HEAD so the release branch contains the tree it claims.
    """
    if override:
        sha = override
    else:
        if not repo_url:
            raise SystemExit(
                "error: PERCONA_OBS_PACKAGING_REPO is not set in the profile; "
                "set it or pass --source-commit"
            )
        sha = last_synced_head_sha(repo_slug_from_url(repo_url))
    if not _is_ancestor_of_head(sha):
        raise SystemExit(
            f"error: source commit {sha} is not an ancestor of HEAD; "
            "rebase the release branch on main (and fetch) first"
        )
    return sha


def _plan_release_entries(
    existing: "list[ReleaseEntry]",
    explicit_id: "str | None",
    derive_id: "Callable[[], str]",
    product: str,
    source_commit: str,
) -> "tuple[str, list[ReleaseEntry], str | None]":
    """Decide the release id and the new ``releases:`` list.

    Returns (release_id, entries, prev_release_id).  The last entry whose
    tag is not yet a git tag is *open*: without ``--release-id`` it is
    refreshed in place (same id, new source_commit) and prev_release_id is
    the entry before it.  Otherwise the next id is derived and appended.
    """
    open_entry = existing[-1] if existing and not _tag_exists_locally(existing[-1].tag) else None
    if explicit_id:
        tag = f"{product}/{explicit_id}"
        if any(e.tag == tag for e in existing):
            raise SystemExit(f"error: release tag {tag} is already present in release.yaml")
        prev = existing[-1].tag.split("/")[-1] if existing else None
        return explicit_id, [*existing, ReleaseEntry(tag, source_commit)], prev
    if open_entry is not None:
        rid = open_entry.tag.split("/")[-1]
        print(
            f"note: {open_entry.tag} has no git tag locally — treating the release as "
            "still open and refreshing it in place (fetch tags if it already shipped)",
            flush=True,
        )
        prev = existing[-2].tag.split("/")[-1] if len(existing) > 1 else None
        return rid, [*existing[:-1], ReleaseEntry(open_entry.tag, source_commit)], prev
    rid = derive_id()
    tag = f"{product}/{rid}"
    if any(e.tag == tag for e in existing):
        raise SystemExit(f"error: release tag {tag} is already present in release.yaml")
    prev = existing[-1].tag.split("/")[-1] if existing else None
    return rid, [*existing, ReleaseEntry(tag, source_commit)], prev


def _replace_changelog_section(text: str, release_id: str, section: str) -> str:
    """Replace the ``## [release_id]`` section (up to the next ``## [``) or,
    when absent, prepend *section* above the first section."""
    pattern = re.compile(
        r"## \[" + re.escape(release_id) + r"\].*?(?=\n## \[|\Z)", re.DOTALL
    )
    if pattern.search(text):
        return pattern.sub(lambda _m: section.rstrip("\n") + "\n", text, count=1)
    m = re.search(r"\n(## \[)", text)
    if m:
        pos = m.start() + 1
        return text[:pos] + section.rstrip("\n") + "\n\n" + text[pos:]
    return text.rstrip() + "\n\n" + section.rstrip("\n") + "\n"
```

Add imports: `from .github_api import last_synced_head_sha, repo_slug_from_url` and `from .release_record import ReleaseEntry, dump_release_entry, parse_release_entries` (merge with Task 1's line).

- [ ] **Step 4: Rewrite the decision block in `cmd_project_release`**

Replace from `# Auto-derive release-id from OBS if not provided.` down to and including `if tag in existing_releases: raise SystemExit(...)` with:

```python
    release_env: dict[str, str] = {
        **(parse_env_overrides(args.env_overrides) if args.env_overrides else {}),
        **auto_rootprj_env(args.rootprj),
    }
    source_commit = _resolve_source_commit(
        getattr(args, "source_commit", None),
        release_env.get("PERCONA_OBS_PACKAGING_REPO", ""),
    )

    def _derive() -> str:
        pkg_archs = _fetch_all_pkg_archs(apiurl, source_obs_project)
        return _derive_release_id(
            pkg_archs,
            existing_releases,
            release_name,
            lambda repo, arch, pkg: _fetch_pkg_versrel(
                apiurl, source_obs_project, repo, arch, pkg
            ),
            counter_mode=not tree_has_server_package(source_path),
            major=major,
        )

    release_id, new_entries, prev_release_id = _plan_release_entries(
        existing_entries, args.release_id or None, _derive, product, source_commit
    )
    tag = f"{product}/{release_id}"
    is_refresh = bool(existing_entries) and existing_entries[-1].tag == tag
```

Then:
- delete the later duplicate `release_env` definition (it now lives above);
- replace `prev_release_id: str | None = None` and the `if not is_first_release and existing_releases: prev_release_id = existing_releases[-1].split("/")[-1]` assignment with just the `for rel_sub in ...` loop guarded by `if not is_first_release and prev_release_id:`;
- in the CVE scan, `prev_tag_for_scan = f"{product}/{prev_release_id}" if prev_release_id else None`;
- `release_data["releases"] = [dump_release_entry(e) for e in new_entries]`;
- in the update path, replace the manual "prepend changelog section" block (`m = re.search(r"\n(## \[)", ...)` … `new_content = ...`) with `new_content = _replace_changelog_section(existing_changelog, release_id, changelog_section)`;
- commit message: `f"Refresh release {release_project} ({release_id})"` when `is_refresh`, else as today; print `Refresh release:` in the preview when `is_refresh`.

Note `existing_releases` (tags list) is still what `_derive_release_id` counts; on a refresh the open tag is counted too but `_derive` is never called, so the count is irrelevant.

- [ ] **Step 5: CLI flag**

```python
    project_release_parser.add_argument(
        "--source-commit",
        metavar="SHA",
        default=None,
        dest="source_commit",
        help="Commit of main whose staging tree is released (default: head of the "
        "last sync-main run with successful sync jobs, via gh). Recorded in release.yaml.",
    )
```

- [ ] **Step 6: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add percona_obs/cmd_project.py percona_obs/cli.py tests/test_project_release.py
git commit -s -m "project release: record source_commit, refresh an open release in place"
```

---

### Task 9: Documentation and final verification

**Goal:** The tool reference, the architecture reference and the key-files tables describe the two commands, the `release.yaml` mapping form and the refresh rule; the whole suite and type-check pass on the final tree.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md` ("Releasing packages" chapter: Step 1, `release.yaml` format, "Running `sync release` manually", new "`sync prerelease`" section)
- Modify: `.github/copilot-instructions.md` (key files table; a short "Release hops" note next to the `sync release-pr` section; the obs-pr-cleanup one-liner mention)
- Modify: `CLAUDE.md` (key files table: `release_copy.py`, `release_record.py`, `github_api.py`)

**Acceptance Criteria:**
- [ ] `docs/PERCONA_OBS_TOOL.md` documents: `--source-commit`, the refresh rule ("last entry without a git tag is open"), the mapping entry form, `sync prerelease` flags (`--branch-from`, `--synced-commit`, `--source-commit`, `--force`, `--no-freeze`, `--freeze-timeout`, `--verify-timeout`, `--dry-run`), `sync release --from`, and that the workflow integration follows in rollout step 2
- [ ] Key-file tables list the three new modules
- [ ] `venv/bin/pytest -q`, `venv/bin/black --check percona_obs/`, `venv/bin/pyright` all pass

**Verify:** `venv/bin/pytest -q && venv/bin/black --check percona_obs/ && venv/bin/pyright && grep -c "sync prerelease" docs/PERCONA_OBS_TOOL.md` → green, count ≥ 3

**Steps:**

- [ ] **Step 1: `docs/PERCONA_OBS_TOOL.md`**

In "Step 1 — Create or update a release": add after item 1 (auto-derive) a new item:

```markdown
2. **Resolves the source commit** — the head SHA of the last `sync-main.yml` run on
   `main` whose sync jobs succeeded (`gh api`), or `--source-commit <sha>`. It must be
   an ancestor of HEAD. It is recorded in `release.yaml` so the release names the
   staging tree its binaries were built from.
3. **Open-release refresh** — if the last `releases:` entry has no git tag yet, the
   release is still in flight: the same id is kept, the mirror tree is regenerated, the
   `CHANGELOG.md` section for that id is replaced and `source_commit` is updated. Only
   when the tag exists is the next id derived and appended (`--release-id` always wins).
```

Renumber the following items. Replace the "`release.yaml` format" block with:

```yaml
repository: ${PERCONA_OBS_PACKAGING_REPO}
project: ppg:staging:17
releases:
  - ppg/17.9-1                       # historical entries stay plain tags
  - tag: ppg/17.10-1                 # written by project release
    source_commit: 9e9d9738c0ffee…   # full SHA of main the binaries were built from
```

and note that the last entry is the current release in either form.

Add a new section before "Running `sync release` manually":

```markdown
### `sync prerelease` — hop 1 (staging → PR pre-release)

Run with the PR profile; `--branch-from` names the production profile holding staging:

    ./percona-obs -P pr-12 sync prerelease ppg:releases:18 --branch-from main

Steps: (1) require a `source_commit` on the last `release.yaml` entry; (2) **record
check** — the freeze-scope paths (source tree, its `macros.yaml` chain, every
whole-frozen project, every aggregate-frozen package) must be identical between
`source_commit` and the last synced `main` (`--synced-commit`, else `gh api`), or it
fails with "staging changed since the cut"; (3) pre-release meta from the mirrors,
**publish forced on**; (4) drain, assert green, freeze, `osc release`, verify,
restore; (5) `source_commit: <sha>` appended to each pre-release project description.
`--dry-run` runs (1), (2), the mirror/changelog/tag checks and the green check only.
`--force` skips (2). The workflow that calls this on release PRs lands in rollout step 2.

### `sync release --from` — hop 2 (pre-release → release project)

    ./percona-obs -P main sync release ppg:releases:18 --from isv:percona:PR:pr-12:ppg:releases:18

No freeze, no git divergence check. The pre-release description's `source_commit`
must equal the tagged `release.yaml` entry's (`--force` skips); then the release
project meta is applied from the mirrors and binaries are copied with `osc release`.
```

In the flags table of "Running `sync release` manually" add the `--from` row. Add a one-line note at the top of the chapter: "Until rollout step 2 lands, CI still runs the single-hop `sync release` on merge; the two hops are available for manual and rehearsal use."

- [ ] **Step 2: `.github/copilot-instructions.md` and `CLAUDE.md`**

Add rows to both key-file tables:

```markdown
| `percona_obs/release_copy.py` | Shared release hop mechanics (mirror meta apply, `osc release` copy, verify, orphans) |
| `percona_obs/release_record.py` | `release.yaml` `releases:` entries (tag strings and `{tag, source_commit}`) |
| `percona_obs/github_api.py` | `gh api` lookups (last synced `main` commit) |
```

In copilot-instructions, after the `sync release-pr` section, add a 6-line "Release hops" paragraph pointing at the spec and summarising `sync prerelease` / `sync release --from`.

- [ ] **Step 3: Final verification**

Run: `venv/bin/pytest -q && venv/bin/black --check percona_obs/ && venv/bin/pyright`
Expected: all pass, `0 errors`. Then `git status` must be clean apart from `venv/`.

- [ ] **Step 4: Commit**

```bash
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md CLAUDE.md
git commit -s -m "docs: pre-release flow tool commands and release.yaml entry form"
```

---

## Self-review notes

- Spec coverage (tool PR scope): §2 `release.yaml` format → Task 1; `project release` three changes → Tasks 7, 8; `sync prerelease` → Task 5; `sync release --from` → Task 6; `release_copy.py` → Task 3; marker/publish primitives → Task 4; §6 unit tests → each task; §7 docs (tool reference) → Task 9. Workflow changes (§3), the one-in-flight guard and the rehearsal are the step-2 plan.
- Deviation flagged in Global Constraints: temporary `releasetarget` entries are kept alongside `--target-project`.
- Type consistency: `collect_release_subprojects`, `filter_release_repo_names`, `apply_mirror_meta`, `copy_project_binaries`, `release_tree`, `warn_orphans` (release_copy); `set_project_description_marker`, `read_project_description_marker`, `publish_override` (obs_api); `parse_release_entries`, `release_tags`, `current_release`, `dump_release_entry`, `ReleaseEntry` (release_record); `repo_slug_from_url`, `last_synced_head_sha`, `_gh_api_json` (github_api); `_scope_local_paths`, `_changed_files_between`, `_run_frozen`, `_check_source_unchanged_since_tag`, `cmd_sync_prerelease`, `args.from_project`, `args.synced_commit`, `args.source_commit` (cmd_sync); `_rewrite_qa_project_refs`, `_tag_exists_locally`, `_is_ancestor_of_head`, `_resolve_source_commit`, `_plan_release_entries`, `_replace_changelog_section` (cmd_project).
