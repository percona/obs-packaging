# Pre-release Flow — Workflows PR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the two-hop release flow into CI (spec rollout step 2): a release PR populates a per-PR pre-release project and runs every QA lane against it; merging tags and dispatches one `obs-release.yml` run that copies pre-release → release, publishes GitHub releases and deletes the pre-release; the sync-main lock and release-only skip disappear.

**Architecture:** Release PRs get their own workflow (`obs-release-pr.yml`) with a no-cancel concurrency group, because `obs-pr-check.yml` cancels superseded runs and a cancelled populate would strand a frozen production staging. The QA fan-out (`detect-qa-matrix` → `merge-qa-matrix` → `qa`) is extracted verbatim into a reusable `workflow_call` workflow (`qa-fanout.yml`) that both the PR check and the release-PR workflow call. `obs-pr-cleanup.yml` becomes tag + one dispatch; `obs-release.yml` becomes per-instance `sync release --from` + finalize. One tool prerequisite (Task 0) makes hop 1 redirect external repository paths to the production root, as `sync push --branch-from` does.

**Tech Stack:** GitHub Actions YAML (reusable workflows, matrix over `vars.OBS_INSTANCES`), bash, `gh`, Python 3.11 CI scripts (tested with pytest via `importlib`), the `percona-obs` CLI (`sync prerelease`, `sync release --from`, `qa show`, `qa run`).

**Spec:** `docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md` (sections 1, 3, 4, 5; §2 is already implemented by PRs #142/#143)

## Global Constraints

- Work in the worktree `.claude/worktrees/prerelease-workflows` on branch `prerelease-workflows` (off `percona/main` d0d3dff6). Never touch the primary checkout.
- Python changes: `venv/bin/black percona_obs/` → `venv/bin/pyright` (0 errors) → `venv/bin/pytest -q`, all green before each commit. Workflow YAML changes: every touched `.github/workflows/*.yml` must parse (`venv/bin/python -c 'import sys,yaml; [yaml.safe_load(open(f)) for f in sys.argv[1:]]' <files>`) and must pass `actionlint` when the binary is available (see Task 1 Step 1 for how to obtain it; a missing binary is reported, never silently skipped).
- Commits: `git commit -s`. No `Co-Authored-By` lines of any kind. Never `git push`, never open a PR.
- No OBS, GitHub or Jenkins network access in tests; CI scripts are tested through pure functions loaded with `importlib` (pattern: `tests/test_manual_qa_scripts.py::_load`).
- Matrix job outputs are last-writer-wins: only values identical across every `OBS_INSTANCES` leg may be job outputs.
- A job that `needs` a skipped job is itself skipped unless its `if` starts with `!cancelled() &&` (or `always()`). Every job gated on a conditionally-skipped job in this plan uses `!cancelled() &&`.
- Release PRs are detected as "every changed `root/**` file is under `root/*/releases/`" (existing rule in `obs-pr-check` / `obs-pr-cleanup`); the new workflow fails a PR that mixes release and non-release `root/` changes.
- The pre-release project of release mirror `<product>:releases:<major>` on an instance is `<pr_rootprj>:pr-<N>:<product>:releases:<major>`; `obs-release.yml` derives it from the tag and `pr_number`, never from the PR's file list.
- Dispatching `obs-release.yml` uses `gh workflow run obs-release.yml --ref main -f pr_number=<N> -f tags="<tag1> <tag2>"` exactly once per merged release PR.
- The sync-main lock (disable/enable of `sync-main.yml`), the `sync-main-sync` lock group and the release-only push skip in `sync-main.yml` are removed, not relocated.
- Spec section numbering is referenced below as "spec §N".

**User decisions (already made):**
- Pre-release lives under the PR namespace `<pr-root>:pr-N:<product>:releases:<major>`.
- Release QA = every `qa:` lane the staging project, its subprojects and their packages declare (package lanes already copied into mirrors by PR #143); it runs automatically on a release PR with no trigger label.
- Population runs on every push to the release PR and on demand via `workflow_dispatch` with a PR number.
- One in-flight release PR per major: the first opened wins; a later one fails its check.
- Merge: one tag per changed `release.yaml`, one `obs-release.yml` dispatch per PR; the pre-release is deleted by `obs-release.yml` after a successful final copy, never by `obs-pr-cleanup.yml` for a merged release PR.
- `source_commit` is never committed back by CI.

---

## File structure

| File | Responsibility |
|---|---|
| `percona_obs/release_copy.py`, `percona_obs/cmd_sync.py` (Task 0) | `apply_mirror_meta`/`release_tree` accept `branch_rootprj`/`active_projects`; `sync prerelease` passes them so external repository paths resolve to the production root. |
| `.github/workflows/qa-fanout.yml` (new, Task 1) | Reusable `workflow_call`: `detect-qa-matrix`, `merge-qa-matrix`, `qa` — moved verbatim from `obs-pr-check.yml`, parameterised by `pr_number` and `qa_types`. |
| `.github/workflows/obs-pr-check.yml` (Tasks 1, 3) | Calls `qa-fanout.yml`; release PRs are gated out entirely (no dry-run, no sync). |
| `.github/scripts/release_pr.py` (new, Task 2) | Pure helpers for the release-PR workflow: release-only check, changed `release.yaml` → project ids, one-in-flight conflict detection, pre-release project naming. Tested. |
| `.github/workflows/obs-release-pr.yml` (new, Task 2) | `resolve` → `populate` (per instance, no-cancel) → `comment` → `qa-fanout.yml`; `workflow_dispatch(pr_number)`. |
| `.github/scripts/post_pr_comment.py` (Task 4) | Pre-release mode of the PR comment (per-instance pre-release project links, source commit, outcome); rendering extracted into a tested function. |
| `.github/workflows/obs-pr-cleanup.yml` (Task 5) | Tag per `release.yaml`, one dispatch with `pr_number` + `tags`, no lock; `delete` skipped for a merged release PR. |
| `.github/workflows/obs-release.yml` (Task 6) | Inputs `pr_number`, `tags`; per-instance `sync release --from`; `finalize` publishes GitHub releases and deletes the PR projects; no lock. |
| `.github/workflows/sync-main.yml` (Task 7) | Release-only push skip removed. |
| `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md`, `root/README.md`, `root/ppg/releases/README.md` (Task 8) | Process and workflow docs. |
| `docs/superpowers/specs/2026-10-14-prerelease-rehearsal-runbook.md` (new, Task 9) | Labs rehearsal checklist with a throwaway release id. |

---

### Task 0: `sync prerelease` applies mirror meta with branch-root path redirection

**Goal:** Pre-release project meta keeps its repository paths: paths to projects outside the release tree (e.g. `common:containers:ubi9`, `ppg:common:deps`) are redirected to the production root instead of being stripped by OBS.

**Files:**
- Modify: `percona_obs/release_copy.py` (`apply_mirror_meta` ~line 102, `release_tree` ~line 183)
- Modify: `percona_obs/cmd_sync.py` (`cmd_sync_prerelease`: the top-level `apply_mirror_meta(...)` call ~line 2939 and the `release_tree(...)` call ~line 2954)
- Test: `tests/test_release_copy.py`, `tests/test_sync_prerelease.py`

**Acceptance Criteria:**
- [ ] `apply_mirror_meta(..., branch_rootprj=X, active_projects=S)` forwards both to `_apply_project_config` on both passes; omitted → `None` (legacy hops unchanged)
- [ ] `release_tree(..., branch_rootprj=X, active_projects=S)` forwards both to every subproject `apply_mirror_meta` call
- [ ] `cmd_sync_prerelease` passes `branch_rootprj=<source rootprj>` and `active_projects={pre-release top, pre-release:<name> for every pair}` to both calls
- [ ] Existing tests keep their assertions

**Verify:** `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q tests/test_release_copy.py tests/test_sync_prerelease.py` → PASS, 0 errors

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_release_copy.py`:

```python
def test_apply_mirror_meta_forwards_branch_redirection(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        rc,
        "_apply_project_config",
        lambda *a, **k: seen.append((k.get("branch_rootprj"), k.get("active_projects")))
        or (False, True),
    )
    monkeypatch.setattr(rc, "_disable_project_builds", lambda *a, **k: None)
    rc.apply_mirror_meta(
        "http://obs", "PR:T", tmp_path, "PR", {},
        branch_rootprj="prod", active_projects={"PR:T", "PR:T:containers"},
    )
    assert seen == [("prod", {"PR:T", "PR:T:containers"})]


def test_release_tree_forwards_branch_redirection_to_subprojects(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        rc,
        "apply_mirror_meta",
        lambda apiurl, prj, path, rootprj, env, **k: seen.append((prj, k.get("branch_rootprj"), k.get("active_projects"))),
    )
    monkeypatch.setattr(rc, "copy_project_binaries", lambda *a, **k: None)
    monkeypatch.setattr(rc, "warn_orphans", lambda *a, **k: None)
    rc.release_tree(
        "http://obs", "S", "PR:T", [("containers", tmp_path)], "PR", {},
        verify_timeout=0, branch_rootprj="prod", active_projects={"PR:T", "PR:T:containers"},
    )
    assert seen == [("PR:T:containers", "prod", {"PR:T", "PR:T:containers"})]
```

Append to `tests/test_sync_prerelease.py` (reuses `_tree_with_record`, `_wire`, `_Args` from that file):

```python
def test_prerelease_meta_redirects_external_paths_to_production_root(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    seen = {}
    monkeypatch.setattr(
        cmd_sync,
        "apply_mirror_meta",
        lambda apiurl, prj, path, rootprj, env, **k: seen.setdefault("meta", (prj, k.get("branch_rootprj"), k.get("active_projects"))),
    )
    monkeypatch.setattr(
        cmd_sync,
        "release_tree",
        lambda *a, **k: seen.setdefault("tree", (k.get("branch_rootprj"), k.get("active_projects"))),
    )
    cmd_sync.cmd_sync_prerelease(_Args())
    top = "home:Admin:PR:pr-5:ppg:releases:17"
    expected = {top, f"{top}:containers", f"{top}:tarballs"}
    assert seen["meta"] == (top, "home:Admin", expected)
    assert seen["tree"] == ("home:Admin", expected)
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_release_copy.py tests/test_sync_prerelease.py -k redirect`
Expected: FAIL (`TypeError: unexpected keyword argument 'branch_rootprj'` / assertion on `None`).

- [ ] **Step 3: Implement**

`percona_obs/release_copy.py`, `apply_mirror_meta`: add keyword parameters `branch_rootprj: "str | None" = None, active_projects: "set[str] | None" = None` after `publish_override`, forward `branch_rootprj=branch_rootprj, active_projects=active_projects` in both `_apply_project_config(...)` calls, and extend the docstring: "``branch_rootprj``/``active_projects`` enable the same path redirection ``sync push --branch-from`` uses: a ``subproject:`` path whose project is not in ``active_projects`` is rewritten to ``<branch_rootprj>:<subproject>`` (hop 1: the pre-release tree is the active set, production is the branch root)."

`release_tree`: add the same two keyword parameters after `verify_timeout` and pass them to the `apply_mirror_meta(...)` call inside the pairs loop.

`percona_obs/cmd_sync.py`, `cmd_sync_prerelease`: right before the top-level `apply_mirror_meta(...)` call compute

```python
    prerelease_tree = {prerelease_obs_project} | {
        f"{prerelease_obs_project}:{name}" for name, _ in subproject_pairs
    }
```

and pass `branch_rootprj=source_rootprj, active_projects=prerelease_tree` to both `apply_mirror_meta(...)` and the `release_tree(...)` lambda.

Note: with `branch_rootprj` set, `_apply_project_config` emits no `<build>` section (PR semantics) and `apply_mirror_meta` then calls `_disable_project_builds`, which adds `<build><disable/></build>` — builds stay disabled.

- [ ] **Step 4: Run tests, format, type-check**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
Expected: PASS, `0 errors`.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/release_copy.py percona_obs/cmd_sync.py tests/test_release_copy.py tests/test_sync_prerelease.py
git commit -s -m "sync prerelease: redirect external repository paths to the production root"
```

---

### Task 1: Extract the QA fan-out into the reusable `qa-fanout.yml`

**Goal:** `detect-qa-matrix`, `merge-qa-matrix` and `qa` live in a `workflow_call` workflow taking `pr_number` and `qa_types`; `obs-pr-check.yml` calls it with behaviour unchanged for labelled non-release PRs.

**Files:**
- Create: `.github/workflows/qa-fanout.yml`
- Modify: `.github/workflows/obs-pr-check.yml` (`resolve` outputs; jobs `detect-qa-matrix`, `merge-qa-matrix`, `qa` replaced by one `qa` job that `uses:` the reusable workflow)

**Acceptance Criteria:**
- [ ] `qa-fanout.yml` declares `on: workflow_call` with inputs `pr_number` (string, required) and `qa_types` (string, required, comma-separated subset of `packages,containers`), `secrets: inherit` is used by callers
- [ ] The three jobs in `qa-fanout.yml` are the current ones with `needs.resolve.outputs.pr_number` → `inputs.pr_number`, the label-derived type list → `inputs.qa_types`, and the `needs: [resolve, sync]` / `needs.build` gates removed (the caller gates)
- [ ] `obs-pr-check.yml` `resolve` gains output `qa_types` (empty when no `qa-*` label); the caller job is `qa: needs: [resolve, build]`, `if: !cancelled() && needs.build.result == 'success' && needs.resolve.outputs.qa_types != ''`, `uses: ./.github/workflows/qa-fanout.yml`, `with: {pr_number, qa_types}`, `secrets: inherit`
- [ ] Both files parse; `actionlint` passes on both when available

**Verify:** `venv/bin/python -c 'import sys,yaml; [yaml.safe_load(open(f)) for f in sys.argv[1:]]' .github/workflows/qa-fanout.yml .github/workflows/obs-pr-check.yml && (test -x /tmp/actionlint/actionlint && /tmp/actionlint/actionlint .github/workflows/qa-fanout.yml .github/workflows/obs-pr-check.yml || echo "actionlint unavailable")` → no output from yaml, actionlint clean or "unavailable"

**Steps:**

- [ ] **Step 1: Obtain actionlint (best effort, once for the whole plan)**

```bash
mkdir -p /tmp/actionlint && cd /tmp/actionlint && \
  curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/v1.7.7/scripts/download-actionlint.bash | bash -s -- 1.7.7 /tmp/actionlint || echo "actionlint download failed; YAML parse check only"
cd - >/dev/null
```

Record in the task report whether actionlint ran.

- [ ] **Step 2: Create `.github/workflows/qa-fanout.yml`**

Header:

```yaml
name: OBS QA fan-out

# Reusable QA fan-out over a PR OBS project: discover the `qa:` lanes of
# every subproject of <pr_rootprj>:pr-<N> on each OBS_INSTANCES entry, merge
# the per-instance shares, and run one `qa run` job per combo.  Called by
# obs-pr-check.yml (labelled PRs, after the builds passed) and by
# obs-release-pr.yml (release PRs, after the pre-release was populated).
# The caller decides WHEN to call; this workflow never gates on builds.

on:
  workflow_call:
    inputs:
      pr_number:
        description: "PR number; the PR OBS root is <pr_rootprj>:pr-<N>"
        required: true
        type: string
      qa_types:
        description: "Comma-separated QA kinds to run: packages,containers (or one of them)"
        required: true
        type: string

jobs:
```

Then paste the three jobs from `obs-pr-check.yml` (current lines 603-891) with these edits and nothing else:

- `detect-qa-matrix`: drop `needs: [resolve, sync]` and the whole `if:`; replace every `${{ needs.resolve.outputs.pr_number }}` with `${{ inputs.pr_number }}`; in the "Resolve QA type filter" step replace the label-derived `TYPES` computation (the two `jq` label tests) with `TYPES="${REQUESTED_TYPES}"` and add `REQUESTED_TYPES: ${{ inputs.qa_types }}` to that step's `env` (drop `LABELS_JSON`). Keep the `qa_types` intersection with the instance's `qa_types` exactly.
- `merge-qa-matrix`: `needs: [detect-qa-matrix]`, `if: '!cancelled() && needs.detect-qa-matrix.result == ''success'''`.
- `qa`: `needs: [merge-qa-matrix]`, `if: '!cancelled() && needs.merge-qa-matrix.outputs.has_matrix == ''true'''`; `${{ needs.resolve.outputs.pr_number }}` → `${{ inputs.pr_number }}`.

- [ ] **Step 3: Edit `obs-pr-check.yml`**

In `resolve`, add output `qa_types: ${{ steps.ctx.outputs.qa_types }}` and, inside the "Fetch PR context" script after `HAS_TRIGGER=...`, add:

```bash
          QA_TYPES=""
          if echo "$LABELS" | jq -e '[.[] | select(. == "qa-packages")] | length > 0' > /dev/null; then QA_TYPES="packages"; fi
          if echo "$LABELS" | jq -e '[.[] | select(. == "qa-containers")] | length > 0' > /dev/null; then QA_TYPES="${QA_TYPES:+$QA_TYPES,}containers"; fi
```

and `echo "qa_types=${QA_TYPES}"` inside the `{ ... } >> "$GITHUB_OUTPUT"` block.

Delete the `detect-qa-matrix`, `merge-qa-matrix` and `qa` jobs (lines 603-891) and append:

```yaml
  # ──────────────────────────────────────────────────────────────────────────
  # qa: the reusable fan-out (qa-fanout.yml), after the builds passed.
  # Trade-off vs. the former inline jobs: discovery no longer runs in
  # parallel with the build poll, so the per-combo check runs appear only
  # once the builds are green.
  # ──────────────────────────────────────────────────────────────────────────
  qa:
    name: OBS QA
    needs: [resolve, build]
    if: ${{ !cancelled() && needs.build.result == 'success' && needs.resolve.outputs.qa_types != '' }}
    uses: ./.github/workflows/qa-fanout.yml
    with:
      pr_number: ${{ needs.resolve.outputs.pr_number }}
      qa_types: ${{ needs.resolve.outputs.qa_types }}
    secrets: inherit
```

Update the header comment block of `obs-pr-check.yml` where it describes the QA jobs (grep `detect-qa-matrix` in the comments) to point at `qa-fanout.yml`.

- [ ] **Step 4: Verify**

Run the Verify command. Expected: no yaml errors; actionlint clean (or reported unavailable).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/qa-fanout.yml .github/workflows/obs-pr-check.yml
git commit -s -m "ci: extract the QA fan-out into the reusable qa-fanout.yml"
```

---

### Task 2: `release_pr.py` helpers and the `obs-release-pr.yml` workflow (populate + QA)

**Goal:** A release PR, on open/push/reopen or on `workflow_dispatch(pr_number)`, is checked (release-only, one in-flight per major), populates its pre-release projects on every instance with `sync prerelease`, and runs the full QA fan-out against them.

**Files:**
- Create: `.github/scripts/release_pr.py`
- Create: `.github/workflows/obs-release-pr.yml`
- Test: `tests/test_release_pr_script.py`

**Acceptance Criteria:**
- [ ] `release_pr.classify_files(paths)` → `("release", [release.yaml paths])` when every `root/**` path is under `root/*/releases/`, `("mixed", ...)` when some are not, `("none", [])` when no `root/**` path
- [ ] `release_pr.release_projects(release_yaml_paths)` → `["ppg:releases:18", ...]` (dir of each `root/<p>/releases/<n>/release.yaml` with `/`→`:`), sorted, deduplicated
- [ ] `release_pr.conflicting_prs(this_pr, this_files, open_prs)` → list of `(number, path)` for every OTHER open PR with a LOWER number that changes one of the same `release.yaml` paths (`open_prs` = `[{"number": int, "files": [paths]}]`)
- [ ] `release_pr.prerelease_project(pr_rootprj, pr_number, project)` → `f"{pr_rootprj}:pr-{pr_number}:{project}"`
- [ ] `obs-release-pr.yml`: triggers `pull_request` (branches main, paths `root/*/releases/**`, types opened/synchronize/reopened) and `workflow_dispatch` with `pr_number`; workflow concurrency group `obs-release-pr-<N>` with `cancel-in-progress: false`
- [ ] `resolve` fails on a mixed PR and on a conflict (message names the other PR and file); outputs `pr_number`, `head_sha`, `clone_url`, `release_projects` (JSON list), `release_files` (JSON list)
- [ ] `populate` runs once per `OBS_INSTANCES` entry in concurrency group `sync-main-sync-<name>` (no cancel), checks out `refs/pull/<N>/head` with full history, creates `main` and `pr-<N>` profiles with the instance slice, computes the synced commit with `percona_obs.github_api.last_synced_head_sha`, runs `sync prerelease <project> --branch-from main --synced-commit <sha>` for every release project, writes `/tmp/prerelease-report.json`, uploads it as artifact `prerelease-report-<instance>`, and posts the per-instance PR comment (Task 4 script; until Task 4 lands the step may post the current release-mode comment)
- [ ] `qa` job: `needs: [resolve, populate]`, `if: !cancelled() && needs.populate.result == 'success'`, `uses: ./.github/workflows/qa-fanout.yml` with `qa_types: packages,containers`, `secrets: inherit`
- [ ] Both files parse; `actionlint` clean when available; script tests pass

**Verify:** `venv/bin/pytest -q tests/test_release_pr_script.py && venv/bin/python -c 'import sys,yaml; [yaml.safe_load(open(f)) for f in sys.argv[1:]]' .github/workflows/obs-release-pr.yml && (test -x /tmp/actionlint/actionlint && /tmp/actionlint/actionlint .github/workflows/obs-release-pr.yml || echo "actionlint unavailable")` → PASS

**Steps:**

- [ ] **Step 1: Write the failing script tests**

`tests/test_release_pr_script.py`:

```python
"""Pure helpers of the release-PR workflow (.github/scripts/release_pr.py)."""

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent / ".github/scripts"


def _load():
    spec = importlib.util.spec_from_file_location("release_pr", _SCRIPTS / "release_pr.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classify_files():
    m = _load()
    assert m.classify_files(
        ["root/ppg/releases/18/release.yaml", "root/ppg/releases/18/CHANGELOG.md", "docs/x.md"]
    ) == ("release", ["root/ppg/releases/18/release.yaml"])
    assert m.classify_files(["root/ppg/releases/18/release.yaml", "root/ppg/staging/18/x/rpm/x.spec"])[0] == "mixed"
    assert m.classify_files(["docs/x.md"]) == ("none", [])


def test_release_projects():
    m = _load()
    assert m.release_projects(
        ["root/ppg/releases/18/release.yaml", "root/ppg/releases/17/release.yaml", "root/ppg/releases/18/release.yaml"]
    ) == ["ppg:releases:17", "ppg:releases:18"]


def test_conflicting_prs_only_older_same_file():
    m = _load()
    mine = ["root/ppg/releases/18/release.yaml"]
    others = [
        {"number": 10, "files": ["root/ppg/releases/18/release.yaml"]},
        {"number": 12, "files": ["root/ppg/releases/18/release.yaml"]},  # newer: not a conflict for 11
        {"number": 9, "files": ["root/ppg/releases/17/release.yaml"]},
        {"number": 11, "files": mine},  # self
    ]
    assert m.conflicting_prs(11, mine, others) == [(10, "root/ppg/releases/18/release.yaml")]


def test_prerelease_project():
    m = _load()
    assert m.prerelease_project("isv:percona:PR", 42, "ppg:releases:18") == "isv:percona:PR:pr-42:ppg:releases:18"
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_release_pr_script.py`
Expected: FAIL (`FileNotFoundError` / `AttributeError`).

- [ ] **Step 3: Create `.github/scripts/release_pr.py`**

```python
#!/usr/bin/env python3
"""Pure helpers for obs-release-pr.yml, plus a CLI used by its `resolve` job.

CLI:  release_pr.py classify <pr_number>
Reads the PR's changed files and every open PR's files through `gh`, and
appends to $GITHUB_OUTPUT: kind=release|mixed|none, release_files=<json>,
release_projects=<json>.  Exits 1 (with ::error::) on a mixed PR or on a
one-in-flight conflict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

_RELEASE_YAML_RE = re.compile(r"^root/[^/]+/releases/[^/]+/release\.yaml$")


def classify_files(paths: list[str]) -> tuple[str, list[str]]:
    root = [p for p in paths if p.startswith("root/")]
    if not root:
        return "none", []
    under_releases = [p for p in root if re.match(r"^root/[^/]+/releases/", p)]
    release_yamls = sorted({p for p in root if _RELEASE_YAML_RE.match(p)})
    if len(under_releases) != len(root):
        return "mixed", release_yamls
    return "release", release_yamls


def release_projects(release_yaml_paths: list[str]) -> list[str]:
    out = set()
    for p in release_yaml_paths:
        rel = p.removeprefix("root/").removesuffix("/release.yaml")
        out.add(rel.replace("/", ":"))
    return sorted(out)


def conflicting_prs(
    this_pr: int, this_files: list[str], open_prs: list[dict]
) -> list[tuple[int, str]]:
    mine = {p for p in this_files if _RELEASE_YAML_RE.match(p)}
    hits: list[tuple[int, str]] = []
    for pr in open_prs:
        number = int(pr["number"])
        if number >= this_pr:
            continue
        for path in pr.get("files") or []:
            if path in mine:
                hits.append((number, path))
    return sorted(hits)


def prerelease_project(pr_rootprj: str, pr_number: int | str, project: str) -> str:
    return f"{pr_rootprj}:pr-{pr_number}:{project}"


def _gh_json(args: list[str]):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"error: gh {' '.join(args)}: {r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def _cli_classify(pr_number: int) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    files = [f["path"] for f in _gh_json(["pr", "view", str(pr_number), "-R", repo, "--json", "files", "--jq", ".files"])]
    kind, release_files = classify_files(files)
    if kind == "mixed":
        print("::error::release PRs must change only files under root/*/releases/; this PR also changes other root/ files")
        sys.exit(1)
    open_prs = _gh_json(["pr", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", "number,files"])
    open_prs = [{"number": p["number"], "files": [f["path"] for f in p.get("files") or []]} for p in open_prs]
    conflicts = conflicting_prs(pr_number, release_files, open_prs)
    if conflicts:
        for number, path in conflicts:
            print(f"::error::open PR #{number} already releases {path}; one in-flight release PR per major")
        sys.exit(1)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"kind={kind}\n")
        fh.write(f"release_files={json.dumps(release_files)}\n")
        fh.write(f"release_projects={json.dumps(release_projects(release_files))}\n")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "classify":
        _cli_classify(int(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(2)
```

- [ ] **Step 4: Run the script tests**

Run: `venv/bin/pytest -q tests/test_release_pr_script.py`
Expected: PASS.

- [ ] **Step 5: Create `.github/workflows/obs-release-pr.yml`**

```yaml
name: OBS Release PR

# Hop 1 of the two-hop release flow (docs/superpowers/specs/
# 2026-10-13-prerelease-project-release-flow-design.md §1, §3): a release
# PR (every root/ change under root/*/releases/) populates a per-PR
# pre-release OBS project tree on every instance -- <pr_rootprj>:pr-<N>:
# <product>:releases:<major> -- with `sync prerelease`, then runs every QA
# lane the release mirrors declare against it (qa-fanout.yml).
#
# Own workflow, not obs-pr-check.yml: that one cancels superseded runs on
# every push, and a cancelled populate would leave production staging
# frozen.  Here the run-level group never cancels, and each populate leg
# serializes on the instance's "sync-main-sync-<name>" group so it never
# overlaps a staging upload.  A second push queues behind the first.
#
# Repopulate without a push: workflow_dispatch with the PR number.

on:
  pull_request:
    branches: [main]
    paths: ['root/*/releases/**']
    types: [opened, synchronize, reopened]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "Release PR number to (re)populate"
        required: true

concurrency:
  group: obs-release-pr-${{ inputs.pr_number || github.event.number }}
  cancel-in-progress: false

jobs:
  resolve:
    name: Resolve release PR
    runs-on: ubuntu-latest
    permissions:
      pull-requests: read
    outputs:
      pr_number:        ${{ steps.ctx.outputs.pr_number }}
      head_sha:         ${{ steps.ctx.outputs.head_sha }}
      clone_url:        ${{ steps.ctx.outputs.clone_url }}
      release_files:    ${{ steps.classify.outputs.release_files }}
      release_projects: ${{ steps.classify.outputs.release_projects }}
    steps:
      - uses: actions/checkout@v4
        with:
          sparse-checkout: .github/scripts
      - name: Fetch PR context
        id: ctx
        env:
          GH_TOKEN: ${{ github.token }}
          PR: ${{ inputs.pr_number || github.event.number }}
        run: |
          DATA=$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR}")
          STATE=$(echo "$DATA" | jq -r '.state')
          {
            echo "pr_number=${PR}"
            echo "head_sha=$(echo "$DATA" | jq -r '.head.sha')"
            echo "clone_url=$(echo "$DATA" | jq -r '.head.repo.clone_url')"
          } >> "$GITHUB_OUTPUT"
          if [ "$STATE" != "open" ] && [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            echo "::notice::PR #${PR} is ${STATE}; repopulating anyway (recovery of a merged release)"
          fi
      # Release-only + one-in-flight-per-major guard (spec §1).
      - name: Classify the PR and check for in-flight conflicts
        id: classify
        env:
          GH_TOKEN: ${{ github.token }}
        run: python3 .github/scripts/release_pr.py classify "${{ steps.ctx.outputs.pr_number }}"
      - name: Require a release PR
        if: steps.classify.outputs.kind != 'release'
        run: |
          echo "::error::not a release PR (kind=${{ steps.classify.outputs.kind }}); nothing to populate"
          exit 1

  populate:
    name: Populate pre-release (${{ matrix.instance.name }})
    needs: [resolve]
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    timeout-minutes: 180
    strategy:
      fail-fast: false
      matrix:
        instance: ${{ fromJSON(vars.OBS_INSTANCES) }}
    # Never overlap this instance's staging upload (sync-main's sync job
    # uses the same group); never cancel a populate mid-freeze.
    concurrency:
      group: sync-main-sync-${{ matrix.instance.name }}
      cancel-in-progress: false
    permissions:
      pull-requests: write
      packages: read
      contents: read
    env:
      PR_NUMBER: ${{ needs.resolve.outputs.pr_number }}
      OBS_APIURL: ${{ matrix.instance.apiurl }}
      OBS_WEB_URL: ${{ vars.OBS_WEB_URL }}
      OBS_ROOTPRJ: ${{ matrix.instance.rootprj }}
      OBS_PR_ROOTPRJ: ${{ matrix.instance.pr_rootprj }}
      OBS_INSTANCE: ${{ matrix.instance.name }}
    steps:
      - uses: actions/checkout@v4
        with:
          # The PR head, not the merge ref: release.yaml and the mirrors are
          # what the operator cut.  Full history: the record check diffs
          # source_commit against the synced main commit.
          ref: refs/pull/${{ needs.resolve.outputs.pr_number }}/head
          fetch-depth: 0

      - uses: ./.github/actions/obs-setup
        with:
          obs-apiurl: ${{ matrix.instance.apiurl }}
          obs-user: ${{ matrix.instance.user || vars.OBS_USER }}
          obs-password: ${{ secrets[format('OBS_PASSWORD_{0}', matrix.instance.name)] }}

      # `main` = the production root (staging source); `pr-N` = this PR's
      # root (pre-release target).  Same slice flags as obs-pr-check.
      - name: Create percona-obs profiles (${{ matrix.instance.name }})
        shell: bash
        env:
          INCLUDE_REPOS: ${{ matrix.instance.include_repos }}
          EXCLUDE_REPOS: ${{ matrix.instance.exclude_repos }}
          INCLUDE_PROJECTS: ${{ matrix.instance.include_projects }}
          EXCLUDE_PROJECTS: ${{ matrix.instance.exclude_projects }}
          CLONE_URL: ${{ needs.resolve.outputs.clone_url }}
          MAIN_REPO_URL: ${{ github.server_url }}/${{ github.repository }}.git
          INSTANCE_ENV: ${{ toJSON(matrix.instance.env) }}
        run: |
          set -euo pipefail
          env_args=()
          if [ -n "${INSTANCE_ENV:-}" ] && [ "$INSTANCE_ENV" != "null" ]; then
            while IFS= read -r kv; do
              if [ -n "$kv" ]; then env_args+=(-e "$kv"); fi
            done <<<"$(jq -r 'to_entries[] | "\(.key):\(.value)"' <<<"$INSTANCE_ENV")"
          fi
          inst=()
          if [ -n "${INCLUDE_REPOS:-}" ]; then inst+=(--include-repos "$INCLUDE_REPOS"); fi
          if [ -n "${EXCLUDE_REPOS:-}" ]; then inst+=(--exclude-repos "$EXCLUDE_REPOS"); fi
          if [ -n "${INCLUDE_PROJECTS:-}" ]; then inst+=(--include-projects "$INCLUDE_PROJECTS"); fi
          if [ -n "${EXCLUDE_PROJECTS:-}" ]; then inst+=(--exclude-projects "$EXCLUDE_PROJECTS"); fi
          venv/bin/python -m percona_obs -A "$OBS_APIURL" -R "$OBS_ROOTPRJ" \
            -e "REMOTE_OBS_ORG_INTERCONNECT:" -e "PERCONA_OBS_PACKAGING_BRANCH:main" \
            -e "PERCONA_OBS_PACKAGING_REPO:${MAIN_REPO_URL}" "${env_args[@]}" \
            profile create main "${inst[@]}"
          venv/bin/python -m percona_obs -A "$OBS_APIURL" -R "${OBS_PR_ROOTPRJ}:pr-${PR_NUMBER}" \
            -e "REMOTE_OBS_ORG_INTERCONNECT:" -e "PERCONA_OBS_PACKAGING_BRANCH:refs/pull/${PR_NUMBER}/head" \
            -e "PERCONA_OBS_PACKAGING_REPO:${CLONE_URL}" "${env_args[@]}" \
            profile create "pr-${PR_NUMBER}" "${inst[@]}"

      # The commit of main whose staging tree OBS holds: the newest completed
      # sync-main run whose sync jobs all succeeded.  Passed explicitly so the
      # tool never has to guess the repository from the PR's clone URL.
      - name: Resolve the synced main commit
        id: synced
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          SHA=$(venv/bin/python -c "from percona_obs.github_api import last_synced_head_sha; print(last_synced_head_sha('${GITHUB_REPOSITORY}'))")
          echo "sha=${SHA}" >> "$GITHUB_OUTPUT"
          echo "synced main commit: ${SHA}"

      - name: Populate the pre-release projects
        id: populate
        shell: bash
        env:
          RELEASE_PROJECTS: ${{ needs.resolve.outputs.release_projects }}
          SYNCED: ${{ steps.synced.outputs.sha }}
        run: |
          set -uo pipefail
          rc=0
          echo '[]' > /tmp/prerelease-report.json
          for proj in $(jq -r '.[]' <<<"$RELEASE_PROJECTS"); do
            echo "== sync prerelease ${proj} (${OBS_INSTANCE})"
            if venv/bin/python -u -m percona_obs -P "pr-${PR_NUMBER}" sync prerelease "$proj" \
                 --branch-from main --synced-commit "$SYNCED"; then
              outcome=success
            else
              outcome=failure; rc=1
            fi
            SRC=$(venv/bin/python -c "import sys,yaml; from percona_obs.release_record import current_release; e=current_release(yaml.safe_load(open('root/'+'$proj'.replace(':','/')+'/release.yaml'))); print(e.source_commit if e else '')")
            jq -c --arg p "$proj" --arg o "$outcome" --arg s "$SRC" --arg pre "${OBS_PR_ROOTPRJ}:pr-${PR_NUMBER}:${proj}" \
              '. + [{project: $p, prerelease: $pre, outcome: $o, source_commit: $s}]' \
              /tmp/prerelease-report.json > /tmp/prerelease-report.tmp && mv /tmp/prerelease-report.tmp /tmp/prerelease-report.json
          done
          cat /tmp/prerelease-report.json
          exit $rc

      - name: Upload populate report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: prerelease-report-${{ matrix.instance.name }}
          path: /tmp/prerelease-report.json
          retention-days: 7

      # Per-instance comment (post_pr_comment.py keys on OBS_INSTANCE).
      - name: Post pre-release comment
        if: always()
        env:
          GH_TOKEN: ${{ github.token }}
          IS_RELEASE_PR: 'true'
          SYNC_OUTCOME: ''
          RELEASE_OUTCOME: ${{ steps.populate.outcome }}
          PRERELEASE_REPORT: /tmp/prerelease-report.json
          POLL_OUTCOME: ''
          WORKFLOW_RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: python .github/scripts/post_pr_comment.py

  # Every QA lane the release mirrors declare, against the pre-release.
  qa:
    name: OBS QA
    needs: [resolve, populate]
    if: ${{ !cancelled() && needs.populate.result == 'success' }}
    uses: ./.github/workflows/qa-fanout.yml
    with:
      pr_number: ${{ needs.resolve.outputs.pr_number }}
      qa_types: packages,containers
    secrets: inherit
```

`actionlint` may flag `inputs.pr_number` under a `pull_request` event as possibly empty; that is the intended `||` fallback. If it flags the `concurrency` expression, keep it: both event types resolve one of the two.

- [ ] **Step 6: Verify**

Run the Verify command. Expected: tests pass, yaml parses, actionlint clean or unavailable.

- [ ] **Step 7: Commit**

```bash
git add .github/scripts/release_pr.py .github/workflows/obs-release-pr.yml tests/test_release_pr_script.py
git commit -s -m "ci: obs-release-pr.yml populates the pre-release and runs release QA"
```

---

### Task 3: `obs-pr-check.yml` gates release PRs out

**Goal:** `obs-pr-check.yml` no longer handles release PRs at all (no dry-run, no sync, no comment); `obs-release-pr.yml` owns them.

**Files:**
- Modify: `.github/workflows/obs-pr-check.yml` (`resolve` job `if` and outputs; `sync` job `if`, the "Detect release-only PR" step inside `sync`, the "Create main profile (release dry-run)" and "Release dry-run" steps, the sync-side comment condition; `build` job `if`; header comments)

**Acceptance Criteria:**
- [ ] `resolve` keeps output `is_release_pr` (computed as today) and the job-level `if`
- [ ] `sync` job `if: needs.resolve.outputs.has_trigger_label == 'true' && needs.resolve.outputs.is_release_pr != 'true'`; its `outputs.is_release_pr` and the in-job "Detect release-only PR", "Create main profile (release dry-run)" and "Release dry-run" steps are deleted; "Plan sync" and "Sync PR to OBS" drop the `steps.detect.outputs.is_release_pr != 'true' &&` clause; the sync-side comment step condition becomes `always() && steps.profiles.outputs.skip != 'true' && steps.sync.outcome != 'success'` with `IS_RELEASE_PR: 'false'` and `RELEASE_OUTCOME: ''`
- [ ] `build` job `if: needs.sync.result == 'success'` (release clause dropped)
- [ ] The header comment explains that release PRs are handled by `obs-release-pr.yml`
- [ ] File parses; `actionlint` clean when available

**Verify:** `venv/bin/python -c 'import yaml; yaml.safe_load(open(".github/workflows/obs-pr-check.yml"))' && grep -c "release dry-run\|sync release" .github/workflows/obs-pr-check.yml` → yaml ok, count `0`

**Steps:**

- [ ] **Step 1: Apply the edits listed in the acceptance criteria.** Keep the `resolve` "Detect release-only PR" step (it is the gate). In the header comment (lines 16-21 today: "Release-only PRs ... reach `sync` without a trigger label ...") replace with: "Release-only PRs (all root/ changes under root/*/releases/) are NOT handled here: obs-release-pr.yml populates their pre-release OBS projects and runs release QA. `resolve` still detects them so `sync` can gate them out even when a trigger label is present."

- [ ] **Step 2: Verify**

Run the Verify command plus `actionlint` when available. Expected: yaml ok, no remaining dry-run references.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/obs-pr-check.yml
git commit -s -m "ci: obs-pr-check no longer handles release PRs"
```

---

### Task 4: `post_pr_comment.py` pre-release mode

**Goal:** On a release PR the per-instance comment names the pre-release projects (linked), the source commit, the outcome per project, and how to repopulate; rendering is a pure, tested function.

**Files:**
- Modify: `.github/scripts/post_pr_comment.py`
- Test: `tests/test_post_pr_comment.py`

**Acceptance Criteria:**
- [ ] New pure function `render_prerelease_comment(marker, suffix, report, web_url, run_url, timestamp, pr_number, repo)` returns the markdown; `report` is the list written by `obs-release-pr.yml` (`[{project, prerelease, outcome, source_commit}]`)
- [ ] Heading `## OBS Release PR — ✅ Pre-release populated` when every outcome is `success`, `❌ Pre-release population failed` otherwise, `⚠️ no pre-release populated` for an empty list
- [ ] One table row per project: project, linked pre-release (`<web_url>/project/show/<prerelease>`), outcome, `source_commit` shortened to 12 chars
- [ ] A line "Repopulate without a push: `gh workflow run obs-release-pr.yml -f pr_number=<N>`" and a line pointing at the workflow run
- [ ] `main()` uses the new function when `IS_RELEASE_PR == 'true'` and reads the report from `PRERELEASE_REPORT` (missing/unreadable file → empty list); the old dry-run branch is removed; all other modes unchanged

**Verify:** `venv/bin/pytest -q tests/test_post_pr_comment.py` → PASS

**Steps:**

- [ ] **Step 1: Write the failing test**

`tests/test_post_pr_comment.py`:

```python
"""Rendering of the pre-release PR comment (.github/scripts/post_pr_comment.py)."""

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent / ".github/scripts"


def _load():
    spec = importlib.util.spec_from_file_location("post_pr_comment", _SCRIPTS / "post_pr_comment.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_REPORT = [
    {"project": "ppg:releases:18", "prerelease": "isv:percona:PR:pr-7:ppg:releases:18", "outcome": "success", "source_commit": "9e9d9738c0ffee1234567890"},
    {"project": "ppg:releases:17", "prerelease": "isv:percona:PR:pr-7:ppg:releases:17", "outcome": "failure", "source_commit": "9e9d9738c0ffee1234567890"},
]


def test_render_failure_when_any_project_failed():
    m = _load()
    out = m.render_prerelease_comment("<!-- m -->", " (boo)", _REPORT, "https://obs", "https://run", "now", "7", "o/r")
    assert out.startswith("<!-- m -->\n## OBS Release PR — ❌ Pre-release population failed (boo)")
    assert "[isv:percona:PR:pr-7:ppg:releases:18](https://obs/project/show/isv:percona:PR:pr-7:ppg:releases:18)" in out
    assert "9e9d9738c0ff" in out and "9e9d9738c0ffee1234567890" not in out
    assert "gh workflow run obs-release-pr.yml -f pr_number=7" in out
    assert "https://run" in out


def test_render_success_and_empty():
    m = _load()
    ok = [dict(_REPORT[0])]
    assert "✅ Pre-release populated" in m.render_prerelease_comment("<!-- m -->", "", ok, "https://obs", "r", "t", "7", "o/r")
    assert "⚠️ no pre-release populated" in m.render_prerelease_comment("<!-- m -->", "", [], "https://obs", "r", "t", "7", "o/r")
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_post_pr_comment.py`
Expected: FAIL (`AttributeError: render_prerelease_comment`).

- [ ] **Step 3: Implement**

Add above `main()`:

```python
def render_prerelease_comment(
    marker: str,
    suffix: str,
    report: list[dict],
    web_url: str,
    run_url: str,
    timestamp: str,
    pr_number: str,
    repo: str,
) -> str:
    if not report:
        heading = "## OBS Release PR — ⚠️ no pre-release populated" + suffix
    elif all(r.get("outcome") == "success" for r in report):
        heading = "## OBS Release PR — ✅ Pre-release populated" + suffix
    else:
        heading = "## OBS Release PR — ❌ Pre-release population failed" + suffix
    lines = [
        marker,
        heading,
        "",
        "Release QA runs against the pre-release projects below; nothing is built in OBS.",
        "",
        "| Release | Pre-release project | Populate | Source commit |",
        "|---|---|---|---|",
    ]
    for r in report:
        pre = r.get("prerelease", "")
        icon = {"success": "✅", "failure": "❌"}.get(r.get("outcome", ""), "⚠️")
        lines.append(
            f"| `{r.get('project', '')}` | [{pre}]({web_url}/project/show/{pre}) "
            f"| {icon} {r.get('outcome', '')} | `{(r.get('source_commit') or '')[:12]}` |"
        )
    lines += [
        "",
        f"Repopulate without a push: `gh workflow run obs-release-pr.yml -f pr_number={pr_number}` "
        f"(after a staging fix, re-run `project release` and push instead).",
        f"Details: [workflow run]({run_url}).",
        "",
        f"> _Updated: {timestamp}_",
    ]
    return "\n".join(lines)
```

In `main()`: replace the whole `if is_release_pr:` branch body with

```python
    if is_release_pr:
        try:
            report = json.load(open(os.environ.get("PRERELEASE_REPORT", "/tmp/prerelease-report.json")))
        except (OSError, json.JSONDecodeError):
            report = []
        body = render_prerelease_comment(
            marker, suffix, report if isinstance(report, list) else [],
            obs_web_url, workflow_run_url, timestamp, pr_number, repo,
        )
        lines = body.split("\n")
```

(keeping the later `body = "\n".join(lines)` and the gh post/patch logic untouched). Update the module docstring: `RELEASE_OUTCOME` is now informational only; `PRERELEASE_REPORT` documented. Remove the now-unused `obs_rootprj` read only if nothing else uses it (grep).

- [ ] **Step 4: Run tests**

Run: `venv/bin/pytest -q tests/test_post_pr_comment.py && venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/post_pr_comment.py tests/test_post_pr_comment.py
git commit -s -m "ci: pre-release mode of the PR comment"
```

---

### Task 5: `obs-pr-cleanup.yml` — tag, one dispatch, no lock, keep the pre-release

**Goal:** A merged release PR gets one tag per changed `release.yaml` and exactly one `obs-release.yml` dispatch carrying `pr_number` and all tags; the sync-main lock code is gone; the `delete` job skips merged release PRs.

**Files:**
- Modify: `.github/workflows/obs-pr-cleanup.yml` (header comment, "Tag release and dispatch obs-release" step, `delete` job `if`)

**Acceptance Criteria:**
- [ ] The tag step contains no `gh workflow disable/enable`, no `release_lock_if_unused`, no `trap`; it loops over the changed `release.yaml` files creating tags (same `gh api .../git/refs` call and "already exists" tolerance as today), collects them into `TAGS`, then runs once: `gh workflow run obs-release.yml --ref main -f "pr_number=${PR_NUMBER}" -f "tags=${TAGS}"`; a dispatch failure fails the job with `::error::` naming the manual command
- [ ] `release-dispatch` exposes output `is_release_pr`
- [ ] `delete` job: `needs: [release-dispatch]`, `if: always() && !(github.event.pull_request.merged == true && needs.release-dispatch.outputs.is_release_pr == 'true')`
- [ ] Header comment updated (no lock; pre-release deleted by obs-release.yml after a successful final copy)
- [ ] File parses; `actionlint` clean when available

**Verify:** `venv/bin/python -c 'import yaml; yaml.safe_load(open(".github/workflows/obs-pr-cleanup.yml"))' && grep -c "workflow disable\|workflow enable\|release_lock" .github/workflows/obs-pr-cleanup.yml` → yaml ok, count `0`

**Steps:**

- [ ] **Step 1: Replace the tag-and-dispatch step script** with:

```bash
          set -euo pipefail
          FILES=$(gh pr view "$PR_NUMBER" --json files \
            --jq '.files[].path | select(test("^root/[^/]+/releases/[^/]+/release\\.yaml$"))' | sort -u)
          [ -z "$FILES" ] && { echo "No release.yaml changed; nothing to tag."; exit 0; }
          TAGS=""
          while IFS= read -r release_file; do
            TAG=$(git show "${MERGE_SHA}:${release_file}" | venv/bin/python3 -c \
              "import sys,yaml; d=yaml.safe_load(sys.stdin); r=d.get('releases') or []; last=r[-1] if r else d.get('revision') or ''; print(last.get('tag','') if isinstance(last, dict) else last)")
            [ -z "$TAG" ] && continue
            echo "Creating tag ${TAG} at ${MERGE_SHA}"
            if ! OUT=$(gh api "repos/${GITHUB_REPOSITORY}/git/refs" -X POST \
                -f "ref=refs/tags/${TAG}" -f "sha=${MERGE_SHA}" 2>&1); then
              if echo "$OUT" | grep -q "Reference already exists"; then
                echo "Tag ${TAG} already exists — dispatching anyway"
              else
                echo "::error::Failed to create tag ${TAG}: ${OUT}"
                exit 1
              fi
            fi
            TAGS="${TAGS:+$TAGS }${TAG}"
          done <<< "$FILES"
          [ -z "$TAGS" ] && { echo "No tag derived; nothing to dispatch."; exit 0; }
          echo "Dispatching obs-release.yml with pr_number=${PR_NUMBER} tags=${TAGS}"
          if ! gh workflow run obs-release.yml --ref main -f "pr_number=${PR_NUMBER}" -f "tags=${TAGS}"; then
            echo "::error::Failed to dispatch obs-release.yml. Run manually: gh workflow run obs-release.yml -f pr_number=${PR_NUMBER} -f tags=\"${TAGS}\""
            exit 1
          fi
```

Keep the step's `env` (`GH_TOKEN`, `MERGE_SHA`) and `if:`. Delete the lock comment paragraph above it; the `actions: write` permission stays (dispatch + cache deletion).

- [ ] **Step 2: Outputs and the delete gate.** Add to `release-dispatch`: `outputs: { is_release_pr: ${{ steps.detect.outputs.is_release_pr }} }`. On `delete`: add `needs: [release-dispatch]` and `if: always() && !(github.event.pull_request.merged == true && needs.release-dispatch.outputs.is_release_pr == 'true')`, with a comment: "A merged release PR's project tree is the pre-release obs-release.yml copies from; obs-release.yml deletes it after a successful final copy. Closed-unmerged release PRs are cleaned here like any PR."

- [ ] **Step 3: Header comment.** Replace the paragraph mentioning "the obs-release dispatch with its sync-main lock" with "tagging and ONE obs-release dispatch per PR (pr_number + all tags; no lock: the released binaries sit in the pre-release, not in staging)".

- [ ] **Step 4: Verify, commit**

```bash
git add .github/workflows/obs-pr-cleanup.yml
git commit -s -m "ci: obs-pr-cleanup tags and dispatches obs-release once, without the lock"
```

---

### Task 6: `obs-release.yml` — hop 2 per instance, finalize, no lock

**Goal:** `obs-release.yml` takes `pr_number` and `tags`, runs `sync release <project> --from <pre-release>` per tag on every instance, then creates one GitHub release per tag and deletes the PR project tree on every instance; the lock jobs are gone.

**Files:**
- Modify: `.github/workflows/obs-release.yml` (rewrite)

**Acceptance Criteria:**
- [ ] `workflow_dispatch` inputs: `pr_number` (required), `tags` (required, space-separated); validation step rejects a non-numeric `pr_number` and any tag not matching `^[a-z0-9-]+/([0-9]+(\.[0-9]+)+|[a-z][a-z0-9]*)-[0-9]+$`
- [ ] No `lock`/`unlock` jobs; no `gh workflow disable/enable`; no `sync-main-sync` plain group
- [ ] `release` job: matrix over `OBS_INSTANCES`, concurrency `sync-main-sync-<name>` (no cancel), checkout `refs/tags/<first tag>` full history, `main` profile with the instance slice (as today), then for each tag in order: derive `<product>:releases:<major>` (same case logic as today), run `venv/bin/python -m percona_obs -P main sync release "<project>" --from "<pr_rootprj>:pr-<N>:<project>"`
- [ ] `finalize` job: `needs: [validate, release]`, `if: always() && needs.validate.result == 'success'`; on a failed copy prints `::error::` with the re-dispatch command, states the pre-release was kept and fails; otherwise creates/updates one GitHub release per tag from `root/<product>/releases/<major>/CHANGELOG.md`
- [ ] `delete` matrix job per instance (`needs: [validate, release, finalize]`, only when both succeeded) runs `sync delete --yes --recursive --from-obs` with a `pr-<N>` profile created after `obs-setup`
- [ ] File parses; `actionlint` clean when available

**Verify:** `venv/bin/python -c 'import yaml; yaml.safe_load(open(".github/workflows/obs-release.yml"))' && grep -c "workflow disable\|workflow enable\|lock" .github/workflows/obs-release.yml` → yaml ok, count `0`

**Steps:**

- [ ] **Step 1: Rewrite the file**

```yaml
name: OBS Release

# Hop 2 of the two-hop release flow: copy a merged release PR's pre-release
# OBS project tree (<pr_rootprj>:pr-<N>:<product>:releases:<major>) into the
# release project, publish the GitHub releases and delete the pre-release.
# Dispatched by obs-pr-cleanup.yml with the PR number and every tag the PR
# created (one dispatch per PR).  workflow_dispatch is the ONLY trigger.
#
# Staging is never touched here, so there is no lock on sync-main: the
# released binaries already sit in the pre-release.  A failed leg keeps the
# pre-release in place; recovery is a re-dispatch with the same inputs:
#   gh workflow run obs-release.yml -f pr_number=42 -f tags="ppg/17.12-1 ppg/18.7-1"

on:
  workflow_dispatch:
    inputs:
      pr_number:
        description: "Merged release PR number (its pre-release tree is the copy source)"
        required: true
      tags:
        description: "Release tags created from that PR, space-separated (e.g. ppg/18.7-1)"
        required: true

jobs:
  validate:
    name: Validate inputs
    runs-on: ubuntu-latest
    outputs:
      first_tag: ${{ steps.v.outputs.first_tag }}
    steps:
      - id: v
        shell: bash
        run: |
          set -euo pipefail
          PR="${{ inputs.pr_number }}"
          echo "$PR" | grep -Eq '^[0-9]+$' || { echo "::error::pr_number '$PR' is not a number"; exit 1; }
          FIRST=""
          for TAG in ${{ inputs.tags }}; do
            echo "$TAG" | grep -Eq '^[a-z0-9-]+/([0-9]+(\.[0-9]+)+|[a-z][a-z0-9]*)-[0-9]+$' \
              || { echo "::error::tag '$TAG' does not match <product>/<major.minor-N> or <product>/<name-N>"; exit 1; }
            FIRST="${FIRST:-$TAG}"
          done
          [ -n "$FIRST" ] || { echo "::error::tags is empty"; exit 1; }
          echo "first_tag=${FIRST}" >> "$GITHUB_OUTPUT"

  release:
    name: Release to OBS (${{ matrix.instance.name }})
    needs: validate
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    strategy:
      fail-fast: false
      matrix:
        instance: ${{ fromJSON(vars.OBS_INSTANCES) }}
    # The final hop writes release-project meta; never overlap this
    # instance's sync-main upload (same group as sync-main's sync job).
    concurrency:
      group: sync-main-sync-${{ matrix.instance.name }}
      cancel-in-progress: false
    permissions:
      contents: read
      packages: read
    env:
      OBS_APIURL: ${{ matrix.instance.apiurl }}
      OBS_ROOTPRJ: ${{ matrix.instance.rootprj }}
      OBS_PR_ROOTPRJ: ${{ matrix.instance.pr_rootprj }}
      PR_NUMBER: ${{ inputs.pr_number }}
    steps:
      - uses: actions/checkout@v4
        with:
          # All tags of one PR point at the same commit; any of them is the
          # reviewed release tree.
          ref: refs/tags/${{ needs.validate.outputs.first_tag }}
          fetch-depth: 0

      - uses: ./.github/actions/obs-setup
        with:
          obs-apiurl: ${{ matrix.instance.apiurl }}
          obs-user: ${{ matrix.instance.user || vars.OBS_USER }}
          obs-password: ${{ secrets[format('OBS_PASSWORD_{0}', matrix.instance.name)] }}

      - name: Create percona-obs profile (${{ matrix.instance.name }})
        shell: bash
        env:
          INCLUDE_REPOS: ${{ matrix.instance.include_repos }}
          EXCLUDE_REPOS: ${{ matrix.instance.exclude_repos }}
          INCLUDE_PROJECTS: ${{ matrix.instance.include_projects }}
          EXCLUDE_PROJECTS: ${{ matrix.instance.exclude_projects }}
          INSTANCE_ENV: ${{ toJSON(matrix.instance.env) }}
        run: |
          set -euo pipefail
          args=()
          if [ -n "${INCLUDE_REPOS:-}" ]; then args+=(--include-repos "$INCLUDE_REPOS"); fi
          if [ -n "${EXCLUDE_REPOS:-}" ]; then args+=(--exclude-repos "$EXCLUDE_REPOS"); fi
          if [ -n "${INCLUDE_PROJECTS:-}" ]; then args+=(--include-projects "$INCLUDE_PROJECTS"); fi
          if [ -n "${EXCLUDE_PROJECTS:-}" ]; then args+=(--exclude-projects "$EXCLUDE_PROJECTS"); fi
          env_args=()
          if [ -n "${INSTANCE_ENV:-}" ] && [ "$INSTANCE_ENV" != "null" ]; then
            while IFS= read -r kv; do
              if [ -n "$kv" ]; then env_args+=(-e "$kv"); fi
            done <<<"$(jq -r 'to_entries[] | "\(.key):\(.value)"' <<<"$INSTANCE_ENV")"
          fi
          venv/bin/python -m percona_obs \
            -A "$OBS_APIURL" -R "$OBS_ROOTPRJ" \
            -e "REMOTE_OBS_ORG_INTERCONNECT:" \
            -e "PERCONA_OBS_PACKAGING_BRANCH:main" \
            -e "PERCONA_OBS_PACKAGING_REPO:${{ github.server_url }}/${{ github.repository }}.git" \
            "${env_args[@]}" \
            profile create main "${args[@]}"

      # Tag ppg/17.9-1   → ppg:releases:17 ; tag ppg/common-3 → ppg:releases:common
      - name: Release every tag from the pre-release
        shell: bash
        run: |
          set -euo pipefail
          for TAG in ${{ inputs.tags }}; do
            PRODUCT="${TAG%%/*}"; VERSION="${TAG#*/}"
            case "$VERSION" in
              [0-9]*) MAJOR="${VERSION%%.*}" ;;
              *)      MAJOR="${VERSION%-*}" ;;
            esac
            PROJECT="${PRODUCT}:releases:${MAJOR}"
            FROM="${OBS_PR_ROOTPRJ}:pr-${PR_NUMBER}:${PROJECT}"
            echo "== sync release ${PROJECT} --from ${FROM}  (${TAG})"
            venv/bin/python -m percona_obs -P main sync release "$PROJECT" --from "$FROM"
          done

  finalize:
    name: Publish GitHub releases and delete the pre-release
    needs: [validate, release]
    if: always() && needs.validate.result == 'success'
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    permissions:
      contents: write
      packages: read
    steps:
      - uses: actions/checkout@v4
        with:
          ref: refs/tags/${{ needs.validate.outputs.first_tag }}
          fetch-depth: 0

      - name: Report a failed copy
        if: needs.release.result != 'success'
        run: |
          echo "::error::sync release --from failed on at least one instance; the pre-release of PR #${{ inputs.pr_number }} was KEPT. Fix the cause and re-dispatch: gh workflow run obs-release.yml -f pr_number=${{ inputs.pr_number }} -f tags=\"${{ inputs.tags }}\""
          exit 1

      # Idempotent: an existing release (re-run) gets its notes updated.
      - name: Create GitHub releases
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: |
          set -euo pipefail
          for TAG in ${{ inputs.tags }}; do
            PRODUCT="${TAG%%/*}"; VERSION="${TAG#*/}"
            case "$VERSION" in
              [0-9]*) MAJOR="${VERSION%%.*}" ;;
              *)      MAJOR="${VERSION%-*}" ;;
            esac
            CHANGELOG="root/${PRODUCT}/releases/${MAJOR}/CHANGELOG.md"
            BODY=$(python3 -c \
              "import re,sys; content=open(sys.argv[2]).read(); m=re.search(r'(## \['+re.escape(sys.argv[1])+r'\].*?)(?=\n## \[|\Z)',content,re.DOTALL); print(m.group(1).strip() if m else '')" \
              "$VERSION" "$CHANGELOG" 2>/dev/null || true)
            gh release create "$TAG" --title "$TAG" --notes "${BODY:-No changelog available.}" \
              || gh release edit "$TAG" --notes "${BODY:-No changelog available.}"
          done

  # The pre-release has done its job on every instance: one leg per
  # OBS_INSTANCES entry, each with its own credentials (same shape as
  # obs-pr-cleanup.yml's delete job).  Only after every copy succeeded and
  # the GitHub releases exist.
  delete:
    name: Delete the pre-release (${{ matrix.instance.name }})
    needs: [validate, release, finalize]
    if: needs.release.result == 'success' && needs.finalize.result == 'success'
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    strategy:
      fail-fast: false
      matrix:
        instance: ${{ fromJSON(vars.OBS_INSTANCES) }}
    permissions:
      packages: read
    env:
      PR_NUMBER: ${{ inputs.pr_number }}
      OBS_APIURL: ${{ matrix.instance.apiurl }}
      OBS_PR_ROOTPRJ: ${{ matrix.instance.pr_rootprj }}
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/obs-setup
        with:
          obs-apiurl: ${{ matrix.instance.apiurl }}
          obs-user: ${{ matrix.instance.user || vars.OBS_USER }}
          obs-password: ${{ secrets[format('OBS_PASSWORD_{0}', matrix.instance.name)] }}
      - name: Create percona-obs profile
        run: |
          venv/bin/python -m percona_obs -A "$OBS_APIURL" -R "${OBS_PR_ROOTPRJ}:pr-${PR_NUMBER}" \
            -e "REMOTE_OBS_ORG_INTERCONNECT:" -e "PERCONA_OBS_PACKAGING_BRANCH:main" \
            -e "PERCONA_OBS_PACKAGING_REPO:${{ github.server_url }}/${{ github.repository }}.git" \
            profile create "pr-${PR_NUMBER}"
      - name: Delete the pre-release project tree
        run: |
          venv/bin/python -m percona_obs --verbose -P "pr-${PR_NUMBER}" \
            sync delete --yes --recursive --from-obs
```

`finalize` needs no OBS credentials (it only runs `gh`), so it does not use `obs-setup`; the `delete` job authenticates per instance through the action. If `finalize` fails after the releases were created, a re-dispatch is idempotent (`gh release edit`).

- [ ] **Step 2: Verify, commit**

```bash
git add .github/workflows/obs-release.yml
git commit -s -m "ci: obs-release copies the pre-release into the release project, no lock"
```

---

### Task 7: `sync-main.yml` — drop the release-only skip

**Goal:** A push whose `root/` changes are all under `root/*/releases/` syncs like any other push; nothing races it because the released images already sit in the pre-release.

**Files:**
- Modify: `.github/workflows/sync-main.yml` (header comment, the "Detect release-only push" step, the `release_only` output, the four `steps.detect.outputs.release_only != 'true'` conditions, `poll` job `if`)

**Acceptance Criteria:**
- [ ] No `release_only` output, no detect step, no `release_only` conditions remain; the `poll` job keeps `needs: sync` and no `if`
- [ ] The header comment paragraph about release-only pushes is replaced by one sentence: "Merging a release PR raises PPG_RELEASE; the next sync retags the staging images, which is safe because the released images already sit in that PR's pre-release project."
- [ ] File parses; `actionlint` clean when available

**Verify:** `venv/bin/python -c 'import yaml; yaml.safe_load(open(".github/workflows/sync-main.yml"))' && grep -c "release_only" .github/workflows/sync-main.yml` → yaml ok, count `0`

**Steps:**

- [ ] **Step 1: Apply the removals.** The steps "Sync to OBS", "Prune stale cache entries" (keep `if: always()`), "Upload sync report" lose their `release_only` clauses; delete the detect step and the `outputs:` block of `sync` (nothing else reads it: `grep -rn release_only .github/` must be empty afterwards).

- [ ] **Step 2: Verify, commit**

```bash
git add .github/workflows/sync-main.yml
git commit -s -m "ci: sync-main no longer skips release-only pushes"
```

---

### Task 8: Documentation

**Goal:** The tool reference, the architecture reference and the tree READMEs describe the live two-hop process and the five workflows as they now behave.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md` ("Releasing packages": the process list, "Step 2 — CI ships the release", the "Pending-cancellation race" paragraph, the rollout notes added by PR #142)
- Modify: `.github/copilot-instructions.md` ("GitHub Actions CI/CD": Workflow 2 (obs-pr-check), Workflow 3 (obs-pr-cleanup), new "Workflow 6 — obs-release-pr.yml" and "Workflow 7 — qa-fanout.yml", the obs-release description, Workflow 1's lock sentence)
- Modify: `root/README.md`, `root/ppg/releases/README.md` (one paragraph each: releases tier is populated from a per-PR pre-release)
- Modify: `docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md` (§3 "obs-pr-check.yml": state that the populate job and release QA live in `obs-release-pr.yml` because obs-pr-check cancels superseded runs, and that the QA fan-out is the reusable `qa-fanout.yml`)

**Acceptance Criteria:**
- [ ] `docs/PERCONA_OBS_TOOL.md` process list matches spec §5 (cut → PR populates + QA → fix loop via `project release` + push or `gh workflow run obs-release-pr.yml -f pr_number=N` → merge → tag + one dispatch → copy, GitHub releases, pre-release deleted); the two "Until rollout step 2 lands" notes are removed; the lock/pending-cancellation paragraphs are replaced by the recovery table of spec §4
- [ ] `.github/copilot-instructions.md` describes every workflow's triggers, jobs and required config as implemented in Tasks 1-7 (reusable `qa-fanout.yml` inputs; `obs-release-pr.yml` jobs; `obs-release.yml` inputs and finalize; cleanup's single dispatch; sync-main without the skip); the "Required repository config" lines are updated
- [ ] Spec §3 corrected as listed in Files (one paragraph), so spec and workflows agree
- [ ] No remaining mention of the sync-main lock as a current mechanism (`grep -n "lock" docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md` shows only historical/other uses)

**Verify:** `grep -c "obs-release-pr" docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md && ! grep -q "Until rollout step 2" docs/PERCONA_OBS_TOOL.md` → counts ≥ 2 each, second command succeeds

**Steps:**

- [ ] **Step 1: Write the docs** per the acceptance criteria, using the spec's §3-§5 wording as the source and the final YAML of Tasks 1-7 as the facts.

- [ ] **Step 2: Commit**

```bash
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md root/README.md root/ppg/releases/README.md docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md
git commit -s -m "docs: two-hop release flow workflows"
```

---

### Task 9: Labs rehearsal runbook

**Goal:** A step-by-step checklist the operator follows on labs with a throwaway release id, covering populate, repopulate, merge, final copy, manual re-dispatch and cleanup, with the expected observation at each step.

**Files:**
- Create: `docs/superpowers/specs/2026-10-14-prerelease-rehearsal-runbook.md`

**Acceptance Criteria:**
- [ ] Preconditions: `OBS_INSTANCES` entries with `pr_rootprj`, secrets, Jenkins vars; `gh auth status` locally; tags fetched
- [ ] Steps with the exact commands: cut a throwaway id (`project release ppg:staging:18 --release-id 18.<minor>-99`), open the PR, observe `obs-release-pr.yml` (populate per instance, comment table, QA check names `OBS QA / ppg:releases:18 / …`), force a record-check failure (merge a trivial staging change, push the PR unchanged → "staging changed since the cut"), refresh (`project release` again, push), repopulate via `gh workflow run obs-release-pr.yml -f pr_number=N`, merge, observe tag + one `obs-release.yml` run, GitHub release, pre-release deleted, `sync-main` runs on the release-only push; manual re-dispatch recipe; cleanup (delete the GitHub release and tag, revert the release.yaml/CHANGELOG entry through a normal PR, `osc rdelete` of the throwaway binaries in `ppg:releases:18` if any landed)
- [ ] Each step names what to look at (job name, comment heading, OBS project URL pattern) and the pass condition
- [ ] Known limitations to watch: `EXPECTED_VERSIONS` is empty on release mirrors; `--from --dry-run` only runs staging-side checks

**Verify:** `test -s docs/superpowers/specs/2026-10-14-prerelease-rehearsal-runbook.md && grep -c "^- \[ \]" docs/superpowers/specs/2026-10-14-prerelease-rehearsal-runbook.md` → count ≥ 12

**Steps:**

- [ ] **Step 1: Write the runbook** as a checklist (`- [ ]` items) in the order above, one subsection per phase (Preconditions, Cut, Populate, Fix loop, Merge, Recovery, Cleanup), each item ending with "Expect: …".

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-prerelease-rehearsal-runbook.md
git commit -s -m "docs: labs rehearsal runbook for the two-hop release flow"
```

---

## Self-review notes

- Spec coverage: §1 lifecycle (create/repopulate on push + dispatch, delete after hop 2, one in-flight) → Tasks 2, 5, 6; §3 obs-pr-check → Tasks 1, 3; obs-pr-cleanup → Task 5; obs-release → Task 6; sync-main → Task 7; stale-cleanup unchanged; §4 recovery recipes → Tasks 6 (error text), 8 (docs); §5 process → Task 8; rehearsal → Task 9. The spec's "populate job inside obs-pr-check" is implemented as a separate workflow for the cancellation reason stated in the Architecture paragraph; the spec text is corrected in Task 8 (one sentence in §3).
- Tool prerequisite discovered while planning → Task 0.
- Type/name consistency: `qa-fanout.yml` inputs `pr_number`, `qa_types`; `release_pr.py` functions `classify_files`, `release_projects`, `conflicting_prs`, `prerelease_project`; `post_pr_comment.render_prerelease_comment`; env `PRERELEASE_REPORT`; artifact `prerelease-report-<instance>`; `obs-release.yml` inputs `pr_number`, `tags`, job outputs `first_tag`; `apply_mirror_meta`/`release_tree` kwargs `branch_rootprj`, `active_projects`.
