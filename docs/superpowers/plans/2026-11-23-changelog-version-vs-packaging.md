# Changelog: Version vs Packaging Updates + Image CVE Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `project release` writes a CHANGELOG section that separates upstream version updates from packaging updates (with PR-linked commits), drops pure rebuilds, and lists the CVEs each container image stops carrying.

**Architecture:** Two new pure modules hold the new logic: `percona_obs/release_changes.py` (version-release parsing, change classification, packaging commit lookup and formatting) and `percona_obs/image_cves.py` (obs-dashboard scan fetch and fixed-CVE diff). `_build_changelog_section` in `percona_obs/cmd_project.py` consumes the classifier and takes pre-computed packaging notes; `cmd_project_release` gathers the notes and the image CVE lines and passes them in. Git, `gh` and HTTP calls are injected so tests stub them.

**Tech Stack:** Python 3 stdlib, `git` and `gh` subprocesses, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-23-changelog-version-vs-packaging-design.md`

## Global Constraints

- Work in a git worktree at `.claude/worktrees/changelog-version-vs-packaging`, branch `changelog-version-vs-packaging`, created off `percona/main`.
- Commits: `git commit -s`. No `Co-Authored-By` or other attribution lines. Do not push or open a PR without asking.
- After every code change: `venv/bin/black <files you touched>` then `venv/bin/pyright` (must report `0 errors`). Run `black` only on files you touched: other files under `tests/` are not black-clean.
- Tests: `venv/bin/python -m pytest tests -q` must pass at the end of every task.
- Never run a write operation with `-P isv`. Nothing in this plan needs OBS access; all tests stub network, git and `gh`.
- Arrow in new changelog lines is `→` (U+2192) with one space each side.
- Exact strings (copy verbatim):
  - `#### Version updates`, `#### Packaging updates`
  - `- Rebuild only: no version or packaging changes.`
  - `  - no package-level commits (shared macro or tooling change)`
  - `- Container image CVEs not scanned (OBS_DASHBOARD_URL not set).`
- Environment variable name: `OBS_DASHBOARD_URL`.

**User decisions (already made):**
- "we can completely ignore build counter increments, and just show 1. and 2." (version bumps and packaging revisions).
- Packaging lines carry both the counter change and the commit subjects ("3").
- "I want to go with 1": the counter decides the class, git explains it.
- "the commit subject line should have an hyperling to the PR that added the commit".
- Container image CVEs from obs-dashboard: "Fixes only" (no still-open list).

## Review Focus

1. **Deb-form version-release on one side, RPM-form on the other, same source revision** (`4.2.0-6+7.3.bookworm` vs `4.2.0-7.5`): must classify as rebuild, not packaging. Test in Task 1.
2. **Refresh of an open release** (the last `release.yaml` entry is the release being re-cut): the commit range must start at the entry before it, not at the open entry itself. Test in Task 4.
3. **Commit subject containing `<…>`** (`percona-pgaudit<N>-llvmjit …`): GitHub markdown would swallow `<N>` as an HTML tag; the `<` must be escaped so the subject reads in full. Test in Task 3.
4. **`gh` missing, logged out or offline**: one warning in total (not one per commit), subjects written without links, the release continues. Test in Task 4.
5. **Dashboard answers for the candidate image on one side only, or a row with no `findings` key**: a clean row (no `findings`) means zero findings, an absent row means not scanned; a CVE found in the `ubi8` image must never be credited to the `ubi9` entry. Tests in Task 5.

---

## File Structure

| File | Responsibility |
|---|---|
| `percona_obs/release_changes.py` (new) | Parse version-release strings, classify a change, list packaging commits, format commit lines |
| `percona_obs/image_cves.py` (new) | Fetch dashboard scans, compute fixed CVEs per image, format Security lines |
| `percona_obs/github_api.py` | Add `commit_pull_request` |
| `percona_obs/cmd_project.py` | `_build_changelog_section` layout; `cmd_project_release` wiring |
| `percona_obs/cve_scan.py` | Drop the "UBI base-image package CVEs are not covered" line and its parameter |
| `tests/test_release_changes.py`, `tests/test_image_cves.py` (new) | Unit tests for the new modules |
| `tests/test_project_release.py`, `tests/test_cve_scan.py`, `tests/test_github_api.py` | Updated and added tests |
| `docs/PERCONA_OBS_TOOL.md` | Step 6 "Builds CHANGELOG.md" describes the new layout and `OBS_DASHBOARD_URL` |

---

### Task 1: Version-release parsing and change classification

**Goal:** A pure classifier that tells a version update from a packaging update from a rebuild.

**Files:**
- Create: `percona_obs/release_changes.py`
- Test: `tests/test_release_changes.py`

**Acceptance Criteria:**
- [ ] `split_versrel` returns the upstream version and the source-commit counter for RPM and deb forms.
- [ ] `classify_change` returns `"version"`, `"packaging"` or `"rebuild"` per the spec table.
- [ ] A deb-form and an RPM-form string with the same counter classify as `"rebuild"`.

**Verify:** `venv/bin/python -m pytest tests/test_release_changes.py -q` → all pass

**Interfaces (used by later tasks):**

```python
ChangeKind = Literal["version", "packaging", "rebuild"]

def split_versrel(versrel: str) -> "tuple[str, str | None]": ...
def classify_change(old: str, new: str) -> ChangeKind: ...
```

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from percona_obs.release_changes import classify_change, split_versrel


@pytest.mark.parametrize(
    "versrel, expected",
    [
        ("2.60.0-4.2.el9", ("2.60.0", "4")),
        ("3.5.26-6.1", ("3.5.26", "6")),
        ("17.11-1", ("17.11", "1")),
        ("4.2.0-6+7.3.bookworm", ("4.2.0", "7")),
        ("2.9.0.post0-3.1.el8", ("2.9.0.post0", "3")),
        ("1.19", ("1.19", None)),
    ],
)
def test_split_versrel(versrel, expected):
    assert split_versrel(versrel) == expected


@pytest.mark.parametrize(
    "old, new, kind",
    [
        ("5.0-5.1.el10", "6.0-1.2.el10", "version"),
        ("2.4.1-4.3.el10", "2.4.0-3.1.el10", "version"),  # downgrade is a version change
        ("17.1-5.6.el10", "17.1-6.2.el10", "packaging"),
        ("2.60.0-4.1.el10", "2.60.0-4.2.el10", "rebuild"),
        ("2.60.0-4.1.el10", "2.60.0-4.1.el10", "rebuild"),
        ("4.2.0-6+7.3.bookworm", "4.2.0-7.5", "rebuild"),
        ("4.2.0-6+7.3.bookworm", "4.2.0-8.1", "packaging"),
        ("1.19", "1.19", "rebuild"),
        ("1.19", "1.19-2.1", "packaging"),
    ],
)
def test_classify_change(old, new, kind):
    assert classify_change(old, new) == kind
```

- [ ] **Step 2: Run to verify they fail** — `venv/bin/python -m pytest tests/test_release_changes.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement both functions in `percona_obs/release_changes.py`**

Rules the signature does not determine:
- Upstream version is everything before the first `-` (same rule the existing changelog code uses: `versrel.split("-")[0]`); the release is the rest.
- Counter: if the release contains `+`, take the text after the last `+`; then take the part before the first `.`. No `-` in the string → counter `None`.
- `classify_change`: versions differ → `"version"`; else counters differ → `"packaging"`; else `"rebuild"`.

- [ ] **Step 4: Run to verify they pass**, then `venv/bin/black percona_obs/release_changes.py tests/test_release_changes.py` and `venv/bin/pyright`.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/release_changes.py tests/test_release_changes.py
git commit -s -m "release changelog: classify version, packaging and rebuild changes"
```

---

### Task 2: New `### Changed` layout in `_build_changelog_section`

**Goal:** The section builder emits the two subsections, filters rebuilds from packages and container image lists, and accepts pre-computed packaging notes.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`_build_changelog_section`, around line 2164)
- Test: `tests/test_project_release.py` (new tests; update the existing container-entry tests near lines 1302–1470 and any test asserting on `### Changed` content), `tests/test_cve_scan.py` (section-wiring tests near line 339 if their assertions break)

**Acceptance Criteria:**
- [ ] `### Changed` holds `#### Version updates` and `#### Packaging updates`; an empty subsection is omitted.
- [ ] A package with only a build-counter change produces no line anywhere.
- [ ] A packaging line reads `- <key>: <version>-<old counter> → <version>-<new counter>`, followed by its notes when given.
- [ ] A container image appears under Version updates with `added:` / `removed:` / `updated: <pkg> <old version> → <new version>` items, and separately under Packaging updates with `repackaged:` items; with neither it has no entry.
- [ ] Nothing under `### Changed` (and `source_versions` non-empty) → the single line `- Rebuild only: no version or packaging changes.`
- [ ] `### Added`, `### Removed`, `### Security` and the empty-`source_versions` TODO placeholder behave as before.

**Verify:** `venv/bin/python -m pytest tests/test_project_release.py tests/test_cve_scan.py -q` → all pass

**Interfaces:**

```python
def _build_changelog_section(
    release_id, source_versions, release_versions, source_path, *,
    source_container_pkgs=None, release_container_pkgs=None,
    prev_release_id=None, security_lines=None,
    packaging_notes: "dict[str, list[str]] | None" = None,   # NEW
) -> str: ...

def _packaging_changed_keys(                                   # NEW, same file
    source_versions: "dict[str, str]",
    release_versions: "dict[str, str] | None",
) -> "list[str]": ...
```

`packaging_notes[key]` is a list of ready-to-print sub-item lines (each already starting with `  - `). A key absent from the dict, or `packaging_notes=None`, prints the packaging line with no sub-items. `_packaging_changed_keys` returns, sorted, the keys present in both dicts whose `classify_change(release, source)` is `"packaging"`.

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/test_project_release.py`

```python
def test_changelog_splits_version_and_packaging_updates(tmp_path):
    section = cmd_project._build_changelog_section(
        "17.12-2",
        {"percona-credcheck": "6.0-1.2", "percona-pgaudit": "17.2-2.1", "etcd": "3.5.35-4.2"},
        {"percona-credcheck": "5.0-5.1", "percona-pgaudit": "17.2-1.4", "etcd": "3.5.35-4.1"},
        tmp_path,
        packaging_notes={"percona-pgaudit": ["  - PG-2955 fix ([#310](https://x/pull/310))"]},
    )
    changed = section.split("### Changed")[1]
    assert changed.index("#### Version updates") < changed.index("#### Packaging updates")
    assert "- percona-credcheck: update upstream version 6.0" in changed
    assert (
        "- percona-pgaudit: 17.2-1 → 17.2-2\n"
        "  - PG-2955 fix ([#310](https://x/pull/310))"
    ) in changed
    assert "etcd" not in section


def test_changelog_packaging_line_without_notes(tmp_path):
    section = cmd_project._build_changelog_section(
        "17.12-2", {"etcd": "3.5.35-5.1"}, {"etcd": "3.5.35-4.9"}, tmp_path
    )
    assert "#### Version updates" not in section
    assert "#### Packaging updates\n- etcd: 3.5.35-4 → 3.5.35-5\n" in section


def test_changelog_rebuild_only(tmp_path):
    section = cmd_project._build_changelog_section(
        "17.11-4",
        {"etcd": "3.5.35-4.2"},
        {"etcd": "3.5.35-4.1"},
        tmp_path,
        source_container_pkgs={"img (ubi9)": {"gosu": "1.19-4.4.el9"}},
        release_container_pkgs={"img (ubi9)": {"gosu": "1.19-4.3.el9"}},
        prev_release_id="17.11-3",
    )
    assert "### Changed\n- Rebuild only: no version or packaging changes.\n" in section
    assert "img (ubi9)" not in section
    assert "####" not in section


def test_changelog_container_entries_split_by_kind(tmp_path):
    section = cmd_project._build_changelog_section(
        "17.12-1",
        {"percona-postgresql": "17.12-1.1"},
        {"percona-postgresql": "17.11-8.3"},
        tmp_path,
        source_container_pkgs={
            "img (ubi9)": {
                "percona-credcheck17": "6.0-1.3.el9",
                "percona-pgaudit17": "17.1-6.3.el9",
                "gosu": "1.19-5.4.el9",
                "curl": "8.23.0-3.1.el9",
            }
        },
        release_container_pkgs={
            "img (ubi9)": {
                "percona-credcheck17": "5.0-5.1.el9",
                "percona-pgaudit17": "17.1-5.7.el9",
                "gosu": "1.19-5.3.el9",
                "llvm": "21.1.8-1.6.el9",
            }
        },
        prev_release_id="17.11-5",
    )
    version, packaging = section.split("#### Packaging updates")
    header = "- img (ubi9) [container image]: update image 17.11-5 → 17.12-1"
    assert header in version and header in packaging
    assert "  - added: curl 8.23.0-3.1.el9" in version
    assert "  - updated: percona-credcheck17 5.0 → 6.0" in version
    assert "  - removed: llvm" in version
    assert "  - repackaged: percona-pgaudit17 17.1-5 → 17.1-6" in packaging
    assert "gosu" not in section


def test_packaging_changed_keys():
    assert cmd_project._packaging_changed_keys(
        {"a": "1.0-2.1", "b": "2.0-1.1", "c": "1.0-1.2", "new": "1.0-1.1"},
        {"a": "1.0-1.9", "b": "1.0-1.1", "c": "1.0-1.1"},
    ) == ["a"]
    assert cmd_project._packaging_changed_keys({"a": "1.0-2.1"}, None) == []
```

- [ ] **Step 2: Run to verify they fail** (`TypeError: unexpected keyword 'packaging_notes'`, missing attribute).

- [ ] **Step 3: Rework `_build_changelog_section`**

Keep the existing package loop, upstream-URL resolution, Added and Removed handling unchanged. Replace the single `changed` list with two lists, `version_updates` and `packaging_updates`, and route by `classify_change(rel_ver, src_ver)` (import from `.release_changes`): `"version"` keeps today's `update upstream version` line; `"packaging"` writes the packaging line plus `packaging_notes.get(pkg, [])`; `"rebuild"` writes nothing. In the container branch for an image present on both sides, classify each common package the same way; added and removed packages count as version items. Emit the `### Changed` block as: heading, then each non-empty subsection as a `####` heading followed by its entries and a blank line; if both are empty and `source_versions` is non-empty, the rebuild-only line. Add `_packaging_changed_keys` next to `_build_changed_packages`.

- [ ] **Step 4: Update existing tests** whose assertions depended on the old flat `### Changed` list or on `updated: <pkg> <old> -> <new>` with full release strings. Change only the expected strings; do not delete a test.

- [ ] **Step 5: Run the Verify command**, then `black` on the touched files and `pyright`.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/cmd_project.py tests/test_project_release.py tests/test_cve_scan.py
git commit -s -m "release changelog: separate version updates from packaging updates, drop rebuilds"
```

---

### Task 3: Packaging commits and PR links

**Goal:** Given two commits and a package's paths, produce the changelog sub-items: one line per commit, linked to its pull request.

**Files:**
- Modify: `percona_obs/github_api.py`, `percona_obs/release_changes.py`
- Test: `tests/test_github_api.py`, `tests/test_release_changes.py`

**Acceptance Criteria:**
- [ ] `commit_pull_request` returns the merged PR's number and URL for a commit, or `None` when the commit has no PR.
- [ ] `packaging_commits` returns commits oldest first, merges excluded, restricted to the given paths.
- [ ] `commit_line` renders `  - <subject> ([#N](<pr url>))`, a commit link when there is no PR, and the bare subject when lookup is disabled.
- [ ] `<` in a subject is written as `\<`.

**Verify:** `venv/bin/python -m pytest tests/test_release_changes.py tests/test_github_api.py -q` → all pass

**Interfaces:**

```python
# github_api.py
def commit_pull_request(repo_slug: str, sha: str) -> "tuple[int, str] | None": ...

# release_changes.py
@dataclass(frozen=True)
class CommitRef:
    sha: str        # full SHA
    subject: str

RunGit = Callable[["list[str]"], str]                      # args after "git" -> stdout
PrLookup = Callable[[str], "tuple[int, str] | None"]       # sha -> (number, url)

def packaging_commits(
    prev_commit: str, new_commit: str, paths: "list[str]", run_git: RunGit
) -> "list[CommitRef]": ...

def commit_line(
    commit: CommitRef, repo_slug: "str | None", pr_lookup: "PrLookup | None"
) -> str: ...
```

**Steps:**

- [ ] **Step 1: Write the failing tests**

`tests/test_github_api.py`:

```python
def test_commit_pull_request_prefers_merged(monkeypatch):
    calls = []

    def fake(path):
        calls.append(path)
        return [
            {"number": 7, "html_url": "https://github.com/o/r/pull/7", "merged_at": None},
            {"number": 9, "html_url": "https://github.com/o/r/pull/9", "merged_at": "2026-11-20T10:00:00Z"},
        ]

    monkeypatch.setattr(gha, "_gh_api_json", fake)
    assert gha.commit_pull_request("o/r", "abc") == (9, "https://github.com/o/r/pull/9")
    assert calls == ["repos/o/r/commits/abc/pulls"]


def test_commit_pull_request_none(monkeypatch):
    monkeypatch.setattr(gha, "_gh_api_json", lambda path: [])
    assert gha.commit_pull_request("o/r", "abc") is None
```

`tests/test_release_changes.py`:

```python
from percona_obs.release_changes import CommitRef, commit_line, packaging_commits


def test_packaging_commits_parses_git_log():
    seen = []

    def run_git(args):
        seen.append(args)
        return "a" * 40 + "\x00first\x1e\n" + "b" * 40 + "\x00second\x1e\n"

    commits = packaging_commits("P", "N", ["root/x/pkg", "root/_shared/pkg"], run_git)
    assert commits == [CommitRef("a" * 40, "first"), CommitRef("b" * 40, "second")]
    assert seen == [
        ["log", "--no-merges", "--reverse", "--format=%H%x00%s%x1e", "P..N",
         "--", "root/x/pkg", "root/_shared/pkg"]
    ]


def test_packaging_commits_empty_output():
    assert packaging_commits("P", "N", ["p"], lambda args: "") == []


def test_commit_line_with_pr():
    c = CommitRef("a" * 40, "PG-2955 percona-pgaudit<N>-llvmjit is not installable")
    line = commit_line(c, "o/r", lambda sha: (310, "https://github.com/o/r/pull/310"))
    assert line == (
        "  - PG-2955 percona-pgaudit\\<N>-llvmjit is not installable "
        "([#310](https://github.com/o/r/pull/310))"
    )


def test_commit_line_without_pr_links_commit():
    c = CommitRef("abcdef1234" + "0" * 30, "direct push")
    assert commit_line(c, "o/r", lambda sha: None) == (
        "  - direct push ([abcdef1](https://github.com/o/r/commit/abcdef1234" + "0" * 30 + "))"
    )


def test_commit_line_lookup_disabled():
    c = CommitRef("a" * 40, "subject")
    assert commit_line(c, "o/r", None) == "  - subject"
    assert commit_line(c, None, lambda sha: (1, "u")) == "  - subject"
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement `commit_pull_request` in `github_api.py`** — `_gh_api_json(f"repos/{repo_slug}/commits/{sha}/pulls")`; first item with a truthy `merged_at`, else the first item, else `None`. Errors propagate (the caller handles them).

- [ ] **Step 4: Implement `CommitRef`, `packaging_commits`, `commit_line` in `release_changes.py`** — records are separated by `\x1e`, fields by `\x00`, blank records skipped; short SHA is 7 characters; lookup is used only when both `repo_slug` and `pr_lookup` are given.

- [ ] **Step 5: Run the Verify command**, then `black` on the touched files and `pyright`.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/github_api.py percona_obs/release_changes.py tests/test_github_api.py tests/test_release_changes.py
git commit -s -m "release changelog: packaging commits with pull request links"
```

---

### Task 4: Wire packaging notes into `project release`

**Goal:** `cmd_project_release` computes the notes for every packaging-class package and passes them to the section builder.

**Files:**
- Modify: `percona_obs/cmd_project.py` (new helper `_packaging_notes`; call site in `cmd_project_release` just before `_build_changelog_section`, around line 2983)
- Test: `tests/test_project_release.py`

**Acceptance Criteria:**
- [ ] The commit range is `<previous entry's source_commit>..<this cut's source_commit>`, where the previous entry is the one before the entry being written (also on a refresh).
- [ ] Paths per key: the package directory under the source tree as a repo-relative path, plus its resolved target when it is a symlink (no duplicates). Key `"pkg (sub:path)"` maps to `<source>/sub/path/pkg`.
- [ ] A key with no commits gets `["  - no package-level commits (shared macro or tooling change)"]`.
- [ ] Previous entry without `source_commit`, or no previous entry → `None` (no notes at all).
- [ ] A failing PR lookup prints exactly one warning to stderr, and that commit and all later ones are written without links; nothing raises.

**Verify:** `venv/bin/python -m pytest tests/test_project_release.py -q` → all pass

**Interfaces:**

```python
def _packaging_notes(
    keys: "list[str]",
    source_path: Path,
    prev_commit: "str | None",
    new_commit: str,
    repo_slug: "str | None",
    *,
    run_git: "RunGit | None" = None,      # default: cve_scan._default_run_git
    pr_lookup: "PrLookup | None" = None,  # default: github_api.commit_pull_request bound to repo_slug
) -> "dict[str, list[str]] | None": ...
```

**Steps:**

- [ ] **Step 1: Write the failing tests** (`_REPO_DIR` is monkeypatched to `tmp_path` so paths are relative to it; follow how other tests in this file patch `cmd_project._REPO_DIR`)

```python
def _notes_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    src = tmp_path / "root" / "ppg" / "staging" / "17"
    (tmp_path / "root" / "ppg" / "_shared" / "percona-pgaudit").mkdir(parents=True)
    src.mkdir(parents=True)
    (src / "percona-pgaudit").symlink_to("../../_shared/percona-pgaudit")
    (src / "extras" / "h3").mkdir(parents=True)
    return src


def test_packaging_notes_paths_and_lines(tmp_path, monkeypatch):
    src = _notes_tree(tmp_path, monkeypatch)
    calls = []

    def run_git(args):
        calls.append(args)
        return ("a" * 40 + "\x00fix it\x1e") if "root/ppg/_shared/percona-pgaudit" in args else ""

    notes = cmd_project._packaging_notes(
        ["h3 (extras)", "percona-pgaudit"], src, "PREV", "NEW", "o/r",
        run_git=run_git, pr_lookup=lambda sha: (5, "https://github.com/o/r/pull/5"),
    )
    assert notes == {
        "h3 (extras)": ["  - no package-level commits (shared macro or tooling change)"],
        "percona-pgaudit": ["  - fix it ([#5](https://github.com/o/r/pull/5))"],
    }
    assert calls[0][-2:] == ["--", "root/ppg/staging/17/extras/h3"]
    assert calls[1][-3:] == [
        "--", "root/ppg/staging/17/percona-pgaudit", "root/ppg/_shared/percona-pgaudit",
    ]
    assert calls[0][4] == "PREV..NEW"


def test_packaging_notes_none_without_previous_commit(tmp_path, monkeypatch):
    src = _notes_tree(tmp_path, monkeypatch)
    assert cmd_project._packaging_notes(["percona-pgaudit"], src, None, "NEW", "o/r") is None


def test_packaging_notes_lookup_failure_warns_once(tmp_path, monkeypatch, capsys):
    src = _notes_tree(tmp_path, monkeypatch)
    lookups = []

    def boom(sha):
        lookups.append(sha)
        raise SystemExit("error: gh api failed")

    notes = cmd_project._packaging_notes(
        ["percona-pgaudit"], src, "PREV", "NEW", "o/r",
        run_git=lambda args: "a" * 40 + "\x00one\x1e" + "b" * 40 + "\x00two\x1e",
        pr_lookup=boom,
    )
    assert notes == {"percona-pgaudit": ["  - one", "  - two"]}
    assert len(lookups) == 1
    assert capsys.readouterr().err.count("warning:") == 1


def test_previous_source_commit_on_refresh():
    entries = [
        ReleaseEntry("ppg/17.12-1", "aaa"),
        ReleaseEntry("ppg/17.12-2", "bbb"),   # the open entry being refreshed
    ]
    assert cmd_project._previous_source_commit(entries) == "aaa"
    assert cmd_project._previous_source_commit(entries[:1]) is None
    assert cmd_project._previous_source_commit(
        [ReleaseEntry("ppg/17.11-1"), ReleaseEntry("ppg/17.12-1", "ccc")]
    ) is None
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**

- `_previous_source_commit(new_entries: "list[ReleaseEntry]") -> "str | None"`: `source_commit` of the second-to-last entry, `None` if there is none. `new_entries` is the list `_plan_release_entries` returns, whose last element is always the entry being written.
- `_packaging_notes`: resolve each key with `_split_changelog_key`; catch `Exception` and `SystemExit` around the first failing `pr_lookup`, print `warning: pull request lookup failed: <exc>; commits are listed without links` to stderr, and continue with lookup disabled. Cache lookups by SHA (one commit can touch several packages). A `git log` failure for a key (`Exception`) prints one warning and leaves that key out of the dict.
- Call site: `repo_slug` is `repo_slug_from_url(repo_url)` when `repo_url` is set, else `None`. Pass `packaging_notes=_packaging_notes(_packaging_changed_keys(source_versions, release_versions), source_path, _previous_source_commit(new_entries), source_commit, repo_slug)` to `_build_changelog_section`. Print `_print_pending("collecting packaging commits for CHANGELOG")` first.

- [ ] **Step 4: Run the Verify command**, then `black` on the touched files and `pyright`.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_project.py tests/test_project_release.py
git commit -s -m "project release: list PR-linked packaging commits in the changelog"
```

---

### Task 5: Container image CVE fixes from obs-dashboard

**Goal:** A module that fetches image scans from the dashboard and renders the fixed-CVE lines.

**Files:**
- Create: `percona_obs/image_cves.py`
- Test: `tests/test_image_cves.py`

**Acceptance Criteria:**
- [ ] `fetch_scans` requests `<base>/api/cve/scans?project=<project>&package=<package>` (query values URL-encoded, trailing `/` on the base tolerated) and returns the decoded list.
- [ ] `findings_by_repo` unions findings across architectures per repo; a row without `findings` contributes an empty set but still marks the repo as scanned.
- [ ] `image_cve_lines` lists, per image key, CVE ids found in the previous image and absent from the candidate, grouped by package.
- [ ] A key scanned on one side only yields one `Not scanned` line naming the missing side; a key with no fixes yields nothing.

**Verify:** `venv/bin/python -m pytest tests/test_image_cves.py -q` → all pass

**Interfaces:**

```python
@dataclass(frozen=True)
class Finding:
    id: str
    pkg: str
    installed: str
    fixed: str        # "" when the scanner names no fixing version
    severity: str     # upper case

Fetcher = Callable[[str], str]     # url -> response body

def fetch_scans(base_url: str, project: str, package: str, fetcher: Fetcher) -> "list[dict[str, Any]]": ...
def findings_by_repo(rows: "list[dict[str, Any]]") -> "dict[str, set[Finding]]": ...
def image_cve_lines(
    keys: "list[str]",
    previous: "dict[str, set[Finding]]",     # changelog image key -> findings
    candidate: "dict[str, set[Finding]]",
    candidate_pkgs: "dict[str, dict[str, str]]",   # key -> {binary pkg: version-release}
) -> "list[str]": ...
```

Line formats (exact):

```
- <key> [container image]: fixes <N> <SEV>[/<SEV>…] CVE[s]
  - <pkg> <installed> → <candidate version>: <id>, <id>
  - <pkg> <installed> (fix: <fixed>): <id>
  - <pkg> <installed>: <id>
- Not scanned: <key> [container image] (no dashboard scan of the previous image)
- Not scanned: <key> [container image] (no dashboard scan of the candidate image)
```

`<N>` counts distinct CVE ids; severities are listed in the order `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, then any other alphabetically; `CVE` is singular when `N == 1`. Sub-items are sorted by package then installed version; ids sorted. `→ <candidate version>` is used when the package is in `candidate_pkgs[key]`.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
import json
from percona_obs.image_cves import Finding, fetch_scans, findings_by_repo, image_cve_lines

ROW = {
    "repo": "ubi9", "arch": "x86_64", "scanned_at": "2026-11-23T02:38:50Z",
    "findings": [
        {"id": "CVE-1", "pkg": "krb5-libs", "installed": "1.21-11.el9",
         "fixed": "1.21-11.el9_3.2", "severity": "HIGH"},
    ],
}


def test_fetch_scans_url():
    seen = []

    def fetcher(url):
        seen.append(url)
        return json.dumps([ROW])

    rows = fetch_scans("https://dash.example/", "ppg:releases:17:containers", "img a", fetcher)
    assert rows == [ROW]
    assert seen == [
        "https://dash.example/api/cve/scans?project=ppg%3Areleases%3A17%3Acontainers&package=img+a"
    ]


def test_findings_by_repo_unions_archs_and_keeps_clean_rows():
    other_arch = {**ROW, "arch": "aarch64", "findings": [
        {"id": "CVE-2", "pkg": "curl", "installed": "8.1-1.el9", "fixed": "", "severity": "critical"},
    ]}
    clean = {"repo": "ubi8", "arch": "x86_64", "clean_since": "2026-11-20T00:00:00Z"}
    by_repo = findings_by_repo([ROW, other_arch, clean])
    assert by_repo["ubi8"] == set()
    assert by_repo["ubi9"] == {
        Finding("CVE-1", "krb5-libs", "1.21-11.el9", "1.21-11.el9_3.2", "HIGH"),
        Finding("CVE-2", "curl", "8.1-1.el9", "", "CRITICAL"),
    }
    assert "ubi10" not in by_repo


def test_image_cve_lines_fixed_only_and_grouped():
    f1 = Finding("CVE-2", "krb5-libs", "1.21-11.el9", "1.21-11.el9_3.2", "HIGH")
    f2 = Finding("CVE-1", "krb5-libs", "1.21-11.el9", "1.21-11.el9_3.2", "HIGH")
    f3 = Finding("CVE-3", "python3.12-dns", "2.8.0-3.1.el9", "2.9.0", "CRITICAL")
    f4 = Finding("CVE-4", "zlib", "1.2-1.el9", "", "HIGH")
    still_open = Finding("CVE-9", "openssl", "3.0-1.el9", "3.0-2.el9", "HIGH")
    lines = image_cve_lines(
        ["img (ubi9)"],
        {"img (ubi9)": {f1, f2, f3, f4, still_open}},
        {"img (ubi9)": {still_open}},
        {"img (ubi9)": {"python3.12-dns": "2.9.0-3.2.el9"}},
    )
    assert lines == [
        "- img (ubi9) [container image]: fixes 4 CRITICAL/HIGH CVEs\n"
        "  - krb5-libs 1.21-11.el9 (fix: 1.21-11.el9_3.2): CVE-1, CVE-2\n"
        "  - python3.12-dns 2.8.0-3.1.el9 → 2.9.0-3.2.el9: CVE-3\n"
        "  - zlib 1.2-1.el9: CVE-4"
    ]


def test_image_cve_lines_single_cve_is_singular():
    f = Finding("CVE-1", "zlib", "1.2-1.el9", "", "HIGH")
    assert image_cve_lines(["k"], {"k": {f}}, {"k": set()}, {})[0].startswith(
        "- k [container image]: fixes 1 HIGH CVE\n"
    )


def test_image_cve_lines_no_fixes_no_entry():
    f = Finding("CVE-1", "zlib", "1.2-1.el9", "", "HIGH")
    assert image_cve_lines(["k"], {"k": {f}}, {"k": {f}}, {}) == []
    assert image_cve_lines(["k"], {"k": set()}, {"k": set()}, {}) == []


def test_image_cve_lines_missing_scan_side():
    f = Finding("CVE-1", "zlib", "1.2-1.el9", "", "HIGH")
    assert image_cve_lines(["a", "b"], {"a": {f}}, {"b": set()}, {}) == [
        "- Not scanned: a [container image] (no dashboard scan of the candidate image)",
        "- Not scanned: b [container image] (no dashboard scan of the previous image)",
    ]


def test_image_cve_lines_does_not_cross_repos():
    f = Finding("CVE-1", "zlib", "1.2-1.el8", "", "HIGH")
    lines = image_cve_lines(
        ["img (ubi8)", "img (ubi9)"],
        {"img (ubi8)": {f}, "img (ubi9)": set()},
        {"img (ubi8)": set(), "img (ubi9)": set()},
        {},
    )
    assert len(lines) == 1 and lines[0].startswith("- img (ubi8) ")
```

- [ ] **Step 2: Run to verify they fail** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `percona_obs/image_cves.py`** — a CVE is fixed when its `id` is in the previous set and no candidate finding has that `id` (compare ids, not whole `Finding`s: the installed version differs between images). Missing dict fields default to `""`; severity is upper-cased. `fetch_scans` raises on a non-list response.

- [ ] **Step 4: Run the Verify command**, then `black` on the two files and `pyright`.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/image_cves.py tests/test_image_cves.py
git commit -s -m "image_cves: fixed-CVE diff of container images from obs-dashboard scans"
```

---

### Task 6: Wire image CVE fixes into `project release`; docs

**Goal:** The Security section of a cut lists image CVE fixes from the dashboard; the old "not covered" line is gone; the tool reference describes the new section.

**Files:**
- Modify: `percona_obs/cmd_project.py` (new helper `_image_cve_security_lines`; call site in `cmd_project_release` after the upstream scan, around line 2965)
- Modify: `percona_obs/cve_scan.py` (remove the `has_container_images` parameter of `scan_release_cves` and the `UBI base-image package CVEs are not covered by this scan.` line)
- Modify: `docs/PERCONA_OBS_TOOL.md` (step 6 "Builds `CHANGELOG.md`", around line 1430; the `--no-cve-scan` description)
- Test: `tests/test_project_release.py`, `tests/test_cve_scan.py`

**Acceptance Criteria:**
- [ ] Image keys considered: those present in both `source_container_pkgs` and `release_container_pkgs`. None → no lines and no dashboard request.
- [ ] `OBS_DASHBOARD_URL` is read from `release_env`, then `os.environ`; unset → the single line `- Container image CVEs not scanned (OBS_DASHBOARD_URL not set).`
- [ ] Scans are requested per (container project, image package) on both sides; projects are named without the instance root: `<args.project>:<sub>` and `<release_project>:<sub>` for each container subproject.
- [ ] A dashboard row maps to a changelog key as `"<package> (<label>)"` with `<label>` from `_container_changelog_label(project, repo, parent)`.
- [ ] Any fetch error → one stderr warning and the single line `- Container image CVEs not scanned (dashboard error: <exc>)`; the release continues.
- [ ] Each candidate scan's `scanned_at` is printed while fetching.
- [ ] `--no-cve-scan` skips the image CVE lines too. A failure of the upstream scan does not skip them.
- [ ] `scan_release_cves` no longer emits the "not covered" line.
- [ ] `docs/PERCONA_OBS_TOOL.md` describes: the two `### Changed` subsections, that rebuilds are not listed, PR-linked packaging commits, image CVE fixes and `OBS_DASHBOARD_URL`.

**Verify:** `venv/bin/python -m pytest tests -q` → all pass; `venv/bin/pyright` → `0 errors`

**Interfaces:**

```python
def _image_cve_security_lines(
    source_project: str,                # e.g. "ppg:staging:17" (no instance root)
    release_project: str,               # e.g. "ppg:releases:17"
    container_subs: "list[str]",
    source_container_pkgs: "dict[str, dict[str, str]]",
    release_container_pkgs: "dict[str, dict[str, str]]",
    dashboard_url: "str | None",
    *,
    fetcher: "Fetcher | None" = None,   # default: cve_scan._default_fetcher
) -> "list[str]": ...
```

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/test_project_release.py`

```python
def _dash_fetcher(by_project):
    import json
    from urllib.parse import parse_qs, urlparse

    seen = []

    def fetcher(url):
        q = parse_qs(urlparse(url).query)
        seen.append((q["project"][0], q["package"][0]))
        return json.dumps(by_project.get(q["project"][0], []))

    return fetcher, seen


_FINDING = {"id": "CVE-1", "pkg": "zlib", "installed": "1.2-1.el9", "fixed": "", "severity": "HIGH"}
_PKGS = {"img (ubi9)": {"gosu": "1.19-5.4.el9"}}


def test_image_cve_security_lines_diff(capsys):
    fetcher, seen = _dash_fetcher({
        "ppg:releases:17:containers": [{"repo": "ubi9", "arch": "x86_64", "findings": [_FINDING]}],
        "ppg:staging:17:containers": [
            {"repo": "ubi9", "arch": "x86_64", "scanned_at": "2026-11-23T11:09:04Z"}
        ],
    })
    lines = cmd_project._image_cve_security_lines(
        "ppg:staging:17", "ppg:releases:17", ["containers"], _PKGS, _PKGS,
        "https://dash.example", fetcher=fetcher,
    )
    assert lines == [
        "- img (ubi9) [container image]: fixes 1 HIGH CVE\n  - zlib 1.2-1.el9: CVE-1"
    ]
    assert sorted(seen) == [
        ("ppg:releases:17:containers", "img"), ("ppg:staging:17:containers", "img"),
    ]
    assert "2026-11-23T11:09:04Z" in capsys.readouterr().out


def test_image_cve_security_lines_url_unset():
    assert cmd_project._image_cve_security_lines(
        "ppg:staging:17", "ppg:releases:17", ["containers"], _PKGS, _PKGS, None
    ) == ["- Container image CVEs not scanned (OBS_DASHBOARD_URL not set)."]


def test_image_cve_security_lines_no_common_images_no_request():
    def fetcher(url):
        raise AssertionError("no request expected")

    assert cmd_project._image_cve_security_lines(
        "ppg:staging:17", "ppg:releases:17", ["containers"], _PKGS, {},
        "https://dash.example", fetcher=fetcher,
    ) == []


def test_image_cve_security_lines_dashboard_error(capsys):
    def fetcher(url):
        raise OSError("connection refused")

    lines = cmd_project._image_cve_security_lines(
        "ppg:staging:17", "ppg:releases:17", ["containers"], _PKGS, _PKGS,
        "https://dash.example", fetcher=fetcher,
    )
    assert lines == [
        "- Container image CVEs not scanned (dashboard error: connection refused)"
    ]
    assert "warning:" in capsys.readouterr().err
```

In `tests/test_cve_scan.py`: remove `has_container_images=` from existing calls and add

```python
def test_scan_no_longer_emits_ubi_not_covered_line(tmp_path):
    result = scan_release_cves([], tmp_path, None, fetcher=lambda *a, **k: "")
    assert not any("UBI base-image" in line for line in result.lines)
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement `_image_cve_security_lines`** — image package names are the distinct `key.rsplit(" (", 1)[0]` of the common keys. For each side, each container subproject and each image package: `fetch_scans`, `findings_by_repo`, then merge into a `{key: findings}` dict using the label rule above (union when two projects yield the same key). Print one line per candidate row, `  scan: <key> <arch> scanned_at <scanned_at>`. Finish with `image_cve_lines(common keys sorted, previous, candidate, source_container_pkgs)`.

- [ ] **Step 4: Call site in `cmd_project_release`** — inside the existing `if not getattr(args, "no_cve_scan", False):` block, after the upstream scan's `try/except`: compute the image lines (wrapped in its own `try/except Exception` that prints `warning: container image CVE scan failed: <exc>`), and set `security_lines` to the upstream lines followed by the image lines, or `None` when both are empty. Dashboard URL: `release_env.get("OBS_DASHBOARD_URL") or os.environ.get("OBS_DASHBOARD_URL")`. Drop the `has_container_images=` argument.

- [ ] **Step 5: Remove the parameter and the line from `scan_release_cves`** in `percona_obs/cve_scan.py`; fix its docstring.

- [ ] **Step 6: Update `docs/PERCONA_OBS_TOOL.md`** — rewrite step 6 to describe the layout (include a short example section with both subsections and one image CVE entry), state that pure rebuilds are not listed, that packaging commits come from `git log <previous source_commit>..<source_commit>` and are linked through `gh`, and document `OBS_DASHBOARD_URL` (profile env or environment; unset leaves a "not scanned" line). Update the `--no-cve-scan` text to say it also skips the container image CVE lines.

- [ ] **Step 7: Run the Verify command**, then `black` on the touched Python files.

- [ ] **Step 8: Commit**

```bash
git add percona_obs/cmd_project.py percona_obs/cve_scan.py docs/PERCONA_OBS_TOOL.md tests/test_project_release.py tests/test_cve_scan.py
git commit -s -m "project release: list container image CVE fixes from obs-dashboard"
```

---

## After the last task

A real cut is the only end-to-end check and it needs OBS, `gh` and the dashboard. It is the user's to run (dry run only on `-P isv`); the plan stops at green unit tests, `black` and `pyright`.
