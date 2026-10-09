# ppg:staging:common:tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the five PG-independent components (pgbouncer, pgbadger, haproxy, pgbackrest, patroni) once in a new `ppg:staging:tools` project, feed every major through `_aggregate`, move the pgbouncer/pgbackrest images to the cross-version containers project, and give that project a counter-tagged release flow.

**Architecture:** `root/ppg/staging/tools/` is a direct child of staging (inherits repos/prjconf via `subprojects.yaml`) pinned to `PG_MAJOR_VERSION: 18` with a path to `ppg:staging:18`. The per-major `_shared/<pkg>` directories become aggregate-only like `etcd`. `sync release` extends its freeze scope to aggregate sources (package-scoped) and, for container releases, to path-prefix sources (whole-project). `project release` learns a counter release-id for sources without a `percona-postgresql` package, and `obs-release.yml` accepts the tag shape `<product>/<name>-<N>`.

**Tech Stack:** Python 3 (`percona_obs/`), pytest (`tests/`), black, pyright, OBS `_aggregate`/`_result`/package `_meta` APIs via `osc`, GitHub Actions bash.

**Spec:** `docs/superpowers/specs/2026-10-08-ppg-staging-tools-design.md` (revised 2026-10-09)

> **Revision 2026-10-09.** Tasks 1–7 were executed against the first spec (`ppg:staging:tools`, `ppg:releases:containers`) and are complete on branch `staging-tools` (PR #123). The spec now places every cross-version piece under a tier-level `common/` parent with one release unit `ppg:releases:common`. Tasks 12–15 below rework PR A in place; Tasks 8–11 are rewritten for the new layout and supersede their earlier text. Global Constraints still bind, with `ppg:staging:tools` read as `ppg:staging:common:tools`.

## Global Constraints

- All work happens in the worktree `.claude/worktrees/staging-tools` (branch `staging-tools`, based on `percona/main`). Never work in the primary checkout. Never `git push` or open a PR without asking the user first.
- After every code change run `venv/bin/black percona_obs/ tests/` then `venv/bin/pyright`; both must pass. Run `venv/bin/python -m pytest tests -q` before every commit.
- `project verify --offline` needs a profile. Create it once per worktree (gitignored under `.profile/`):
  `venv/bin/python -m percona_obs -A https://api.opensuse.org -R isv:percona -e "REMOTE_OBS_ORG_INTERCONNECT:" -e "PERCONA_OBS_PACKAGING_BRANCH:main" -e "PERCONA_OBS_PACKAGING_REPO:https://github.com/percona/obs-packaging.git" profile create verify`
  and always invoke `venv/bin/python -m percona_obs -P verify project verify --offline`. Baseline on `percona/main` (2026-10-08): verify passes, 430 tests pass.
- Commits use `git commit -s`. No Claude attribution lines in commit messages or PR bodies.
- PR A (Tasks 1–7) must leave `root/ppg/staging/<V>/` and `root/ppg/staging/_shared/` untouched except for `percona-patroni/debian/control`. PR B (Tasks 8–9) switches consumers. Tasks 10–11 are post-merge, user-driven.
- Aggregate files use the exact shape of `root/ppg/staging/_shared/etcd/obs/_aggregate` with project `${OBS_ROOTPRJ}:ppg:staging:tools`.
- OBS overrides spec `Release:` with `<CI_CNT>.<B_CNT>` (root `project.yaml` prjconf), so no changelog or Release bump can influence the published release counter. The spec's "Changelogs" bullet in Section 3 is therefore dropped (Task 7 records the counter caveat in the spec).
- The container project's `PG_MAJOR_VERSION: 18` and `Prefer: percona-postgresql18-libs` stay.

**User decisions (already made):**
- PGDG candidate rule: pgbouncer, pgbadger, haproxy, pgbackrest, patroni move; pgpool-II, pg_gather, pg-telemetry, postgresql-common, ppg-server* stay per-major.
- Explicit pin `PG_MAJOR_VERSION: 18` in the tools project, bumped by hand when a new GA major enters staging.
- Tools joins the release freeze (aggregate sources package-scoped; path-prefix sources whole-project for container releases).
- New `ppg:staging:tools`, not `ppg:common:deps`.
- patroni Debian drops the server Depends, adds `postgresql` to Suggests.
- Images move to `ppg:staging:containers`; `ppg:releases:containers` is added in this effort.
- Release tag for the containers project is a plain counter: `ppg/containers-<N>`.
- Two content PRs: A (add tools) then B (switch consumers + images).

---

## File structure

| File | Responsibility |
|---|---|
| `percona_obs/release_scope.py` (new) | Pure derivation of the extra freeze scope from the tree: aggregate sources (package-scoped) and container path-prefix sources (whole-project). No OBS traffic. |
| `percona_obs/release_freeze.py` | Package-scoped variants of quiesce/green/freeze/restore. |
| `percona_obs/cmd_sync.py` | `cmd_sync_release` assembles and applies the extended scope; dry-run prints it. |
| `percona_obs/cmd_project.py` | `_derive_release_id` (counter mode) and container-source CHANGELOG routing in `cmd_project_release`. |
| `.github/workflows/obs-release.yml` | Second tag shape. |
| `root/ppg/staging/tools/` (new) | The tools OBS project: `project.yaml`, `macros.yaml`, five packages. |
| `root/ppg/staging/_shared/<pkg>/` | PR B: aggregate-only. |
| `root/ppg/staging/containers/` | PR B: receives the two images; path to tools. |
| `tests/test_release_scope.py` (new), `tests/test_release_freeze.py`, `tests/test_sync_release.py`, `tests/test_project_release.py` | Tests. |
| `root/README.md`, `docs/PERCONA_OBS_TOOL.md`, `docs/PACKAGING_HOWTO.md` | Docs. |

---

## PR A — add the tools project and the tool changes

### Task 1: Freeze-scope derivation module

**Goal:** A pure function that, given a release source project path, returns the extra OBS projects/packages `sync release` must freeze.

**Files:**
- Create: `percona_obs/release_scope.py`
- Test: `tests/test_release_scope.py`

**Acceptance Criteria:**
- [ ] `collect_release_scope(source_path, source_project_id, rootprj, env_vars)` returns a `ReleaseScope(whole_projects: list[str], packages: dict[str, set[str]])`.
- [ ] Every `obs/_aggregate` under the source project and its subprojects (symlinked package dirs followed) whose `<aggregate project>` matches `${OBS_ROOTPRJ}:<id>` contributes `(rootprj:<id>, <package>)` for each `<package>` child to `packages`. Aggregates with no `<package>` child and external aggregates are ignored.
- [ ] When any package dir of the source project itself contains `obs/Dockerfile`, every `subproject:` path entry of the resolved repositories that is not the source or one of its subprojects is added to `whole_projects` (deduplicated, in first-seen order, prefixed with `rootprj:`).
- [ ] Aggregate sources that are the source project or one of its subprojects are not added (already in the base scope).

**Verify:** `venv/bin/python -m pytest tests/test_release_scope.py -v` → all PASS

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_release_scope.py
"""Unit tests for percona_obs.release_scope (pure tree derivation)."""

from pathlib import Path

import yaml

import percona_obs.common as common
import percona_obs.release_scope as rs

_AGG = (
    "<aggregatelist>\n"
    '  <aggregate project="${{OBS_ROOTPRJ}}:{prj}">\n'
    "    <package>{pkg}</package>\n"
    "  </aggregate>\n"
    "</aggregatelist>\n"
)


def _mk_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "project.yaml").write_text(
        yaml.dump({"repositories": [{"name": "R9", "archs": ["x86_64"], "paths": []}]})
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(rs, "REPO_ROOT", root)
    return root


def _pkg(path: Path, files: dict[str, str]) -> None:
    (path / "obs").mkdir(parents=True)
    for name, text in files.items():
        (path / "obs" / name).write_text(text)


def test_aggregate_sources_are_package_scoped(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "percona-pgbouncer", {"_aggregate": _AGG.format(prj="ppg:staging:tools", pkg="percona-pgbouncer")})
    _pkg(src / "etcd", {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="etcd")})
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    # the aggregate targets must exist in the tree
    for prj, pkg in (("ppg/staging/tools", "percona-pgbouncer"), ("ppg/common/deps", "etcd")):
        _pkg(root / prj / pkg, {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.whole_projects == []
    assert scope.packages == {
        "isv:percona:ppg:staging:tools": {"percona-pgbouncer"},
        "isv:percona:ppg:common:deps": {"etcd"},
    }


def test_external_and_packageless_aggregates_ignored(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "ext", {"_aggregate": '<aggregatelist><aggregate project="openSUSE:Factory"><package>x</package></aggregate></aggregatelist>'})
    _pkg(src / "whole", {"_aggregate": '<aggregatelist><aggregate project="${OBS_ROOTPRJ}:ppg:common:deps"/></aggregatelist>'})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {}
    assert scope.whole_projects == []


def test_symlinked_shared_package_is_followed(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    shared = root / "ppg/staging/_shared/percona-pgbadger"
    _pkg(shared, {"_aggregate": _AGG.format(prj="ppg:staging:tools", pkg="percona-pgbadger")})
    _pkg(root / "ppg/staging/tools/percona-pgbadger", {"_service": "<services/>"})
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    (src / "percona-pgbadger").symlink_to("../_shared/percona-pgbadger")
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {"isv:percona:ppg:staging:tools": {"percona-pgbadger"}}


def test_subproject_aggregates_included_and_self_sources_skipped(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    (src / "extras").mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    (src / "extras" / "project.yaml").write_text("title: E\n")
    _pkg(src / "extras" / "ydiff", {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="ydiff")})
    _pkg(src / "self", {"_aggregate": _AGG.format(prj="ppg:staging:17:extras", pkg="ydiff")})
    _pkg(root / "ppg/common/deps/ydiff", {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {"isv:percona:ppg:common:deps": {"ydiff"}}


def test_container_source_adds_path_prefix_projects(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/containers"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories-inherit": False,
                "project-config-inherit": False,
                "repositories": [
                    {
                        "name": "ubi9",
                        "archs": ["x86_64"],
                        "paths": [
                            {"project": "RedHat:UBI:Registry", "repository": "images"},
                            {"subproject": "ppg:staging:18", "repository": "UBI_9"},
                            {"subproject": "ppg:staging:tools", "repository": "UBI_9"},
                            {"subproject": "ppg:common:deps", "repository": "UBI_9"},
                            {"subproject": "ppg:staging:containers", "repository": "ubi9"},
                        ],
                    },
                    {
                        "name": "ubi8",
                        "archs": ["x86_64"],
                        "paths": [
                            {"subproject": "ppg:staging:18", "repository": "UBI_8"},
                            {"subproject": "ppg:common:deps", "repository": "UBI_8"},
                        ],
                    },
                ],
            }
        )
    )
    _pkg(src / "percona-pgbouncer", {"Dockerfile": "FROM x\n"})
    scope = rs.collect_release_scope(src, "ppg:staging:containers", "isv:percona", {})
    assert scope.whole_projects == [
        "isv:percona:ppg:staging:18",
        "isv:percona:ppg:staging:tools",
        "isv:percona:ppg:common:deps",
    ]
    assert scope.packages == {}


def test_non_container_source_ignores_path_prefix(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text(
        yaml.dump({"path-prefix": [{"subproject": "ppg:common:deps", "repository": "%_repository"}]})
    )
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.whole_projects == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_release_scope.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'percona_obs.release_scope'`

- [ ] **Step 3: Write the module**

```python
# percona_obs/release_scope.py
"""Extra freeze scope for ``sync release`` (spec Section 2.1).

``sync release`` freezes the release source project and its subprojects.
Two further kinds of source hold binaries the release copies:

* **aggregate sources** — every ``obs/_aggregate`` in the source tree pulls
  binaries from another local project (``ppg:staging:tools``,
  ``ppg:common:deps``).  Only the aggregated packages are frozen there.
* **path-prefix sources** — a container project's images may consume any
  package of the ``subproject:`` entries in its repository paths, so those
  projects are frozen whole.

Everything here is a pure function of the git tree; no OBS traffic.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .common import REPO_ROOT, find_packages, find_projects
from .project_config import RepositoryFilter, resolve_project_config

_LOCAL_AGGREGATE_RE = re.compile(r"^\$\{OBS_ROOTPRJ\}:(.+)$")


@dataclass
class ReleaseScope:
    whole_projects: list[str] = field(default_factory=list)
    packages: dict[str, set[str]] = field(default_factory=dict)


def _local_aggregates(aggregate_file: Path) -> "list[tuple[str, str]]":
    """Return [(local_project_id, package)] for every local aggregate entry."""
    try:
        root_el = ET.fromstring(aggregate_file.read_text("utf-8"))
    except (ET.ParseError, OSError):
        return []
    out: list[tuple[str, str]] = []
    for agg in root_el.findall("aggregate"):
        m = _LOCAL_AGGREGATE_RE.match((agg.get("project") or "").strip())
        if not m:
            continue
        for pkg_el in agg.findall("package"):
            pkg = (pkg_el.text or "").strip()
            if pkg:
                out.append((m.group(1), pkg))
    return out


def _has_container_images(project_path: Path) -> bool:
    return any(
        (p / "obs" / "Dockerfile").is_file()
        for p in project_path.iterdir()
        if p.is_dir()
    )


def collect_release_scope(
    source_path: Path,
    source_project_id: str,
    rootprj: str,
    env_vars: "dict[str, str] | None",
) -> ReleaseScope:
    scope = ReleaseScope()
    own_ids = {source_project_id}
    for sub_id, _ in find_projects(source_path, source_project_id):
        own_ids.add(sub_id)

    for _, pkg_path in find_packages(source_path, source_project_id):
        agg_file = pkg_path / "obs" / "_aggregate"
        if not agg_file.is_file():
            continue
        for local_id, pkg in _local_aggregates(agg_file):
            if local_id in own_ids:
                continue
            if not REPO_ROOT.joinpath(*local_id.split(":")).is_dir():
                continue
            scope.packages.setdefault(f"{rootprj}:{local_id}", set()).add(pkg)

    if _has_container_images(source_path):
        cfg = resolve_project_config(
            source_path, env_vars or {}, repo_filter=RepositoryFilter.EMPTY
        )
        for repo in cfg.get("repositories", []):
            for entry in repo.get("paths", []):
                sub = entry.get("subproject")
                if not sub or sub in own_ids:
                    continue
                full = f"{rootprj}:{sub}"
                if full not in scope.whole_projects:
                    scope.whole_projects.append(full)
    return scope
```

Check `find_packages` in `percona_obs/common.py:145` yields `(obs_project, package_path)` recursively and follows symlinked package dirs (it does for `_shared` today; if the test `test_symlinked_shared_package_is_followed` fails because `find_packages` skips symlinks, iterate `pkg_path.resolve()` — but do not change `find_packages`). If `find_projects` needs `project.yaml` in subdirs, the fixture already provides it.

- [ ] **Step 4: Run tests, format, type-check**

Run: `venv/bin/python -m pytest tests/test_release_scope.py -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: 6 passed; black reformats or leaves unchanged; pyright `0 errors`

- [ ] **Step 5: Commit**

```bash
git add percona_obs/release_scope.py tests/test_release_scope.py
git commit -s -m "release: derive extra freeze scope from aggregates and container paths"
```

---

### Task 2: Package-scoped freeze helpers

**Goal:** `release_freeze.py` can quiesce, green-check and build-freeze a *subset* of packages in a project.

**Files:**
- Modify: `percona_obs/release_freeze.py:63-166`
- Test: `tests/test_release_freeze.py`

**Acceptance Criteria:**
- [ ] `_pending_items`, `wait_for_quiesce`, `assert_all_green` accept an optional `packages: dict[str, set[str]] | None`; for a project present in that map only the listed packages' codes are considered, and repository-level pending states are ignored for such projects (a package-scoped project is never fully owned by this release).
- [ ] `freeze_packages(apiurl, packages) -> dict[tuple[str, str], str]` replaces each package's `<build>` with `<build><disable/></build>` via `osc.core.edit_meta(metatype="pkg", ...)` and returns the prior meta XML per `(project, package)`; on partial failure it restores what it froze and re-raises.
- [ ] `restore_packages(apiurl, snapshots)` pushes the snapshots back, never raises.
- [ ] Existing tests still pass unchanged.

**Verify:** `venv/bin/python -m pytest tests/test_release_freeze.py -v` → all PASS

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_release_freeze.py`)

```python
def test_assert_all_green_package_scoped(monkeypatch):
    _patch_results(
        monkeypatch,
        _result_xml(
            [("etcd", "R9", "x86_64", "succeeded"), ("krb5", "R9", "x86_64", "failed")]
        ),
    )
    problems = rf.assert_all_green(
        "http://obs", ["deps"], packages={"deps": {"etcd"}}
    )
    assert problems == []
    problems = rf.assert_all_green("http://obs", ["deps"])
    assert problems == ["deps/krb5 R9/x86_64: failed"]


def test_pending_items_package_scoped_ignores_repo_state(monkeypatch):
    _patch_results(
        monkeypatch,
        _result_xml(
            [("etcd", "R9", "x86_64", "succeeded"), ("krb5", "R9", "x86_64", "building")],
            repo_state="building",
        ),
    )
    assert rf._pending_items("http://obs", ["deps"], packages={"deps": {"etcd"}}) == []
    assert rf._pending_items("http://obs", ["deps"], packages={"deps": {"krb5"}}) == [
        "deps/krb5 R9/x86_64: building"
    ]


def test_freeze_packages_round_trip(monkeypatch):
    metas = {("deps", "etcd"): "<package name=\"etcd\" project=\"deps\"><title/></package>"}
    edits = []
    monkeypatch.setattr(
        rf.osc.core, "show_package_meta", lambda api, prj, pkg: [metas[(prj, pkg)].encode()]
    )
    monkeypatch.setattr(rf, "_decode_obs_response", lambda data: b"".join(data).decode())

    def fake_edit(metatype, path_args, data, force, apiurl):
        edits.append((metatype, path_args, data[0]))

    monkeypatch.setattr(rf.osc.core, "edit_meta", fake_edit)
    snaps = rf.freeze_packages("http://obs", {"deps": {"etcd"}})
    assert snaps == {("deps", "etcd"): metas[("deps", "etcd")]}
    assert edits[0][0] == "pkg" and edits[0][1] == ("deps", "etcd")
    assert "<disable" in edits[0][2]
    rf.restore_packages("http://obs", snaps)
    assert edits[1][2] == metas[("deps", "etcd")]


def test_freeze_packages_restores_on_partial_failure(monkeypatch):
    metas = {("deps", "a"): "<package name=\"a\" project=\"deps\"/>"}
    edits = []
    monkeypatch.setattr(
        rf.osc.core,
        "show_package_meta",
        lambda api, prj, pkg: [metas[(prj, pkg)].encode()] if (prj, pkg) in metas else (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(rf, "_decode_obs_response", lambda data: b"".join(data).decode())
    monkeypatch.setattr(
        rf.osc.core, "edit_meta", lambda metatype, path_args, data, force, apiurl: edits.append((path_args, data[0]))
    )
    with pytest.raises(RuntimeError):
        rf.freeze_packages("http://obs", {"deps": {"a", "b"}})
    # a was frozen then restored
    assert edits[0][0] == ("deps", "a") and "<disable" in edits[0][1]
    assert edits[-1] == (("deps", "a"), metas[("deps", "a")])
```

Note: `freeze_packages` must iterate packages in sorted order so that `a` is processed before `b`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_release_freeze.py -q`
Expected: 4 new FAIL (`TypeError: unexpected keyword 'packages'`, `AttributeError: freeze_packages`)

- [ ] **Step 3: Implement**

In `percona_obs/release_freeze.py` change the three signatures and add two functions:

```python
def _pending_items(
    apiurl: str,
    obs_projects: "list[str]",
    packages: "dict[str, set[str]] | None" = None,
) -> "list[str]":
    """Return human-readable descriptions of everything still pending.

    Projects listed in *packages* are package-scoped: only those packages
    count and repository-level states are ignored.
    """
    pending: list[str] = []
    for prj in obs_projects:
        only = (packages or {}).get(prj)
        pkg_codes, repo_states = fetch_project_results(apiurl, prj)
        if only is None:
            for (repo, arch), state in sorted(repo_states.items()):
                if state in PENDING_REPO_STATES or state == "dirty":
                    pending.append(f"{prj} {repo}/{arch}: repository {state}")
        for (pkg, repo, arch), code in sorted(pkg_codes.items()):
            if only is not None and pkg not in only:
                continue
            if code in PENDING_PKG_CODES:
                pending.append(f"{prj}/{pkg} {repo}/{arch}: {code}")
    return pending


def wait_for_quiesce(
    apiurl: str,
    obs_projects: "list[str]",
    timeout_s: int = 3600,
    poll_interval_s: int = 30,
    packages: "dict[str, set[str]] | None" = None,
) -> None:
    # body unchanged except: pending = _pending_items(apiurl, obs_projects, packages)


def assert_all_green(
    apiurl: str,
    obs_projects: "list[str]",
    packages: "dict[str, set[str]] | None" = None,
) -> "list[str]":
    problems: list[str] = []
    for prj in obs_projects:
        only = (packages or {}).get(prj)
        pkg_codes, _ = fetch_project_results(apiurl, prj)
        for (pkg, repo, arch), code in sorted(pkg_codes.items()):
            if only is not None and pkg not in only:
                continue
            if code not in GREEN_PKG_CODES:
                problems.append(f"{prj}/{pkg} {repo}/{arch}: {code}")
    return problems


def _disabled_meta(raw: str) -> str:
    root = ET.fromstring(raw)
    for build_elem in root.findall("build"):
        root.remove(build_elem)
    ET.SubElement(ET.SubElement(root, "build"), "disable")
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def freeze_packages(
    apiurl: str, packages: "dict[str, set[str]]"
) -> "dict[tuple[str, str], str]":
    """Disable builds on the listed packages; return {(project, pkg): prior_meta}.

    Mirrors freeze_builds at package granularity (aggregate sources such as
    ppg:staging:tools and ppg:common:deps are shared with other releases, so
    the whole project must not be frozen).  Partial failure restores what
    was already frozen before re-raising.
    """
    snapshots: dict[tuple[str, str], str] = {}
    try:
        for prj in sorted(packages):
            for pkg in sorted(packages[prj]):
                raw = _decode_obs_response(
                    osc.core.show_package_meta(apiurl, prj, pkg)
                )
                osc.core.edit_meta(
                    metatype="pkg",
                    path_args=(prj, pkg),
                    data=[_disabled_meta(raw)],
                    force=True,
                    apiurl=apiurl,
                )
                snapshots[(prj, pkg)] = raw
                _print_update(f"{prj}/{pkg}  (builds frozen)")
    except Exception:
        if snapshots:
            restore_packages(apiurl, snapshots)
        raise
    return snapshots


def restore_packages(
    apiurl: str, snapshots: "dict[tuple[str, str], str]"
) -> None:
    """Push package meta snapshots back verbatim.  Never raises."""
    for (prj, pkg), meta in snapshots.items():
        try:
            osc.core.edit_meta(
                metatype="pkg", path_args=(prj, pkg), data=[meta], force=True, apiurl=apiurl
            )
            _print_update(f"{prj}/{pkg}  (builds restored)")
        except Exception as exc:
            print(f"warning: failed to restore build flags on {prj}/{pkg}: {exc}", flush=True)
```

Also refactor `freeze_builds` to call `_disabled_meta(raw)` instead of its inline XML edit (same output). Module docstring: add one sentence about package-scoped sources.

- [ ] **Step 4: Run tests, format, type-check**

Run: `venv/bin/python -m pytest tests/test_release_freeze.py -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: all passed; `0 errors`

- [ ] **Step 5: Commit**

```bash
git add percona_obs/release_freeze.py tests/test_release_freeze.py
git commit -s -m "release: package-scoped quiesce, green check and build freeze"
```

---

### Task 3: Wire the extended scope into `sync release`

**Goal:** `cmd_sync_release` freezes aggregate sources (package-scoped) and container path-prefix sources (whole) alongside the source project; `--dry-run` prints and green-checks the full scope.

**Files:**
- Modify: `percona_obs/cmd_sync.py:2631-2700` (freeze scope assembly, dry-run, `_freeze_and_run`), imports at `:107-113`
- Test: `tests/test_sync_release.py`

**Acceptance Criteria:**
- [ ] New helper `_build_freeze_scope(source_obs_project, source_sub_obs_projects, source_path, source_project_id, rootprj, env_vars) -> tuple[list[str], dict[str, set[str]]]` returns `(whole, packages)` where `whole` = base scope + `ReleaseScope.whole_projects` (deduplicated) and `packages` = `ReleaseScope.packages` minus any project already in `whole`.
- [ ] Dry-run prints one line per extra source: `  + <project>  (whole)` or `  + <project>  (<pkg>, <pkg>)` and includes them in `assert_all_green`.
- [ ] `_freeze_and_run` quiesces and green-checks `whole + list(packages)` with the `packages` map, then calls `freeze_builds(whole)` and `freeze_packages(packages)`, restoring both in `finally`.

**Verify:** `venv/bin/python -m pytest tests/test_sync_release.py -v` → all PASS

**Steps:**

- [ ] **Step 1: Write the failing test** (append to `tests/test_sync_release.py`)

```python
def test_build_freeze_scope_merges_extra_sources(tmp_path, monkeypatch):
    import percona_obs.release_scope as rs

    src, rel = _mk_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "collect_release_scope",
        lambda *a, **k: rs.ReleaseScope(
            whole_projects=["home:Admin:ppg:staging:18"],
            packages={
                "home:Admin:ppg:staging:tools": {"percona-pgbouncer"},
                "home:Admin:ppg:staging:18": {"ignored-because-whole"},
            },
        ),
    )
    whole, packages = cmd_sync._build_freeze_scope(
        "home:Admin:ppg:staging:17",
        ["home:Admin:ppg:staging:17:containers"],
        src,
        "ppg:staging:17",
        "home:Admin",
        {},
    )
    assert whole == [
        "home:Admin:ppg:staging:17",
        "home:Admin:ppg:staging:17:containers",
        "home:Admin:ppg:staging:18",
    ]
    assert packages == {"home:Admin:ppg:staging:tools": {"percona-pgbouncer"}}
```

- [ ] **Step 1b: Pin the branch-mode aggregate rewrite for a sibling tools source** (append to `tests/test_branch_link_rewrite.py`; spec Section 2.4 — this is expected to pass already, it documents the guarantee PR B relies on)

```python
TOOLS = f"{ROOTPRJ}:ppg:staging:tools"
TOOLS_PROD = f"{BRANCH}:ppg:staging:tools"


def test_aggregate_from_tools_kept_when_tool_promoted():
    promoted = {(TOOLS, "percona-pgbouncer")}
    out = _rewrite_aggregate_for_branch(
        _agg(TOOLS, "percona-pgbouncer"), ROOTPRJ, BRANCH, promoted
    )
    assert _agg_projs(out) == [TOOLS]


def test_aggregate_from_tools_redirected_when_tool_not_promoted():
    promoted = {(TOOLS, "percona-pgbadger")}
    out = _rewrite_aggregate_for_branch(
        _agg(TOOLS, "percona-pgbouncer"), ROOTPRJ, BRANCH, promoted
    )
    assert _agg_projs(out) == [TOOLS_PROD]
```

- [ ] **Step 2: Run the tests to verify the new scope test fails (the two rewrite tests pass)**

Run: `venv/bin/python -m pytest tests/test_sync_release.py::test_build_freeze_scope_merges_extra_sources tests/test_branch_link_rewrite.py -q`
Expected: FAIL `AttributeError: module 'percona_obs.cmd_sync' has no attribute 'collect_release_scope'` (or `_build_freeze_scope`)

- [ ] **Step 3: Implement**

Imports in `percona_obs/cmd_sync.py`: add `from .release_scope import collect_release_scope` and extend the `release_freeze` import with `freeze_packages, restore_packages`.

Add before `cmd_sync_release`:

```python
def _build_freeze_scope(
    source_obs_project: str,
    source_sub_obs_projects: "list[str]",
    source_path: Path,
    source_project_id: str,
    rootprj: str,
    env_vars: "dict[str, str]",
) -> "tuple[list[str], dict[str, set[str]]]":
    """Return (whole_projects, package_scoped) for the release freeze.

    whole_projects: the source, its subprojects and (container releases)
    the path-prefix sources; package_scoped: aggregate sources restricted
    to the aggregated packages (spec Section 2.1).
    """
    extra = collect_release_scope(source_path, source_project_id, rootprj, env_vars)
    whole = [source_obs_project] + source_sub_obs_projects
    for prj in extra.whole_projects:
        if prj not in whole:
            whole.append(prj)
    packages = {prj: pkgs for prj, pkgs in extra.packages.items() if prj not in whole}
    return whole, packages
```

In `cmd_sync_release`, replace `freeze_scope = [source_obs_project] + source_sub_obs_projects` with:

```python
    freeze_scope, freeze_packages_map = _build_freeze_scope(
        source_obs_project,
        source_sub_obs_projects,
        resolve_project_path(source_project_id),
        source_project_id,
        args.rootprj,
        shared_env_vars,
    )
    quiesce_scope = freeze_scope + sorted(freeze_packages_map)
    for prj in freeze_scope[1 + len(source_sub_obs_projects) :]:
        _print_same(f"+ {prj}  (whole)")
    for prj in sorted(freeze_packages_map):
        _print_same(f"+ {prj}  ({', '.join(sorted(freeze_packages_map[prj]))})")
```

Dry-run: `assert_all_green(apiurl, quiesce_scope, packages=freeze_packages_map)`.

`_freeze_and_run`:

```python
    def _freeze_and_run(release_all) -> None:
        snapshots: dict[str, str] = {}
        pkg_snapshots: dict[tuple[str, str], str] = {}
        if not args.no_freeze:
            _print_pending(f"draining scheduler for {len(quiesce_scope)} project(s)")
            wait_for_quiesce(
                apiurl, quiesce_scope, timeout_s=args.freeze_timeout, packages=freeze_packages_map
            )
            problems = assert_all_green(apiurl, quiesce_scope, packages=freeze_packages_map)
            if problems:
                ...  # unchanged
            snapshots = freeze_builds(apiurl, freeze_scope)
            try:
                pkg_snapshots = freeze_packages(apiurl, freeze_packages_map)
            except Exception:
                restore_builds(apiurl, snapshots)
                raise
        try:
            release_all()
        finally:
            if pkg_snapshots:
                restore_packages(apiurl, pkg_snapshots)
            if snapshots:
                restore_builds(apiurl, snapshots)
```

- [ ] **Step 4: Run the suite, format, type-check**

Run: `venv/bin/python -m pytest tests -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: all passed; `0 errors`

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_sync.py tests/test_sync_release.py tests/test_branch_link_rewrite.py
git commit -s -m "sync release: freeze aggregate and container path sources"
```

---

### Task 4: `project release` for a cross-version container project

**Goal:** `project release ppg:staging:containers` derives a counter release-id (`containers-<N>`), and builds the CHANGELOG from the project's own images instead of looking for `percona-postgresql`.

**Files:**
- Modify: `percona_obs/cmd_project.py:2139-2170` (release-id derivation), `:2187-2243` (changelog sources)
- Modify: `percona_obs/cli.py:784-792` (help text)
- Test: `tests/test_project_release.py`

**Acceptance Criteria:**
- [ ] New pure function `_derive_release_id(pkg_archs, existing_releases, release_name, versrel_lookup) -> str`: when `percona-postgresql` or `percona-postgresql<major>` is present it returns `MAJOR.MINOR-N` exactly as today; otherwise it returns `f"{release_name}-{len(existing_releases) + 1}"`.
- [ ] Tag for the counter mode is `ppg/containers-1`, `ppg/containers-2`, …
- [ ] When the source project itself contains images (`_has_container_images(source_path)`), `source_versions` is `{}` and the project's images are merged into `source_container_pkgs` via `_fetch_subproject_container_pkgs(apiurl, source_obs_project, args.rootprj, source_obs_project)`; on update releases the release project itself is merged into `release_container_pkgs` the same way. `has_container_images=True` is passed to the CVE scan.
- [ ] `--release-id` help text mentions the counter mode.

**Verify:** `venv/bin/python -m pytest tests/test_project_release.py -v` → all PASS

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project_release.py`)

```python
def test_derive_release_id_pg_mode():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql": ("RockyLinux_9", "x86_64")},
        existing_releases=["ppg/17.10-1", "ppg/17.11-1"],
        release_name="17",
        versrel_lookup=lambda repo, arch, pkg: "17.11.1-2.1",
    )
    assert rid == "17.11-2"


def test_derive_release_id_major_suffixed_package():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql18": ("RockyLinux_9", "x86_64")},
        existing_releases=[],
        release_name="18",
        versrel_lookup=lambda repo, arch, pkg: "18.6-1.1",
    )
    assert rid == "18.6-1"


def test_derive_release_id_counter_mode_without_server_package():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-pgbouncer": ("ubi9", "x86_64")},
        existing_releases=["ppg/containers-1", "ppg/containers-2"],
        release_name="containers",
        versrel_lookup=lambda repo, arch, pkg: (_ for _ in ()).throw(AssertionError("not called")),
    )
    assert rid == "containers-3"


def test_derive_release_id_counter_mode_first_release():
    rid = cmd_project._derive_release_id(
        pkg_archs={}, existing_releases=[], release_name="containers",
        versrel_lookup=lambda repo, arch, pkg: None,
    )
    assert rid == "containers-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_project_release.py -q`
Expected: 4 FAIL `AttributeError: _derive_release_id`

- [ ] **Step 3: Implement the derivation**

Add before `cmd_project_release`:

```python
def _derive_release_id(
    pkg_archs: "dict[str, tuple[str, str]]",
    existing_releases: "list[str]",
    release_name: str,
    versrel_lookup: "Callable[[str, str, str], str | None]",
) -> str:
    """Return the next release id for a source project.

    PG mode (a ``percona-postgresql[<major>]`` package is built): ``MAJOR.MINOR-N``
    where N counts existing releases of that minor.  Counter mode (no server
    package — cross-version projects such as ``ppg:staging:containers``):
    ``<release_name>-N`` where N is one plus the number of existing releases.
    """
    pg_pkg = "percona-postgresql"
    repo_arch = pkg_archs.get(pg_pkg)
    if not repo_arch:
        pg_pkg = f"percona-postgresql{release_name}"
        repo_arch = pkg_archs.get(pg_pkg)
    if not repo_arch:
        return f"{release_name}-{len(existing_releases) + 1}"
    repo, arch = repo_arch
    versrel = versrel_lookup(repo, arch, pg_pkg)
    if not versrel:
        raise SystemExit(
            f"error: could not get built version of {pg_pkg}; "
            "use --release-id to specify manually"
        )
    ver_parts = versrel.split("-")[0].split(".")
    major_minor = ".".join(ver_parts[:2])
    matching_count = sum(1 for t in existing_releases if f"/{major_minor}-" in t)
    return f"{major_minor}-{matching_count + 1}"
```

Add `from typing import Callable` to the imports if absent. Replace the body of the `if not release_id:` block in `cmd_project_release` with:

```python
    if not release_id:
        pkg_archs = _fetch_all_pkg_archs(apiurl, source_obs_project)
        release_id = _derive_release_id(
            pkg_archs,
            existing_releases,
            release_name,
            lambda repo, arch, pkg: _fetch_pkg_versrel(
                apiurl, source_obs_project, repo, arch, pkg
            ),
        )
```

(The former "package percona-postgresql not found" SystemExit disappears: that case is now counter mode.)

- [ ] **Step 4: Route a container source project through the image changelog path**

Move the nested `_has_container_images` out to module level (next to `_derive_release_id`, same body). In `cmd_project_release` after `source_versions = _fetch_project_pkg_versions(...)`:

```python
    source_is_container_project = _has_container_images(source_path)
    if source_is_container_project:
        source_versions = {}
```

After the `for subproject_name in container_subs:` loop that fills `source_container_pkgs`, add:

```python
    if source_is_container_project:
        _merge_container_pkgs(
            source_container_pkgs,
            _fetch_subproject_container_pkgs(
                apiurl, source_obs_project, args.rootprj, source_obs_project
            ),
            source_obs_project,
        )
```

Inside the `if not is_first_release and existing_releases:` block, before the `for rel_sub in sorted(...)` loop:

```python
        if source_is_container_project and _obs_project_exists(apiurl, release_obs_project):
            _merge_container_pkgs(
                release_container_pkgs,
                _fetch_subproject_container_pkgs(
                    apiurl, release_obs_project, args.rootprj, release_obs_project
                ),
                release_obs_project,
            )
```

In the CVE scan call: `has_container_images=bool(container_subs) or source_is_container_project`.

- [ ] **Step 5: CLI help**

In `percona_obs/cli.py` `--release-id` help, replace the last sentence with: `"Defaults to auto-derived from OBS: MAJOR.MINOR-N where N counts existing releases of the same minor version; for projects without a percona-postgresql package (e.g. ppg:staging:containers) a plain counter <name>-N."`

- [ ] **Step 6: Run the suite, format, type-check**

Run: `venv/bin/python -m pytest tests -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: all passed; `0 errors`

- [ ] **Step 7: Commit**

```bash
git add percona_obs/cmd_project.py percona_obs/cli.py tests/test_project_release.py
git commit -s -m "project release: counter release ids and image changelog for cross-version projects"
```

---

### Task 5: obs-release.yml accepts `<product>/<name>-<N>` tags

**Goal:** A merged release PR for `root/ppg/releases/containers/release.yaml` with tag `ppg/containers-1` dispatches and releases `ppg:releases:containers`.

**Files:**
- Modify: `.github/workflows/obs-release.yml:85-91`, `:192-205`, `:236-249`

**Acceptance Criteria:**
- [ ] Validation accepts both `^[a-z0-9-]+/[0-9]+(\.[0-9]+)+-[0-9]+$` and `^[a-z0-9-]+/[a-z][a-z0-9]*-[0-9]+$`; the error message names both shapes.
- [ ] Both "Derive release project" steps set `major_version` to the name (`containers`) for the counter shape, so `RELEASE_PROJECT=ppg:releases:containers` and the CHANGELOG path resolves to `root/ppg/releases/containers/CHANGELOG.md`; the PG shape is unchanged.
- [ ] The derivation is checked locally with a bash snippet for both shapes.

**Verify:** the bash snippet in Step 2 prints `ppg:releases:17 17.11-1` and `ppg:releases:containers containers-3`.

**Steps:**

- [ ] **Step 1: Edit the workflow**

Validation step:

```bash
          TAG="${{ inputs.tag }}"
          if ! echo "$TAG" | grep -Eq '^[a-z0-9-]+/([0-9]+(\.[0-9]+)+|[a-z][a-z0-9]*)-[0-9]+$'; then
            echo "::error::tag '$TAG' does not match <product>/<major.minor-N> or <product>/<name-N>"
            exit 1
          fi
```

Both derive steps (replace the `MAJOR_VERSION=` line and the comment above the first one):

```bash
      # Derive the release project from the tag name.
      # Tag ppg/17.9-1      → product=ppg, version=17.9-1, major=17 → ppg:releases:17
      # Tag ppg/containers-3 → product=ppg, version=containers-3, name=containers
      #                      → ppg:releases:containers (counter-tagged cross-version project)
      ...
          VERSION="${TAG#*/}"
          case "$VERSION" in
            [0-9]*) MAJOR_VERSION="${VERSION%%.*}" ;;
            *)      MAJOR_VERSION="${VERSION%-*}" ;;
          esac
```

Keep every `echo ... >> "$GITHUB_OUTPUT"` line as is (`major_version` doubles as the releases directory name).

- [ ] **Step 2: Check the derivation locally**

```bash
for TAG in ppg/17.11-1 ppg/containers-3; do
  PRODUCT="${TAG%%/*}"; VERSION="${TAG#*/}"
  case "$VERSION" in [0-9]*) MAJOR_VERSION="${VERSION%%.*}";; *) MAJOR_VERSION="${VERSION%-*}";; esac
  echo "${PRODUCT}:releases:${MAJOR_VERSION} ${VERSION}"
done
echo ppg/containers-3 | grep -Eq '^[a-z0-9-]+/([0-9]+(\.[0-9]+)+|[a-z][a-z0-9]*)-[0-9]+$' && echo ok
echo ppg/Containers-3 | grep -Eq '^[a-z0-9-]+/([0-9]+(\.[0-9]+)+|[a-z][a-z0-9]*)-[0-9]+$' || echo rejected
```

Expected: `ppg:releases:17 17.11-1`, `ppg:releases:containers containers-3`, `ok`, `rejected`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/obs-release.yml
git commit -s -m "ci: obs-release accepts counter-tagged cross-version releases"
```

---

### Task 6: The `ppg:staging:tools` project tree and the patroni Depends change

**Goal:** `root/ppg/staging/tools/` renders as a valid OBS project holding the five packages, pinned to PG 18; patroni's Debian package no longer depends on a server.

**Files:**
- Create: `root/ppg/staging/tools/project.yaml`, `root/ppg/staging/tools/macros.yaml`
- Create (copies): `root/ppg/staging/tools/{percona-pgbouncer,percona-pgbadger,percona-haproxy,percona-pgbackrest,percona-patroni}/`
- Modify: `root/ppg/staging/_shared/percona-patroni/debian/control:44-46`

**Acceptance Criteria:**
- [ ] `venv/bin/python -m percona_obs -P verify project verify --offline` passes with the new project present.
- [ ] `tools/project.yaml` adds exactly one path-prefix entry (`ppg:staging:18`, `%_repository`) and no `qa:` block; `tools/macros.yaml` declares only `PG_MAJOR_VERSION: 18`.
- [ ] The five copied directories are real directories (not symlinks) and byte-identical to `_shared` at copy time (`diff -r` empty), except `percona-patroni/debian/control`, which is identical to the modified `_shared` copy.
- [ ] `_shared/percona-patroni/debian/control` and `tools/percona-patroni/debian/control` have no `percona-postgresql-%!{PG_MAJOR_VERSION}` token and list `postgresql` in the `percona-patroni` `Suggests:` line.

**Verify:** `venv/bin/python -m percona_obs -P verify project verify --offline && for p in percona-pgbouncer percona-pgbadger percona-haproxy percona-pgbackrest percona-patroni; do diff -r root/ppg/staging/_shared/$p root/ppg/staging/tools/$p && echo "$p identical"; done` → verify passes, five `identical` lines.

**Steps:**

- [ ] **Step 1: patroni Debian control** (in `_shared`, which PR A is allowed to touch for this one file)

In `root/ppg/staging/_shared/percona-patroni/debian/control` change line 44:

```
Depends: ${misc:Depends}, ${python3:Depends}, python3-psycopg2 , python3-etcd | python3-consul | python3-kazoo | python3-kubernetes | python3-pysyncobj, python3-cdiff, python3-systemd
```

and line 46:

```
Suggests: postgresql, etcd-server | consul | zookeeperd, vip-manager, haproxy, percona-patroni-doc
```

- [ ] **Step 2: Create the project files**

`root/ppg/staging/tools/project.yaml`:

```yaml
title: Percona Distribution for PostgreSQL — PG-independent tools
description: |
  Components whose binaries do not depend on the PostgreSQL major
  (pgBouncer, pgBadger, HAProxy, pgBackRest, Patroni), built once here and
  pulled into every ppg:staging:<V> through obs/_aggregate files
  (root/ppg/staging/_shared/<pkg>/obs/_aggregate).  Mirrors PGDG's
  rpm/redhat/main/common.

# Repositories, debuginfo flags and the PPG-wide build configuration come
# from root/project.yaml and root/ppg/staging/subprojects.yaml.  The only
# addition is the path to the pinned major so that pgBackRest resolves
# percona-postgresql18-devel / libpq-dev from our own packages.
path-prefix:
  - subproject: ppg:staging:%!{PG_MAJOR_VERSION}
    repository: "%_repository"
```

`root/ppg/staging/tools/macros.yaml`:

```yaml
# ppg:staging:tools builds PG-independent components once.  PG_MAJOR_VERSION
# is the major whose libpq they link against (pgBackRest) and whose staging
# project is on the repository path.  Bump it by hand in the PR that adds a
# new GA major to root/ppg/staging/ — never derived from the tree, so a new
# major directory cannot silently rebuild every tool.
# No PG_VERSION: nothing here uses the computed PPG_RELEASE counter.
- PG_MAJOR_VERSION: 18
```

Check `root/ppg/staging/macros.yaml` is the tier-level macros file that defines `PGBOUNCER_VERSION`, `PGBACKREST_VERSION` etc.; the tools project inherits it like the majors do (macros resolve up the tree). If `project verify --offline` reports an unresolved macro for a tools package, that macro lives in `root/ppg/staging/<V>/macros.yaml` only — then add it to `tools/macros.yaml` with the same value and note it in the commit message.

- [ ] **Step 3: Copy the packages**

```bash
cd root/ppg/staging
for p in percona-pgbouncer percona-pgbadger percona-haproxy percona-pgbackrest percona-patroni; do
  cp -a "_shared/$p" "tools/$p"
done
ls -la tools
```

Expected: five real directories plus the two yaml files; no symlinks.

- [ ] **Step 4: Verify**

```bash
venv/bin/python -m percona_obs -P verify project verify --offline
for p in percona-pgbouncer percona-pgbadger percona-haproxy percona-pgbackrest percona-patroni; do
  diff -r root/ppg/staging/_shared/$p root/ppg/staging/tools/$p && echo "$p identical"
done
grep -c 'percona-postgresql-%!{PG_MAJOR_VERSION}' root/ppg/staging/tools/percona-patroni/debian/control
```

Expected: verify passes; five `identical`; `0`.

- [ ] **Step 5: Commit**

```bash
git add root/ppg/staging/tools root/ppg/staging/_shared/percona-patroni/debian/control
git commit -s -m "ppg:staging:tools: build PG-independent components once

patroni: drop the per-major server Depends (upstream Debian has none)."
```

---

### Task 7: Documentation and spec correction

**Goal:** Repo docs describe the tools project, the extended freeze, counter-tagged releases, and the OBS release-counter caveat.

**Files:**
- Modify: `root/README.md` (around `:48-55` common/deps text, `:100-135` release ids and cutting a release, `:136-200` staging layout)
- Modify: `docs/PERCONA_OBS_TOOL.md` (the `sync release` / `project release` sections)
- Modify: `docs/PACKAGING_HOWTO.md:401-450` (aggregates)
- Modify: `docs/superpowers/specs/2026-10-08-ppg-staging-tools-design.md` Section 3 "Changelogs" bullet

**Acceptance Criteria:**
- [ ] `root/README.md` gains a `### staging/tools/` subsection (after `staging/<major-version>/`) with: purpose, the PGDG rule, the `PG_MAJOR_VERSION` pin and bump rule, the aggregate pattern, and the note that OBS `<CI_CNT>.<B_CNT>` counters restart in the new project so staging majors may briefly list an equal-version, lower-counter build until the next upstream bump.
- [ ] `root/README.md` release section documents the second tag shape `ppg/containers-<N>` and that `ppg/staging/containers` releases to `ppg:releases:containers` via `project release ppg:staging:containers`.
- [ ] `docs/PERCONA_OBS_TOOL.md` `sync release` section lists the three freeze-scope kinds and the dry-run `+` lines.
- [ ] `docs/PACKAGING_HOWTO.md` "When to use aggregates" names `ppg:staging:tools` as the home of PG-independent components.
- [ ] Spec Section 3 "Changelogs" bullet is replaced by the OBS counter caveat; spec Section 5 "Tree" notes the mirror is produced by `project release` (first release), not by PR B.

**Verify:** `grep -n "staging/tools" root/README.md docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md | wc -l` → at least 3; `grep -c "containers-<N>" root/README.md` → at least 1.

**Steps:**

- [ ] **Step 1: README staging/tools subsection** — insert after the `### staging/<major-version>/` block (before the `_shared` paragraph at `:161` if that is where the block ends):

```markdown
### `staging/tools/`

`ppg:staging:tools` builds the components whose binaries do not depend on the
PostgreSQL major — the PGDG "common" rule: anything whose binary package name
carries no PG major. Today: `percona-pgbouncer`, `percona-pgbadger`,
`percona-haproxy`, `percona-pgbackrest`, `percona-patroni`. Each per-major
project lists the same package as an aggregate
(`staging/_shared/<pkg>/obs/_aggregate` → `${OBS_ROOTPRJ}:ppg:staging:tools`),
so its published repository stays self-contained while OBS builds the component
once.

`tools/macros.yaml` pins `PG_MAJOR_VERSION` (pgBackRest links that major's libpq;
`tools/project.yaml` puts `ppg:staging:<that major>` on the repository path).
Bump it by hand in the PR that adds a new GA major to `staging/`.

OBS release counters (`<CI_CNT>.<B_CNT>`) are per project, so right after a
component moves here the majors list an equal-version build with a lower counter
than the one they built themselves. Nothing breaks (same bytes, same version); the
next upstream bump supersedes it.

`sync release` freezes the aggregated packages of `ppg:staging:tools` (and of
`ppg:common:deps`) for the duration of the `osc release` copy; see
`docs/PERCONA_OBS_TOOL.md`.
```

- [ ] **Step 2: README release section** — after the "Release IDs follow the pattern" paragraph add:

```markdown
Cross-version projects that have no `percona-postgresql` package
(`ppg/staging/containers`) are released with a plain counter instead:
`./percona-obs -P <profile> project release ppg:staging:containers` writes
`root/ppg/releases/containers/` and tags `ppg/containers-<N>`; `obs-release.yml`
maps that tag shape to `ppg:releases:containers`.
```

Also update the `_shared/containers` paragraph (`:188-190`): the pgbouncer/pgbackrest *images* now live in `staging/containers/` (cross-version), not `_shared/containers/` — write that sentence to reflect the PR B end state and mark it "(after PR B)" only if the docs commit lands before PR B; drop the marker in PR B's Task 9.

- [ ] **Step 3: PERCONA_OBS_TOOL.md** — in the `sync release` description add:

```markdown
Freeze scope. Before `osc release` the command drains and green-checks, then
build-disables for the duration of the copy:

- the release source project and its subprojects (whole);
- every local aggregate source referenced by an `obs/_aggregate` under the
  source tree — `ppg:staging:tools`, `ppg:common:deps` — restricted to the
  aggregated packages (package `_meta` build disable);
- for a container project release, the `subproject:` entries of its repository
  paths (whole), since an image may consume any package of them.

`--dry-run` prints the extra sources as `+ <project>  (whole)` or
`+ <project>  (<pkg>, …)` and includes them in the green check.
```

- [ ] **Step 4: PACKAGING_HOWTO.md** — in "When to use aggregates" add a bullet: "A PG-independent component built once in `ppg:staging:tools` and listed in every `ppg:staging:<V>` (pgbouncer, pgbackrest, …): `staging/_shared/<pkg>/obs/_aggregate` → `${OBS_ROOTPRJ}:ppg:staging:tools`."

- [ ] **Step 5: Spec corrections** — in the spec replace the "Changelogs" bullet of Section 3 with:

```markdown
- **No changelog or Release bump**: OBS overrides spec `Release:` with
  `<CI_CNT>.<B_CNT>` (root prjconf), so nothing in the sources can raise the
  published counter. Counters restart in the tools project; the majors list an
  equal-version, lower-counter build until the next upstream bump. Staging-only
  cosmetic effect, documented in root/README.md.
```

and in Section 5 "Tree" change "materialised by `project release`" to "written by the first `project release ppg:staging:containers` run (the release PR), not by PR B"; in Section 6 PR B remove "`root/ppg/releases/containers/` mirror and" so PR B lists only the aggregates, the image move and the containers path addition.

- [ ] **Step 6: Commit**

```bash
git add root/README.md docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md docs/superpowers/specs/2026-10-08-ppg-staging-tools-design.md
git commit -s -m "docs: ppg:staging:tools, extended release freeze, counter-tagged releases"
```

**End of PR A.** Run the full gate (`venv/bin/black percona_obs/ tests/ && venv/bin/pyright && venv/bin/python -m pytest tests -q && venv/bin/python -m percona_obs -P verify project verify --offline`), then ask the user before pushing `staging-tools` to `percona` and opening PR A (label `obs-sync`; QA labels are the user's call). Tasks 8–9 start only after the user says PR A is merged and `ppg:staging:tools` is green on OBS.

---

## PR A rework (2026-10-09) — `common/` layout

Executed on the existing worktree `.claude/worktrees/staging-tools`, branch `staging-tools` (PR #123). Per-task commits; the branch is force-pushed only after the user confirms at the end of Task 15.

### Task 12: Move the tools project under `common/`

**Goal:** `root/ppg/staging/common/tools/` renders as `ppg:staging:common:tools` with the same effective configuration the project had at `root/ppg/staging/tools/`.

> Amended 2026-10-09 during execution: `common/project.yaml` does NOT opt out of inherited repositories (an opt-out resets the list before `common/subprojects.yaml`, which declares none), and `PG_MAJOR_VERSION: 18` lives in `common/macros.yaml`; the heredoc below shows the original text.

**Files:**
- Create: `root/ppg/staging/common/project.yaml`, `root/ppg/staging/common/subprojects.yaml` (symlink)
- Move: `root/ppg/staging/tools/` → `root/ppg/staging/common/tools/` (git mv)
- Modify: `root/ppg/staging/common/tools/macros.yaml:1` (comment), `root/ppg/staging/common/tools/project.yaml` (description text)

**Acceptance Criteria:**
- [ ] `root/ppg/staging/tools/` no longer exists; `root/ppg/staging/common/tools/` holds `project.yaml`, `macros.yaml` and the five package directories unchanged (`git diff -M --stat` shows pure renames for the packages).
- [ ] `root/ppg/staging/common/project.yaml` is a package-less intermediate with `repositories-inherit: false`, `project-config-inherit: false`, `debuginfo: ~`, like `root/ppg/staging/extras/project.yaml`.
- [ ] `root/ppg/staging/common/subprojects.yaml` is a relative symlink to `../subprojects.yaml`.
- [ ] `project config --offline ppg:staging:common:tools` renders the same repositories (14), the same path order (`ppg:staging:18` first, then `ppg:common:deps`, `common:deps:build`, distro) and the same prjconf as `ppg:staging:tools` rendered before the move.
- [ ] `project verify --offline` passes; pytest passes.

**Verify:** `test ! -e root/ppg/staging/tools && readlink root/ppg/staging/common/subprojects.yaml && venv/bin/python -m percona_obs -P verify project config --offline ppg:staging:common:tools | grep -c '<path project="isv:percona:ppg:staging:18"' && venv/bin/python -m percona_obs -P verify project verify --offline` → `../subprojects.yaml`, `14`, verify passes.

**Steps:**

- [ ] **Step 1: Capture the before-state**

```bash
venv/bin/python -m percona_obs -P verify project config --offline ppg:staging:tools > /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/8e247063-ce1c-44e6-9459-6e60b01ee28c/scratchpad/tools-before.txt
```

- [ ] **Step 2: Create the intermediate and move the project**

```bash
mkdir root/ppg/staging/common
cat > root/ppg/staging/common/project.yaml <<'EOF'
title: Percona Distribution for PostgreSQL — Staging cross-version projects
description: |
  Container project for the cross-version subprojects of the staging tier
  (ppg:staging:common:tools, ppg:staging:common:containers, …). It holds no
  buildable packages and therefore no build repositories.
# A package-less intermediate: it must not pick up the per-major repository
# patches, debuginfo flags or build configuration that
# root/ppg/staging/subprojects.yaml folds into every project below it.
# Its own subprojects.yaml (a symlink to the tier's) hands them on to the
# direct children that do want them (tools).
repositories-inherit: false
project-config-inherit: false
debuginfo: ~
EOF
ln -s ../subprojects.yaml root/ppg/staging/common/subprojects.yaml
git mv root/ppg/staging/tools root/ppg/staging/common/tools
```

- [ ] **Step 3: Fix the two self-references**

In `root/ppg/staging/common/tools/macros.yaml` line 1: `# ppg:staging:common:tools builds PG-independent components once.  PG_MAJOR_VERSION`.
In `root/ppg/staging/common/tools/project.yaml` description: replace `(root/ppg/staging/_shared/<pkg>/obs/_aggregate)` context so it reads "pulled into every ppg:staging:<V> through obs/_aggregate files (root/ppg/staging/_shared/<pkg>/obs/_aggregate → ${OBS_ROOTPRJ}:ppg:staging:common:tools)".

- [ ] **Step 4: Compare after-state and verify**

```bash
venv/bin/python -m percona_obs -P verify project config --offline ppg:staging:common:tools > /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/8e247063-ce1c-44e6-9459-6e60b01ee28c/scratchpad/tools-after.txt
diff <(sed 's/ppg:staging:tools/ppg:staging:common:tools/g' /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/8e247063-ce1c-44e6-9459-6e60b01ee28c/scratchpad/tools-before.txt) /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/8e247063-ce1c-44e6-9459-6e60b01ee28c/scratchpad/tools-after.txt
venv/bin/python -m percona_obs -P verify project verify --offline && venv/bin/python -m pytest tests -q
```

Expected: the diff is empty apart from the title/description lines you changed; verify passes; tests pass.

- [ ] **Step 5: Commit**

```bash
git add -A root/ppg/staging/common
git commit -s -m "ppg:staging:common: tier-level parent for cross-version projects; tools moves under it"
```

---

### Task 13: Counter mode from the tree; drop the image-source routing

**Goal:** `project release` chooses counter mode when no `percona-postgresql*` package directory exists under the source tree, and no longer special-cases a source project that holds images itself.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`_derive_release_id` call site ~2185-2200, `source_versions`/`release_versions` ~2222-2260, source-image merges ~2279-2297, CVE flag ~2323)
- Create helper in: `percona_obs/release_scope.py` (`tree_has_server_package`)
- Test: `tests/test_release_scope.py`, `tests/test_project_release.py`

**Acceptance Criteria:**
- [ ] `release_scope.tree_has_server_package(source_path) -> bool` is true when any package directory under the source project or its subprojects (symlinks followed, `_shared` skipped as `find_packages` does) is named `percona-postgresql` or `percona-postgresql<digits>`.
- [ ] `cmd_project_release` passes `counter_mode=not tree_has_server_package(source_path)`; `_derive_release_id` itself is unchanged.
- [ ] Every `source_is_container_project` branch is removed: `source_versions` and `release_versions` are always fetched; no merge of the source or release project itself into the container dicts; CVE scan gets `has_container_images=bool(container_subs)`. `has_container_images` stays imported for the subproject loop.
- [ ] Tests: `test_tree_has_server_package_major_tree` (fixture with `percona-postgresql/obs/_service` → True), `test_tree_has_server_package_common_tree` (fixture `common/` with `tools/percona-pgbouncer` and `containers/img/obs/Dockerfile` → False), `test_tree_has_server_package_suffixed_name` (`percona-postgresql18` → True); the four `_derive_release_id` tests stay as they are.
- [ ] black, pyright, pytest green.

**Verify:** `venv/bin/python -m pytest tests/test_release_scope.py tests/test_project_release.py -q` → all PASS; `grep -c source_is_container_project percona_obs/cmd_project.py` → `0`.

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_release_scope.py`, reusing `_mk_root` and `_pkg`)

```python
def test_tree_has_server_package_major_tree(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    _pkg(src / "percona-pgbouncer", {"_service": "<services/>"})
    assert rs.tree_has_server_package(src) is True


def test_tree_has_server_package_suffixed_name(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/18"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "percona-postgresql18", {"_service": "<services/>"})
    assert rs.tree_has_server_package(src) is True


def test_tree_has_server_package_common_tree(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/common"
    (src / "tools").mkdir(parents=True)
    (src / "containers").mkdir()
    (src / "project.yaml").write_text("repositories-inherit: false\n")
    (src / "tools" / "project.yaml").write_text("title: T\n")
    (src / "containers" / "project.yaml").write_text("repositories-inherit: false\n")
    _pkg(src / "tools" / "percona-pgbouncer", {"_service": "<services/>"})
    _pkg(src / "tools" / "percona-postgresql-common-lookalike", {"_service": "<services/>"})
    _pkg(src / "containers" / "percona-distribution-postgresql-upgrade", {"Dockerfile": "FROM x\n"})
    assert rs.tree_has_server_package(src) is False
```

Note the lookalike: `percona-postgresql-common-lookalike` must NOT match, so the check is an exact name or `percona-postgresql` followed by digits only.

- [ ] **Step 2: Run to see them fail**

Run: `venv/bin/python -m pytest tests/test_release_scope.py -q -k tree_has_server_package`
Expected: 3 FAIL `AttributeError: tree_has_server_package`

- [ ] **Step 3: Implement the helper** (in `percona_obs/release_scope.py`, after `has_container_images`)

```python
_SERVER_PKG_RE = re.compile(r"^percona-postgresql\d*$")


def tree_has_server_package(source_path: Path) -> bool:
    """True when the source project or any subproject holds the server package.

    Decides the release-id mode of ``project release`` from the git tree:
    a PG major carries ``percona-postgresql`` (or ``percona-postgresqlNN``)
    and gets ``MAJOR.MINOR-N`` ids; a cross-version parent such as
    ``ppg:staging:common`` does not and gets a plain counter.
    """
    return any(
        _SERVER_PKG_RE.match(pkg_path.name)
        for _, pkg_path in find_packages(source_path, "")
    )
```

Check `find_packages(source_path, "")` signature accepts an empty obs_project (it only prefixes names); if it needs a non-empty string pass `"x"` — the name is unused here.

- [ ] **Step 4: Rewire `cmd_project_release`**

Replace `source_is_container_project = has_container_images(source_path)` with nothing; at the `_derive_release_id` call use `counter_mode=not tree_has_server_package(source_path)` (add `tree_has_server_package` to the `.release_scope` import). Restore the plain forms:

```python
    source_versions = _fetch_project_pkg_versions(apiurl, source_obs_project)
    ...
        release_versions = _fetch_project_pkg_versions(apiurl, release_obs_project)
```

Delete the two `if source_is_container_project:` merge blocks (source and release project into the container dicts). CVE scan: `has_container_images=bool(container_subs)`.

- [ ] **Step 5: Gate, full suite, commit**

```bash
venv/bin/python -m pytest tests -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright
git add percona_obs/release_scope.py percona_obs/cmd_project.py tests/test_release_scope.py
git commit -s -m "project release: counter mode when the source tree has no server package"
```

---

### Task 14: Path-prefix freeze sources from every image subproject

**Goal:** `collect_release_scope` gathers whole-project path-prefix sources from each image-holding project under the source, so a `ppg:releases:common` release freezes the majors and `ppg:common:deps`.

**Files:**
- Modify: `percona_obs/release_scope.py` (`collect_release_scope`, module docstring)
- Test: `tests/test_release_scope.py`

**Acceptance Criteria:**
- [ ] For every `(sub_id, sub_path)` in `find_projects(source_path, source_project_id)` where `has_container_images(sub_path)` is true (the source itself included), the resolved repositories' `subproject:` entries are collected as today (skip own ids, missing dirs, out-of-slice; dedupe; first-seen order).
- [ ] Existing tests `test_container_source_adds_path_prefix_projects`, `test_non_container_source_ignores_path_prefix`, `test_container_path_prefix_out_of_slice_is_skipped` pass unchanged.
- [ ] New test `test_common_parent_collects_paths_from_image_subprojects`: a `common/` fixture with `tools/` (packages, no images), `containers/` (image, paths to `ppg:staging:18`, `ppg:common:deps`, `ppg:staging:common:tools`) and `tools/containers/` (image, paths to `ppg:staging:17`, `ppg:staging:common:tools`) → `whole_projects == ["<root>:ppg:staging:18", "<root>:ppg:common:deps", "<root>:ppg:staging:17"]` and `packages == {}` (tools is an own subproject and excluded).

**Verify:** `venv/bin/python -m pytest tests/test_release_scope.py -q` → all PASS

**Steps:**

- [ ] **Step 1: Write the failing test** (append to `tests/test_release_scope.py`)

```python
def _image_project_yaml(paths: list[str]) -> str:
    return yaml.dump(
        {
            "repositories-inherit": False,
            "project-config-inherit": False,
            "repositories": [
                {
                    "name": "ubi9",
                    "archs": ["x86_64"],
                    "paths": [{"subproject": p, "repository": "UBI_9"} for p in paths],
                }
            ],
        }
    )


def test_common_parent_collects_paths_from_image_subprojects(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    for major in ("17", "18"):
        (root / "ppg/staging" / major).mkdir(parents=True)
        (root / "ppg/staging" / major / "project.yaml").write_text("title: S\n")
    (root / "ppg/common/deps").mkdir(parents=True)
    (root / "ppg/common/deps/project.yaml").write_text("title: D\n")
    src = root / "ppg/staging/common"
    (src / "tools" / "containers").mkdir(parents=True)
    (src / "containers").mkdir()
    (src / "project.yaml").write_text("repositories-inherit: false\nproject-config-inherit: false\n")
    (src / "tools" / "project.yaml").write_text("title: T\n")
    _pkg(src / "tools" / "percona-pgbouncer", {"_service": "<services/>"})
    (src / "containers" / "project.yaml").write_text(
        _image_project_yaml(["ppg:staging:18", "ppg:common:deps", "ppg:staging:common:tools"])
    )
    _pkg(src / "containers" / "upgrade", {"Dockerfile": "FROM x\n"})
    (src / "tools" / "containers" / "project.yaml").write_text(
        _image_project_yaml(["ppg:staging:17", "ppg:staging:common:tools"])
    )
    _pkg(src / "tools" / "containers" / "percona-pgbouncer", {"Dockerfile": "FROM x\n"})
    scope = rs.collect_release_scope(src, "ppg:staging:common", "isv:percona", {})
    assert scope.whole_projects == [
        "isv:percona:ppg:staging:18",
        "isv:percona:ppg:common:deps",
        "isv:percona:ppg:staging:17",
    ]
    assert scope.packages == {}
```

- [ ] **Step 2: Run to see it fail**

Run: `venv/bin/python -m pytest tests/test_release_scope.py -q -k common_parent`
Expected: FAIL (whole_projects is `[]` because the parent holds no images itself)

- [ ] **Step 3: Implement** — replace the `if has_container_images(source_path):` block in `collect_release_scope` with:

```python
    for _, project_path in find_projects(source_path, source_project_id):
        if not has_container_images(project_path):
            continue
        cfg = resolve_project_config(
            project_path, env_vars or {}, repo_filter=RepositoryFilter.EMPTY
        )
        for repo in cfg.get("repositories", []):
            for entry in repo.get("paths", []):
                sub = entry.get("subproject")
                if not sub or sub in own_ids:
                    continue
                sub_path = REPO_ROOT.joinpath(*sub.split(":"))
                if not sub_path.is_dir() or not project_in_slice(sub_path, env_vars):
                    continue
                full = f"{rootprj}:{sub}"
                if full not in scope.whole_projects:
                    scope.whole_projects.append(full)
```

Update the module docstring bullet: "path-prefix sources — every image-holding project under the release source (the source or any subproject) may consume any package of the `subproject:` entries in its repository paths, so those projects are frozen whole" and replace `ppg:staging:tools` with `ppg:staging:common:tools` in the docstring.

- [ ] **Step 4: Gate and commit**

```bash
venv/bin/python -m pytest tests -q && venv/bin/black percona_obs/ tests/ && venv/bin/pyright
git add percona_obs/release_scope.py tests/test_release_scope.py
git commit -s -m "release_scope: path-prefix sources from every image subproject of the release source"
```

---

### Task 15: Docs for the `common/` layout and PR #123 refresh

**Goal:** Every doc and comment names the new projects and release unit; PR #123's title and body describe the reworked PR A.

**Files:**
- Modify: `root/README.md` (`### staging/tools/` → `### staging/common/`; release paragraph ~115-119; `_shared/containers` sentence ~198), `docs/PERCONA_OBS_TOOL.md` (~945 counter rule, ~1112 freeze scope), `docs/PACKAGING_HOWTO.md:459-461`, `.github/workflows/obs-release.yml:192` (comment)
- PR: title/body via `gh pr edit 123` after user confirmation

**Acceptance Criteria:**
- [ ] `grep -rn "ppg:staging:tools\b\|releases:containers\|containers-<N>\|staging/tools/" root/README.md docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md .github/workflows/obs-release.yml` → no output.
- [ ] README has a `### staging/common/` section (same position, before `### devel/<major-version>/`) describing: the tier-level parent, the `subprojects.yaml` symlink, `common/tools` (PGDG rule, `PG_MAJOR_VERSION` pin, aggregates, counter caveat), the image subprojects arriving in PR B, `devel/common` only when needed, and the `ppg:releases:common` unit tagged `ppg/common-<N>` cut with `project release ppg:staging:common`.
- [ ] README release paragraph states the counter rule as "no `percona-postgresql` package anywhere under the source tree (e.g. `ppg/staging/common`)"; PERCONA_OBS_TOOL.md step 1 says the same and the freeze-scope block names `ppg:staging:common:tools` and "every image-holding project under the source".
- [ ] The branch is pushed and PR #123 updated ONLY after the user says yes.

**Verify:** the grep above prints nothing; `grep -c "### \`staging/common/\`" root/README.md` → `1`.

**Steps:**

- [ ] **Step 1: Edit the docs** per the acceptance criteria (rename the README section heading and body; rewrite the release paragraph; the `_shared/containers` sentence becomes "`percona-pgbouncer` and `percona-pgbackrest` *images* move to `staging/common/tools/containers/` in PR B; until then they live in `staging/_shared/containers/<pkg>/` linked from every `staging/<V>/containers/`"; PACKAGING_HOWTO bullet and obs-release.yml comment use `ppg:staging:common:tools` / `ppg:releases:common` / `ppg/common-3`).

- [ ] **Step 2: Gate and commit**

```bash
venv/bin/python -m percona_obs -P verify project verify --offline && venv/bin/python -m pytest tests -q
git add root/README.md docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md .github/workflows/obs-release.yml
git commit -s -m "docs: common/ layout, ppg:releases:common release unit"
```

- [ ] **Step 3: Ask the user**, then force-push and refresh the PR

```bash
git push --force-with-lease percona staging-tools
gh pr edit 123 -R percona/obs-packaging --title "ppg:staging:common:tools: build PG-independent components once (PR A)" --body-file <refreshed body: same structure as before with the common/ names, the ppg:releases:common unit, and a "Revision" line pointing at the spec>
```

---

## PR B — switch consumers and move the images (rewritten 2026-10-09)

Branch `staging-tools-b` from the updated `percona/main` (new worktree `.claude/worktrees/staging-tools-b`), venv and the `verify` profile created as in Global Constraints. Starts only after PR A is merged and `ppg:staging:common:tools` is green on OBS.

### Task 8: Per-major packages become aggregates

**Goal:** Every `ppg:staging:<V>` lists the five components as aggregates of `ppg:staging:common:tools`.

**Files:**
- Modify (shrink): `root/ppg/staging/_shared/{percona-pgbouncer,percona-pgbadger,percona-haproxy,percona-pgbackrest,percona-patroni}/` → only `obs/_aggregate`

**Acceptance Criteria:**
- [ ] Each of the five `_shared` dirs contains exactly `obs/_aggregate` (project `${OBS_ROOTPRJ}:ppg:staging:common:tools`, the package name; etcd shape) and its pre-existing `package.yaml` (per-major QA lanes, PG-2830) — nothing else. (Amended 2026-10-09: keep `package.yaml`.)
- [ ] The per-major symlinks `root/ppg/staging/{14,15,16,17,18}/<pkg>` are unchanged and resolve.
- [ ] `project verify --offline` and pytest pass.

**Verify:** `for p in percona-pgbouncer percona-pgbadger percona-haproxy percona-pgbackrest percona-patroni; do find root/ppg/staging/_shared/$p -type f; done` → ten lines, `.../obs/_aggregate` and `.../package.yaml` per package; verify passes.

**Steps:**

- [ ] **Step 1: Replace the sources**

```bash
cd root/ppg/staging/_shared
for p in percona-pgbouncer percona-pgbadger percona-haproxy percona-pgbackrest percona-patroni; do
  git rm -r -q "$p/rpm" "$p/debian" "$p/obs"   # keep package.yaml (QA lanes)
  mkdir -p "$p/obs"
  cat > "$p/obs/_aggregate" <<EOF
<aggregatelist>
  <aggregate project="\${OBS_ROOTPRJ}:ppg:staging:common:tools">
    <package>$p</package>
  </aggregate>
</aggregatelist>
EOF
done
cd - >/dev/null
for v in 14 15 16 17 18; do for p in percona-pgbouncer percona-pgbackrest; do test -f root/ppg/staging/$v/$p/obs/_aggregate || echo "BROKEN $v/$p"; done; done
```

- [ ] **Step 2: Verify and commit**

```bash
venv/bin/python -m percona_obs -P verify project verify --offline && venv/bin/python -m pytest tests -q
git add -A root/ppg/staging/_shared
git commit -s -m "ppg:staging:<V>: aggregate pgbouncer, pgbadger, haproxy, pgbackrest, patroni from ppg:staging:common:tools"
```

---

### Task 9: Move the cross-version image projects under `common/`

**Goal:** `ppg:staging:common:containers`, `ppg:staging:common:extras:containers` and the new `ppg:staging:common:tools:containers` replace `ppg:staging:containers`, `ppg:staging:extras:containers` and the five per-major tool images.

**Files:**
- Move: `root/ppg/staging/containers/` → `root/ppg/staging/common/containers/`; `root/ppg/staging/extras/containers/` → `root/ppg/staging/common/extras/containers/`; `root/ppg/staging/_shared/containers/{percona-pgbouncer,percona-pgbackrest}/` → `root/ppg/staging/common/tools/containers/`
- Delete: `root/ppg/staging/extras/project.yaml`; symlinks `root/ppg/staging/{14..18}/containers/{percona-pgbouncer,percona-pgbackrest}`
- Create: `root/ppg/staging/common/extras/project.yaml` (intermediate, copy of the old `extras/project.yaml` with the name updated), `root/ppg/staging/common/tools/containers/{project.yaml,macros.yaml}`
- Modify: the three image `project.yaml` `qa:` `REPOSITORY` values; both tool Dockerfiles (drop `PG_VERSION`); `root/README.md` `_shared/containers` sentence

**Acceptance Criteria:**
- [ ] `root/ppg/staging/containers` and `root/ppg/staging/extras` no longer exist; `root/ppg/staging/_shared/containers/` holds only the two server images and `project.yaml`; no per-major `containers/` links to the tool images.
- [ ] `common/tools/containers/project.yaml` = the moved `common/containers/project.yaml` repositories/prjconf with `- subproject: ppg:staging:common:tools` / `repository: UBI_<N>` inserted after the `ppg:staging:14` entry in each of ubi8/ubi9/ubi10, a `qa:` block whose `REPOSITORY` is `${OBS_CONTAINER_REGISTRY}/${OBS_CONTAINER_REGISTRY_ROOTPRJ}/ppg/staging/common/tools/containers/<ubi>` (keep the pipeline/matrix shape of the source block), and `macros.yaml` with `PG_MAJOR_VERSION: 18` (+ `PG_MINOR_VERSION`/`PG_VERSION` as in the source file).
- [ ] `common/containers/project.yaml` and `common/extras/containers/project.yaml` differ from the originals only in description wording and `REPOSITORY` paths (`ppg/staging/common/containers/<ubi>`, `ppg/staging/common/extras/containers/ubi9`).
- [ ] `grep -c PG_VERSION` is `0` for both tool Dockerfiles.
- [ ] `project verify --offline` and pytest pass; `project config --offline ppg:staging:common:tools:containers` shows `ppg:staging:common:tools` on each repository path.

**Verify:** `test ! -e root/ppg/staging/containers && test ! -e root/ppg/staging/extras && venv/bin/python -m percona_obs -P verify project config --offline ppg:staging:common:tools:containers | grep -c 'ppg:staging:common:tools"'` → `3`; verify passes.

**Steps:**

- [ ] **Step 1: Moves**

```bash
git mv root/ppg/staging/containers root/ppg/staging/common/containers
mkdir -p root/ppg/staging/common/extras
git mv root/ppg/staging/extras/containers root/ppg/staging/common/extras/containers
git mv root/ppg/staging/extras/project.yaml root/ppg/staging/common/extras/project.yaml
mkdir -p root/ppg/staging/common/tools/containers
git mv root/ppg/staging/_shared/containers/percona-pgbouncer root/ppg/staging/common/tools/containers/percona-pgbouncer
git mv root/ppg/staging/_shared/containers/percona-pgbackrest root/ppg/staging/common/tools/containers/percona-pgbackrest
for v in 14 15 16 17 18; do git rm -q root/ppg/staging/$v/containers/percona-pgbouncer root/ppg/staging/$v/containers/percona-pgbackrest; done
cp root/ppg/staging/common/containers/project.yaml root/ppg/staging/common/tools/containers/project.yaml
cp root/ppg/staging/common/containers/macros.yaml root/ppg/staging/common/tools/containers/macros.yaml
```

- [ ] **Step 2: Edit** `common/extras/project.yaml` description (`ppg:staging:common:extras:containers`); `common/tools/containers/project.yaml`: title "Percona Container Images for the PG-independent tools", description, insert the tools path entry after `ppg:staging:14` in each repo (comment: `# tools builds percona-pgbouncer / percona-pgbackrest; the majors only aggregate them.`), set the three `REPOSITORY` values; set `REPOSITORY` in `common/containers/project.yaml` and `common/extras/containers/project.yaml` to their new paths; drop the `ARG PG_VERSION=%!{PG_VERSION}` / `ENV PG_VERSION=${PG_VERSION}` lines from both tool Dockerfiles; README `_shared/containers` sentence: "`percona-pgbouncer` and `percona-pgbackrest` *images* are cross-version and live in `staging/common/tools/containers/`; the two server images stay in `staging/_shared/containers/<pkg>/` linked from every `staging/<V>/containers/`"; README `### staging/common/` section: replace "arriving in PR B" wording with the present tense.

- [ ] **Step 3: Verify and commit**

```bash
venv/bin/python -m percona_obs -P verify project verify --offline && venv/bin/python -m pytest tests -q
git add -A root/ppg/staging root/README.md
git commit -s -m "containers: cross-version image projects move under ppg:staging:common; tool images built once"
```

**End of PR B.** Full gate, then ask the user before pushing `staging-tools-b` and opening PR B (labels `obs-sync` and, on the user's say, `qa-packages` + `qa-containers`). Expected PR-check observations: every major's five packages show `aggregate` with the PR tools project as source; the three image projects build at `pr-N:ppg:staging:common:{containers,tools:containers,extras:containers}`.

---

## Post-merge (user-driven; the agent prepares commands and reads results)

### Task 10: Binary comparison, orphan cleanup and release dry-runs

**Goal:** Evidence that the tools build is equivalent to the per-major builds, the orphaned projects are gone, and the extended freeze scope resolves on production.

**Files:** none (OBS queries; one manual delete per orphan)

**Acceptance Criteria:**
- [ ] For pgbouncer and pgbackrest on `RockyLinux_9/x86_64`, `rpm -qp --requires --provides` of the tools RPM differs from the last released RPM only in libpq lines (pgbackrest) or not at all (pgbouncer).
- [ ] `ppg:staging:containers` and `ppg:staging:extras:containers` are deleted on every instance after their replacements publish (user runs `osc rdelete`, labs and production).
- [ ] `sync release --dry-run ppg:releases:18` prints `+ <root>:ppg:staging:common:tools  (percona-haproxy, percona-patroni, percona-pgbackrest, percona-pgbadger, percona-pgbouncer)` and `+ <root>:ppg:common:deps  (etcd, …)`.

**Verify:** the two dry-run lines appear; `osc ls <root>:ppg:staging:containers` returns 404 on both instances.

**Steps:**

- [ ] **Step 1:** binary comparison as before, with `<root>:ppg:staging:common:tools` as the source project.
- [ ] **Step 2:** after sync-main has published the three new image projects: `venv/bin/osc -A <apiurl> rdelete -m "moved under ppg:staging:common" <root>:ppg:staging:containers <root>:ppg:staging:extras:containers` on each instance (user runs; production is a write and needs their explicit go).
- [ ] **Step 3:** `venv/bin/python -m percona_obs -P <profile> sync release --dry-run ppg:releases:18`.

### Task 11: First `ppg:releases:common` release

**Goal:** The four cross-version subprojects are released under `ppg/common-1`.

**Files:**
- Created by the command: `root/ppg/releases/common/{release.yaml,CHANGELOG.md,project.yaml,containers/,tools/,tools/containers/,extras/containers/}`

**Acceptance Criteria:**
- [ ] `project release ppg:staging:common` previews `Tag: ppg/common-1`, `Directory: root/ppg/releases/common/`, a CHANGELOG with the five tool packages (suffixed `tools`) and the images of `containers`, `tools:containers`, `extras:containers`.
- [ ] `sync release --dry-run ppg:releases:common` lists the five majors and `ppg:common:deps` with `(whole)`.
- [ ] After the release PR merges, obs-release runs for `ppg/common-1`; `ppg:releases:common:{containers,tools,tools:containers,extras:containers}` exist with their binaries; the GitHub release notes come from `root/ppg/releases/common/CHANGELOG.md`.
- [ ] The next `ppg:releases:17` / `18` CHANGELOG gets a one-line pointer: "pgBouncer and pgBackRest images are released from ppg:releases:common (ppg/common-N)." (by hand when that release is cut).

**Verify:** `gh run list --workflow obs-release.yml --limit 1` shows success for `ppg/common-1`; `venv/bin/osc -A <apiurl> ls <root>:ppg:releases:common:tools` lists the five packages.

**Steps:**

- [ ] **Step 1:** `venv/bin/python -m percona_obs -P <profile> project release ppg:staging:common` → review preview → `y`.
- [ ] **Step 2:** `venv/bin/python -m percona_obs -P <profile> sync release --dry-run ppg:releases:common`.
- [ ] **Step 3:** Ask the user before pushing the release branch and opening the release PR.
- [ ] **Step 4:** After merge, watch `obs-release.yml` and verify with the commands under **Verify**.
