# Multi-instance OBS repository/project slices — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a connection profile declare which repositories and projects its OBS instance carries, derive project/package membership from it everywhere (`sync push`, `sync release`, `project verify/config`, `project release`, CI poll), and remove `sync push --only-repos`.

**Architecture:** A `RepositoryFilter` (include/exclude globs for repository names and project names) lives in `percona_obs/project_config.py`; `resolve_project_config` applies it after merging, using a process-wide default that `cli.main()` installs from the active profile. Two predicates, `project_in_slice` and `package_in_slice`, are the only way consumers decide membership. Out-of-slice projects and packages look exactly like things absent from the tree, so the existing orphan cleanup removes them. The release generator reads the tree unfiltered; `sync release` and CI run once per instance.

**Tech Stack:** Python 3 (`percona_obs/`), pytest, black, pyright, GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-09-23-multi-instance-repo-slices-design.md` (read it first; PR #82's `docs/superpowers/specs/2026-09-23-project-yaml-dedup-design.md` describes the resolver this builds on).

## Global Constraints

- Work only in the worktree `.claude/worktrees/multi-obs` (branch `multi-obs`, based on `percona/project-yaml-dedup`). Never touch the main checkout. `venv` is a symlink there.
- After every Python change run, in this order, from the worktree root: `venv/bin/black percona_obs/ tests/` then `venv/bin/pyright` (must print `0 errors`) then `venv/bin/python -m pytest -q tests` (all pass; 314 today, more after each task). A task is not done until all three pass.
- Commit each task with `git commit -s`. No `Co-Authored-By`, no "Generated with" lines, anywhere.
- Never `git push`, never open a PR, never run any command that writes to an OBS instance. `project verify`, `project config --offline`, `--dry-run` and the gate scripts are the only allowed forms of validation against the tree. No network access is needed by any task.
- Never edit anything under `root/ppg/releases/`.
- The rendered output for an unfiltered run (no profile, or a profile without filter keys) must stay byte-identical to the baseline (Task 0 gate), with one deliberate exception: `ppg:staging:extras` (zero repositories) is now out of slice everywhere; the gate renders it directly through the loader so it is unaffected, but `project config --resolved` marks it.
- Repo-relative paths in messages use `root/...` (see `project_config._label`).
- Scratchpad for throwaway scripts and baselines: `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/2c7ad2f6-20ef-4281-ab6e-13f4559d8eb7/scratchpad` (referred to as `$S` below; if it does not exist, create it or any directory outside the repo and use it consistently).

**User decisions (already made):**
- Selection model 3: package projects on both instances with disjoint repos; packages reach labs only if they build in a surviving repo; containers and UBI-only packages leave b.o.o.
- One `percona-obs` run per instance; the profile declares the slice with `include-repositories`, `exclude-repositories`, `include-projects`, `exclude-projects` glob lists. No committed slice catalogue.
- `sync push --only-repos` is removed; PR labels are written into the PR profile by the workflow.
- Out-of-slice projects and packages are orphan-deleted on a full-tree push.
- Projects with zero repositories are never created.
- Filter installed once as a process default in `cli.main()`; explicit argument overrides it.
- `project release` generates the release tree from the unfiltered resolved staging config, not from live OBS meta.
- QA registry host (`registry.opensuse.org/` in `qa:` blocks) and QA workflow routing are deferred.

**Deviations from the spec, decided while planning (Task 11 amends the spec):**
- No `--branch-from` filter-mismatch refusal (spec Section 2). A PR profile is narrowed by labels while `main` is not, so the filters legitimately differ; the existing "repos missing from branch → promote" logic already covers a branch source lacking a repo.
- Project-name matching uses the path-derived name only (`ppg:staging:17:containers`). No `name:` override exists anywhere under `root/`, and an override is a full OBS name that cannot be matched without the rootprj.
- Label narrowing is an intersection, not a list append: `profile create --narrow-repos` (Task 9) keeps only the named repositories the profile's own filter already accepts, and exits 3 when nothing is left so the workflow can skip that instance.

---

## File structure

| File | Responsibility |
|---|---|
| `percona_obs/project_config.py` | `RepositoryFilter`, `project_slice_name`, `project_in_slice`, `package_in_slice`; `resolve_project_config(..., repo_filter=)` |
| `percona_obs/common.py` | process default filter (`set_/get_default_repository_filter`), alias forwards `repo_filter` |
| `percona_obs/cmd_profile.py` | `_load_profile_filter`, `profile create` filter flags and `--narrow-repos`, `profile list` rendering |
| `percona_obs/cli.py` | install default filter in `main()`; new `profile create` flags; `--only-repos` removed |
| `percona_obs/cmd_sync.py` | `_slice_targets`, explicit-target errors, summary line, `--only-repos` plumbing removed, `_collect_release_subprojects` slice-aware |
| `percona_obs/targets.py` | `_iter_project_chain` skips out-of-slice projects; `image_dep_query_repos` loses `only_repos` |
| `percona_obs/obs_api.py` | `_filter_meta_repos` and `only_repos` removed; `_obs_meta_to_yaml_repos`/`_obs_meta_to_yaml_debuginfo` removed if unused |
| `percona_obs/cmd_project.py` | `_validate_repo_path_refs`, verify slice summary, `project config` out-of-slice marking, release generator from tree |
| `.github/scripts/poll_obs_builds.py` | `OBS_REPO_FILTER`, `OBS_DISCOVER_ONLY` |
| `.github/scripts/post_pr_comment.py` | per-instance comment marker |
| `.github/workflows/{sync-main,obs-pr-check,obs-release}.yml` | instance matrix |
| `tests/test_project_config_merge.py` | filter unit tests |
| `tests/test_slice_selection.py` (new) | predicates, profile parsing, `_slice_targets`, `_iter_project_chain`, verify check, release collection |
| `tests/test_meta_repo_filter.py` | deleted (superseded) |
| `tests/test_image_dep_repos.py`, `tests/test_project_prepass.py`, `tests/test_sync_release.py`, `tests/test_project_release.py` | adjusted |
| `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md`, `root/README.md`, `README.md`, the spec | documentation |

---

### Task 0: Unfiltered regression gate and baseline

**Goal:** Capture, from the base branch, the rendered meta XML and per-repository effective prjconf of every non-release project, so later tasks can prove the unfiltered output did not change.

**Files:**
- Create: `$S/gate.py` (throwaway, not committed)
- Create: `$S/gate-baseline/*.json`
- Create: detached worktree `$S/base` of `percona/project-yaml-dedup`

**Acceptance Criteria:**
- [ ] `gate.py capture` run from `$S/base` prints `captured N projects into $S/gate-baseline` with N ≥ 40
- [ ] `gate.py check $S/gate-baseline` run from the `multi-obs` worktree (unchanged tree) prints `GATE PASSED`, exit 0

**Verify:** `cd .claude/worktrees/multi-obs && venv/bin/python $S/gate.py check $S/gate-baseline` → `GATE PASSED`

**Steps:**

- [ ] **Step 1: Write the gate script**

Write `$S/gate.py` with exactly this content (it is the PR #82 gate, unchanged; it reads the tree through the loader with no filter, so it also proves later tasks keep the default filter empty when no profile is active):

```python
"""Throwaway regression gate (not committed).

  gate.py capture <dir>        render every non-release project into <dir>/<proj>.json
  gate.py check   <dir>        re-render and compare; exit 1 on any difference
  gate.py effective <project-dir> [<repo>]   print effective prjconf lines per repository

Per project: meta XML (build_project_meta, rootprj "ROOT", env vars unsubstituted) must be
byte-identical; prjconf is compared per repository as a sorted multiset of effective lines
(comments/blank lines dropped, `%if "%_repository" == ...` blocks attributed to the repos named).
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from percona_obs.common import (  # noqa: E402
    REPO_ROOT,
    _is_release_dir,
    _load_project_config_with_inheritance,
    build_project_meta,
)

_IF_RE = re.compile(r"^%if\s+(.*)$")
_REPO_RE = re.compile(r'"%_repository"\s*==\s*"([^"]+)"')


def _is_release(p: Path) -> bool:
    return any(
        _is_release_dir(a) or a.name == "releases"
        for a in [p, *p.parents]
        if a.is_relative_to(REPO_ROOT)
    )


def project_dirs() -> list[Path]:
    return sorted(
        p.parent
        for p in REPO_ROOT.rglob("project.yaml")
        if not _is_release(p.parent) and "_shared" not in p.parts
    )


def effective_prjconf(text: str, repo_names: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {r: [] for r in repo_names}
    active: "set[str] | None" = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _IF_RE.match(line)
        if m:
            if active is not None:
                raise SystemExit(f"nested %if not supported: {line}")
            names = _REPO_RE.findall(m.group(1))
            if not names or len(names) != m.group(1).count("=="):
                raise SystemExit(f"unsupported %if form: {line}")
            active = set(names)
            continue
        if line == "%endif":
            active = None
            continue
        if line.startswith("%else") or line.startswith("%elif"):
            raise SystemExit(f"unsupported directive: {line}")
        for r in repo_names:
            if active is None or r in active:
                out[r].append(line)
    if active is not None:
        raise SystemExit("unterminated %if")
    return {r: sorted(v) for r, v in out.items()}


def render(p: Path) -> dict:
    cfg = _load_project_config_with_inheritance(p, None)
    obs_name = "ROOT" if p == REPO_ROOT else "ROOT:" + ":".join(p.relative_to(REPO_ROOT).parts)
    repos = cfg.get("repositories", [])
    meta = build_project_meta(
        obs_name,
        cfg.get("title", ""),
        cfg.get("description", ""),
        repos,
        "ROOT",
        publish=cfg.get("publish"),
        build=cfg.get("build"),
        debuginfo=cfg.get("debuginfo"),
    )
    return {
        "meta": meta,
        "prjconf": effective_prjconf(cfg.get("project-config") or "", [r["name"] for r in repos]),
    }


def _key(p: Path) -> str:
    return "__".join(p.relative_to(REPO_ROOT.parent).parts)


def capture(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    dirs = project_dirs()
    for p in dirs:
        (out / f"{_key(p)}.json").write_text(json.dumps(render(p), indent=1, sort_keys=True))
    print(f"captured {len(dirs)} projects into {out}")


def check(base: Path) -> None:
    bad = 0
    seen: set[str] = set()
    for p in project_dirs():
        f = base / f"{_key(p)}.json"
        seen.add(f.name)
        rel = p.relative_to(REPO_ROOT.parent).as_posix()
        if not f.is_file():
            print(f"NEW PROJECT (no baseline): {rel}")
            bad += 1
            continue
        want = json.loads(f.read_text())
        got = render(p)
        if got["meta"] != want["meta"]:
            bad += 1
            print(f"META DIFFERS: {rel}")
            for l in difflib.unified_diff(
                want["meta"].splitlines(), got["meta"].splitlines(), "baseline", "now", lineterm="", n=1
            ):
                print("   ", l)
        if got["prjconf"] != want["prjconf"]:
            bad += 1
            print(f"PRJCONF DIFFERS: {rel}")
            for r in sorted(set(want["prjconf"]) | set(got["prjconf"])):
                a, b = want["prjconf"].get(r, []), got["prjconf"].get(r, [])
                if a != b:
                    print(f"    [{r}] missing={[x for x in a if x not in b]} extra={[x for x in b if x not in a]}")
    for f in base.glob("*.json"):
        if f.name not in seen:
            print(f"PROJECT GONE: {f.stem.replace('__', '/')}")
            bad += 1
    print("GATE PASSED" if not bad else f"GATE FAILED ({bad} differences)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["capture", "check", "effective"])
    ap.add_argument("target")
    ap.add_argument("repo", nargs="?")
    a = ap.parse_args()
    if a.cmd == "capture":
        capture(Path(a.target))
    elif a.cmd == "check":
        check(Path(a.target))
    else:
        r = render(REPO_ROOT.parent / a.target)["prjconf"]
        for repo in [a.repo] if a.repo else r:
            print(f"[{repo}]")
            for l in r[repo]:
                print("   ", l)
```

- [ ] **Step 2: Capture the baseline from a detached worktree of the base branch**

```bash
cd /home/rdias/Work/percona-obs-packaging/.claude/worktrees/multi-obs
git worktree add --detach $S/base percona/project-yaml-dedup
ln -s /home/rdias/Work/percona-obs-packaging/venv $S/base/venv
cd $S/base && venv/bin/python $S/gate.py capture $S/gate-baseline
```
Expected: `captured N projects into …` (N ≥ 40).

- [ ] **Step 3: Self-check on the unchanged multi-obs tree**

```bash
cd /home/rdias/Work/percona-obs-packaging/.claude/worktrees/multi-obs
venv/bin/python $S/gate.py check $S/gate-baseline
```
Expected: `GATE PASSED`.

- [ ] **Step 4: No commit** (scratchpad only). Keep `$S/base` until Task 11 removes it with `git worktree remove $S/base`.

---

### Task 1: `RepositoryFilter` with tests

**Goal:** A pure value type describing a slice, with glob matching, same-project rescue and flag-map pruning, and constructors from profile data and from CI JSON.

**Files:**
- Modify: `percona_obs/project_config.py` (append after `REPO_ENTRY_KEYS`)
- Test: `tests/test_project_config_merge.py` (new section at the end)

**Acceptance Criteria:**
- [ ] `RepositoryFilter.EMPTY.is_empty` is `True` and `EMPTY.apply(cfg, name) is cfg`
- [ ] include-then-exclude semantics for repositories and projects; the root project (`""`) always passes
- [ ] `apply` keeps siblings referenced through same-project `subproject:` paths, transitively, never through cross-project or `project:` paths
- [ ] `apply` prunes `debuginfo`/`publish`/`build` maps to kept repos but leaves the `{disable: true}` shorthand and booleans untouched
- [ ] `from_profile` rejects a non-list or non-string entry with `SystemExit("error: <source>: <key> must be a list of non-empty strings")`
- [ ] `from_env_json` accepts comma-separated strings or lists under snake_case keys; `to_profile()` round-trips

**Verify:** `venv/bin/python -m pytest -q tests/test_project_config_merge.py -k filter` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project_config_merge.py`)

```python
# --- repository filter ---------------------------------------------------------

from percona_obs.project_config import RepositoryFilter  # noqa: E402


def _cfg(*names, paths=None, flags=None):
    repos = [{"name": n, "paths": list((paths or {}).get(n, [])), "archs": ["x86_64"]} for n in names]
    cfg = {"title": "T", "repositories": repos}
    cfg.update(flags or {})
    return cfg


def test_filter_empty_is_passthrough():
    cfg = _cfg("RockyLinux_9", "UBI_9")
    assert RepositoryFilter.EMPTY.is_empty
    assert RepositoryFilter().is_empty
    assert RepositoryFilter.EMPTY.apply(cfg, "ppg:staging:17") is cfg
    assert RepositoryFilter.EMPTY.repo_matches("anything")
    assert RepositoryFilter.EMPTY.project_passes("anything")


def test_filter_repo_include_then_exclude():
    f = RepositoryFilter(include_repos=("UBI_*", "ubi*", "images"), exclude_repos=("ubi8",))
    assert f.repo_matches("UBI_9") and f.repo_matches("ubi9") and f.repo_matches("images")
    assert not f.repo_matches("ubi8")  # excluded wins over included
    assert not f.repo_matches("RockyLinux_9")
    only_exclude = RepositoryFilter(exclude_repos=("UBI_*",))
    assert only_exclude.repo_matches("RockyLinux_9") and not only_exclude.repo_matches("UBI_8")


def test_filter_project_globs_and_root_never_excluded():
    f = RepositoryFilter(exclude_projects=("*:containers", "common:containers:*"))
    assert not f.project_passes("ppg:staging:17:containers")
    assert not f.project_passes("common:containers:ubi8")
    assert f.project_passes("ppg:staging:17:containers:x")  # descendants are independent
    assert f.project_passes("ppg:staging:17")
    assert f.project_passes("")
    inc = RepositoryFilter(include_projects=("ppg:*",))
    assert inc.project_passes("ppg:staging:17") and not inc.project_passes("common:deps:build")
    assert inc.project_passes("")  # root passes even with an include list


def test_filter_apply_prunes_repositories_and_flag_maps():
    f = RepositoryFilter(exclude_repos=("UBI_*",))
    cfg = _cfg(
        "RockyLinux_9",
        "UBI_9",
        flags={
            "debuginfo": {"RockyLinux_9": True, "UBI_9": True},
            "build": {"UBI_9": False},
            "publish": False,
        },
    )
    out = f.apply(cfg, "ppg:staging:17")
    assert [r["name"] for r in out["repositories"]] == ["RockyLinux_9"]
    assert out["debuginfo"] == {"RockyLinux_9": True}
    assert out["build"] == {}
    assert out["publish"] is False
    assert out["title"] == "T"
    # shorthand maps are not repository maps
    short = f.apply(_cfg("RockyLinux_9", flags={"build": {"disable": True}}), "x")
    assert short["build"] == {"disable": True}
    # the input is not mutated
    assert [r["name"] for r in cfg["repositories"]] == ["RockyLinux_9", "UBI_9"]


def test_filter_apply_same_project_rescue_is_transitive_not_cross_project():
    f = RepositoryFilter(include_repos=("ssl3",))
    cfg = _cfg(
        "helper",
        "helper2",
        "standard",
        "ssl3",
        paths={
            "ssl3": [
                {"subproject": "ppg:staging:17:tarballs", "repository": "helper"},
                {"subproject": "ppg:staging:17", "repository": "helper2"},  # other project
                {"project": "RockyLinux:9", "repository": "standard"},
            ],
            "helper": [{"subproject": "ppg:staging:17:tarballs", "repository": "helper2"}],
        },
    )
    out = f.apply(cfg, "ppg:staging:17:tarballs")
    assert [r["name"] for r in out["repositories"]] == ["helper", "helper2", "ssl3"]
    # without the same-project name nothing is rescued
    out2 = f.apply(cfg, "somewhere:else")
    assert [r["name"] for r in out2["repositories"]] == ["ssl3"]


def test_filter_from_profile_and_validation():
    f = RepositoryFilter.from_profile(
        {
            "apiurl": "x",
            "include-repositories": ["UBI_*"],
            "exclude-projects": ["common:containers:ubi8"],
        },
        source=".profile/labs.yaml",
    )
    assert f.include_repos == ("UBI_*",)
    assert f.exclude_projects == ("common:containers:ubi8",)
    assert f.exclude_repos == () and f.include_projects == ()
    assert f.to_profile() == {
        "include-repositories": ["UBI_*"],
        "exclude-projects": ["common:containers:ubi8"],
    }
    with pytest.raises(
        SystemExit,
        match=r"\.profile/labs\.yaml: include-repositories must be a list of non-empty strings",
    ):
        RepositoryFilter.from_profile({"include-repositories": "UBI_*"}, source=".profile/labs.yaml")
    with pytest.raises(SystemExit, match="exclude-repositories must be a list"):
        RepositoryFilter.from_profile({"exclude-repositories": ["ok", ""]}, source=".profile/labs.yaml")


def test_filter_from_env_json():
    assert RepositoryFilter.from_env_json("").is_empty
    f = RepositoryFilter.from_env_json(
        '{"name": "labs", "include_repos": "UBI_*, ubi*,images", "exclude_projects": ["a:b"]}'
    )
    assert f.include_repos == ("UBI_*", "ubi*", "images")
    assert f.exclude_projects == ("a:b",)
    with pytest.raises(SystemExit, match="include_repos"):
        RepositoryFilter.from_env_json('{"include_repos": 5}')
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `venv/bin/python -m pytest -q tests/test_project_config_merge.py -k filter`
Expected: ImportError / FAIL (`RepositoryFilter` does not exist).

- [ ] **Step 3: Implement `RepositoryFilter`** in `percona_obs/project_config.py`

Add imports at the top (`fnmatch`, `json`, `dataclasses`, `ClassVar`):

```python
import copy
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar
```

Append after `REPO_ENTRY_KEYS`:

```python
# (profile key, attribute) pairs; the attribute names double as the snake_case
# keys of the CI JSON form (RepositoryFilter.from_env_json).
FILTER_PROFILE_KEYS: tuple[tuple[str, str], ...] = (
    ("include-repositories", "include_repos"),
    ("exclude-repositories", "exclude_repos"),
    ("include-projects", "include_projects"),
    ("exclude-projects", "exclude_projects"),
)


def _glob_any(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


@dataclass(frozen=True)
class RepositoryFilter:
    """The slice of the tree one OBS instance carries (spec Section 1).

    A repository *matches* iff (no include list or it matches an include glob)
    and it matches no exclude glob; a project *passes* under the same rule on
    its rootprj-less OBS name (``ppg:staging:17:containers``).  The root
    project (name ``""``) always passes.  All four lists empty = unfiltered.
    """

    include_repos: tuple[str, ...] = ()
    exclude_repos: tuple[str, ...] = ()
    include_projects: tuple[str, ...] = ()
    exclude_projects: tuple[str, ...] = ()

    EMPTY: ClassVar["RepositoryFilter"]

    @property
    def is_empty(self) -> bool:
        return not (
            self.include_repos
            or self.exclude_repos
            or self.include_projects
            or self.exclude_projects
        )

    def repo_matches(self, name: str) -> bool:
        if self.include_repos and not _glob_any(name, self.include_repos):
            return False
        return not _glob_any(name, self.exclude_repos)

    def project_passes(self, name: str) -> bool:
        if name == "":
            return True  # the root project is never excluded
        if self.include_projects and not _glob_any(name, self.include_projects):
            return False
        return not _glob_any(name, self.exclude_projects)

    def apply(self, config: dict, project_name: str) -> dict:
        """Return *config* restricted to the repositories this filter keeps.

        Same-project rescue: a kept repository whose ``paths`` reference a
        sibling repository of *project_name* (``subproject:`` equal to it)
        keeps that sibling too, transitively — OBS rejects meta whose kept
        repo paths to a missing sibling.  ``debuginfo``/``publish``/``build``
        maps lose the entries of dropped repositories; booleans and the
        ``{disable: true}`` shorthand are left alone.  Returns *config* itself
        when the filter is empty; never mutates its input otherwise.
        """
        if self.is_empty:
            return config
        repos = list(config.get("repositories") or [])
        by_name = {r["name"]: r for r in repos}
        keep = {n for n in by_name if self.repo_matches(n)}
        queue = [by_name[n] for n in keep]
        while queue:
            for path in queue.pop().get("paths") or []:
                if path.get("subproject") != project_name:
                    continue
                ref = path.get("repository")
                if ref in by_name and ref not in keep:
                    keep.add(ref)
                    queue.append(by_name[ref])
        out = dict(config)
        out["repositories"] = [copy.deepcopy(r) for r in repos if r["name"] in keep]
        for key in FLAG_KEYS:
            value = out.get(key)
            if isinstance(value, dict) and not set(value) <= {"disable", "enable"}:
                out[key] = {k: v for k, v in value.items() if k in keep}
        return out

    def to_profile(self) -> dict[str, list[str]]:
        """The non-empty lists as profile keys (what ``profile create`` writes)."""
        return {
            key: list(getattr(self, attr))
            for key, attr in FILTER_PROFILE_KEYS
            if getattr(self, attr)
        }

    @classmethod
    def from_profile(cls, data: dict, source: str = "profile") -> "RepositoryFilter":
        """Build from a ``.profile/<name>.yaml`` mapping; unknown keys are ignored."""
        kwargs: dict[str, tuple[str, ...]] = {}
        for key, attr in FILTER_PROFILE_KEYS:
            raw = data.get(key)
            if raw is None:
                continue
            if not isinstance(raw, list) or not all(
                isinstance(x, str) and x.strip() for x in raw
            ):
                raise SystemExit(
                    f"error: {source}: {key} must be a list of non-empty strings"
                )
            kwargs[attr] = tuple(x.strip() for x in raw)
        return cls(**kwargs)

    @classmethod
    def from_env_json(cls, text: str) -> "RepositoryFilter":
        """Build from the CI instance JSON (``include_repos`` etc.; strings are comma-separated)."""
        if not text.strip():
            return cls()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise SystemExit("error: OBS_REPO_FILTER must be a JSON object")
        kwargs: dict[str, tuple[str, ...]] = {}
        for _, attr in FILTER_PROFILE_KEYS:
            raw = data.get(attr, "")
            if isinstance(raw, str):
                items = [x.strip() for x in raw.split(",") if x.strip()]
            elif isinstance(raw, list) and all(isinstance(x, str) for x in raw):
                items = [x.strip() for x in raw if x.strip()]
            else:
                raise SystemExit(
                    f"error: OBS_REPO_FILTER: {attr} must be a string or a list of strings"
                )
            if items:
                kwargs[attr] = tuple(items)
        return cls(**kwargs)


RepositoryFilter.EMPTY = RepositoryFilter()
```

- [ ] **Step 4: Run the tests, then black/pyright/full suite**

```bash
venv/bin/python -m pytest -q tests/test_project_config_merge.py -k filter
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
```
Expected: filter tests PASS; `0 errors`; full suite passes.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/project_config.py tests/test_project_config_merge.py
git commit -s -m "project_config: RepositoryFilter (profile-declared repo/project slices)"
```

---

### Task 2: Wire the filter into the resolver, the process default, profiles and the CLI

**Goal:** `resolve_project_config` applies a filter (explicit or the process default); `cli.main()` installs the active profile's filter; `profile create` writes the four lists; `profile list` shows them.

**Files:**
- Modify: `percona_obs/project_config.py` (`project_slice_name`, `resolve_project_config` signature)
- Modify: `percona_obs/common.py` (default filter accessors, alias signature; lines 734-745)
- Modify: `percona_obs/cmd_profile.py` (`_load_profile` list handling, `_load_profile_filter`, `cmd_profile_create`, `cmd_profile_list`)
- Modify: `percona_obs/cli.py` (`profile create` flags near line 555; `main()` near line 743)
- Test: `tests/test_slice_selection.py` (new)

**Acceptance Criteria:**
- [ ] `resolve_project_config(p, env, repo_filter=f)` returns the filtered config; with `repo_filter=None` it uses the default; `RepositoryFilter.EMPTY` passed explicitly beats a non-empty default
- [ ] `common.get_default_repository_filter()` is `RepositoryFilter.EMPTY` until set
- [ ] `_load_profile_filter("labs")` reads the four keys; a profile without them yields `EMPTY`; `_load_profile` still returns `apiurl`/`rootprj` as strings and no longer stringifies lists
- [ ] `profile create --include-repos "UBI_*,ubi*" --include-repos images --exclude-projects x` writes `include-repositories: [UBI_*, ubi*, images]` and `exclude-projects: [x]`; `-P name profile create name` without filter flags keeps the profile's existing lists
- [ ] `profile list` prints list values comma-joined

**Verify:** `venv/bin/python -m pytest -q tests/test_slice_selection.py` → all pass; `venv/bin/python -m percona_obs -R ROOT -e REMOTE_OBS_ORG_INTERCONNECT:x project config ppg:staging:17 --offline --resolved | grep -c "name: UBI_"` → `2` (unfiltered)

**Steps:**

- [ ] **Step 1: Write the failing tests** — create `tests/test_slice_selection.py`

```python
"""Slice selection: filter wiring, profile parsing, in-slice predicates (percona_obs.project_config)."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import percona_obs.cmd_profile as cmd_profile
import percona_obs.common as common
from percona_obs.project_config import (
    RepositoryFilter,
    project_slice_name,
    resolve_project_config,
)

_ROOT = """\
repositories:
  - name: RockyLinux_9
    paths:
      - subproject: common:deps:build
        repository: RockyLinux_9
    archs: [x86_64]
  - name: UBI_9
    paths:
      - subproject: common:deps:build
        repository: UBI_9
    archs: [x86_64]
debuginfo: {RockyLinux_9: true, UBI_9: true}
"""

LABS = RepositoryFilter(include_repos=("UBI_*", "ubi*", "images"))
BOO = RepositoryFilter(exclude_repos=("UBI_*", "ubi*", "images"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def make(files: dict) -> Path:
        root = tmp_path / "root"
        root.mkdir(exist_ok=True)
        (root / "macros.yaml").write_text("- M: 1\n")
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        monkeypatch.setattr(common, "REPO_ROOT", root)
        return root

    return make


@pytest.fixture(autouse=True)
def _reset_default_filter():
    common.set_default_repository_filter(None)
    yield
    common.set_default_repository_filter(None)


def _names(cfg):
    return [r["name"] for r in cfg["repositories"]]


# --- resolver wiring -------------------------------------------------------------


def test_project_slice_name(repo):
    root = repo({"project.yaml": _ROOT, "ppg/staging/17/project.yaml": "title: S\n"})
    assert project_slice_name(root) == ""
    assert project_slice_name(root / "ppg" / "staging" / "17") == "ppg:staging:17"


def test_resolve_with_explicit_filter(repo):
    root = repo({"project.yaml": _ROOT, "a/project.yaml": "title: A\n"})
    assert _names(resolve_project_config(root / "a", repo_filter=LABS)) == ["UBI_9"]
    boo = resolve_project_config(root / "a", repo_filter=BOO)
    assert _names(boo) == ["RockyLinux_9"]
    assert boo["debuginfo"] == {"RockyLinux_9": True}


def test_resolve_uses_process_default_and_explicit_empty_wins(repo):
    root = repo({"project.yaml": _ROOT, "a/project.yaml": "title: A\n"})
    assert common.get_default_repository_filter() is RepositoryFilter.EMPTY
    common.set_default_repository_filter(LABS)
    assert _names(resolve_project_config(root / "a")) == ["UBI_9"]
    assert _names(common._load_project_config_with_inheritance(root / "a")) == ["UBI_9"]
    assert _names(resolve_project_config(root / "a", repo_filter=RepositoryFilter.EMPTY)) == [
        "RockyLinux_9",
        "UBI_9",
    ]


# --- profiles --------------------------------------------------------------------


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / ".profile"
    d.mkdir()
    monkeypatch.setattr(cmd_profile, "_PROFILES_DIR", d)
    return d


def test_load_profile_filter(profiles_dir):
    (profiles_dir / "labs.yaml").write_text(
        "apiurl: https://labs\nrootprj: percona\n"
        "include-repositories: ['UBI_*', 'ubi*', images]\nexclude-projects: [common:containers:ubi8]\n"
    )
    (profiles_dir / "dev.yaml").write_text("apiurl: http://dev\nrootprj: home:Admin\n")
    f = cmd_profile._load_profile_filter("labs")
    assert f == RepositoryFilter(
        include_repos=("UBI_*", "ubi*", "images"), exclude_projects=("common:containers:ubi8",)
    )
    assert cmd_profile._load_profile_filter("dev") is RepositoryFilter.EMPTY
    assert cmd_profile._load_profile_filter("missing") is RepositoryFilter.EMPTY
    # scalar loader unchanged for apiurl/rootprj and drops the lists
    p = cmd_profile._load_profile("labs")
    assert p["apiurl"] == "https://labs" and p["rootprj"] == "percona"
    assert "include-repositories" not in p


def test_profile_create_writes_and_round_trips_filter(profiles_dir, capsys):
    args = SimpleNamespace(
        apiurl="https://labs",
        rootprj="percona",
        name="labs",
        env_overrides=[],
        profile=None,
        include_repos=["UBI_*,ubi*", "images"],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=["common:containers:ubi8"],
        narrow_repos=[],
    )
    cmd_profile.cmd_profile_create(args)
    data = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data["include-repositories"] == ["UBI_*", "ubi*", "images"]
    assert data["exclude-projects"] == ["common:containers:ubi8"]
    assert "exclude-repositories" not in data
    # -P labs profile create labs with no filter flags keeps the lists
    args2 = SimpleNamespace(
        apiurl="https://labs",
        rootprj="percona",
        name="labs",
        env_overrides=["X:1"],
        profile="labs",
        include_repos=[],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=[],
        narrow_repos=[],
    )
    cmd_profile.cmd_profile_create(args2)
    data2 = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data2["include-repositories"] == ["UBI_*", "ubi*", "images"]
    assert data2["env"] == [{"name": "X", "value": "1"}]
    cmd_profile.cmd_profile_list(SimpleNamespace())
    out = capsys.readouterr().out
    assert "include-repositories:" in out and "UBI_*, ubi*, images" in out
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `venv/bin/python -m pytest -q tests/test_slice_selection.py`
Expected: ImportError (`project_slice_name`, `set_default_repository_filter` missing).

- [ ] **Step 3: Resolver changes** in `percona_obs/project_config.py`

Add after `_chain`:

```python
def project_slice_name(project_path: Path) -> str:
    """OBS project name without the rootprj prefix (``ppg:staging:17``; ``""`` for root).

    Derived from the directory path; ``name:`` overrides are not consulted
    (none exist in the tree, and an override is a full OBS name).
    """
    root = common.REPO_ROOT
    if project_path == root or not project_path.is_relative_to(root):
        return ""
    return ":".join(project_path.relative_to(root).parts)
```

Change `resolve_project_config`:

```python
def resolve_project_config(
    project_path: Path,
    env_vars: dict[str, str] | None = None,
    repo_filter: "RepositoryFilter | None" = None,
) -> dict:
    """Return the effective configuration of the project at *project_path*.

    Keys: everything the leaf's own project.yaml declares except control keys,
    plus the merged ``repositories`` (always present, possibly empty),
    ``project-config`` (when any layer contributes text) and whichever of
    ``debuginfo``/``publish``/``build`` resolve to a non-null value.

    *repo_filter* restricts ``repositories`` and the flag maps to the active
    slice (``RepositoryFilter.apply``).  ``None`` means the process default
    installed by ``cli.main()`` from the profile
    (``common.get_default_repository_filter``); pass ``RepositoryFilter.EMPTY``
    for an explicitly unfiltered view (release generator, gates).
    """
    ...existing body unchanged up to...
    resolved = _fold(layers, own, own_path)
    _check_no_macro_leftovers(resolved, own_path)
    if repo_filter is None:
        repo_filter = common.get_default_repository_filter()
    return repo_filter.apply(resolved, project_slice_name(project_path))
```

Update the module docstring: add a paragraph "Slices: a ``RepositoryFilter`` (from the active profile) is applied to the resolved configuration; see spec 2026-09-23-multi-instance-repo-slices-design.md."

- [ ] **Step 4: Process default in `percona_obs/common.py`**

Add near the top (after imports) a `TYPE_CHECKING` import and the accessors; place the accessors right before `_load_project_config_with_inheritance` and extend the alias:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from percona_obs.project_config import RepositoryFilter
```

```python
# Process-wide repository/project slice, installed once by cli.main() from the
# active profile so that no consumer of the resolver can forget it.  None
# means unfiltered (RepositoryFilter.EMPTY).
_default_repository_filter: "RepositoryFilter | None" = None


def set_default_repository_filter(repo_filter: "RepositoryFilter | None") -> None:
    """Install the slice every resolver call without an explicit filter uses."""
    global _default_repository_filter
    _default_repository_filter = repo_filter


def get_default_repository_filter() -> "RepositoryFilter":
    from percona_obs.project_config import RepositoryFilter

    return _default_repository_filter or RepositoryFilter.EMPTY


def _load_project_config_with_inheritance(
    project_path: Path,
    env_vars: dict[str, str] | None = None,
    repo_filter: "RepositoryFilter | None" = None,
) -> dict:
    """Backward-compatible alias for ``project_config.resolve_project_config``.

    Kept so obs_api, cmd_sync, targets and cmd_project need no import changes.
    New code should import ``resolve_project_config`` directly.
    """
    from percona_obs.project_config import resolve_project_config

    return resolve_project_config(project_path, env_vars, repo_filter)
```

- [ ] **Step 5: Profiles** in `percona_obs/cmd_profile.py`

Import `from .project_config import RepositoryFilter`. Change `_load_profile`'s return expression to skip lists/dicts:

```python
    return {
        k: str(v)
        for k, v in data.items()
        if v is not None and not isinstance(v, (list, dict))
    }
```

Add:

```python
def _load_profile_filter(name: str) -> RepositoryFilter:
    """The slice declared in .profile/<name>.yaml (``include-repositories`` …).

    A missing profile or one without filter keys is unfiltered.  Malformed
    lists exit with an error naming the file.
    """
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.is_file():
        return RepositoryFilter.EMPTY
    with path.open(encoding="utf-8") as fh:
        data: object = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return RepositoryFilter.EMPTY
    f = RepositoryFilter.from_profile(data, source=str(path))
    return RepositoryFilter.EMPTY if f.is_empty else f


def _split_globs(values: list[str]) -> tuple[str, ...]:
    """``["a,b", "c"]`` → ``("a", "b", "c")`` (profile create flag values)."""
    return tuple(x.strip() for v in values for x in v.split(",") if x.strip())
```

In `cmd_profile_create`, after `env_vars = parse_env_overrides(...)`:

```python
    repo_filter = RepositoryFilter(
        include_repos=_split_globs(getattr(args, "include_repos", []) or []),
        exclude_repos=_split_globs(getattr(args, "exclude_repos", []) or []),
        include_projects=_split_globs(getattr(args, "include_projects", []) or []),
        exclude_projects=_split_globs(getattr(args, "exclude_projects", []) or []),
    )
    # `-P name profile create name` without filter flags re-creates the
    # profile from its current state (like -e does for env): keep its slice.
    if repo_filter.is_empty and getattr(args, "profile", None):
        repo_filter = _load_profile_filter(args.profile)
    data: dict[str, object] = {"apiurl": args.apiurl, "rootprj": args.rootprj}
    if env_vars:
        data["env"] = [{"name": k, "value": v} for k, v in sorted(env_vars.items())]
    data.update(repo_filter.to_profile())
```

(The `narrow_repos` attribute is read in Task 9; ignore it here.) In `cmd_profile_list`, print lists comma-joined:

```python
                for key, val in data.items():
                    shown = ", ".join(map(str, val)) if isinstance(val, list) and key != "env" else val
                    print(f"    {_col(_DIM, key + ':')}  {shown}")
```

- [ ] **Step 6: CLI** in `percona_obs/cli.py`

Add to `profile_create_parser` (after the `name` argument):

```python
    for _flag, _dest, _what in (
        ("--include-repos", "include_repos", "repository names to keep"),
        ("--exclude-repos", "exclude_repos", "repository names to drop"),
        ("--include-projects", "include_projects", "project names (without rootprj) to keep"),
        ("--exclude-projects", "exclude_projects", "project names (without rootprj) to drop"),
    ):
        profile_create_parser.add_argument(
            _flag,
            metavar="GLOB[,GLOB...]",
            action="append",
            default=[],
            dest=_dest,
            help=f"Slice rule: {_what} (shell globs, repeatable). Written to the profile as "
            f"{_flag[2:].replace('repos', 'repositories')}. See docs/PERCONA_OBS_TOOL.md.",
        )
```

In `main()`, inside `if args.profile:` after the env block:

```python
        set_default_repository_filter(_load_profile_filter(args.profile))
```

with imports `from .cmd_profile import _load_profile_filter` and `from .common import set_default_repository_filter` (add to the existing import lists).

- [ ] **Step 7: Run tests, black, pyright, full suite; smoke-test the CLI**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
venv/bin/python -m percona_obs -R ROOT -e REMOTE_OBS_ORG_INTERCONNECT:x project config ppg:staging:17 --offline --resolved | grep -c "name: UBI_"
venv/bin/python $S/gate.py check $S/gate-baseline
```
Expected: all pass, `2`, `GATE PASSED`.

- [ ] **Step 8: Commit**

```bash
git add percona_obs/project_config.py percona_obs/common.py percona_obs/cmd_profile.py percona_obs/cli.py tests/test_slice_selection.py
git commit -s -m "profiles: declare the instance slice; resolver applies the active RepositoryFilter"
```

---

### Task 3: `project_in_slice` / `package_in_slice` predicates

**Goal:** The two predicates every consumer uses to decide membership, with a per-run cache hook.

**Files:**
- Modify: `percona_obs/project_config.py` (append)
- Test: `tests/test_slice_selection.py` (append)

**Acceptance Criteria:**
- [ ] a project fails the project test → out; passes but keeps zero repos → out (including zero repos unfiltered); otherwise in
- [ ] a package is in iff its project is in and at least one surviving repo is not `false` in its `package.yaml` `build:` map; no `package.yaml`, no `build:`, or the `{disable: true}` shorthand → in
- [ ] both accept a pre-resolved config and an optional `cache: dict[Path, bool]`

**Verify:** `venv/bin/python -m pytest -q tests/test_slice_selection.py -k slice` → pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_slice_selection.py`)

```python
# --- predicates ------------------------------------------------------------------

from percona_obs.project_config import package_in_slice, project_in_slice  # noqa: E402

_TREE = {
    "project.yaml": _ROOT,
    "ppg/staging/17/project.yaml": "title: S\n",
    "ppg/staging/17/percona-postgresql/obs/_service": "",
    "ppg/staging/17/bison/obs/_service": "",
    "ppg/staging/17/bison/package.yaml": "build:\n  UBI_9: false\n",
    "ppg/staging/17/blanket/obs/_service": "",
    "ppg/staging/17/blanket/package.yaml": "build:\n  disable: true\n",
    "ppg/staging/17/containers/project.yaml": (
        "repositories-inherit: false\nrepositories:\n  - name: ubi9\n    paths: []\n    archs: [x86_64]\n"
    ),
    "ppg/staging/17/containers/image/obs/Dockerfile": "FROM scratch\n",
    "ppg/staging/extras/project.yaml": "repositories-inherit: false\n",
}


def test_project_in_slice(repo):
    root = repo(_TREE)
    s17 = root / "ppg/staging/17"
    assert project_in_slice(s17, repo_filter=RepositoryFilter.EMPTY)
    assert project_in_slice(s17, repo_filter=LABS)
    assert project_in_slice(s17, repo_filter=BOO)
    assert project_in_slice(root, repo_filter=LABS)  # root keeps UBI_9
    containers = s17 / "containers"
    assert project_in_slice(containers, repo_filter=LABS)
    assert not project_in_slice(containers, repo_filter=BOO)
    assert not project_in_slice(
        containers, repo_filter=RepositoryFilter(exclude_projects=("*:containers",))
    )
    # zero repositories: out everywhere, even unfiltered
    assert not project_in_slice(root / "ppg/staging/extras", repo_filter=RepositoryFilter.EMPTY)
    # pre-resolved config and cache are honoured
    cfg = resolve_project_config(containers, repo_filter=BOO)
    cache: dict[Path, bool] = {}
    assert not project_in_slice(containers, repo_filter=BOO, config=cfg, cache=cache)
    assert cache == {containers: False}
    cache[containers] = True
    assert project_in_slice(containers, repo_filter=BOO, cache=cache)  # cache is authoritative


def test_package_in_slice(repo):
    root = repo(_TREE)
    s17 = root / "ppg/staging/17"
    assert package_in_slice(s17 / "percona-postgresql", repo_filter=LABS)
    assert package_in_slice(s17 / "percona-postgresql", repo_filter=BOO)
    assert not package_in_slice(s17 / "bison", repo_filter=LABS)  # disabled on its only labs repo
    assert package_in_slice(s17 / "bison", repo_filter=BOO)
    assert package_in_slice(s17 / "blanket", repo_filter=LABS)  # shorthand map is not per-repo
    assert package_in_slice(s17 / "containers" / "image", repo_filter=LABS)
    assert not package_in_slice(s17 / "containers" / "image", repo_filter=BOO)  # project out
    # default filter applies when none is passed
    common.set_default_repository_filter(LABS)
    assert not package_in_slice(s17 / "bison")
```

- [ ] **Step 2: Run to see them fail**: `venv/bin/python -m pytest -q tests/test_slice_selection.py -k slice` → ImportError.

- [ ] **Step 3: Implement** (append to `percona_obs/project_config.py`)

```python
def project_in_slice(
    project_path: Path,
    env_vars: dict[str, str] | None = None,
    repo_filter: "RepositoryFilter | None" = None,
    config: dict | None = None,
    cache: "dict[Path, bool] | None" = None,
) -> bool:
    """True iff the project passes the project test and keeps ≥ 1 repository.

    A project with zero repositories (unfiltered or after slicing) is out of
    slice everywhere: it is never created on any instance.  *config* is an
    already-resolved configuration for *project_path* under *repo_filter*
    (saves a resolution in loops); *cache* memoises per project path and is
    authoritative when it holds the path.
    """
    if cache is not None and project_path in cache:
        return cache[project_path]
    if repo_filter is None:
        repo_filter = common.get_default_repository_filter()
    result = repo_filter.project_passes(project_slice_name(project_path))
    if result:
        if config is None:
            config = resolve_project_config(project_path, env_vars, repo_filter)
        result = bool(config.get("repositories"))
    if cache is not None:
        cache[project_path] = result
    return result


def package_in_slice(
    package_path: Path,
    env_vars: dict[str, str] | None = None,
    repo_filter: "RepositoryFilter | None" = None,
    project_config: dict | None = None,
    cache: "dict[Path, bool] | None" = None,
) -> bool:
    """True iff the package's project is in slice and the package builds in a kept repo.

    "Builds in": its ``package.yaml`` ``build:`` per-repository map does not set
    every surviving repository to ``false``.  No ``package.yaml``, no ``build:``,
    booleans and the ``{disable: true}`` shorthand all count as building.
    """
    if repo_filter is None:
        repo_filter = common.get_default_repository_filter()
    project_path = package_path.parent
    if project_config is None:
        project_config = resolve_project_config(project_path, env_vars, repo_filter)
    if not project_in_slice(project_path, env_vars, repo_filter, project_config, cache):
        return False
    repos = [r["name"] for r in project_config.get("repositories") or []]
    pkg_yaml = package_path / "package.yaml"
    build = common.load_package_yaml(pkg_yaml).get("build") if pkg_yaml.is_file() else None
    if isinstance(build, dict) and not set(build) <= {"disable", "enable"}:
        return any(build.get(name, True) is not False for name in repos)
    return True
```

- [ ] **Step 4: black, pyright, full suite; commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
git add percona_obs/project_config.py tests/test_slice_selection.py
git commit -s -m "project_config: project_in_slice / package_in_slice predicates"
```

---

### Task 4: Remove `sync push --only-repos` and its plumbing

**Goal:** Delete the label-driven meta filter; the profile filter (already applied by the loader) is the only repository selection.

**Files:**
- Modify: `percona_obs/cli.py:180-189` (delete the `--only-repos` argument)
- Modify: `percona_obs/cmd_sync.py` (`_IMAGES_REPO_RE`, `_CONTAINER_SUBPROJ_RE` and comments at 121-132; `_can_skip_project_apply` at 895-919; the `only_repos`/`effective_only_repos`/`container_subprojs` block at 1078-1103; `effective_repos` at 1272-1276; `image_dep_query_repos(...)` calls at ~1415 and ~1456; `only_repos=effective_only_repos` at ~1707, ~1726, ~1749, ~1836, ~1855)
- Modify: `percona_obs/obs_api.py` (delete `_filter_meta_repos` 1192-1239; `_apply_project_config` parameter `only_repos`, the `self_subproject` computation and the `_filter_meta_repos` call at ~1286-1302)
- Modify: `percona_obs/targets.py` (`image_dep_query_repos` drops `only_repos`)
- Delete: `tests/test_meta_repo_filter.py`
- Modify: `tests/test_image_dep_repos.py`, `tests/test_project_prepass.py`

**Acceptance Criteria:**
- [ ] `grep -rn "only_repos\|only-repos\|_IMAGES_REPO_RE\|_CONTAINER_SUBPROJ_RE\|_filter_meta_repos\|self_subproject" percona_obs tests` prints nothing
- [ ] `_can_skip_project_apply(verdict, branch_rootprj, force)` has three parameters
- [ ] `image_dep_query_repos` honours the process default filter (test below)
- [ ] gate: `GATE PASSED`

**Verify:** `venv/bin/python -m pytest -q tests && venv/bin/python $S/gate.py check $S/gate-baseline`

**Steps:**

- [ ] **Step 1: Rewrite the tests first**

Delete `tests/test_meta_repo_filter.py` (`git rm`). Its rescue semantics are covered by `test_filter_apply_same_project_rescue_is_transitive_not_cross_project` (Task 1).

Replace `tests/test_project_prepass.py` with:

```python
"""Unit tests for the project pre-pass skip logic (percona_obs.cmd_sync)."""

from percona_obs.cmd_sync import _can_skip_project_apply


def test_skip_when_unchanged_existing_plain_push():
    assert _can_skip_project_apply((False, False), None, False) is True


def test_no_skip_when_changed():
    assert _can_skip_project_apply((True, False), None, False) is False


def test_no_skip_when_new():
    assert _can_skip_project_apply((True, True), None, False) is False
    assert _can_skip_project_apply((False, True), None, False) is False


def test_no_skip_without_verdict():
    assert _can_skip_project_apply(None, None, False) is False


def test_no_skip_in_branch_mode():
    assert _can_skip_project_apply((False, False), "isv:percona", False) is False


def test_no_skip_with_force():
    assert _can_skip_project_apply((False, False), None, True) is False
```

In `tests/test_image_dep_repos.py`: delete `UBI9_ONLY_REPOS`, `test_new_layout_only_repos_filter`, `test_old_layout_only_repos_filter`, `test_filter_excluding_all_repos`; update the module docstring's last sentence to "Repository selection comes from the process-default RepositoryFilter (the active profile's slice)." and add:

```python
import percona_obs.common as common
from percona_obs.project_config import RepositoryFilter


def test_default_filter_slices_image_repos(tmp_path):
    pkg = _make_image_pkg(tmp_path, NEW_LAYOUT_YAML)
    common.set_default_repository_filter(RepositoryFilter(include_repos=("ubi9",)))
    try:
        assert image_dep_query_repos(pkg) == {"ubi9"}
        common.set_default_repository_filter(RepositoryFilter(include_repos=("UBI_8",)))
        assert image_dep_query_repos(pkg) == set()
    finally:
        common.set_default_repository_filter(None)
```

(`_make_image_pkg` writes a project.yaml with `name:` and repositories only; the tmp dir is outside `REPO_ROOT`, so `project_slice_name` returns `""` and the project test passes — the repo filter is what is exercised.)

Run: `venv/bin/python -m pytest -q tests/test_project_prepass.py tests/test_image_dep_repos.py` → FAIL (signatures still old).

- [ ] **Step 2: `targets.py`** — `image_dep_query_repos(package_path, env_vars=None, cache=None)`: delete the `only_repos` parameter, its docstring paragraph and the `if only_repos is not None:` block. Update the docstring: "The repository set is the sliced one (the active profile's filter is applied by the loader)."

- [ ] **Step 3: `obs_api.py`** — delete `_filter_meta_repos`. In `_apply_project_config` remove the `only_repos` parameter; replace

```python
    repos = project_config.get("repositories", [])
    # This project's own subproject path ...
    self_subproject = (...)
    repos = _filter_meta_repos(repos, only_repos, self_subproject)
```
with `repos = project_config.get("repositories", [])`.

- [ ] **Step 4: `cmd_sync.py`** — delete the `_IMAGES_REPO_RE`/`_CONTAINER_SUBPROJ_RE` definitions and their comment block; delete the `only_repos … container_subprojs … targets = [...]` block (from `only_repos: set[str] | None = getattr(args, "only_repos", None)` through the `targets = [ … ]` list comprehension that filters on `_CONTAINER_SUBPROJ_RE`); change `_can_skip_project_apply` to

```python
def _can_skip_project_apply(
    verdict: "tuple[bool, bool] | None",
    branch_rootprj: "str | None",
    force: bool,
) -> bool:
    """Return True when the pre-pass may skip a project's meta/prjconf apply.

    Requires a Phase 2.5 verdict of (changed=False, is_new=False) on a plain,
    unforced push.  In --branch-from mode the verdict compares the
    *production* project, so it cannot stand in for the target project's state.
    The verdict is computed on the sliced configuration (same loader), so the
    active profile's filter never invalidates it.
    """
    return branch_rootprj is None and not force and verdict == (False, False)
```
Replace the `effective_repos = (target_repos & effective_only_repos if … else target_repos)` expression with `effective_repos = target_repos`; drop the `effective_only_repos` argument from both `image_dep_query_repos(...)` calls (keep `env_vars` and `_target_repos_cache`: the new signature is `(package_path, env_vars, cache)`, so pass `cache=_target_repos_cache`); delete every `only_repos=effective_only_repos,` line; drop the fourth argument from the `_can_skip_project_apply(...)` call.

- [ ] **Step 5: `cli.py`** — delete the `sync_push_parser.add_argument("--only-repos", …)` block.

- [ ] **Step 6: Verify**

```bash
grep -rn "only_repos\|only-repos\|_IMAGES_REPO_RE\|_CONTAINER_SUBPROJ_RE\|_filter_meta_repos\|self_subproject" percona_obs tests ; echo "grep exit $?"
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
venv/bin/python $S/gate.py check $S/gate-baseline
```
Expected: grep prints nothing (exit 1), `0 errors`, suite passes, `GATE PASSED`.

- [ ] **Step 7: Commit**

```bash
git add -A percona_obs tests
git commit -s -m "sync push: drop --only-repos; the profile slice is the only repository selection"
```

---

### Task 5: `sync push` is slice-aware

**Goal:** Out-of-slice projects and packages are neither created nor counted as local (so orphan cleanup deletes them); explicit out-of-slice targets are an error; the run reports slice counts.

**Files:**
- Modify: `percona_obs/cmd_sync.py` (`cmd_sync`: env_vars block moved before target resolution; new `_slice_targets`, `_require_targets_in_slice`; summary line before both `_print_ok(f"sync successful…")` calls)
- Modify: `percona_obs/targets.py` (`_iter_project_chain` skips out-of-slice projects)
- Test: `tests/test_slice_selection.py` (append)

**Acceptance Criteria:**
- [ ] `_slice_targets(targets, env_vars, repo_filter, cache)` returns `(kept, skipped_projects, skipped_packages)`; an out-of-slice project drops all its packages and appears once in `skipped_projects`; an out-of-slice package appears as `<project>/<pkg>`
- [ ] `_require_targets_in_slice(args, kept, skipped_projects, skipped_packages)` raises `SystemExit` naming the package for `sync push <prj> <pkg>` and the project for `sync push <prj>` when nothing is kept; full-tree runs with nothing kept raise `SystemExit("error: nothing to sync: every target is out of slice for the active profile")`
- [ ] `_iter_project_chain` never yields a project for which `project_in_slice` is false (root included), using the shared cache
- [ ] the summary prints `slice: N project(s), M package(s) out of slice` when the filter is non-empty or anything was skipped; `--verbose` lists each skipped item as a `·` debug line
- [ ] gate: `GATE PASSED`

**Verify:** `venv/bin/python -m pytest -q tests/test_slice_selection.py -k "targets or chain"` → pass; then an offline smoke test of the whole command is not possible (it needs OBS), so also run `venv/bin/python -m percona_obs -R ROOT -e REMOTE_OBS_ORG_INTERCONNECT:x project config --offline --resolved >/dev/null` to confirm the resolver path still renders the tree.

**Steps:**

- [ ] **Step 1: Failing tests** (append to `tests/test_slice_selection.py`)

```python
# --- sync push targets -----------------------------------------------------------

from types import SimpleNamespace as _NS  # noqa: E402

from percona_obs.cmd_sync import _require_targets_in_slice, _slice_targets  # noqa: E402
from percona_obs.targets import _iter_project_chain  # noqa: E402


def _targets(root):
    s17 = root / "ppg/staging/17"
    return [
        ("ROOT:ppg:staging:17", s17 / "percona-postgresql"),
        ("ROOT:ppg:staging:17", s17 / "bison"),
        ("ROOT:ppg:staging:17:containers", s17 / "containers" / "image"),
    ]


def test_slice_targets_labs_and_boo(repo):
    root = repo(_TREE)
    cache: dict[Path, bool] = {}
    kept, skipped_projects, skipped_packages = _slice_targets(_targets(root), {}, LABS, cache)
    assert [p.name for _, p in kept] == ["percona-postgresql", "image"]
    assert skipped_projects == []
    assert skipped_packages == ["ROOT:ppg:staging:17/bison"]
    kept, skipped_projects, skipped_packages = _slice_targets(_targets(root), {}, BOO, {})
    assert [p.name for _, p in kept] == ["percona-postgresql", "bison"]
    assert skipped_projects == ["ROOT:ppg:staging:17:containers"]
    assert skipped_packages == []
    kept, sp, sk = _slice_targets(_targets(root), {}, RepositoryFilter.EMPTY, {})
    assert len(kept) == 3 and sp == [] and sk == []


def test_require_targets_in_slice_errors(repo):
    root = repo(_TREE)
    full = _NS(project=None, package=None)
    _require_targets_in_slice(full, [("x", root)], [], [])  # kept → fine
    with pytest.raises(SystemExit, match="nothing to sync: every target is out of slice"):
        _require_targets_in_slice(full, [], ["ROOT:a"], [])
    with pytest.raises(SystemExit, match=r"ppg:staging:17/bison is out of slice"):
        _require_targets_in_slice(
            _NS(project="ppg:staging:17", package="bison"), [], [], ["ROOT:ppg:staging:17/bison"]
        )
    with pytest.raises(SystemExit, match=r"project 'ppg:staging:17:containers' is out of slice"):
        _require_targets_in_slice(
            _NS(project="ppg:staging:17:containers", package=None),
            [],
            ["ROOT:ppg:staging:17:containers"],
            [],
        )


def test_iter_project_chain_skips_out_of_slice_projects(repo):
    root = repo(_TREE)
    (root / "ppg/staging/extras/containers").mkdir()
    (root / "ppg/staging/extras/containers/project.yaml").write_text(
        "repositories-inherit: false\nrepositories:\n  - name: ubi9\n    paths: []\n    archs: [x86_64]\n"
    )
    (root / "ppg/staging/project.yaml").write_text("title: staging\n")
    (root / "ppg/project.yaml").write_text("title: ppg\n")
    cache: dict[Path, bool] = {}
    common.set_default_repository_filter(LABS)
    names = [
        n for _, n, _ in _iter_project_chain(
            "ROOT:ppg:staging:extras:containers", root / "ppg/staging/extras/containers", cache
        )
    ]
    # root, ppg, ppg:staging keep UBI_9; ppg:staging:extras has zero repos → skipped
    assert names == ["ROOT", "ROOT:ppg", "ROOT:ppg:staging", "ROOT:ppg:staging:extras:containers"]
    common.set_default_repository_filter(BOO)
    names = [
        n for _, n, _ in _iter_project_chain(
            "ROOT:ppg:staging:extras:containers", root / "ppg/staging/extras/containers", {}
        )
    ]
    assert names == ["ROOT", "ROOT:ppg", "ROOT:ppg:staging"]
```

Run: `venv/bin/python -m pytest -q tests/test_slice_selection.py -k "targets or chain"` → ImportError.

- [ ] **Step 2: `targets.py`** — add the import `from .project_config import project_in_slice` and change `_iter_project_chain`:

```python
def _iter_project_chain(
    obs_project: str,
    project_path: Path,
    slice_cache: "dict[Path, bool] | None" = None,
):
    """Yield (raw_obs_project, obs_project_name, path) from root down to project_path.

    Walks up from project_path to REPO_ROOT, then yields in reverse (root-first)
    so every ancestor project level is visited before the immediate project.
    Projects that are out of the active slice (``project_in_slice``: excluded
    by the profile, or left with zero repositories) are not yielded: they are
    never created, and a full-tree push deletes them as orphans.

    raw_obs_project is the path-derived key used for deduplication.
    obs_project_name may differ if project.yaml contains a 'name' override.
    *slice_cache* memoises the in-slice decision per project path across calls.
    """
    ...existing walk...
    for proj, obs_name, path in reversed(chain):
        if _is_release_dir(path):
            continue  # release dirs are managed by sync release, not sync push
        if not ((path / "project.yaml").exists() or _has_direct_packages(path)):
            continue
        if not project_in_slice(path, cache=slice_cache):
            continue
        yield proj, obs_name, path
```

- [ ] **Step 3: `cmd_sync.py`** — add imports `from .project_config import package_in_slice, project_in_slice` and `from .common import get_default_repository_filter` (extend the existing `from .common import (...)` list). Add the helpers next to `_can_skip_project_apply`:

```python
def _slice_targets(
    targets: "list[tuple[str, Path]]",
    env_vars: dict[str, str],
    repo_filter,
    slice_cache: "dict[Path, bool]",
) -> "tuple[list[tuple[str, Path]], list[str], list[str]]":
    """Drop targets that are out of the active slice.

    Returns (kept, skipped_projects, skipped_packages): projects whose every
    package is dropped because the *project* is out of slice, and
    ``<project>/<package>`` entries dropped because the package builds in no
    surviving repository.  *slice_cache* is filled for _iter_project_chain.
    """
    kept: list[tuple[str, Path]] = []
    skipped_projects: set[str] = set()
    skipped_packages: list[str] = []
    configs: dict[Path, dict] = {}
    for obs_project, package_path in targets:
        proj_path = package_path.parent
        cfg = configs.get(proj_path)
        if cfg is None:
            cfg = configs[proj_path] = _load_project_config_with_inheritance(
                proj_path, env_vars, repo_filter
            )
        if not project_in_slice(proj_path, env_vars, repo_filter, cfg, slice_cache):
            skipped_projects.add(obs_project)
            logger.debug(f"out of slice: project {obs_project}")
            continue
        if not package_in_slice(package_path, env_vars, repo_filter, cfg, slice_cache):
            skipped_packages.append(f"{obs_project}/{package_path.name}")
            logger.debug(f"out of slice: package {obs_project}/{package_path.name}")
            continue
        kept.append((obs_project, package_path))
    return kept, sorted(skipped_projects), skipped_packages


def _require_targets_in_slice(
    args, kept: list, skipped_projects: list[str], skipped_packages: list[str]
) -> None:
    """Explicit targets that are entirely out of slice are an error, not a silent no-op."""
    if kept:
        return
    if getattr(args, "package", None):
        raise SystemExit(
            f"error: {args.project}/{args.package} is out of slice for the active "
            "profile (the package builds in no repository this instance carries)"
        )
    if getattr(args, "project", None):
        raise SystemExit(
            f"error: project '{args.project}' is out of slice for the active profile"
        )
    raise SystemExit(
        "error: nothing to sync: every target is out of slice for the active profile"
    )
```

In `cmd_sync`: move the `env_vars: dict[str, str] = {...}` block (with its comment) to just before `targets = _resolve_targets(args)`, then insert after `targets = _resolve_targets(args)`:

```python
    # Restrict the run to the active profile's slice.  Dropped projects and
    # packages are not counted as local, so the orphan cleanup below removes
    # them from this instance on a full-tree push (spec Section 2).
    _slice_cache: dict[Path, bool] = {}
    targets, _slice_skipped_projects, _slice_skipped_packages = _slice_targets(
        targets, env_vars, get_default_repository_filter(), _slice_cache
    )
    _require_targets_in_slice(args, targets, _slice_skipped_projects, _slice_skipped_packages)
    if _slice_skipped_projects or _slice_skipped_packages:
        _print_action(
            f"planning: {len(_slice_skipped_projects)} project(s) and "
            f"{len(_slice_skipped_packages)} package(s) out of slice"
        )
```

Pass `_slice_cache` to every `_iter_project_chain(...)` call in `cmd_sync` (two call sites: the pre-pass and the single-package chain): `_iter_project_chain(obs_project, package_path.parent, _slice_cache)`.

Before each of the two `_print_ok(f"sync successful{suffix}")` lines add:

```python
    if (
        not get_default_repository_filter().is_empty
        or _slice_skipped_projects
        or _slice_skipped_packages
    ):
        _print_same(
            f"slice: {len(_slice_skipped_projects)} project(s), "
            f"{len(_slice_skipped_packages)} package(s) out of slice"
        )
```

- [ ] **Step 4: black, pyright, tests, gate; commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
venv/bin/python $S/gate.py check $S/gate-baseline
git add percona_obs/cmd_sync.py percona_obs/targets.py tests/test_slice_selection.py
git commit -s -m "sync push: skip out-of-slice projects and packages; report slice counts"
```

---

### Task 6: `project verify` path integrity and slice summary; `project config` marking

**Goal:** Catch a kept repository pathing into a repository or project the slice does not carry; show what is out of slice.

**Files:**
- Modify: `percona_obs/cmd_project.py` (new `_validate_repo_path_refs` after `_validate_subproject_refs`; `cmd_project_verify`; `cmd_project_config` loop)
- Test: `tests/test_slice_selection.py` (append)

**Acceptance Criteria:**
- [ ] `_validate_repo_path_refs(root, env_vars)` returns `(yaml_path, msg)` for a kept repo whose `subproject:` path names (a) an out-of-slice project or (b) a repository that project does not keep; unfiltered it is plain repo-level validation; paths whose `subproject:` contains `${…}` or names a directory that does not exist are skipped (the latter is reported by `_validate_subproject_refs`)
- [ ] `project verify` prints these as `error: <file>: …` and exits 1; with a non-empty filter it prints `slice: N project(s), M package(s) out of slice`
- [ ] `project config --resolved` prints `# project <name>: out of slice` for out-of-slice projects instead of their YAML
- [ ] On the real tree: `project verify` unfiltered reports zero new errors (obs_scm revision errors are network noise); with the `boo` and `labs` profiles below it reports zero errors (any error found is a genuine tree/slice inconsistency: report it to the user verbatim, do not silence it)

**Verify:**
```bash
venv/bin/python -m pytest -q tests/test_slice_selection.py -k path_refs
venv/bin/python -m percona_obs -e OBS_ROOTPRJ:x -e REMOTE_OBS_ORG_INTERCONNECT:x -e OBS_CONTAINER_REGISTRY_ROOTPRJ:x project verify 2>&1 | grep -v "obs_scm revision" | tail -5
```

**Steps:**

- [ ] **Step 1: Failing tests** (append)

```python
# --- verify: repository path integrity -----------------------------------------

from percona_obs.cmd_project import _validate_repo_path_refs  # noqa: E402


def test_validate_repo_path_refs(repo):
    root = repo(
        {
            "project.yaml": _ROOT,
            "common/deps/build/project.yaml": "title: B\n",
            "ppg/staging/17/project.yaml": "title: S\n",
            "ppg/staging/17/containers/project.yaml": (
                "repositories-inherit: false\nrepositories:\n"
                "  - name: ubi9\n    archs: [x86_64]\n    paths:\n"
                "      - subproject: ppg:staging:17\n        repository: UBI_9\n"
                "      - subproject: ppg:staging:17\n        repository: UBI_8\n"
                "      - subproject: does:not:exist\n        repository: UBI_9\n"
                "      - subproject: ${OBS_X}:y\n        repository: UBI_9\n"
            ),
        }
    )

    def msgs(errors):
        return [(str(p.relative_to(root)), m) for p, m in errors]

    # unfiltered: UBI_8 is not defined by ppg:staging:17 (root only has RockyLinux_9/UBI_9)
    assert msgs(_validate_repo_path_refs(root, None)) == [
        (
            "ppg/staging/17/containers/project.yaml",
            "repository 'ubi9' paths to 'ppg:staging:17/UBI_8', which that subproject does not define",
        )
    ]
    # boo: containers itself is out of slice → nothing to check there
    common.set_default_repository_filter(BOO)
    assert _validate_repo_path_refs(root, None) == []
    # labs with staging excluded by project glob: the target is out of slice
    common.set_default_repository_filter(
        RepositoryFilter(include_repos=("UBI_*", "ubi*"), exclude_projects=("ppg:staging:17",))
    )
    assert msgs(_validate_repo_path_refs(root, None)) == [
        (
            "ppg/staging/17/containers/project.yaml",
            "repository 'ubi9' paths to subproject 'ppg:staging:17', which is out of slice",
        ),
        (
            "ppg/staging/17/containers/project.yaml",
            "repository 'ubi9' paths to subproject 'ppg:staging:17', which is out of slice",
        ),
    ]
```

Run: `venv/bin/python -m pytest -q tests/test_slice_selection.py -k path_refs` → ImportError.

- [ ] **Step 2: Implement `_validate_repo_path_refs`** (after `_validate_subproject_refs` in `cmd_project.py`; import `from .project_config import package_in_slice, project_in_slice` and `from .common import get_default_repository_filter`)

```python
def _validate_repo_path_refs(
    root: Path, env_vars: dict[str, str] | None
) -> list[tuple[Path, str]]:
    """Check that kept repositories path into repositories the slice carries.

    For every in-slice project and every kept repository, each ``subproject:``
    path that names a project in the tree must name a project that is in
    slice and a repository that project keeps.  Unfiltered this is plain
    repo-level reference validation.  Paths with ``${VAR}`` in the subproject
    name and paths to directories that do not exist are skipped (the latter
    is reported by ``_validate_subproject_refs``).
    """
    errors: list[tuple[Path, str]] = []
    repo_filter = get_default_repository_filter()
    configs: dict[Path, dict] = {}
    slice_cache: dict[Path, bool] = {}

    def cfg(p: Path) -> dict:
        if p not in configs:
            configs[p] = _load_project_config_with_inheritance(p, env_vars, repo_filter)
        return configs[p]

    for yaml_path in _project_yaml_files(root):
        proj = yaml_path.parent
        if not project_in_slice(proj, env_vars, repo_filter, cfg(proj), slice_cache):
            continue
        for repo in cfg(proj).get("repositories", []):
            for path_info in repo.get("paths", []):
                sub = path_info.get("subproject")
                if sub is None or _ENV_VAR_RE.search(str(sub)):
                    continue
                target = REPO_ROOT.joinpath(*str(sub).split(":"))
                if not target.is_dir():
                    continue
                if not project_in_slice(target, env_vars, repo_filter, cfg(target), slice_cache):
                    errors.append(
                        (
                            yaml_path,
                            f"repository '{repo['name']}' paths to subproject '{sub}', "
                            "which is out of slice",
                        )
                    )
                    continue
                kept = {r["name"] for r in cfg(target).get("repositories", [])}
                ref = path_info.get("repository")
                if ref not in kept:
                    errors.append(
                        (
                            yaml_path,
                            f"repository '{repo['name']}' paths to '{sub}/{ref}', "
                            "which that subproject does not define",
                        )
                    )
    return errors
```

- [ ] **Step 3: `cmd_project_verify`** — after `ref_errors = _validate_subproject_refs(scan_root)` add `repo_path_errors = _validate_repo_path_refs(scan_root, env_vars)`; print them in the same loop style as `ref_errors`; add `repo_path_errors` to the `if … or …: sys.exit(1)` condition. Before `_print_ok("project verify: all checks passed")` add the slice summary:

```python
    repo_filter = get_default_repository_filter()
    if not repo_filter.is_empty:
        root_obs = load_project_yaml(REPO_ROOT / "project.yaml").get("name") or (
            args.rootprj or "ROOT"
        )
        out_projects = [
            name
            for name, path in find_projects(REPO_ROOT, root_obs)
            if not project_in_slice(path, env_vars, repo_filter)
        ]
        out_packages = [
            f"{obs}/{path.name}"
            for obs, path in find_packages(REPO_ROOT, root_obs)
            if not package_in_slice(path, env_vars, repo_filter)
        ]
        for name in out_projects:
            logger.debug(f"out of slice: project {name}")
        for name in out_packages:
            logger.debug(f"out of slice: package {name}")
        _print_same(
            f"slice: {len(out_projects)} project(s), {len(out_packages)} package(s) out of slice"
        )
```
(`find_packages`, `logger` and `_print_same` — check the module's existing imports and add what is missing from `.common`; `logger = logging.getLogger("percona_obs")` is the pattern used in `cmd_sync.py`.)

- [ ] **Step 4: `cmd_project_config`** — at the top of the `for obs_project_name, project_path in projects:` loop insert:

```python
        if not project_in_slice(project_path, env_vars):
            print(sep)
            print(f"# project {obs_project_name}: out of slice")
            continue
```

- [ ] **Step 5: Offline profiles for the real-tree check** — create these two files in the worktree (they are git-ignored; no `apiurl`, so `project verify` makes no network calls):

`.profile/boo.yaml`:
```yaml
rootprj: isv:percona
exclude-repositories: ["UBI_*", "ubi*", "images"]
```
`.profile/labs.yaml`:
```yaml
rootprj: percona
include-repositories: ["UBI_*", "ubi*", "images"]
```

Run:
```bash
E="-e OBS_ROOTPRJ:x -e REMOTE_OBS_ORG_INTERCONNECT:x -e OBS_CONTAINER_REGISTRY_ROOTPRJ:x"
venv/bin/python -m percona_obs $E project verify 2>&1 | grep -v "obs_scm revision" | tail -5
venv/bin/python -m percona_obs -P boo $E --verbose project verify 2>&1 | grep -v "obs_scm revision" | tail -40
venv/bin/python -m percona_obs -P labs $E --verbose project verify 2>&1 | grep -v "obs_scm revision" | tail -60
```
Expected: no `error:` lines other than obs_scm ones; `slice:` lines. For `labs` the listed out-of-slice projects must include every `*:tarballs` project and `common:deps:runtime`-style RPM projects must be *in* (they keep UBI repos); for `boo` they must include `common:containers:ubi8`, `common:containers:ubi9`, every `*:containers` and `ppg:staging:extras`. Paste both `slice:` summaries and any `error:` line into the task report.

- [ ] **Step 6: black, pyright, tests, gate; commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
venv/bin/python $S/gate.py check $S/gate-baseline
git add percona_obs/cmd_project.py tests/test_slice_selection.py
git commit -s -m "project verify: repository path integrity across the slice; slice summary; config marks out-of-slice projects"
```

---

### Task 7: Release flow — generator reads the tree; `sync release` collects in-slice mirrors

**Goal:** `project release` writes an instance-agnostic release tree from the unfiltered resolved staging config; `sync release` releases only the subprojects the instance holds.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`cmd_project_release` live-meta block ~2033-2047; `_write_release_tree` loader call ~1494)
- Modify: `percona_obs/obs_api.py` (delete `_obs_meta_to_yaml_repos`, `_obs_meta_to_yaml_debuginfo` if no remaining caller; keep `_read_project_release_source`)
- Modify: `percona_obs/cmd_sync.py` (`_collect_release_subprojects`)
- Test: `tests/test_sync_release.py` (`_mk_tree` fixture, new test), `tests/test_project_release.py` (new test)
- Create: `$S/release_gate.py` (throwaway)

**Acceptance Criteria:**
- [ ] `_write_release_tree` output is unchanged when a non-empty default filter is installed (mirrors are unfiltered)
- [ ] `cmd_project_release` no longer calls `show_project_meta`/`show_project_conf`/`_read_project_release_source` for the top-level file; `project_data["repositories"]`, `["debuginfo"]`, `["project-config"]` come from `resolve_project_config(source_path, env_vars, repo_filter=RepositoryFilter.EMPTY)`
- [ ] `_collect_release_subprojects` skips subprojects whose mirror is out of slice and reports a missing mirror only when the *source* subproject is in slice
- [ ] `release_gate.py` output for `ppg:releases:17` and `18` is reported verbatim (repositories/debuginfo/effective-prjconf differences between the frozen files and the tree-based rendering), with no edit under `root/ppg/releases/`

**Verify:** `venv/bin/python -m pytest -q tests/test_sync_release.py tests/test_project_release.py` → pass

**Steps:**

- [ ] **Step 1: Failing tests**

In `tests/test_sync_release.py` replace `_mk_tree` with a tree the resolver can slice, and add the slice test:

```python
_REPO_YAML = "repositories:\n  - name: {name}\n    archs: [x86_64]\n    paths: []\n"


def _mk_tree(tmp_path: Path, monkeypatch=None):
    """staging tree with containers (ubi9 repo) + tarballs (ssl3 repo); release tree mirrors only containers."""
    root = tmp_path / "root"
    (root / "macros.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "project.yaml").write_text(_REPO_YAML.format(name="RockyLinux_9"))
    src = root / "ppg/staging/17"
    (src / "containers").mkdir(parents=True)
    (src / "containers" / "project.yaml").write_text(
        "repositories-inherit: false\n" + _REPO_YAML.format(name="ubi9")
    )
    (src / "tarballs").mkdir()
    (src / "tarballs" / "project.yaml").write_text(
        "repositories-inherit: false\n" + _REPO_YAML.format(name="ssl3")
    )
    (src / "project.yaml").write_text("title: S\n")
    rel = root / "ppg/releases/17"
    (rel / "containers").mkdir(parents=True)
    (rel / "containers" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ubi9")
    )
    (rel / "release.yaml").write_text("project: ppg:staging:17\nreleases: [ppg/17.11-1]\n")
    if monkeypatch is not None:
        import percona_obs.common as common

        monkeypatch.setattr(common, "REPO_ROOT", root)
    return src, rel
```

Update every existing `_mk_tree(tmp_path)` call in that file to `_mk_tree(tmp_path, monkeypatch)` (all those tests already take `monkeypatch`). Add:

```python
def test_collect_release_subprojects_respects_slice(tmp_path, monkeypatch):
    import percona_obs.common as common
    from percona_obs.project_config import RepositoryFilter

    src, rel = _mk_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(cmd_sync, "resolve_project_path", lambda pid: src)
    try:
        # boo: containers is out of slice (mirror and source) → not a pair, not missing;
        # tarballs is in slice on boo and has no mirror → missing
        common.set_default_repository_filter(RepositoryFilter(exclude_repos=("ubi*",)))
        pairs, missing = _collect_release_subprojects("ppg:staging:17", rel)
        assert pairs == [] and missing == ["tarballs"]
        # labs: containers released, tarballs is out of slice → not missing
        common.set_default_repository_filter(RepositoryFilter(include_repos=("ubi*",)))
        pairs, missing = _collect_release_subprojects("ppg:staging:17", rel)
        assert [n for n, _ in pairs] == ["containers"] and missing == []
    finally:
        common.set_default_repository_filter(None)
```

In `tests/test_project_release.py` add after `test_write_release_tree_materializes_delta_source`:

```python
def test_write_release_tree_ignores_the_process_default_filter(tmp_path, monkeypatch):
    """Release mirrors are instance-agnostic: a labs/boo default filter must not slice them."""
    import percona_obs.common as common
    from percona_obs.project_config import RepositoryFilter

    root = tmp_path / "root"
    (root / "ppg/staging/17/extras").mkdir(parents=True)
    (root / "macros.yaml").write_text("- X: 1\n")
    (root / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {"name": "UBI_9", "paths": [], "archs": ["x86_64"]},
                    {"name": "RockyLinux_9", "paths": [], "archs": ["x86_64"]},
                ]
            }
        )
    )
    (root / "ppg/staging/17/project.yaml").write_text("title: S17\n")
    (root / "ppg/staging/17/extras/project.yaml").write_text("title: E\n")
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    common.set_default_repository_filter(RepositoryFilter(exclude_repos=("UBI_*",)))
    try:
        rel = root / "ppg/releases/17"
        _write_release_tree(
            rel, {"build": False, "repositories": []}, root / "ppg/staging/17",
            "ppg:staging:17", "ppg:releases:17", "ppg", "17",
        )
    finally:
        common.set_default_repository_filter(None)
    extras = yaml.safe_load((rel / "extras" / "project.yaml").read_text())
    assert [r["name"] for r in extras["repositories"]] == ["UBI_9", "RockyLinux_9"]
```

Run both files → the new tests FAIL.

- [ ] **Step 2: `_write_release_tree`** — change the loader call to

```python
        source_sub_config = _load_project_config_with_inheritance(
            sub_path, repo_filter=RepositoryFilter.EMPTY
        )
```
and extend the docstring: "Always unfiltered (RepositoryFilter.EMPTY): the release tree is instance-agnostic; each instance's `sync release` slices it." Import `from .project_config import RepositoryFilter, resolve_project_config` in `cmd_project.py`.

- [ ] **Step 3: `cmd_project_release`** — replace the block from `# Fetch source project topology from OBS.` through the `source_prjconf` try/except with:

```python
    # Source project topology comes from the tree, unfiltered: the release
    # snapshot is instance-agnostic and each instance's `sync release` slices
    # it (spec Section 4).  Env vars follow the same precedence as sync.
    release_env: dict[str, str] = {
        **(parse_env_overrides(args.env_overrides) if args.env_overrides else {}),
        **auto_rootprj_env(args.rootprj),
    }
    source_cfg = resolve_project_config(
        source_path, release_env, repo_filter=RepositoryFilter.EMPTY
    )
    source_repos = source_cfg.get("repositories", [])
    source_debuginfo = source_cfg.get("debuginfo")
    source_prjconf = (source_cfg.get("project-config") or "").strip()
```
Remove the now-unused imports/variables (`ET` use for `meta_root` if nothing else uses it in the module, `_read_project_release_source`, `_obs_meta_to_yaml_repos`, `_obs_meta_to_yaml_debuginfo`); make sure `parse_env_overrides` and `auto_rootprj_env` are imported from `.common`. If `_obs_meta_to_yaml_repos`/`_obs_meta_to_yaml_debuginfo` have no remaining caller (`grep -rn` in `percona_obs tests`), delete them from `obs_api.py`.

- [ ] **Step 4: `_collect_release_subprojects`** in `cmd_sync.py`

```python
    for sub_obs_id, sub_path in find_projects(source_path, source_project_id):
        if sub_obs_id == source_project_id:
            continue
        if not (sub_path / "project.yaml").is_file():
            continue  # intermediate directory, not a real OBS project
        subproject_name = sub_obs_id[len(source_project_id) + 1 :]
        release_sub_path = release_path / Path(*subproject_name.split(":"))
        if (release_sub_path / "project.yaml").is_file():
            if project_in_slice(release_sub_path):
                pairs.append((subproject_name, release_sub_path))
            # else: this instance does not hold the subproject — nothing to release
        elif project_in_slice(sub_path):
            missing.append(subproject_name)
        # else: source out of slice too; a missing mirror is irrelevant here
    return pairs, missing
```
Update the docstring: "Subprojects out of the active slice are skipped on both sides; `missing` lists only in-slice source subprojects without a mirror."

- [ ] **Step 5: Release generator gate** — write `$S/release_gate.py`:

```python
"""Compare the frozen release project.yaml with the tree-based rendering (throwaway)."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, ".")
sys.path.insert(0, sys.argv[1])  # directory holding gate.py (for effective_prjconf)
from gate import effective_prjconf  # noqa: E402
from percona_obs.common import REPO_ROOT, auto_rootprj_env  # noqa: E402
from percona_obs.project_config import RepositoryFilter, resolve_project_config  # noqa: E402

env = {"REMOTE_OBS_ORG_INTERCONNECT": "", **auto_rootprj_env("isv:percona")}
for major in sys.argv[2:]:
    frozen = yaml.safe_load((REPO_ROOT / "ppg/releases" / major / "project.yaml").read_text())
    cfg = resolve_project_config(REPO_ROOT / "ppg/staging" / major, env, repo_filter=RepositoryFilter.EMPTY)
    print(f"== ppg:releases:{major}")
    fr = {r["name"]: r for r in frozen.get("repositories", [])}
    tr = {r["name"]: r for r in cfg.get("repositories", [])}
    for name in sorted(set(fr) | set(tr)):
        if name not in fr: print(f"  repo only in tree:   {name}"); continue
        if name not in tr: print(f"  repo only in frozen: {name}"); continue
        if fr[name].get("paths") != tr[name].get("paths") or fr[name].get("archs") != tr[name].get("archs"):
            print(f"  repo differs: {name}\n    frozen={fr[name]}\n    tree  ={tr[name]}")
    if frozen.get("debuginfo") != cfg.get("debuginfo"):
        print(f"  debuginfo differs: frozen={frozen.get('debuginfo')} tree={cfg.get('debuginfo')}")
    names = sorted(set(fr) | set(tr))
    a = effective_prjconf(frozen.get("project-config") or "", names)
    b = effective_prjconf(cfg.get("project-config") or "", names)
    for n in names:
        if a[n] != b[n]:
            print(f"  prjconf[{n}] missing={[x for x in a[n] if x not in b[n]]} extra={[x for x in b[n] if x not in a[n]]}")
```
Run: `venv/bin/python $S/release_gate.py $S 17 18`. Copy the output verbatim into the task report. Differences are expected wherever staging moved on since the release was cut (they are what the *next* `project release` would legitimately snapshot); do not edit anything under `root/ppg/releases/`.

- [ ] **Step 6: black, pyright, tests, gate; commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
venv/bin/python $S/gate.py check $S/gate-baseline
git add percona_obs/cmd_project.py percona_obs/cmd_sync.py percona_obs/obs_api.py tests/test_sync_release.py tests/test_project_release.py
git commit -s -m "release: generate the release tree from the tree, release only in-slice subprojects"
```

---

### Task 8: CI poll script honours the slice

**Goal:** `poll_obs_builds.py` never polls projects the instance does not hold.

**Files:**
- Modify: `.github/scripts/poll_obs_builds.py` (env section, imports, discovery loop, docstring)

**Acceptance Criteria:**
- [ ] `OBS_REPO_FILTER` (JSON object; keys `include_repos`, `exclude_repos`, `include_projects`, `exclude_projects`, comma-separated strings or lists; other keys ignored) installs the default filter before discovery
- [ ] discovery skips packages for which `package_in_slice` is false
- [ ] `OBS_DISCOVER_ONLY=1` prints the monitored project list and exits 0 before any OBS call other than `osc.conf.get_config`

**Verify:**
```bash
cd .claude/worktrees/multi-obs
OBS_APIURL=http://localhost:1 OBS_ROOTPRJ=isv:percona OBS_DISCOVER_ONLY=1 \
  OBS_REPO_FILTER='{"include_repos":"UBI_*,ubi*,images"}' PYTHONPATH=. venv/bin/python .github/scripts/poll_obs_builds.py | grep -c ":containers"
```
→ ≥ 5 (containers projects monitored on labs), and the same command with `OBS_REPO_FILTER='{"exclude_repos":"UBI_*,ubi*,images"}'` → `0`.

**Steps:**

- [ ] **Step 1: Edit the script**

Docstring, add under "Optional environment variables":
```
OBS_REPO_FILTER         JSON object with the instance's slice (include_repos,
                        exclude_repos, include_projects, exclude_projects as
                        comma-separated strings or lists; the matrix entry of
                        OBS_INSTANCES can be passed as is).  Projects and
                        packages out of the slice are never polled.
OBS_DISCOVER_ONLY       When set, print the monitored project list and exit 0
                        (offline self-test of the discovery/slice logic)
```
Imports: add `from percona_obs.common import set_default_repository_filter` (extend the existing import) and `from percona_obs.project_config import RepositoryFilter, package_in_slice`.

After `scope_project = …` add:
```python
# The instance's slice: projects/packages it does not hold must not be polled.
repo_filter = RepositoryFilter.from_env_json(os.environ.get("OBS_REPO_FILTER", ""))
set_default_repository_filter(repo_filter)
discover_only = bool(os.environ.get("OBS_DISCOVER_ONLY"))
```
In the discovery loop, first statement inside `for obs_project, package_path in find_packages(scope_path, scope_obs):`:
```python
    if not package_in_slice(package_path, cache=_slice_cache):
        continue
```
with `_slice_cache: dict = {}` defined right before the loop. After the `print(f"Monitoring {len(obs_projects)} OBS project(s): …")` line add:
```python
if discover_only:
    sys.exit(0)
```

- [ ] **Step 2: Verify** with the two commands above, then `venv/bin/python -m pyflakes .github/scripts/poll_obs_builds.py 2>/dev/null || venv/bin/python -c "import ast,sys; ast.parse(open('.github/scripts/poll_obs_builds.py').read())"`.

- [ ] **Step 3: Commit**

```bash
git add .github/scripts/poll_obs_builds.py
git commit -s -m "poll_obs_builds: honour the instance slice (OBS_REPO_FILTER)"
```

---

### Task 9: `profile create --narrow-repos` (label narrowing as an intersection)

**Goal:** The PR workflow can narrow an instance profile to the PR's repo labels without ever widening it.

**Files:**
- Modify: `percona_obs/cli.py` (flag on `profile_create_parser`)
- Modify: `percona_obs/cmd_profile.py` (`cmd_profile_create`)
- Test: `tests/test_slice_selection.py` (append)

**Acceptance Criteria:**
- [ ] `--narrow-repos A,B` (repeatable) sets `include-repositories` to the entries of A,B that the profile's own filter accepts (`repo_matches` on the entry, so a concrete name is tested against the include/exclude globs; a glob entry such as `ssl*` is kept iff it is itself accepted as a name would be, e.g. by `exclude-repositories` not matching it and an include glob matching it literally or being absent)
- [ ] the profile's `exclude-repositories`, `include-projects`, `exclude-projects` are kept as they are
- [ ] an empty result exits with code 3 and `error: --narrow-repos leaves no repository for this profile (…)`, writing nothing
- [ ] without `--narrow-repos` behaviour is unchanged

**Verify:** `venv/bin/python -m pytest -q tests/test_slice_selection.py -k narrow` → pass

**Steps:**

- [ ] **Step 1: Failing tests** (append)

```python
# --- profile create --narrow-repos -------------------------------------------------


def _create_args(profiles_dir, **over):
    base = dict(
        apiurl="https://x", rootprj="r", name="pr-1", env_overrides=[], profile=None,
        include_repos=[], exclude_repos=[], include_projects=[], exclude_projects=[], narrow_repos=[],
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_narrow_repos_intersects_with_instance_filter(profiles_dir):
    # labs instance narrowed by labels RockyLinux_9, ubi9-images (→ ubi9, UBI_9) and ssl*
    args = _create_args(
        profiles_dir,
        include_repos=["UBI_*,ubi*,images"],
        exclude_projects=["common:containers:ubi8"],
        narrow_repos=["RockyLinux_9,ubi9", "UBI_9", "ssl*"],
    )
    cmd_profile.cmd_profile_create(args)
    data = yaml.safe_load((profiles_dir / "pr-1.yaml").read_text())
    assert data["include-repositories"] == ["ubi9", "UBI_9"]
    assert data["exclude-projects"] == ["common:containers:ubi8"]
    # boo instance narrowed by the same labels keeps RockyLinux_9 and ssl*
    args = _create_args(
        profiles_dir, name="pr-2", exclude_repos=["UBI_*,ubi*,images"],
        narrow_repos=["RockyLinux_9,ubi9,UBI_9,ssl*"],
    )
    cmd_profile.cmd_profile_create(args)
    data = yaml.safe_load((profiles_dir / "pr-2.yaml").read_text())
    assert data["include-repositories"] == ["RockyLinux_9", "ssl*"]
    assert data["exclude-repositories"] == ["UBI_*", "ubi*", "images"]


def test_narrow_repos_empty_result_exits_3(profiles_dir):
    args = _create_args(
        profiles_dir, include_repos=["UBI_*"], narrow_repos=["RockyLinux_9,Debian_13"]
    )
    with pytest.raises(SystemExit) as exc:
        cmd_profile.cmd_profile_create(args)
    assert exc.value.code == 3
    assert not (profiles_dir / "pr-1.yaml").exists()
```

- [ ] **Step 2: Implement** — `cli.py`, after the four filter flags:

```python
    profile_create_parser.add_argument(
        "--narrow-repos",
        metavar="REPO[,REPO...]",
        action="append",
        default=[],
        dest="narrow_repos",
        help="Restrict the slice to these repository names (repeatable; used by the PR "
        "workflow for repo labels). Only names the profile's own include/exclude rules "
        "already accept are kept; exits 3 when none is left.",
    )
```
`cmd_profile.cmd_profile_create`, after the round-trip block and before `data = …`:

```python
    narrow = _split_globs(getattr(args, "narrow_repos", []) or [])
    if narrow:
        kept = tuple(n for n in narrow if repo_filter.repo_matches(n))
        if not kept:
            print(
                "error: --narrow-repos leaves no repository for this profile "
                f"(narrowed to {', '.join(narrow)}; profile rules: {repo_filter.to_profile()})",
                file=sys.stderr,
            )
            raise SystemExit(3)
        repo_filter = RepositoryFilter(
            include_repos=kept,
            exclude_repos=repo_filter.exclude_repos,
            include_projects=repo_filter.include_projects,
            exclude_projects=repo_filter.exclude_projects,
        )
```
(add `import sys` to `cmd_profile.py`).

- [ ] **Step 3: black, pyright, tests; commit**

```bash
venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest -q tests
git add percona_obs/cli.py percona_obs/cmd_profile.py tests/test_slice_selection.py
git commit -s -m "profile create --narrow-repos: intersect the slice with PR repo labels"
```

---

### Task 10: CI workflows — one job per instance

**Goal:** `sync-main`, `obs-pr-check` and `obs-release` run their OBS jobs once per entry of the `OBS_INSTANCES` repository variable, each with its own profile, credentials and artifacts.

**Files:**
- Modify: `.github/workflows/sync-main.yml`
- Modify: `.github/workflows/obs-pr-check.yml`
- Modify: `.github/workflows/obs-release.yml`
- Modify: `.github/scripts/post_pr_comment.py`
- Modify: `README.md` (badge URL)

**Acceptance Criteria:**
- [ ] every job that talks to OBS uses `strategy: {fail-fast: false, matrix: {instance: "${{ fromJSON(vars.OBS_INSTANCES) }}"}}`, `matrix.instance.apiurl`/`rootprj`/`pr_rootprj`, `secrets[format('OBS_PASSWORD_{0}', matrix.instance.name)]`, `matrix.instance.user || vars.OBS_USER`
- [ ] profiles are created with the instance's filter flags; PR profiles additionally get `--narrow-repos` from labels, and a leg whose narrowed slice is empty (exit 3) skips its sync steps and posts no comment
- [ ] artifacts and badge files are suffixed with the instance name; the poll step receives `OBS_REPO_FILTER: ${{ toJSON(matrix.instance) }}`
- [ ] `obs-release`: lock taken in a `lock` job, released in an `unlock` job that `needs: release` and runs `if: always()` with the existing pending-runs guard and the GitHub-release step; the matrix `release` job runs between them
- [ ] `post_pr_comment.py` uses marker `<!-- obs-pr-check:<instance> -->` and a heading suffix `(<instance>)` when `OBS_INSTANCE` is set, so each instance owns one comment
- [ ] `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml` succeeds

**Verify:** the YAML parse command above; `grep -c "matrix.instance" .github/workflows/sync-main.yml .github/workflows/obs-pr-check.yml .github/workflows/obs-release.yml` (each > 0); `grep -n "vars.OBS_APIURL\|vars.OBS_ROOTPRJ\|vars.OBS_PR_ROOTPRJ\|secrets.OBS_PASSWORD\b" .github/workflows/sync-main.yml .github/workflows/obs-release.yml` prints nothing; in `obs-pr-check.yml` those names remain only in the `detect-qa-matrix` and `qa` jobs (QA deferred).

**Steps:**

- [ ] **Step 1: Shared snippets** (use verbatim in all three workflows)

Job header:
```yaml
    strategy:
      fail-fast: false
      matrix:
        instance: ${{ fromJSON(vars.OBS_INSTANCES) }}
```
Setup:
```yaml
      - uses: ./.github/actions/obs-setup
        with:
          obs-apiurl: ${{ matrix.instance.apiurl }}
          obs-user: ${{ matrix.instance.user || vars.OBS_USER }}
          obs-password: ${{ secrets[format('OBS_PASSWORD_{0}', matrix.instance.name)] }}
```
Profile creation (bash; `NAME` is the profile name, `ROOTPRJ` the rootprj to use, `BRANCH`/`REPO_URL` the packaging ref/url):
```yaml
      - name: Create percona-obs profile (${{ matrix.instance.name }})
        shell: bash
        env:
          OBS_APIURL: ${{ matrix.instance.apiurl }}
          INCLUDE_REPOS: ${{ matrix.instance.include_repos }}
          EXCLUDE_REPOS: ${{ matrix.instance.exclude_repos }}
          INCLUDE_PROJECTS: ${{ matrix.instance.include_projects }}
          EXCLUDE_PROJECTS: ${{ matrix.instance.exclude_projects }}
        run: |
          set -euo pipefail
          args=()
          if [ -n "${INCLUDE_REPOS:-}" ]; then args+=(--include-repos "$INCLUDE_REPOS"); fi
          if [ -n "${EXCLUDE_REPOS:-}" ]; then args+=(--exclude-repos "$EXCLUDE_REPOS"); fi
          if [ -n "${INCLUDE_PROJECTS:-}" ]; then args+=(--include-projects "$INCLUDE_PROJECTS"); fi
          if [ -n "${EXCLUDE_PROJECTS:-}" ]; then args+=(--exclude-projects "$EXCLUDE_PROJECTS"); fi
          venv/bin/python -m percona_obs \
            -A "$OBS_APIURL" \
            -R "<ROOTPRJ>" \
            -e "REMOTE_OBS_ORG_INTERCONNECT:" \
            -e "PERCONA_OBS_PACKAGING_BRANCH:<BRANCH>" \
            -e "PERCONA_OBS_PACKAGING_REPO:<REPO_URL>" \
            "${args[@]}" \
            profile create <NAME>
```

- [ ] **Step 2: `sync-main.yml`**

`sync` job: add the matrix header; `name: percona-obs sync push (${{ matrix.instance.name }})`; `concurrency.group: sync-main-sync-${{ matrix.instance.name }}`; replace the obs-setup and profile steps with the snippets (`ROOTPRJ` = `${{ matrix.instance.rootprj }}`, `NAME` = `main`, `BRANCH` = `main`, `REPO_URL` = `${{ github.server_url }}/${{ github.repository }}.git`); the sync step is unchanged (`-P main`); the report artifact becomes `name: sync-report-${{ matrix.instance.name }}`.

`poll` job: add the matrix header; `name: Wait for OBS builds (${{ matrix.instance.name }})`; `concurrency.group: sync-main-poll-${{ matrix.instance.name }}`; obs-setup snippet; download `sync-report-${{ matrix.instance.name }}`; poll env:
```yaml
          OBS_APIURL: ${{ matrix.instance.apiurl }}
          OBS_ROOTPRJ: ${{ matrix.instance.rootprj }}
          OBS_REPO_FILTER: ${{ toJSON(matrix.instance) }}
```
Badge step: use `obs-build-badge-${{ matrix.instance.name }}.json` as the badges-branch file name (both `gh api` paths and the `FILE_SHA` lookup). The disabled "Update version lists" step: change `OBS_ROOTPRJ` to `${{ matrix.instance.rootprj }}` and leave `if: false`. Update the header comment: one sync/poll pair per instance in `OBS_INSTANCES`; secrets `OBS_PASSWORD_<NAME>`.

- [ ] **Step 3: `obs-pr-check.yml`**

`sync` job: matrix header; `name: Sync packages to OBS (${{ matrix.instance.name }})`; env block → `OBS_APIURL: ${{ matrix.instance.apiurl }}`, `OBS_ROOTPRJ: ${{ matrix.instance.rootprj }}`, `OBS_PR_ROOTPRJ: ${{ matrix.instance.pr_rootprj }}`, `OBS_INSTANCE: ${{ matrix.instance.name }}` (keep `OBS_WEB_URL: ${{ vars.OBS_WEB_URL }}` for now; the comment link host is a QA/UI follow-up); obs-setup snippet. Replace "Create percona-obs profiles" and "Resolve repo label filter" with:

```yaml
      # Repo labels narrow this instance's slice (never widen it): each label
      # is a repository name; <flavor>-images expands to <flavor>,UBI_<n> and
      # excludes the other flavor's base-image project; ssl* keeps tarballs
      # building whenever any repo label is present.  A leg whose narrowed
      # slice is empty (profile create exits 3) has nothing to build here.
      - name: Create percona-obs profiles (${{ matrix.instance.name }})
        id: profiles
        shell: bash
        env:
          LABELS_JSON: ${{ needs.resolve.outputs.labels_json }}
          INCLUDE_REPOS: ${{ matrix.instance.include_repos }}
          EXCLUDE_REPOS: ${{ matrix.instance.exclude_repos }}
          INCLUDE_PROJECTS: ${{ matrix.instance.include_projects }}
          EXCLUDE_PROJECTS: ${{ matrix.instance.exclude_projects }}
          CLONE_URL: ${{ needs.resolve.outputs.clone_url }}
          MAIN_REPO_URL: ${{ github.server_url }}/${{ github.repository }}.git
        run: |
          set -euo pipefail
          inst=()
          if [ -n "${INCLUDE_REPOS:-}" ]; then inst+=(--include-repos "$INCLUDE_REPOS"); fi
          if [ -n "${EXCLUDE_REPOS:-}" ]; then inst+=(--exclude-repos "$EXCLUDE_REPOS"); fi
          if [ -n "${INCLUDE_PROJECTS:-}" ]; then inst+=(--include-projects "$INCLUDE_PROJECTS"); fi
          if [ -n "${EXCLUDE_PROJECTS:-}" ]; then inst+=(--exclude-projects "$EXCLUDE_PROJECTS"); fi

          CONTROL='. != "obs-sync" and . != "qa-packages" and . != "qa-containers" and . != "no-dep-cascade"'
          mapfile -t REPO_LABELS < <(echo "$LABELS_JSON" | jq -r ".[] | select(${CONTROL})")
          narrow=(); flavors=(); labels=()
          for l in "${REPO_LABELS[@]}"; do
            case "$l" in
              *-images) f="${l%-images}"; flavors+=("$f"); narrow+=("$f" "UBI_${f#ubi}") ;;
              *)        narrow+=("$l") ;;
            esac
          done
          if [ ${#REPO_LABELS[@]} -gt 0 ]; then
            narrow+=("ssl*")
            labels+=(--narrow-repos "$(IFS=,; echo "${narrow[*]}")")
            if [ ${#flavors[@]} -gt 0 ]; then
              for other in ubi8 ubi9; do
                if ! printf '%s\n' "${flavors[@]}" | grep -qx "$other"; then
                  labels+=(--exclude-projects "common:containers:${other}")
                fi
              done
            fi
          fi
          if echo "$LABELS_JSON" | jq -e '[.[] | select(. == "no-dep-cascade")] | length > 0' > /dev/null; then
            echo "no_dep_cascade_arg=--no-dep-cascade" >> "$GITHUB_OUTPUT"
          fi

          venv/bin/python -m percona_obs -A "$OBS_APIURL" -R "$OBS_ROOTPRJ" \
            -e "REMOTE_OBS_ORG_INTERCONNECT:" -e "PERCONA_OBS_PACKAGING_BRANCH:main" \
            -e "PERCONA_OBS_PACKAGING_REPO:${MAIN_REPO_URL}" "${inst[@]}" profile create main

          PR_ROOTPRJ="${OBS_PR_ROOTPRJ}:pr-${PR_NUMBER}"
          set +e
          venv/bin/python -m percona_obs -A "$OBS_APIURL" -R "$PR_ROOTPRJ" \
            -e "REMOTE_OBS_ORG_INTERCONNECT:" -e "PERCONA_OBS_PACKAGING_BRANCH:refs/pull/${PR_NUMBER}/head" \
            -e "PERCONA_OBS_PACKAGING_REPO:${CLONE_URL}" "${inst[@]}" "${labels[@]}" profile create "pr-${PR_NUMBER}"
          rc=$?
          set -e
          if [ "$rc" = "3" ]; then
            echo "::notice::instance ${{ matrix.instance.name }}: no repository of this slice is selected by the PR labels; skipping"
            echo "skip=true" >> "$GITHUB_OUTPUT"
          elif [ "$rc" != "0" ]; then
            exit "$rc"
          fi
```
Add `if: steps.detect.outputs.is_release_pr != 'true' && steps.profiles.outputs.skip != 'true'` to "Plan sync (dry run)" and "Sync PR to OBS"; drop `${{ steps.repo-filter.outputs.only_repos_arg }}` from both and use `${{ steps.profiles.outputs.no_dep_cascade_arg }}`. The "Create main profile (release dry-run)" step uses the instance snippet for `main` too (replace its body with the same `inst` array logic, `-A "$OBS_APIURL" -R "$OBS_ROOTPRJ"`). Sync-side comment step: add `&& steps.profiles.outputs.skip != 'true'` and `OBS_INSTANCE: ${{ matrix.instance.name }}`, `OBS_ROOTPRJ: ${{ matrix.instance.rootprj }}`, `OBS_PR_ROOTPRJ: ${{ matrix.instance.pr_rootprj }}`. Artifact `sync-output` → `sync-output-${{ matrix.instance.name }}` with `if: steps.sync.outcome == 'success'` unchanged.

`build` job: matrix header; `name: Wait for OBS builds (${{ matrix.instance.name }})`; `if: needs.sync.outputs.is_release_pr != 'true' && needs.sync.result == 'success'` (a leg that skipped counts as success; a failed leg blocks all builds — accepted trade-off, note it in a comment); env from the matrix plus `OBS_INSTANCE`; obs-setup snippet; download `sync-output-${{ matrix.instance.name }}` with `continue-on-error: true` (a skipped leg uploaded none); poll env `OBS_APIURL: ${{ matrix.instance.apiurl }}`, `OBS_ROOTPRJ: ${{ matrix.instance.pr_rootprj }}:pr-${{ needs.resolve.outputs.pr_number }}`, `OBS_REPO_FILTER: ${{ toJSON(matrix.instance) }}`; comment step env gets `OBS_INSTANCE`, `OBS_ROOTPRJ: ${{ matrix.instance.rootprj }}`, `OBS_PR_ROOTPRJ: ${{ matrix.instance.pr_rootprj }}`. Leave `detect-qa-matrix` and `qa` untouched (they keep `vars.OBS_APIURL`/`vars.OBS_PR_ROOTPRJ`; add a comment `# QA still targets the legacy single-instance variables; per-instance routing is a follow-up.`). Update the header comment of the file accordingly.

- [ ] **Step 4: `obs-release.yml`** — split the single `release` job into three:

```yaml
jobs:
  lock:
    name: Take the release lock
    runs-on: ubuntu-latest
    concurrency:
      group: sync-main-sync
      cancel-in-progress: false
    permissions:
      actions: write
    steps:
      - <Validate tag input step, unchanged>
      - <Take the release lock step, unchanged>

  release:
    name: Release packages in OBS (${{ matrix.instance.name }})
    needs: lock
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    strategy:
      fail-fast: false
      matrix:
        instance: ${{ fromJSON(vars.OBS_INSTANCES) }}
    concurrency:
      group: sync-main-sync-${{ matrix.instance.name }}
      cancel-in-progress: false
    permissions:
      contents: read
      packages: read
    env:
      OBS_APIURL: ${{ matrix.instance.apiurl }}
      OBS_ROOTPRJ: ${{ matrix.instance.rootprj }}
    steps:
      - checkout (unchanged)
      - obs-setup snippet
      - profile snippet (NAME main, ROOTPRJ ${{ matrix.instance.rootprj }})
      - Derive release project (unchanged)
      - Release to OBS (unchanged)

  unlock:
    name: Release the lock and publish the GitHub release
    needs: [lock, release]
    if: always() && needs.lock.result == 'success'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      actions: write
    steps:
      - checkout at refs/tags/${{ inputs.tag }} (needed for CHANGELOG)
      - Derive release project (copy of the step; only tag/product/major/release_id are used)
      - Create GitHub release  with `if: needs.release.result == 'success'`
      - Release the lock (re-enable sync-main)  with `if: needs.release.result == 'success'`
      - Report lock state on failure or cancellation  with `if: needs.release.result != 'success'`
```
The unchanged step bodies are moved verbatim. Update the header comment (lock → per-instance release → unlock).

- [ ] **Step 5: `post_pr_comment.py`** — after `poll_outcome = …` add `instance = os.environ.get("OBS_INSTANCE", "")`, `marker = f"<!-- obs-pr-check:{instance} -->" if instance else "<!-- obs-pr-check -->"`, `suffix = f" ({instance})" if instance else ""`; replace the three literal `"<!-- obs-pr-check -->"` list entries with `marker`; append `suffix` to each `heading = "## OBS … Check — …"` string (there are several assignments; add `+ suffix` to each) ; in the `gh api … --jq` search replace `contains("<!-- obs-pr-check -->")` with `contains("{marker}")` via an f-string.

- [ ] **Step 6: `README.md`** — change the badge URL file name to `obs-build-badge-boo.json` (the b.o.o instance is the production build badge).

- [ ] **Step 7: Verify and commit**

```bash
venv/bin/python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml && echo YAML-OK
grep -c "matrix.instance" .github/workflows/sync-main.yml .github/workflows/obs-pr-check.yml .github/workflows/obs-release.yml
grep -n "vars.OBS_APIURL\|vars.OBS_ROOTPRJ\|vars.OBS_PR_ROOTPRJ\|secrets.OBS_PASSWORD\b" .github/workflows/sync-main.yml .github/workflows/obs-release.yml ; echo "exit $?"
venv/bin/python -c "import ast; ast.parse(open('.github/scripts/post_pr_comment.py').read())"
git add .github/workflows/sync-main.yml .github/workflows/obs-pr-check.yml .github/workflows/obs-release.yml .github/scripts/post_pr_comment.py README.md
git commit -s -m "ci: run sync, PR check and release once per OBS instance (OBS_INSTANCES matrix)"
```

---

### Task 11: Documentation, spec amendments, final gates

**Goal:** Docs describe slices and the CI variables; the spec records the planning deviations; the unfiltered gate and a partition gate pass; scratch worktree removed.

**Files:**
- Modify: `.github/copilot-instructions.md` (Connection profiles section ~218-246; `sync push` synopsis ~307-330; `project verify` section ~650-676; Project Configuration section ~98-126)
- Modify: `docs/PERCONA_OBS_TOOL.md` (Connection profiles ~56-88; new "Slices: several OBS instances" subsection after it)
- Modify: `root/README.md` (project.yaml section, one paragraph)
- Modify: `docs/superpowers/specs/2026-09-23-multi-instance-repo-slices-design.md`
- Create: `$S/slice_gate.py` (throwaway)

**Acceptance Criteria:**
- [ ] copilot-instructions: `--only-repos` no longer appears anywhere in the repo docs (`grep -rn "only-repos" docs .github root/README.md README.md` → nothing); profile file format shows the four keys; `sync push` docs state the slice rules (project/package membership, orphan deletion, zero-repo rule, explicit-target error); `project verify` lists the repository-path check and the slice summary
- [ ] PERCONA_OBS_TOOL.md documents: profile keys, `profile create` flags incl. `--narrow-repos` (exit 3), the boo/labs example, `OBS_INSTANCES` JSON shape and `OBS_PASSWORD_<NAME>` secrets, first-run deletion warning and `--dry-run` rollout
- [ ] spec: Section 2 sentence about `--branch-from` refusal replaced; Section 1 `name:` override sentence replaced; Section 5 label narrowing described as `--narrow-repos`; an "Amendments made while planning" list records the three deviations
- [ ] `gate.py check` → `GATE PASSED`; `slice_gate.py` → `PARTITION OK` (every repo of every project in exactly one of boo/labs; every package in slice on ≥ 1 instance; no package's surviving repo sets overlap), or its findings reported verbatim
- [ ] `$S/base` worktree removed

**Verify:** the two gates and `venv/bin/python -m pytest -q tests`

**Steps:**

- [ ] **Step 1: copilot-instructions.md**

In "Connection profiles", extend the file format example:
```yaml
apiurl: http://192.168.1.103:3000   # OBS API URL
rootprj: home:Admin:percona         # OBS root project
env:                                 # optional: variables for ${VAR} substitution
  - name: REMOTE_OBS_ORG_INTERCONNECT
    value: 'openSUSE.org:'           # values containing colons must be quoted
# optional slice (all four are shell-glob lists; absent = the instance carries everything)
exclude-repositories: ["UBI_*", "ubi*", "images"]   # b.o.o: no UBI RPM repos, no images
# include-repositories: ["UBI_*", "ubi*", "images"] # labs: only those
# include-projects / exclude-projects: globs on the OBS project name without the rootprj
```
and this paragraph after it:

> **Slices.** A profile may declare which repositories and projects its instance carries. The tree stays instance-agnostic; `percona_obs/project_config.py::RepositoryFilter` is applied to every resolved configuration by the loader (`cli.main()` installs the active profile's filter as the process default). A project is *in slice* iff its name passes the project globs and it keeps at least one repository (a project with zero repositories is never created); a package is in slice iff its project is and it is not `build: false` on every surviving repository. Out-of-slice projects and packages are treated exactly like things absent from the tree: `sync push` neither creates nor uploads them, and a full-tree push deletes them from that instance as orphans. `profile create --include-repos/--exclude-repos/--include-projects/--exclude-projects GLOB[,GLOB]` write the keys; `--narrow-repos REPO[,REPO]` intersects the slice with the given names (used by the PR workflow for repo labels; exits 3 when nothing is left). See `docs/PERCONA_OBS_TOOL.md`.

In the `sync push` synopsis: remove nothing else, but add an option bullet:
- `The active profile's slice` — `sync push -P labs` renders only the repositories the profile keeps; projects/packages out of slice are skipped and reported (`slice: N project(s), M package(s) out of slice`; `--verbose` lists them) and are orphan-deleted on a full-tree push. `sync push <project> <package>` for an out-of-slice target is an error.

In `project verify`: add the check "kept repositories must path into subprojects that are in slice and define the referenced repository" and the `slice:` summary line with `-P`.

In "Project Configuration": after the `project-config` bullet add "- A project whose resolved `repositories` list is empty is never created on OBS."

- [ ] **Step 2: PERCONA_OBS_TOOL.md** — after "Connection profiles" add:

```markdown
### Slices: several OBS instances

build.opensuse.org cannot build UBI container images, so the UBI RPM repositories and the
container-image projects live on a second instance. One tree, two profiles:

```yaml
# .profile/boo.yaml — production RPM/DEB on build.opensuse.org
apiurl: https://api.opensuse.org
rootprj: isv:percona
exclude-repositories: ["UBI_*", "ubi*", "images"]

# .profile/labs.yaml — UBI RPMs and images on obs.pg.labs.percona.com
apiurl: https://obs.pg.labs.percona.com
rootprj: percona
include-repositories: ["UBI_*", "ubi*", "images"]
```

Rules (globs are `fnmatch`, case-sensitive):
- a repository is kept iff it matches an `include-repositories` glob (or there is none) and no `exclude-repositories` glob; a kept repository also keeps the same-project sibling repositories its paths reference;
- a project is in slice iff its rootprj-less name passes `include-projects`/`exclude-projects` **and** it keeps at least one repository (zero repositories → never created);
- a package is in slice iff its project is and its `package.yaml` `build:` map does not disable every kept repository;
- out-of-slice projects and packages are not created/uploaded and are **deleted as orphans** on a full-tree `sync push`. The first `sync push -P boo` against production therefore removes every `:containers` project and every UBI-only package there: run it with `--dry-run` first and read the `-` lines.

Create the profiles with flags instead of editing YAML (flags are repeatable and comma-separated):

```sh
./percona-obs -A https://api.opensuse.org -R isv:percona \
  profile create boo --exclude-repos 'UBI_*,ubi*,images'
./percona-obs -A https://obs.pg.labs.percona.com -R percona \
  profile create labs --include-repos 'UBI_*,ubi*,images'
```

`--narrow-repos RockyLinux_9,ssl*` keeps only the named repositories the profile already accepts
and exits 3 when nothing is left; the PR workflow uses it for repo labels.

Inspect a slice offline: `./percona-obs -P labs -e REMOTE_OBS_ORG_INTERCONNECT:x project config --offline --resolved`
(out-of-slice projects print `# project <name>: out of slice`) and `./percona-obs -P labs project verify`
(prints `slice: N project(s), M package(s) out of slice`, `--verbose` lists them, and fails if a kept
repository paths into a repository the slice does not carry).

`sync release -P <profile>` releases the subprojects that instance holds; `project release` always
generates the full, instance-agnostic release tree.

CI: the repository variable `OBS_INSTANCES` is a JSON list, one object per instance —
`{"name": "boo", "apiurl": "…", "rootprj": "isv:percona", "pr_rootprj": "isv:percona:pr",
"exclude_repos": "UBI_*,ubi*,images"}` (also `include_repos`, `include_projects`,
`exclude_projects`, optional `user`). The password secret is `OBS_PASSWORD_<NAME>` (upper-case
name). `sync-main`, `obs-pr-check` and `obs-release` run their OBS jobs once per entry.
```
Remove any remaining mention of `--only-repos` in this file.

- [ ] **Step 3: root/README.md** — append to the `## project.yaml` section:

> The tree describes every OBS instance at once. Which repositories and projects a given instance carries is declared in the connection profile (`.profile/<name>.yaml`, see `docs/PERCONA_OBS_TOOL.md` "Slices"); a project that keeps no repository under the active profile is out of slice and is never created there.

- [ ] **Step 4: Spec amendments** — in `docs/superpowers/specs/2026-09-23-multi-instance-repo-slices-design.md`:
  - Section 1 Implementation: replace "honouring a `name:` override in the leaf file" with "(`name:` overrides are not consulted: none exist in the tree and an override is a full OBS name)".
  - Section 2 last bullet: replace "both profiles must also carry the same filter, which the tool checks and refuses otherwise" with "the two profiles' filters may differ (a PR profile is narrowed by labels); a repository missing from the branch source already forces a promote".
  - Section 5: replace "the label-derived rules appended: each repo label becomes an `--include-repos` entry" with "narrowed by `profile create --narrow-repos` (intersection with the instance slice; a leg left with no repository skips its sync)".
  - Add after "Decisions taken during design": `## Amendments made while planning (2026-09-23)` with the three bullets from this plan's "Deviations from the spec".

- [ ] **Step 5: Partition gate** — write `$S/slice_gate.py`:

```python
"""Throwaway: prove boo and labs partition the tree (spec Section 7, gate 2)."""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from percona_obs.common import REPO_ROOT, _is_release_dir, find_packages  # noqa: E402
from percona_obs.project_config import RepositoryFilter, package_in_slice, resolve_project_config  # noqa: E402

BOO = RepositoryFilter(exclude_repos=("UBI_*", "ubi*", "images"))
LABS = RepositoryFilter(include_repos=("UBI_*", "ubi*", "images"))


def projects():
    for p in sorted(x.parent for x in REPO_ROOT.rglob("project.yaml")):
        if "_shared" in p.parts or any(_is_release_dir(a) or a.name == "releases" for a in [p, *p.parents] if a.is_relative_to(REPO_ROOT)):
            continue
        yield p


bad = 0
for p in projects():
    rel = p.relative_to(REPO_ROOT).as_posix() or "."
    full = {r["name"] for r in resolve_project_config(p, None, RepositoryFilter.EMPTY)["repositories"]}
    b = {r["name"] for r in resolve_project_config(p, None, BOO)["repositories"]}
    l = {r["name"] for r in resolve_project_config(p, None, LABS)["repositories"]}
    if b | l != full or b & l:
        bad += 1
        print(f"REPOS NOT PARTITIONED {rel}: boo={sorted(b)} labs={sorted(l)} full={sorted(full)}")
    for obs, pkg in find_packages(p, rel, recursive=False):
        in_b = package_in_slice(pkg, None, BOO)
        in_l = package_in_slice(pkg, None, LABS)
        if not (in_b or in_l):
            bad += 1
            print(f"PACKAGE NOWHERE {rel}/{pkg.name}")
print("PARTITION OK" if not bad else f"PARTITION FAILED ({bad})")
sys.exit(1 if bad else 0)
```
Run `venv/bin/python $S/slice_gate.py`. Expected: `PARTITION OK`. If `PACKAGE NOWHERE` lines appear they are packages disabled on every repository of their project (report them; they are pre-existing tree facts, not something to fix here).

- [ ] **Step 6: Final gates and cleanup**

```bash
venv/bin/python $S/gate.py check $S/gate-baseline
venv/bin/python -m pytest -q tests
git -C /home/rdias/Work/percona-obs-packaging worktree remove $S/base
grep -rn "only-repos\|only_repos" docs .github root/README.md README.md percona_obs tests ; echo "exit $?"
```
Expected: `GATE PASSED`, suite passes, grep exit 1.

- [ ] **Step 7: Commit**

```bash
git add .github/copilot-instructions.md docs/PERCONA_OBS_TOOL.md root/README.md docs/superpowers/specs/2026-09-23-multi-instance-repo-slices-design.md
git commit -s -m "docs: profile slices, OBS_INSTANCES, spec amendments"
```

Report to the user: the commit list (`git log --oneline percona/project-yaml-dedup..HEAD`), the `slice:` summaries from Task 6, the `release_gate.py` output from Task 7, and the partition gate result. Do not push.
