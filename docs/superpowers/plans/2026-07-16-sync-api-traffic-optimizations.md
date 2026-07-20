# Sync-Main OBS API Traffic Optimizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the OBS API request volume of the sync-main workflow by ~90 % so runs stop tripping OBS traffic limiters.

**Architecture:** Six optimizations layered from the inside out: (1) a `--skip-unchanged` sync mode that reuses the existing clean-sync-SHA check against the target project, (2) a local sync-state manifest that makes the skip decision with zero API calls, (3) deduplication of the triple project meta/prjconf fetches, (4) a scoped, backoff-based poll loop, (5) a global client-side throttle with 429/503 retry wrapped around `osc.connection.http_request`, and (6) a workflow restructure that debounces queued pushes by letting the newest run's poll supersede older polls.

**Tech Stack:** Python 3 (`percona_obs` package, `osc` library), pytest, GitHub Actions YAML.

**User decisions (already made):**
- Implement all six optimizations from the study (user: "write a plan to implement all those optimizations").
- Work happens on the `main` branch of this repo (user: "implement each one in `main` branch" for the prior cache work; same repo conventions apply).
- Repo rules: `git commit -s`, no Claude attribution, run `venv/bin/black percona_obs/` + `venv/bin/pyright` after every change, never `git push` without asking.

**Baseline numbers (from the study, for regression comparison):** 40 projects / ~330 packages; a no-change sync makes ~950 requests (path-ref validation ~40, project checks 200, package meta 330, file md5 listings 330, orphan cleanup 41) and the poll loop makes ~60 req/min for 3–6 h.

---

## File Structure

| File | Change |
|---|---|
| `percona_obs/cmd_sync.py` | Extract `_clean_sync_check`; add skip decision, report-json, project-check dedup |
| `percona_obs/sync_state.py` | **New** — sync-state manifest load/save/check |
| `percona_obs/http_throttle.py` | **New** — global request pacing + retry |
| `percona_obs/git_utils.py` | Add `_head_short_sha()` |
| `percona_obs/common.py` | Add `next_poll_interval()` (shared with poll script) |
| `percona_obs/cli.py` | `--skip-unchanged`, `--report-json` flags; install throttle |
| `.github/scripts/poll_obs_builds.py` | Scoped monitoring, backoff, final full sweep |
| `.github/workflows/sync-main.yml` | Split sync/poll jobs, job-level concurrency, wire new flags |
| `tests/test_skip_unchanged.py` | **New** — Tasks 1–2 tests |
| `tests/test_sync_state.py` | **New** — Task 3 tests |
| `tests/test_project_prepass.py` | **New** — Task 4 tests |
| `tests/test_http_throttle.py` | **New** — Task 5 tests |
| `tests/test_poll_interval.py` | **New** — Task 6 tests |
| `docs/PERCONA_OBS_TOOL.md` | Document new flags and env vars |

Every task ends with: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest tests/ -q` → all pass, then `git commit -s`.

---

### Task 1: Extract `_clean_sync_check` helper from `_resolve_branch_decision`

**Goal:** Factor the "is the package on OBS synced from a clean git SHA with no local changes since" check into a reusable helper, so the new skip mode (Task 2) and the existing branch decision share one implementation.

**Files:**
- Modify: `percona_obs/cmd_sync.py:544-637` (`_resolve_branch_decision`)
- Test: `tests/test_skip_unchanged.py` (new)

**Acceptance Criteria:**
- [ ] `_clean_sync_check(apiurl, obs_project, package_name, package_path) -> str | None` exists in `cmd_sync.py`: returns `None` when clean, else a human-readable reason string.
- [ ] `_resolve_branch_decision` delegates to it and behaves identically (all existing tests in `tests/test_branch_decision_meta.py` pass unmodified).
- [ ] New unit tests cover: no comment, non-sync comment, dirty-sync comment, git changes since SHA, dirty working tree, inherited macros changed, and the clean case.

**Verify:** `venv/bin/python -m pytest tests/test_skip_unchanged.py tests/test_branch_decision_meta.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `tests/test_skip_unchanged.py`:

```python
"""Unit tests for _clean_sync_check and the --skip-unchanged decision
(percona_obs.cmd_sync).

_clean_sync_check is the shared fast path: it trusts the 'sync: <branch>@<sha>'
OBS revision comment and local git state, returning None (clean) or a reason
string.  _resolve_skip_decision maps that onto the plain-push skip decision.
"""

from pathlib import Path

import percona_obs.cmd_sync as cmd_sync
from percona_obs.cmd_sync import _clean_sync_check, _resolve_skip_decision

PKG = Path("/repo/root/ppg/17/percona-pgaudit")


def _patch_git_clean(monkeypatch):
    monkeypatch.setattr(cmd_sync, "_has_package_changes_since", lambda *a: False)
    monkeypatch.setattr(cmd_sync, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(cmd_sync, "_macros_changed_since", lambda *a: False)


def test_clean_when_sync_comment_and_no_changes(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is None


def test_reason_when_no_comment(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: None
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_comment_not_sync_format(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: "manual edit"
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_synced_dirty(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (local changes on somehost)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_git_changes_since_sha(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_has_package_changes_since", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_working_tree_dirty(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_is_path_dirty", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_inherited_macros_changed(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_macros_changed_since", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None
```

(`_resolve_skip_decision` is imported now but added in Task 2 — comment that import out until Task 2, or add it in Task 2's step. Keep the import commented in Task 1 and enable it in Task 2.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_skip_unchanged.py -q`
Expected: FAIL with `ImportError: cannot import name '_clean_sync_check'`

- [ ] **Step 3: Implement `_clean_sync_check` and refactor `_resolve_branch_decision`**

In `percona_obs/cmd_sync.py`, insert immediately above `_resolve_branch_decision` (line 544):

```python
def _clean_sync_check(
    apiurl: str,
    obs_project: str,
    package_name: str,
    package_path: Path,
) -> str | None:
    """Return None when the OBS package matches the local git state, else a reason.

    Fast path shared by --branch-from (aggregate decision) and --skip-unchanged
    (skip decision): trusts the 'sync: <branch>@<sha> (...)' revision comment
    recorded by _generate_sync_message, then checks locally (no further API
    calls) that nothing feeding the package's uploaded content changed since
    that SHA: package directory commits, uncommitted edits, and inherited
    ancestor macros.yaml values.
    """
    comment = _fetch_obs_package_meaningful_comment(apiurl, obs_project, package_name)
    if not comment:
        return "no revision comment"
    m = _SYNC_MSG_RE.match(comment)
    if not m:
        return f"comment is not a sync message: {comment!r}"
    short_sha = m.group(1)
    details = m.group(2)
    if details.startswith("local changes on"):
        return f"synced dirty at {short_sha}"
    if _has_package_changes_since(short_sha, package_path):
        return f"git changes since {short_sha}"
    if _is_path_dirty(package_path):
        return "uncommitted changes in package directory"
    if _macros_changed_since(short_sha, package_path):
        return "inherited macros changed"
    return None
```

Then replace the body of `_resolve_branch_decision` from `label = f"{branch_project}/{package_name}"` (line 603) to the end (line 636) with:

```python
    label = f"{branch_project}/{package_name}"
    reason = _clean_sync_check(apiurl, branch_project, package_name, package_path)
    if reason is None:
        logger.debug(f"branch decision: aggregate  {label}  (clean sync state)")
        return True
    return _content_check(reason)
```

Keep the `_content_check` inner function and its docstring exactly as they are. Delete the now-unused direct references to `_SYNC_MSG_RE` matching inside `_resolve_branch_decision` (they moved into the helper). The explanatory comment block about uncommitted edits / inherited macros moves into `_clean_sync_check`'s docstring (shown above) — do not duplicate it.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python -m pytest tests/test_skip_unchanged.py tests/test_branch_decision_meta.py -q`
Expected: PASS (all)

Note: `tests/test_branch_decision_meta.py` monkeypatches `cmd_sync._fetch_obs_package_meaningful_comment`, `cmd_sync._has_package_changes_since`, etc. — those module attributes are still what `_clean_sync_check` calls, so the existing tests keep working without modification.

- [ ] **Step 5: Format, type-check, commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest tests/ -q
git add percona_obs/cmd_sync.py tests/test_skip_unchanged.py
git commit -s -m "sync: extract _clean_sync_check from _resolve_branch_decision"
```

---

### Task 2: `--skip-unchanged` mode for plain pushes

**Goal:** On plain (non-`--branch-from`) syncs, decide "skip" for packages whose OBS revision comment records a clean sync SHA with no local changes since — skipping package-meta fetch, service runs, and the file-md5 listing (2+ requests and all service work per unchanged package → 1 request).

**Files:**
- Modify: `percona_obs/cli.py:180` (add flag after `--only-repos`)
- Modify: `percona_obs/cmd_sync.py` (`_decide_package` else-branch ~line 929; Phase 3 loop ~line 1430; arg validation ~line 710)
- Test: `tests/test_skip_unchanged.py`

**Acceptance Criteria:**
- [ ] `sync push --skip-unchanged` exists; combining it with `--branch-from` exits with an error.
- [ ] `_resolve_skip_decision(apiurl, obs_project, package_name, package_path) -> bool` returns True only when `_clean_sync_check` returns None.
- [ ] Phase 1 returns decision `"skip"` for clean packages when the flag is set (plain push only); `--force` disables skipping.
- [ ] Phase 3 for `"skip"`: registers the package in `local_packages_by_project` (orphan-cleanup protection) and continues before `_apply_package_config` and service runs.
- [ ] Dep-cascade (Phase 2) does not run for skip decisions (OBS rebuilds reverse deps server-side on main).

**Verify:** `venv/bin/python -m pytest tests/test_skip_unchanged.py -q` → PASS; `venv/bin/python -m percona_obs -P dev sync push --dry-run --skip-unchanged ppg:17.9 percona-pgaudit` prints a `skip` or normal promote line without traceback.

**Steps:**

- [ ] **Step 1: Enable the `_resolve_skip_decision` import in `tests/test_skip_unchanged.py` and add failing tests**

```python
def test_skip_decision_true_when_clean(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _resolve_skip_decision("http://obs", "prj", "pkg", PKG) is True


def test_skip_decision_false_when_unclean(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: None
    )
    assert _resolve_skip_decision("http://obs", "prj", "pkg", PKG) is False
```

Run: `venv/bin/python -m pytest tests/test_skip_unchanged.py -q` → FAIL (ImportError).

- [ ] **Step 2: Add the CLI flag**

In `percona_obs/cli.py` after the `--only-repos` argument (line 180-…):

```python
    sync_push_parser.add_argument(
        "--skip-unchanged",
        action="store_true",
        default=False,
        dest="skip_unchanged",
        help="Skip packages whose OBS revision comment records a sync from a git "
        "SHA with no local changes since (plain pushes only; cannot be combined "
        "with --branch-from). Skipped packages make one API call (or zero with "
        "a warm sync-state manifest) instead of running services and uploads.",
    )
```

- [ ] **Step 3: Implement `_resolve_skip_decision` and wire the decision**

In `percona_obs/cmd_sync.py`, below `_clean_sync_check`:

```python
def _resolve_skip_decision(
    apiurl: str, obs_project: str, package_name: str, package_path: Path
) -> bool:
    """Return True if the package can be skipped entirely on a plain push.

    Unlike the --branch-from aggregate decision there is no content-check
    fallback: any doubt (no comment, dirty sync, changes since the SHA) simply
    routes the package through the normal promote path, whose MD5 comparison
    makes an unchanged upload a no-op anyway.
    """
    reason = _clean_sync_check(apiurl, obs_project, package_name, package_path)
    if reason is not None:
        logger.debug(
            f"skip decision: promote  {obs_project}/{package_name}  ({reason})"
        )
        return False
    logger.debug(f"skip decision: skip  {obs_project}/{package_name}")
    return True
```

Arg validation in `cmd_sync` (next to the `--no-dep-cascade` check at line 774):

```python
    if getattr(args, "skip_unchanged", False) and args.branch_from:
        print(
            "error: --skip-unchanged cannot be combined with --branch-from",
            file=sys.stderr,
        )
        sys.exit(1)
```

In `_decide_package`, replace the final `else:` branch (lines 929-933):

```python
        else:
            # Without --branch-from: --skip-unchanged trusts the recorded sync
            # SHA and skips clean packages outright (no meta fetch, no services,
            # no md5 listing).  Otherwise always promote — the upload function
            # compares file MD5s against OBS and only uploads what changed,
            # so unchanged packages are effectively skipped at upload time.
            if (
                getattr(args, "skip_unchanged", False)
                and not args.force
                and _resolve_skip_decision(
                    apiurl, obs_project_name, package_path.name, package_path
                )
            ):
                return key, "skip", None, None
            return key, "promote", None, None
```

In the Phase 3 loop, immediately after `decision = decisions.get(key, "promote")` (line 1431):

```python
        if decision == "skip":
            # Register for orphan cleanup — a skipped package still exists
            # locally and must not be deleted from OBS.
            local_packages_by_project.setdefault(obs_project_name, set()).add(
                package_path.name
            )
            _print_same(f"skip  {obs_project_name}/{package_path.name}  (unchanged)")
            continue
```

(`_print_same` is already imported in cmd_sync.)

- [ ] **Step 4: Run tests, then a live dry-run**

```bash
venv/bin/python -m pytest tests/test_skip_unchanged.py -q
venv/bin/python -m percona_obs -P dev sync push --dry-run --skip-unchanged ppg:17.9 percona-pgaudit
```

Expected: tests PASS; the dry-run prints either `= skip ppg:17.9/percona-pgaudit (unchanged)` or the normal promote flow, with no traceback.

- [ ] **Step 5: Format, type-check, commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest tests/ -q
git add percona_obs/cli.py percona_obs/cmd_sync.py tests/test_skip_unchanged.py
git commit -s -m "sync: add --skip-unchanged fast path for plain pushes"
```

---

### Task 3: Sync-state manifest for zero-request skips

**Goal:** Persist a per-(apiurl, rootprj) manifest mapping `project/package` → last-synced short SHA under `.cache/sync_state/`, so the skip decision needs zero API calls when the manifest is warm (CI persists `.cache/` via actions/cache).

**Files:**
- Create: `percona_obs/sync_state.py`
- Modify: `percona_obs/git_utils.py` (add `_head_short_sha`)
- Modify: `percona_obs/cmd_sync.py` (manifest check in `_decide_package`; record after upload/skip; save at end)
- Test: `tests/test_sync_state.py`

**Acceptance Criteria:**
- [ ] `load_manifest` / `save_manifest` round-trip; corrupt or missing files load as `{}`; save is atomic (tmp + rename).
- [ ] `manifest_entry_clean(manifest, key, package_path) -> bool` returns True only when the stored SHA exists and `_has_package_changes_since` / `_is_path_dirty` / `_macros_changed_since` are all clean.
- [ ] `_decide_package` consults the manifest before falling back to the OBS comment fetch.
- [ ] Promoted uploads and confirmed skips record the current HEAD short SHA (only when the package path is not dirty, never in dry-run); the manifest is saved once at the end of `cmd_sync` when `--skip-unchanged` is active.

**Verify:** `venv/bin/python -m pytest tests/test_sync_state.py -q` → PASS

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `tests/test_sync_state.py`:

```python
"""Unit tests for the sync-state manifest (percona_obs.sync_state)."""

import percona_obs.sync_state as sync_state
from percona_obs.sync_state import load_manifest, save_manifest, manifest_entry_clean


def _point_at(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_state, "_SYNC_STATE_DIR", tmp_path / "sync_state")


def test_round_trip(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    save_manifest("http://obs", "root:prj", {"p/x": "abc1234"})
    assert load_manifest("http://obs", "root:prj") == {"p/x": "abc1234"}


def test_missing_and_corrupt_load_empty(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    assert load_manifest("http://obs", "root:prj") == {}
    save_manifest("http://obs", "root:prj", {"p/x": "abc1234"})
    path = sync_state._manifest_path("http://obs", "root:prj")
    path.write_text("{not json")
    assert load_manifest("http://obs", "root:prj") == {}


def test_manifests_keyed_by_apiurl_and_rootprj(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    save_manifest("http://obs-a", "root", {"p/x": "aaa1111"})
    save_manifest("http://obs-b", "root", {"p/x": "bbb2222"})
    assert load_manifest("http://obs-a", "root") == {"p/x": "aaa1111"}
    assert load_manifest("http://obs-b", "root") == {"p/x": "bbb2222"}


def test_entry_clean_checks_git_state(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    monkeypatch.setattr(sync_state, "_has_package_changes_since", lambda *a: False)
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(sync_state, "_macros_changed_since", lambda *a: False)
    manifest = {"p/x": "abc1234"}
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is True
    assert manifest_entry_clean(manifest, "p/missing", tmp_path) is False
    monkeypatch.setattr(sync_state, "_has_package_changes_since", lambda *a: True)
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is False
```

Run: `venv/bin/python -m pytest tests/test_sync_state.py -q` → FAIL (ModuleNotFoundError).

- [ ] **Step 2: Implement `percona_obs/sync_state.py`**

```python
"""Local manifest of the last-synced git SHA per OBS package.

The manifest lets ``sync push --skip-unchanged`` decide "nothing to do" with
zero OBS API calls: if the recorded SHA matches HEAD's history for the package
directory (and nothing is dirty), the package is skipped without even fetching
the OBS revision comment.  The manifest lives under ``.cache/sync_state/`` —
persisted between CI runs by actions/cache — and is keyed by (apiurl, rootprj)
so different profiles/instances never share entries.

The manifest is an optimization layer only: a missing, stale, or evicted
manifest falls back to the OBS revision-comment check, and any doubt there
falls back to the normal promote path whose MD5 comparison is authoritative.
"""

import hashlib
import json
from pathlib import Path

from .common import _REPO_DIR, logger
from .git_utils import (
    _has_package_changes_since,
    _is_path_dirty,
    _macros_changed_since,
)

_SYNC_STATE_DIR = _REPO_DIR / ".cache" / "sync_state"


def _manifest_path(apiurl: str, rootprj: str) -> Path:
    key = hashlib.sha256(f"{apiurl}|{rootprj}".encode()).hexdigest()[:16]
    return _SYNC_STATE_DIR / f"{key}.json"


def load_manifest(apiurl: str, rootprj: str) -> dict[str, str]:
    """Return the {'project/package': 'short-sha'} manifest, or {} when absent/corrupt."""
    path = _manifest_path(apiurl, rootprj)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def save_manifest(apiurl: str, rootprj: str, manifest: dict[str, str]) -> None:
    """Atomically write the manifest (tmp file + rename)."""
    path = _manifest_path(apiurl, rootprj)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning(f"sync-state manifest save failed: {exc}")


def manifest_entry_clean(
    manifest: dict[str, str], key: str, package_path: Path
) -> bool:
    """Return True when the manifest SHA for *key* is present and nothing changed.

    Runs the same local git checks as the OBS-comment fast path — package
    directory commits since the SHA, uncommitted edits, inherited macros —
    but requires no API call.
    """
    sha = manifest.get(key)
    if not sha:
        return False
    if _has_package_changes_since(sha, package_path):
        return False
    if _is_path_dirty(package_path):
        return False
    if _macros_changed_since(sha, package_path):
        return False
    return True
```

- [ ] **Step 3: Add `_head_short_sha` to `percona_obs/git_utils.py`**

After `_generate_sync_message` (line 250):

```python
def _head_short_sha() -> str | None:
    """Return the abbreviated SHA of HEAD, or None on git error."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
```

- [ ] **Step 4: Wire the manifest into `cmd_sync`**

Imports in `cmd_sync.py`:

```python
from .git_utils import _head_short_sha
from .sync_state import load_manifest, manifest_entry_clean, save_manifest
```

In `cmd_sync`, before Phase 1 (next to the `_branch_repo_cache` declarations, ~line 830):

```python
    # Sync-state manifest: {'project/package': short-sha} of the last upload.
    # Only maintained in --skip-unchanged mode; lets the skip decision run
    # with zero API calls when warm.  _head_sha is recorded for packages
    # uploaded or confirmed-skipped in this run.
    skip_unchanged = getattr(args, "skip_unchanged", False)
    sync_manifest: dict[str, str] = (
        load_manifest(apiurl, args.rootprj) if skip_unchanged else {}
    )
    _head_sha = _head_short_sha()
```

In `_decide_package`, extend the skip branch from Task 2:

```python
            if skip_unchanged and not args.force:
                mkey = f"{obs_project_name}/{package_path.name}"
                if manifest_entry_clean(sync_manifest, mkey, package_path):
                    logger.debug(f"skip decision: skip  {mkey}  (manifest)")
                    return key, "skip", None, None
                if _resolve_skip_decision(
                    apiurl, obs_project_name, package_path.name, package_path
                ):
                    return key, "skip", None, None
            return key, "promote", None, None
```

In the Phase 3 loop:

- In the `"skip"` branch (Task 2), before `continue`, add:

```python
            if skip_unchanged and _head_sha and not _is_path_dirty(package_path):
                sync_manifest[f"{obs_project_name}/{package_path.name}"] = _head_sha
```

- After each of the two `files_changed = _upload_obs_files(...)` call sites (service and no-service paths), i.e. right after the inner `try/finally` blocks complete at the end of the promote handling, add once (both paths converge at the end of the loop body — place it as the final statement of the `for obs_project, package_path in targets:` body):

```python
        if (
            skip_unchanged
            and not dry_run_obs
            and _head_sha
            and not _is_path_dirty(package_path)
        ):
            sync_manifest[f"{obs_project_name}/{package_path.name}"] = _head_sha
```

- Before the final `_print_ok(f"sync successful{suffix}")` (line 1565):

```python
    if skip_unchanged and not dry_run_obs:
        save_manifest(apiurl, args.rootprj, sync_manifest)
```

- [ ] **Step 5: Run tests, format, type-check, commit**

```bash
venv/bin/python -m pytest tests/ -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright
git add percona_obs/sync_state.py percona_obs/git_utils.py percona_obs/cmd_sync.py tests/test_sync_state.py
git commit -s -m "sync: record per-package sync state for zero-request skips"
```

---

### Task 4: Deduplicate project meta/prjconf fetches

**Goal:** Stop fetching each project's meta and prjconf three times per run: reuse the Phase 2.5 verdicts to skip the skeleton existence GET and the whole `_apply_project_config` call for unchanged existing projects (plain pushes only). Saves ~3 requests per unchanged project (~120/run) plus a wasted 5-second sleep.

**Files:**
- Modify: `percona_obs/cmd_sync.py` (Phase 2.5 ~line 1195; pre-pass ~lines 1250-1330)
- Modify: `percona_obs/obs_api.py:734` (`_create_project_skeleton` returns whether it created)
- Test: `tests/test_project_prepass.py`

**Acceptance Criteria:**
- [ ] Phase 2.5 collects `proj_verdicts: dict[str, tuple[bool, bool]]` ((changed, is_new) per project) in addition to `config_changed_projects`.
- [ ] `_can_skip_project_apply(verdict, branch_rootprj, force, only_repos) -> bool` is a pure helper: True only for `verdict == (False, False)` on a plain, unforced, unfiltered push.
- [ ] Pre-pass: skeleton creation is skipped for projects known to exist; the 5-second settle sleep runs only when at least one skeleton was actually created.
- [ ] Pre-pass: `_apply_project_config` is skipped (with `=` output lines preserved) when `_can_skip_project_apply` is True; projects without a verdict (root/intermediate chain projects) take the full path as today.
- [ ] `--branch-from` behaviour is unchanged (verdicts there compare the production project, so the skip must not apply).

**Verify:** `venv/bin/python -m pytest tests/test_project_prepass.py -q` → PASS; `venv/bin/python -m percona_obs -P dev sync push --dry-run --project-only ppg:17.9` output still lists every project with `=`/`~` markers.

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `tests/test_project_prepass.py`:

```python
"""Unit tests for the project pre-pass skip logic (percona_obs.cmd_sync)."""

from percona_obs.cmd_sync import _can_skip_project_apply


def test_skip_when_unchanged_existing_plain_push():
    assert _can_skip_project_apply((False, False), None, False, None) is True


def test_no_skip_when_changed():
    assert _can_skip_project_apply((True, False), None, False, None) is False


def test_no_skip_when_new():
    assert _can_skip_project_apply((True, True), None, False, None) is False
    assert _can_skip_project_apply((False, True), None, False, None) is False


def test_no_skip_without_verdict():
    assert _can_skip_project_apply(None, None, False, None) is False


def test_no_skip_in_branch_mode():
    assert _can_skip_project_apply((False, False), "isv:percona", False, None) is False


def test_no_skip_with_force_or_only_repos():
    assert _can_skip_project_apply((False, False), None, True, None) is False
    assert _can_skip_project_apply((False, False), None, False, {"Debian_13"}) is False
```

Run: `venv/bin/python -m pytest tests/test_project_prepass.py -q` → FAIL (ImportError).

- [ ] **Step 2: Implement the helper and collect verdicts**

In `cmd_sync.py` (module level, near `_compute_branch_project`):

```python
def _can_skip_project_apply(
    verdict: "tuple[bool, bool] | None",
    branch_rootprj: "str | None",
    force: bool,
    only_repos: "set[str] | None",
) -> bool:
    """Return True when the pre-pass may skip a project's meta/prjconf apply.

    Requires a Phase 2.5 verdict of (changed=False, is_new=False) on a plain,
    unforced, unfiltered push.  In --branch-from mode the verdict compares the
    *production* project, so it cannot stand in for the target project's state;
    --only-repos changes the desired meta, invalidating the comparison.
    """
    return (
        branch_rootprj is None
        and not force
        and only_repos is None
        and verdict == (False, False)
    )
```

In Phase 2.5, change the collection loop (lines 1195-1200) to also keep the verdicts:

```python
    proj_verdicts: dict[str, tuple[bool, bool]] = {}
    ...
        with ThreadPoolExecutor(max_workers=8) as _proj_pool:
            for _pname, _changed, _is_new in _proj_pool.map(
                _check_proj_changed, _unique_proj_paths.items()
            ):
                proj_verdicts[_pname] = (_changed, _is_new)
                if not _is_new and _changed:
                    config_changed_projects.add(_pname)
```

(Declare `proj_verdicts: dict[str, tuple[bool, bool]] = {}` next to `config_changed_projects` at line 1138 so it exists even when `targets` is empty.)

- [ ] **Step 3: Make `_create_project_skeleton` report creation and use verdicts in the pre-pass**

In `obs_api.py`, change `_create_project_skeleton`'s signature to `-> bool`; `return False` at the early `return  # project already exists` (line 758), and `return True` at the end after the create.

In `cmd_sync.py`, rewrite the pre-pass loops (lines 1262-1330):

```python
        sorted_projs = sorted(all_projects.items(), key=lambda kv: kv[1][0].count(":"))
        created_any = False
        for _raw, (prj_name, proj_path) in sorted_projs:
            # Skip the existence GET when Phase 2.5 already saw the project.
            _verdict = proj_verdicts.get(prj_name)
            if _verdict is not None and not _verdict[1]:
                continue
            if _create_project_skeleton(
                apiurl,
                prj_name,
                proj_path,
                args.rootprj,
                dry_run=dry_run_obs,
                env_vars=env_vars,
            ):
                created_any = True
        # Give OBS a moment to settle after creating skeleton projects
        # before applying the full configuration.
        if created_any and not dry_run_obs:
            time.sleep(5)
```

And in the Stage 2 pass-1 loop, before calling `_apply_project_config`:

```python
        for raw_proj, (prj_name, proj_path) in sorted_projs:
            if _can_skip_project_apply(
                proj_verdicts.get(prj_name),
                branch_rootprj,
                args.force,
                effective_only_repos,
            ):
                _print_same(f"project meta  {prj_name}")
                _print_same(f"project config  {prj_name}")
                seen_projects.add(raw_proj)
                continue
            stripped, _ = _apply_project_config(...)   # unchanged call as today
            ...
```

The single-package path (lines 1355-1427) is untouched — it only runs for explicit `sync push <project> <package>` invocations, not the full-tree CI sync.

- [ ] **Step 4: Run tests and a live dry-run**

```bash
venv/bin/python -m pytest tests/ -q
venv/bin/python -m percona_obs -P dev sync push --dry-run --project-only ppg:17.9
```

Expected: tests PASS; dry-run prints the same set of `project meta` / `project config` lines as before this change.

- [ ] **Step 5: Format, type-check, commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright
git add percona_obs/cmd_sync.py percona_obs/obs_api.py tests/test_project_prepass.py
git commit -s -m "sync: reuse Phase 2.5 verdicts to skip redundant project fetches"
```

---

### Task 5: Global client-side throttle and 429/503 retry

**Goal:** Pace all osc HTTP traffic through one token-interval limiter (default 8 req/s, env-tunable) and retry on 429/503 (plus 502/504 for GETs) honoring `Retry-After` — so bursts stop tripping OBS traffic limiters and throttled runs survive instead of failing.

**Files:**
- Create: `percona_obs/http_throttle.py`
- Modify: `percona_obs/cli.py` (install in `main()`)
- Modify: `.github/scripts/poll_obs_builds.py` (install after `osc.conf.get_config`)
- Modify: `percona_obs/cmd_sync.py:935` (Phase 1 pool 16 → 8)
- Test: `tests/test_http_throttle.py`

**Acceptance Criteria:**
- [ ] All osc requests flow through the wrapper (patched at `osc.connection.http_request`, which `http_GET/PUT/POST/DELETE` resolve at call time — verified against `venv/lib/python3*/site-packages/osc/connection.py:427-443`).
- [ ] 429/503 retried up to 5 attempts for all methods; 502/504 retried for GET only; `Retry-After` honored; exponential backoff `min(2**attempt, 60)` otherwise; final failure re-raises the original `HTTPError`.
- [ ] Pacing enforces a minimum interval of `1 / PERCONA_OBS_MAX_RPS` (default 8 rps; `0` disables) across threads.
- [ ] `install()` is idempotent.

**Verify:** `venv/bin/python -m pytest tests/test_http_throttle.py -q` → PASS

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `tests/test_http_throttle.py`:

```python
"""Unit tests for the osc HTTP throttle/retry wrapper (percona_obs.http_throttle)."""

import urllib.error

import percona_obs.http_throttle as ht


def _http_error(code: int, headers: dict | None = None):
    import email.message

    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("http://obs/x", code, "err", msg, None)


def test_retries_on_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(ht.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return "ok"

    assert ht._request_with_retry(orig, "GET", "http://obs/x") == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_honors_retry_after(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(ht.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(503, {"Retry-After": "42"})
        return "ok"

    assert ht._request_with_retry(orig, "GET", "http://obs/x") == "ok"
    assert sleeps == [42.0]


def test_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(ht.time, "sleep", lambda s: None)

    def orig(method, url, *a, **k):
        raise _http_error(429)

    try:
        ht._request_with_retry(orig, "GET", "http://obs/x")
        assert False, "should have raised"
    except urllib.error.HTTPError as e:
        assert e.code == 429


def test_502_retried_for_get_only(monkeypatch):
    monkeypatch.setattr(ht.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        raise _http_error(502)

    try:
        ht._request_with_retry(orig, "POST", "http://obs/x")
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == 1  # POST not retried on 502

    calls["n"] = 0
    try:
        ht._request_with_retry(orig, "GET", "http://obs/x")
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == ht._MAX_ATTEMPTS  # GET retried


def test_other_errors_not_retried(monkeypatch):
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        raise _http_error(404)

    try:
        ht._request_with_retry(orig, "GET", "http://obs/x")
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == 1


def test_pace_respects_min_interval(monkeypatch):
    monkeypatch.setenv("PERCONA_OBS_MAX_RPS", "1000")
    ht._pace()
    ht._pace()  # must not raise; interval math exercised
```

Run: `venv/bin/python -m pytest tests/test_http_throttle.py -q` → FAIL (ModuleNotFoundError).

- [ ] **Step 2: Implement `percona_obs/http_throttle.py`**

```python
"""Global client-side pacing and retry for all osc HTTP requests.

install() wraps osc.connection.http_request; osc's http_GET/PUT/POST/DELETE
resolve that name at call time, so a single patch covers every request made
through osc (including osc.core.show_* helpers).

Pacing: a minimum interval of 1 / PERCONA_OBS_MAX_RPS seconds between request
starts, shared across threads (default 8 rps; set 0 to disable).  This
reshapes thread-pool bursts into a steady stream that OBS traffic limiters
tolerate.

Retry: 429 and 503 are retried for every method (the request was not
processed); 502/504 only for GET (a proxy may have processed a POST).
Retry-After is honored when present, otherwise exponential backoff capped at
60 s, up to 5 attempts.
"""

import os
import threading
import time
import urllib.error

import osc.connection

from .common import logger

_RETRY_ALL = {429, 503}
_RETRY_GET_ONLY = {502, 504}
_MAX_ATTEMPTS = 5

_pace_lock = threading.Lock()
_next_slot = 0.0
_installed = False


def _min_interval() -> float:
    try:
        rps = float(os.environ.get("PERCONA_OBS_MAX_RPS", "8"))
    except ValueError:
        rps = 8.0
    return 1.0 / rps if rps > 0 else 0.0


def _pace() -> None:
    """Block until this thread may start a request (shared min-interval)."""
    global _next_slot
    interval = _min_interval()
    if interval <= 0:
        return
    with _pace_lock:
        now = time.monotonic()
        start = max(now, _next_slot)
        _next_slot = start + interval
    delay = start - now
    if delay > 0:
        time.sleep(delay)


def _retry_delay(e: urllib.error.HTTPError, attempt: int) -> float:
    try:
        retry_after = float(e.headers.get("Retry-After") or 0)
    except (TypeError, ValueError):
        retry_after = 0.0
    return retry_after if retry_after > 0 else float(min(2**attempt, 60))


def _request_with_retry(orig, method: str, url: str, *args, **kwargs):
    retry_codes = _RETRY_ALL | (_RETRY_GET_ONLY if method == "GET" else set())
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        _pace()
        try:
            return orig(method, url, *args, **kwargs)
        except urllib.error.HTTPError as e:
            if e.code not in retry_codes or attempt == _MAX_ATTEMPTS:
                raise
            delay = _retry_delay(e, attempt)
            logger.warning(
                f"OBS returned HTTP {e.code} for {method} {url}; "
                f"retrying in {delay:.0f}s ({attempt}/{_MAX_ATTEMPTS})"
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def install() -> None:
    """Patch osc.connection.http_request with the paced, retrying wrapper."""
    global _installed
    if _installed:
        return
    _installed = True
    orig = osc.connection.http_request

    def throttled(method, url, *args, **kwargs):
        return _request_with_retry(orig, method, url, *args, **kwargs)

    osc.connection.http_request = throttled
```

- [ ] **Step 3: Install the wrapper and lower the Phase 1 pool**

In `percona_obs/cli.py`, inside `main()` right after osc configuration is initialised (locate the `osc.conf.get_config(...)` call and add immediately after it):

```python
    from .http_throttle import install as _install_http_throttle

    _install_http_throttle()
```

In `.github/scripts/poll_obs_builds.py` after `osc.conf.get_config(override_apiurl=apiurl)` (line 50):

```python
from percona_obs.http_throttle import install as _install_http_throttle

_install_http_throttle()
```

In `percona_obs/cmd_sync.py` line 935, change `ThreadPoolExecutor(max_workers=16)` → `ThreadPoolExecutor(max_workers=8)` (the throttle makes wider pools pointless; 8 keeps latency hiding for the git subprocess work).

- [ ] **Step 4: Run tests, format, type-check, commit**

```bash
venv/bin/python -m pytest tests/ -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright
git add percona_obs/http_throttle.py percona_obs/cli.py percona_obs/cmd_sync.py .github/scripts/poll_obs_builds.py tests/test_http_throttle.py
git commit -s -m "obs: pace and retry all osc HTTP requests client-side"
```

---

### Task 6: Sync report + scoped, backoff-based poll loop

**Goal:** `sync push` writes a JSON report of projects that actually need rebuild monitoring; the poll script monitors only those (falling back to a single full snapshot when nothing changed), ramps its interval up to 300 s while nothing changes, and does one full-tree sweep at the end to adopt cross-project rebuild cascades.

**Files:**
- Modify: `percona_obs/cli.py` (add `--report-json`)
- Modify: `percona_obs/cmd_sync.py` (collect rebuild projects, write report)
- Modify: `percona_obs/common.py` (add `next_poll_interval`)
- Modify: `.github/scripts/poll_obs_builds.py`
- Test: `tests/test_poll_interval.py`

**Acceptance Criteria:**
- [ ] `sync push --report-json PATH` writes `{"rebuild_projects": [...], "promoted": ["proj/pkg", ...], "skipped": N}` where `rebuild_projects` contains projects with at least one committed file upload or a created/updated project meta/prjconf.
- [ ] `next_poll_interval(current, changed, base, cap)` ramps ×1.5 to `cap` while unchanged and resets to `base` on change.
- [ ] Poll script with `OBS_SYNC_REPORT` set: monitors only `rebuild_projects` (devel skip still applied); when the set is empty it takes one full snapshot for the badge and exits without looping; after the monitored set goes terminal it does one full-tree sweep and adopts any project still building.
- [ ] Poll script without `OBS_SYNC_REPORT` behaves as today (full-tree polling) plus backoff.

**Verify:** `venv/bin/python -m pytest tests/test_poll_interval.py -q` → PASS

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `tests/test_poll_interval.py`:

```python
"""Unit tests for the poll-interval backoff helper (percona_obs.common)."""

from percona_obs.common import next_poll_interval


def test_ramps_up_when_unchanged():
    assert next_poll_interval(30, changed=False, base=30, cap=300) == 45
    assert next_poll_interval(45, changed=False, base=30, cap=300) == 67


def test_caps_at_max():
    assert next_poll_interval(280, changed=False, base=30, cap=300) == 300
    assert next_poll_interval(300, changed=False, base=30, cap=300) == 300


def test_resets_on_change():
    assert next_poll_interval(300, changed=True, base=30, cap=300) == 30
```

Run: `venv/bin/python -m pytest tests/test_poll_interval.py -q` → FAIL (ImportError).

- [ ] **Step 2: Implement `next_poll_interval` in `percona_obs/common.py`**

```python
def next_poll_interval(current: int, changed: bool, base: int, cap: int) -> int:
    """Return the next poll sleep: reset to *base* on change, else ramp 1.5x to *cap*."""
    if changed:
        return base
    return min(int(current * 1.5), cap)
```

- [ ] **Step 3: Add `--report-json` and collect rebuild projects in `cmd_sync`**

`percona_obs/cli.py`, after `--skip-unchanged`:

```python
    sync_push_parser.add_argument(
        "--report-json",
        metavar="PATH",
        default=None,
        dest="report_json",
        help="Write a JSON sync report (projects needing rebuild monitoring, "
        "promoted packages, skip count) to PATH.",
    )
```

`percona_obs/cmd_sync.py`:

- Near the manifest declarations (~line 830): `rebuild_projects: set[str] = set()` and `promoted_uploads: list[str] = []`.
- In the pre-pass Stage 2 loop, capture the second return value of `_apply_project_config` (currently discarded): change `stripped, _ = _apply_project_config(...)` to `stripped, _proj_changed = _apply_project_config(...)` and after it:

```python
            if _proj_changed:
                rebuild_projects.add(prj_name)
```

(Same in the Stage 2 pass-2 loop: `_, _proj_changed2 = _apply_project_config(...)` then `if _proj_changed2: rebuild_projects.add(prj_name)`.)

- In the Phase 3 loop, after each `files_changed = _upload_obs_files(...)` (the loop-final manifest block from Task 3 is a good anchor — extend it):

```python
        if files_changed:
            rebuild_projects.add(obs_project_name)
            promoted_uploads.append(f"{obs_project_name}/{package_path.name}")
```

- Before the final `_print_ok(...)`:

```python
    if getattr(args, "report_json", None):
        _skipped = sum(1 for d in decisions.values() if d == "skip")
        report = {
            "rebuild_projects": sorted(rebuild_projects),
            "promoted": promoted_uploads,
            "skipped": _skipped,
        }
        Path(args.report_json).write_text(json.dumps(report, indent=2))
```

(Add `import json` to cmd_sync's imports if not already present.)

- [ ] **Step 4: Rework the poll loop in `.github/scripts/poll_obs_builds.py`**

Replace the configuration block (lines 41-45) and the poll loop (lines 160-194) as follows. New env vars: `OBS_SYNC_REPORT` (path, optional), `OBS_POLL_MAX_INTERVAL` (default 300).

```python
poll_interval = int(os.environ.get("OBS_POLL_INTERVAL", "30"))
max_interval = int(os.environ.get("OBS_POLL_MAX_INTERVAL", "300"))
initial_wait = int(os.environ.get("OBS_INITIAL_WAIT", "30"))
sync_report_path = os.environ.get("OBS_SYNC_REPORT", "")
```

After the existing `obs_projects` discovery (line 85), scope to the sync report when present:

```python
all_projects = set(obs_projects)
if sync_report_path and os.path.isfile(sync_report_path):
    with open(sync_report_path) as fh:
        report = json.load(fh)
    touched = set(report.get("rebuild_projects", []))
    obs_projects = obs_projects & touched
    print(
        f"Sync report: {len(touched)} project(s) touched, "
        f"monitoring {len(obs_projects)} after devel filter"
    )
```

Replace the poll loop with a `collect(projects)` helper plus scoped loop, backoff, and a final adoption sweep:

```python
from percona_obs.common import next_poll_interval


def collect(projects):
    """One pass over *projects*; returns (state_counts, per_repo_counts)."""
    state_counts: dict[str, int] = {}
    per_repo_counts: dict[str, dict[str, int]] = {}
    for obs_name in projects:
        results, _ = _fetch_build_results(apiurl, obs_name)
        for _pkg, repos in results.items():
            for repo, flavors in repos.items():
                repo_counts = per_repo_counts.setdefault(repo, {})
                for _flavor, code in flavors.items():
                    state_counts[code] = state_counts.get(code, 0) + 1
                    repo_counts[code] = repo_counts.get(code, 0) + 1
    return state_counts, per_repo_counts


if not obs_projects:
    # Nothing uploaded → no rebuilds triggered by this run.  Take a single
    # full-tree snapshot so the badge reflects reality, then exit on it
    # without waiting for unrelated in-flight builds.
    print("No monitored projects; taking one badge snapshot.")
    state_counts, per_repo_counts = collect(all_projects)
else:
    print(f"Waiting {initial_wait}s for OBS to schedule builds…", flush=True)
    time.sleep(initial_wait)
    interval = poll_interval
    prev_counts: dict[str, int] = {}
    while True:
        state_counts, per_repo_counts = collect(obs_projects)
        total = sum(state_counts.values())
        still_building = sum(state_counts.get(s, 0) for s in NON_TERMINAL)
        summary = ", ".join(f"{s}={n}" for s, n in sorted(state_counts.items()))
        print(f"{summary or 'no results yet'}", flush=True)
        if total > 0 and still_building == 0:
            # Monitored set is terminal.  One full-tree sweep adopts projects
            # rebuilt by cross-project cascades (e.g. containers aggregating
            # freshly built packages); loop again if anything was adopted.
            sweep_counts, _ = collect(all_projects - obs_projects)
            sweep_building = sum(sweep_counts.get(s, 0) for s in NON_TERMINAL)
            if sweep_building == 0:
                state_counts, per_repo_counts = collect(all_projects)
                break
            print(f"Adopting {sweep_building} still-building result(s) from full tree")
            obs_projects = set(all_projects)
        interval = next_poll_interval(
            interval, changed=(state_counts != prev_counts),
            base=poll_interval, cap=max_interval,
        )
        prev_counts = state_counts
        time.sleep(interval)
```

The tail of the script (badge, details, exit code) is unchanged — it already consumes `state_counts` / `per_repo_counts`.

- [ ] **Step 5: Run tests, format, type-check, commit**

```bash
venv/bin/python -m pytest tests/ -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright
git add percona_obs/cli.py percona_obs/cmd_sync.py percona_obs/common.py .github/scripts/poll_obs_builds.py tests/test_poll_interval.py
git commit -s -m "sync/poll: scoped build monitoring with backoff via sync report"
```

---

### Task 7: Workflow restructure — debounce queued pushes and wire the new flags

**Goal:** Split sync-main.yml into a serialized `sync` job and a cancellable `poll` job so a newer push's poll supersedes older ones; base the version-lists/release-tags diff range on the last *successful* run instead of `event.before` (making cancellation safe); wire `--skip-unchanged`, `--report-json`, `OBS_SYNC_REPORT`, and persist `.cache/sync_state`.

**Files:**
- Modify: `.github/workflows/sync-main.yml`

**Acceptance Criteria:**
- [ ] Workflow-level `concurrency` removed; `sync` job uses group `sync-main-sync` with `cancel-in-progress: false`; `poll` job uses group `sync-main-poll` with `cancel-in-progress: true` and `needs: sync`.
- [ ] Sync step runs with `--skip-unchanged --report-json /tmp/sync-report.json`; the report is passed to the poll job via an artifact; poll step sets `OBS_SYNC_REPORT`.
- [ ] `.cache/sync_state` added to the deps cache `path` list.
- [ ] Version-lists and release-tags steps compute their diff base as: head SHA of the last successful sync-main run, falling back to `github.event.before`, falling back to the all-zeros SHA (existing behaviour).
- [ ] Badge publish stays `if: always()` in the poll job.
- [ ] `venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/sync-main.yml'))"` passes.

**Verify:** YAML loads; next push to main shows two jobs, with the poll of an older run cancelled when a newer run reaches its poll job.

**Steps:**

- [ ] **Step 1: Restructure the workflow**

Replace `.github/workflows/sync-main.yml`'s `concurrency` block and `jobs:` section with the structure below. Steps marked *(unchanged)* keep their current content verbatim.

```yaml
# No workflow-level concurrency: sync jobs serialize via their own group while
# polls cancel-supersede, so a queued push starts its sync as soon as the
# previous sync (not its hours-long poll) finishes.

jobs:
  sync:
    name: percona-obs sync push
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    # Serialize syncs; never cancel a sync mid-upload.
    concurrency:
      group: sync-main-sync
      cancel-in-progress: false
    permissions:
      contents: read
      packages: read

    steps:
      - uses: actions/checkout@v4          # (unchanged, fetch-depth: 0 + token)

      - name: Restore percona-obs deps cache   # (unchanged, plus sync_state path)
        uses: actions/cache@v4
        with:
          path: |
            .cache/download_url
            .cache/cargo_vendor
            .cache/services
            .cache/sync_state
          key: percona-obs-deps-${{ runner.os }}-${{ github.sha }}
          restore-keys: |
            percona-obs-deps-${{ runner.os }}-

      - name: Restore percona-obs scm cache    # (unchanged)

      - uses: ./.github/actions/obs-setup      # (unchanged)

      - name: Create percona-obs profile       # (unchanged)

      - name: Sync to OBS
        run: >
          venv/bin/python -m percona_obs --verbose -P main sync push
          --no-scm-validate --skip-unchanged --report-json /tmp/sync-report.json

      - name: Prune stale cache entries        # (unchanged)

      - name: Upload sync report
        uses: actions/upload-artifact@v4
        with:
          name: sync-report
          path: /tmp/sync-report.json
          retention-days: 1

  poll:
    name: Wait for OBS builds
    needs: sync
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    # A newer run's poll supersedes this one.  Safe because the version-lists
    # and release-tags steps diff against the last SUCCESSFUL run's SHA, so
    # whichever poll survives covers the cancelled runs' ranges too.
    concurrency:
      group: sync-main-poll
      cancel-in-progress: true
    permissions:
      contents: write
      actions: read
      packages: read

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GH_PAT }}

      - uses: ./.github/actions/obs-setup      # (unchanged)

      - name: Download sync report
        uses: actions/download-artifact@v4
        with:
          name: sync-report
          path: /tmp

      - name: Compute last-successful base SHA
        id: base
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          LAST_GOOD=$(gh api \
            "repos/$GITHUB_REPOSITORY/actions/workflows/sync-main.yml/runs?branch=main&status=success&per_page=1" \
            --jq '.workflow_runs[0].head_sha // empty' || true)
          BASE="${LAST_GOOD:-${{ github.event.before }}}"
          BASE="${BASE:-0000000000000000000000000000000000000000}"
          echo "sha=${BASE}" >> "$GITHUB_OUTPUT"
          echo "Diff base: ${BASE}"

      - name: Poll OBS build status
        id: poll
        env:
          OBS_APIURL: ${{ vars.OBS_APIURL }}
          OBS_ROOTPRJ: ${{ vars.OBS_ROOTPRJ }}
          OBS_SYNC_REPORT: /tmp/sync-report.json
          PYTHONPATH: ${{ github.workspace }}
        run: venv/bin/python .github/scripts/poll_obs_builds.py

      - name: Update version lists             # (unchanged except:)
        env:
          GITHUB_EVENT_BEFORE: ${{ steps.base.outputs.sha }}
          # ... rest unchanged

      - name: Create release tags              # (unchanged except the diff:)
        run: |
          CHANGED=$(git diff --name-only "${{ steps.base.outputs.sha }}" "$GITHUB_SHA" \
            -- 'root/*/releases/*/release.yaml' 2>/dev/null || true)
          # ... rest unchanged

      - name: Publish OBS build badge          # (unchanged, if: always())
```

Notes for the implementer:
- The `sync` job loses `contents: write` (it no longer tags); the `poll` job gains it.
- The all-zeros fallback replicates the existing `github.event.before || '0000…'` behaviour for `workflow_dispatch` runs.
- Keep every step's existing comments; add a header comment explaining the two-job debounce design.

- [ ] **Step 2: Validate and commit**

```bash
venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/sync-main.yml')); print('OK')"
git add .github/workflows/sync-main.yml
git commit -s -m "ci: split sync-main into serialized sync and superseding poll jobs"
```

- [ ] **Step 3: Post-merge observation (after the next real push to main)**

Check with `gh run list --workflow sync-main.yml --limit 3` that: two jobs appear, the sync job's log shows `skip … (unchanged)` lines and a written report, the poll log shows `Monitoring N OBS project(s)` with N equal to the touched set, and a superseded run's poll shows as cancelled while its sync shows success.

---

### Task 8: Documentation and final verification

**Goal:** Document the new flags/env vars and verify the whole stack end-to-end.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md`
- Modify: `.github/copilot-instructions.md` (only if it enumerates sync flags — check first)

**Acceptance Criteria:**
- [ ] `--skip-unchanged`, `--report-json`, `PERCONA_OBS_MAX_RPS`, `OBS_SYNC_REPORT`, `OBS_POLL_MAX_INTERVAL`, and the `.cache/sync_state/` manifest are documented in `docs/PERCONA_OBS_TOOL.md`.
- [ ] Full check suite passes.

**Verify:** `venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest tests/ -q` → all pass

**Steps:**

- [ ] **Step 1: Document**

Add a "Reducing OBS API traffic" section to `docs/PERCONA_OBS_TOOL.md` covering:

```markdown
## Reducing OBS API traffic

`sync push --skip-unchanged` (plain pushes only) skips packages whose OBS
revision comment records a sync from a git SHA with no changes since —
checked against package commits, uncommitted edits, and inherited
macros.yaml. Skipped packages cost one API call, or zero when the
`.cache/sync_state/` manifest (written by previous --skip-unchanged runs) is
warm. Any doubt falls back to the normal promote path, whose MD5 comparison
is authoritative. `--force` disables skipping.

`sync push --report-json PATH` writes `{"rebuild_projects": [...],
"promoted": [...], "skipped": N}` — consumed by the CI poll script
(`OBS_SYNC_REPORT`) to monitor only projects that actually rebuilt.

All osc HTTP requests are paced client-side (default 8 requests/second,
tune with `PERCONA_OBS_MAX_RPS`; 0 disables) and retried on HTTP 429/503
honoring Retry-After.

The CI poll loop ramps its interval from `OBS_POLL_INTERVAL` (30 s) up to
`OBS_POLL_MAX_INTERVAL` (300 s) while build states are unchanged.
```

Check `.github/copilot-instructions.md` with `grep -n "branch-from\|sync push" .github/copilot-instructions.md`; if it documents sync flags, add one line each for `--skip-unchanged` and `--report-json` in the same style.

- [ ] **Step 2: Full verification and commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest tests/ -q
venv/bin/python -m percona_obs -P dev sync push --dry-run --skip-unchanged ppg:17.9
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md
git commit -s -m "docs: document sync API-traffic optimizations"
```

Expected: black unchanged, pyright 0 errors, all tests pass, dry-run shows `skip`/`=` lines for unchanged packages.

---

## Self-Review Notes

- **Spec coverage:** study suggestion 1 → Tasks 1–2; suggestion 3 (manifest) → Task 3; suggestion 2 (dedup) → Task 4; suggestion 5 (throttle) → Task 5; suggestion 4 (poll) → Task 6; suggestion 6 (debounce) → Task 7. Docs → Task 8.
- **Orphan-cleanup hazard** (skipped packages must not be deleted) is handled explicitly in Task 2 Step 3.
- **Release-tag loss under cancellation** (the reason `event.before` is unsafe once polls can be cancelled) is handled by the last-successful-SHA base in Task 7.
- **Type consistency:** `_clean_sync_check` returns `str | None` (Task 1) and is consumed as such in Tasks 2; `_create_project_skeleton` returns `bool` from Task 4 on; `proj_verdicts` is `dict[str, tuple[bool, bool]]` in Tasks 4.
- Known accepted limitations (documented in code comments): root/intermediate chain projects keep the un-deduplicated fetch path (small constant); out-of-band OBS edits between syncs are not detected by the manifest fast path (same trust model as the existing `--branch-from` comment check, and OBS is CI-managed).
