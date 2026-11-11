# Independent Release Units Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A release covers one *release unit* (a staging project plus its `containers`/`tarballs` children); `extras`, `tde` and the `common` subprojects release on their own; `sync release` deletes packages and subprojects that left the release.

**Architecture:** One membership rule (`release_unit_members`) replaces every `find_projects` walk of a release source. Release mirrors lose their `subproject:` repository paths, so no release project depends on another. `project release` maps a nested unit root to a nested release directory with its own `release.yaml`, id prefix and `PPG_RELEASE` counter. `release_tree` gains a prune step used by `sync release`.

**Tech Stack:** Python 3 (`percona_obs/`), pytest, GitHub Actions workflows, bash.

**Spec:** `docs/superpowers/specs/2026-11-10-independent-release-units-design.md` (read it first; section numbers below refer to it).

## Global Constraints

- Work in the worktree `.claude/worktrees/independent-release-units` (branch `independent-release-units`). Never edit the primary checkout.
- The worktree has no `venv/`. Use the primary checkout's: `VENV=/home/rdias/Work/percona-obs-packaging/venv/bin`. Run every command from the worktree root so `percona_obs` resolves to the worktree copy.
- After every code change: `$VENV/black percona_obs/` then `$VENV/pyright` (must report `0 errors`).
- Tests: `$VENV/python -m pytest tests/<file> -q`. No test may reach OBS; monkeypatch the `obs_api` names the module under test imported.
- Commits: `git commit -s`, no `Co-Authored-By`, no Claude attribution. Never `git push`, never `gh pr create`.
- `-P isv` is production: only with `--dry-run`, and only where a task says so.
- The bundled names are exactly `("containers", "tarballs")`, defined once as `common.BUNDLED_SUBPROJECTS`.
- Tag shape stays `<product>/<id>`; ids contain no `/`.
- Read the files a task modifies before editing them (line numbers below are from `percona/main` at `f84efe7c` and drift as tasks land).

**User decisions (already made):**
- Nested units live at `root/ppg/releases/<V>/<unit>/release.yaml`, target `ppg:releases:<V>:<unit>` ("A").
- Tags `ppg/extras-18.6-N`, `ppg/tde-16.11-N`, per-unit counter ("A").
- No coupling check between a nested unit and its parent's released state ("C").
- Unit = project + direct `containers`/`tarballs` children, fixed rule in the tool ("A").
- "In release projects we don't do builds and therefore we don't need to configure repo paths referencing other isv:percona projects. We could strip those repo paths from release projects meta."
- `sync release` deletes packages and projects that no longer belong to the release; package truth source = the hop's source OBS project ("A").
- Upgrade images move to `ppg:staging:common:upgrade:containers` and `ppg:staging:common:upgrade:extras:containers`.
- Two PRs: tool + CI first, tree move second ("A").
- `PPG_RELEASE` follows the unit for nested per-major units; `common` keeps the target major's main record ("A").

## Review Focus

1. **A main release run on a tree where `releases/<V>/extras/` has no `release.yaml` yet** — the mirror writer and the prune must leave `releases/<V>/extras/` and `ppg:releases:<V>:extras` alone. Tests: Task 3 (`test_write_release_tree_leaves_nested_unit_mirror_alone`), Task 6 (`test_stale_subprojects_keeps_projects_with_a_mirror`).
2. **First independent extras release reusing a published image tag** — id and `PPG_RELEASE` must continue the bundled numbering. Tests: Task 4 (`test_derive_release_id_nested_first_release_continues_parent`), Task 5 (`test_ppg_release_nested_unit_without_record_uses_main`).
3. **Source package listing empty while the target has packages** (pre-release deleted, wrong `--from`) — prune must abort, not empty the release. Test: Task 6 (`test_prune_refuses_empty_source_with_packages_in_target`).
4. **Prune after an unverified copy** (`--verify-timeout 0`) — nothing deleted. Test: Task 6 (`test_release_tree_skips_prune_without_verify`).
5. **A repository whose paths are all `subproject:`** — mirror writer must fail naming it, not write a path-less repository. Test: Task 3 (`test_strip_internal_paths_rejects_pathless_repo`).

---

## File Structure

| File | Change |
|---|---|
| `percona_obs/common.py` | `BUNDLED_SUBPROJECTS`; unit-aware `PPG_RELEASE` in `inject_computed_macros` |
| `percona_obs/release_scope.py` | unit model: `release_unit_members`, `unit_packages`, `bundled_parent`, `nested_unit_roots`, `ReleaseLocation`, `release_location`; scope walkers use it |
| `percona_obs/release_copy.py` | unit-bounded `collect_release_subprojects`; `mirror_subproject_pairs` (moved from `cmd_sync.py`); prune; redirection params removed |
| `percona_obs/cmd_project.py` | mirror writer strips internal paths and stays inside the unit; `project release` for nested units; id derivation |
| `percona_obs/cmd_sync.py` | call-site changes; record-check paths; prune wiring and dry-run listing |
| `.github/scripts/release_pr.py` | nested `release.yaml` regex; `project-for-tag` |
| `.github/scripts/post_pr_comment.py` | removal list in the pre-release comment |
| `.github/scripts/update_version_lists.py` | nested release id lookup |
| `.github/workflows/obs-release-pr.yml`, `obs-pr-cleanup.yml`, `obs-release.yml` | nested paths, tag lookup, removal report |
| `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md`, `root/README.md` | documentation |
| `tests/test_release_scope.py`, `test_sync_release.py`, `test_release_copy.py`, `test_project_release.py`, `test_computed_macros.py`, `test_sync_prerelease.py`, `test_prerelease_meta.py`, `test_release_pr_script.py`, `test_post_pr_comment.py`, `test_update_version_lists.py` | tests |

Tasks 1–9 are PR 1. Task 10 is PR 2 (separate branch, after PR 1 merged).

---

### Task 1: Release unit model

**Goal:** One function decides which projects belong to a release unit, and the freeze-scope walkers use it.

**Files:**
- Modify: `percona_obs/common.py` (next to `SHARED_SOURCE_DIRNAME`, ~line 128)
- Modify: `percona_obs/release_scope.py`
- Test: `tests/test_release_scope.py`

**Acceptance Criteria:**
- [ ] `release_unit_members` returns the root, then `containers`, then `tarballs`, only those that have a `project.yaml`; `extras`, `tde`, `containers/ubi9` are never members.
- [ ] `collect_release_scope` and `tree_has_server_package` look only at unit members.
- [ ] `bundled_parent("ppg:staging:18:containers") == "ppg:staging:18"`, `None` for a unit root.
- [ ] `release_location` maps ids to directory, release project, id prefix and counter name as in the table in Step 1.

**Verify:** `$VENV/python -m pytest tests/test_release_scope.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_release_scope.py`)

```python
def _unit_tree(tmp_path, monkeypatch):
    root = tmp_path / "root"
    src = root / "ppg/staging/18"
    for sub in ("", "containers", "tarballs", "extras", "extras/containers", "tde"):
        d = src / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.yaml").write_text("title: x\n")
    (src / "containers" / "ubi9").mkdir()
    (src / "containers" / "ubi9" / "project.yaml").write_text("title: x\n")
    for pkg in ("percona-pgvector", "extras/percona-postgresql", "containers/img"):
        (src / pkg / "obs").mkdir(parents=True)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(rs, "REPO_ROOT", root)
    return root, src


def test_release_unit_members_main(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    ids = [i for i, _ in rs.release_unit_members(src, "ppg:staging:18")]
    assert ids == ["ppg:staging:18", "ppg:staging:18:containers", "ppg:staging:18:tarballs"]


def test_release_unit_members_nested_and_bare(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    ids = [i for i, _ in rs.release_unit_members(src / "extras", "ppg:staging:18:extras")]
    assert ids == ["ppg:staging:18:extras", "ppg:staging:18:extras:containers"]
    ids = [i for i, _ in rs.release_unit_members(src / "tde", "ppg:staging:18:tde")]
    assert ids == ["ppg:staging:18:tde"]


def test_unit_packages_and_server_package_are_unit_scoped(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    names = sorted(p.name for _, p in rs.unit_packages(src, "ppg:staging:18"))
    assert names == ["img", "percona-pgvector"]
    # the server package lives in extras only: the main unit has none
    assert rs.tree_has_server_package(src) is False
    assert rs.tree_has_server_package(src / "extras") is True


def test_bundled_parent_and_nested_unit_roots(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    assert rs.bundled_parent("ppg:staging:18:containers") == "ppg:staging:18"
    assert rs.bundled_parent("ppg:staging:18:extras") is None
    assert rs.nested_unit_roots(src, "ppg:staging:18") == [
        "ppg:staging:18:extras",
        "ppg:staging:18:tde",
    ]


@pytest.mark.parametrize(
    "project,release_name,rel,relprj,prefix,counter",
    [
        ("ppg:staging:18", None, "ppg/releases/18", "ppg:releases:18", "", "18"),
        ("ppg:staging:18:extras", None, "ppg/releases/18/extras", "ppg:releases:18:extras", "extras-", "18-extras"),
        ("ppg:staging:common:upgrade:extras", None, "ppg/releases/common/upgrade/extras",
         "ppg:releases:common:upgrade:extras", "upgrade-extras-", "common-upgrade-extras"),
        ("ppg:staging:18", "lts", "ppg/releases/lts", "ppg:releases:lts", "", "lts"),
    ],
)
def test_release_location(tmp_path, monkeypatch, project, release_name, rel, relprj, prefix, counter):
    root, _ = _unit_tree(tmp_path, monkeypatch)
    loc = rs.release_location(project, release_name)
    assert loc.release_dir == root / rel
    assert loc.release_project == relprj
    assert loc.id_prefix == prefix
    assert loc.counter_name == counter
    assert loc.major == project.split(":")[2]
```

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/python -m pytest tests/test_release_scope.py -q -k "unit or bundled or release_location"`
Expected: FAIL with `AttributeError: module 'percona_obs.release_scope' has no attribute 'release_unit_members'`

- [ ] **Step 3: Add the constant** in `percona_obs/common.py`, directly below `SHARED_SOURCE_DIRNAME = "_shared"`:

```python
# Subprojects released together with their parent project: a release unit is
# a staging project plus its direct children with these names.  Every other
# subproject is the root of its own release unit.
BUNDLED_SUBPROJECTS = ("containers", "tarballs")
```

- [ ] **Step 4: Add the unit model** to `percona_obs/release_scope.py`. Extend the `.common` import with `BUNDLED_SUBPROJECTS` and `is_shared_source_dir` (keep `REPO_ROOT` and `find_packages`; `find_projects` goes in Step 5). New code reads the module global `REPO_ROOT`, which is what the tests patch (`rs.REPO_ROOT`). Add after `ReleaseScope`:

```python
def release_unit_members(
    source_path: Path, source_project_id: str
) -> "list[tuple[str, Path]]":
    """[(project_id, path)] of a release unit: its root, then the bundled
    children (``containers``, ``tarballs``) that are OBS projects."""
    members = [(source_project_id, source_path)]
    for name in BUNDLED_SUBPROJECTS:
        child = source_path / name
        if (child / "project.yaml").is_file():
            members.append((f"{source_project_id}:{name}", child))
    return members


def unit_packages(source_path: Path, source_project_id: str):
    """Yield (project_id, package_path) for every package of a release unit."""
    for project_id, path in release_unit_members(source_path, source_project_id):
        yield from find_packages(path, project_id, recursive=False)


def bundled_parent(project_id: str) -> "str | None":
    """The unit root a bundled child belongs to, or None for a unit root."""
    parent, _, name = project_id.rpartition(":")
    return parent if name in BUNDLED_SUBPROJECTS and parent else None


def nested_unit_roots(source_path: Path, source_project_id: str) -> "list[str]":
    """Direct child projects that are release units of their own."""
    return [
        f"{source_project_id}:{child.name}"
        for child in sorted(source_path.iterdir())
        if child.is_dir()
        and child.name not in BUNDLED_SUBPROJECTS
        and not is_shared_source_dir(child)
        and (child / "project.yaml").is_file()
    ]


@dataclass(frozen=True)
class ReleaseLocation:
    product: str
    major: str  # third component of the source id: "18", "common"
    top: str  # release directory name of that component (--release-name)
    unit_path: "tuple[str, ...]"  # components below it: ("extras",), ()
    release_dir: Path
    release_project: str

    @property
    def id_prefix(self) -> str:
        """PG-mode id prefix: "" for a major, "extras-" for 18:extras."""
        return "".join(f"{p}-" for p in self.unit_path)

    @property
    def counter_name(self) -> str:
        """Counter-mode id stem: "common", "common-upgrade-extras"."""
        return "-".join((self.top, *self.unit_path))


def release_location(
    project_id: str, release_name: "str | None" = None
) -> ReleaseLocation:
    """Where a staging unit root is released to (spec § 2)."""
    parts = project_id.split(":")
    product, major, unit_path = parts[0], parts[2], tuple(parts[3:])
    top = release_name or major
    rel = (top, *unit_path)
    return ReleaseLocation(
        product=product,
        major=major,
        top=top,
        unit_path=unit_path,
        release_dir=REPO_ROOT.joinpath(product, "releases", *rel),
        release_project=":".join((product, "releases", *rel)),
    )
```

- [ ] **Step 5: Scope the existing walkers.** In `tree_has_server_package` replace the generator source with `unit_packages(source_path, "")`. In `collect_release_scope`: build `own_ids = {pid for pid, _ in release_unit_members(source_path, source_project_id)}`; iterate `unit_packages(source_path, source_project_id)` for the aggregate loop; iterate `release_unit_members(...)` (all members, as today's loop includes the root) for the path-prefix loop. Remove the now-unused `find_projects` import.

- [ ] **Step 6: Fix existing tests in the same file.** Tests whose fixture puts packages or image projects in a subproject that is not `containers`/`tarballs` (e.g. `test_subproject_aggregates_included_and_self_sources_skipped`, `test_common_parent_collects_paths_from_image_subprojects`) now describe another unit. For each: if the test's point is "subprojects are included", rename the fixture subproject to `containers`; if it uses a deep path such as `extras/containers`, call the function on the `extras` unit root instead. Do not weaken assertions.

- [ ] **Step 7: Run, format, type-check, commit**

```bash
$VENV/python -m pytest tests/test_release_scope.py -q
$VENV/black percona_obs/ && $VENV/pyright
git add percona_obs/common.py percona_obs/release_scope.py tests/test_release_scope.py
git commit -s -m "release: define release units (project + containers/tarballs)"
```

---

### Task 2: Copy scope follows the unit

**Goal:** Both hops copy exactly the unit members.

**Files:**
- Modify: `percona_obs/release_copy.py:44-78` (`collect_release_subprojects`)
- Modify: `percona_obs/cmd_sync.py:2538-2551` (`_mirror_subproject_pairs` → moved)
- Test: `tests/test_sync_release.py`

**Acceptance Criteria:**
- [ ] `collect_release_subprojects` returns pairs/missing for bundled children only.
- [ ] Hop 2 pairs are the bundled children of the release directory; a nested `extras/` mirror (with or without `release.yaml`) is not a pair.

**Verify:** `$VENV/python -m pytest tests/test_sync_release.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_sync_release.py`)

```python
def test_collect_ignores_non_bundled_subprojects(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (src / "extras").mkdir()
    (src / "extras" / "project.yaml").write_text(
        "repositories-inherit: false\n" + _REPO_YAML.format(name="UBI_9")
    )
    monkeypatch.setattr(rc, "resolve_project_path", lambda pid: src)
    pairs, missing = collect_release_subprojects("ppg:staging:17", rel)
    assert [name for name, _ in pairs] == ["containers"]
    assert missing == ["tarballs"]


def test_mirror_pairs_are_bundled_children_only(tmp_path, monkeypatch):
    _, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "extras" / "containers").mkdir(parents=True)
    for d in (rel / "extras", rel / "extras" / "containers"):
        (d / "project.yaml").write_text("build: false\n" + _REPO_YAML.format(name="ubi9"))
    pairs = rc.mirror_subproject_pairs(rel)
    assert [name for name, _ in pairs] == ["containers"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/python -m pytest tests/test_sync_release.py -q -k "non_bundled or bundled_children"`
Expected: first FAILS on `missing == ["extras", "tarballs"]`, second with `AttributeError: ... 'mirror_subproject_pairs'`

- [ ] **Step 3: Implement.** In `release_copy.py` import `BUNDLED_SUBPROJECTS` from `.common` and `release_unit_members` from `.release_scope`; drop the `find_projects` import. Replace the loop header of `collect_release_subprojects`:

```python
    for sub_obs_id, sub_path in release_unit_members(source_path, source_project_id)[
        1:
    ]:
        subproject_name = sub_obs_id[len(source_project_id) + 1 :]
```

(delete the two `continue` guards above it: members are never the root and always have a `project.yaml`). Update the docstring: "source subproject" → "bundled child of the release unit".

Add to `release_copy.py`:

```python
def mirror_subproject_pairs(release_path: Path) -> "list[tuple[str, Path]]":
    """(name, mirror_path) for the in-slice bundled children of a release
    mirror directory (hop 2 copies what the mirror declares, not staging)."""
    pairs: list[tuple[str, Path]] = []
    for name in BUNDLED_SUBPROJECTS:
        sub_path = release_path / name
        if (sub_path / "project.yaml").is_file() and project_in_slice(sub_path):
            pairs.append((name, sub_path))
    return pairs
```

In `cmd_sync.py` delete `_mirror_subproject_pairs`, import `mirror_subproject_pairs` from `.release_copy`, and change the call to `mirror_subproject_pairs(release_path)`. Update the existing `test_mirror_subproject_pairs` to call `rc.mirror_subproject_pairs(rel)`.

- [ ] **Step 4: Run, format, type-check, commit**

```bash
$VENV/python -m pytest tests/test_sync_release.py tests/test_sync_prerelease.py -q
$VENV/black percona_obs/ && $VENV/pyright
git add percona_obs/release_copy.py percona_obs/cmd_sync.py tests/test_sync_release.py
git commit -s -m "release: copy only the members of the release unit"
```

---

### Task 3: Mirrors without internal paths, bounded to the unit

**Goal:** Release mirrors carry no `subproject:` path, are written for unit members only, and a unit's release never touches another unit's mirror directory.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`_rewrite_subproject_paths` ~1627 removed; `_write_release_tree` ~1757; `cmd_project_release` `project_data["repositories"]` ~2812)
- Modify: `percona_obs/release_copy.py` (`apply_mirror_meta`, `release_tree`: drop `branch_rootprj`, `active_projects`, `branch_fallbacks`)
- Modify: `percona_obs/cmd_sync.py` (`cmd_sync_prerelease` ~2977-3016)
- Test: `tests/test_project_release.py`, `tests/test_release_copy.py`, `tests/test_sync_prerelease.py`; delete `tests/test_prerelease_meta.py`

**Acceptance Criteria:**
- [ ] Written mirrors (top and children) contain no `subproject:` path; `project:` paths keep their order.
- [ ] A repository with no `project:` path raises `SystemExit` naming project and repository.
- [ ] `releases/<V>/extras/` (any content) survives `_write_release_tree` for `<V>`; a stale `releases/<V>/containers/ubi9/` and a `releases/<V>/tarballs/` whose source is gone are removed.
- [ ] No `branch_rootprj`/`active_projects`/`branch_fallbacks` argument remains in `release_copy.py` or in the `sync prerelease` code path.
- [ ] Every repository of every staging unit member keeps ≥ 1 external path (script in Step 6 prints nothing).

**Verify:** `$VENV/python -m pytest tests/test_project_release.py tests/test_release_copy.py tests/test_sync_prerelease.py tests/test_sync_release.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests.** In `tests/test_project_release.py` change the import to `from percona_obs.cmd_project import _strip_internal_paths, _write_release_tree`, delete `test_rewrite_keeps_self_references`, and give every fixture repository an external path (in `_staging_tree`, append `{"project": "RedHat:UBI-9", "repository": "standard"}` to the `ubi9` paths and `{"project": "RockyLinux:9", "repository": "devel"}` to the `ssl3` paths; do the same in the other fixtures of this file whose repositories only have `subproject:` paths). Add:

```python
def test_strip_internal_paths_keeps_external_in_order():
    repos = [
        {
            "name": "UBI_9",
            "paths": [
                {"subproject": "ppg:common:deps", "repository": "UBI_9"},
                {"project": "Fedora:EPEL:9", "repository": "standard"},
                {"subproject": "ppg:staging:18", "repository": "UBI_9"},
                {"project": "RedHat:UBI-9", "repository": "standard"},
            ],
            "archs": ["x86_64"],
        }
    ]
    out = _strip_internal_paths(repos, "ppg:staging:18:extras")
    assert out[0]["paths"] == [
        {"project": "Fedora:EPEL:9", "repository": "standard"},
        {"project": "RedHat:UBI-9", "repository": "standard"},
    ]
    assert out[0]["archs"] == ["x86_64"]
    assert "subproject" in repos[0]["paths"][0]  # input not mutated


def test_strip_internal_paths_rejects_pathless_repo():
    repos = [{"name": "ssl3", "paths": [{"subproject": "ppg:staging:18", "repository": "x"}]}]
    with pytest.raises(SystemExit, match="ppg:staging:18:tarballs.*ssl3"):
        _strip_internal_paths(repos, "ppg:staging:18:tarballs")


def test_write_release_tree_leaves_nested_unit_mirror_alone(tmp_path, monkeypatch):
    src = _staging_tree(tmp_path)
    (src / "extras" / "containers").mkdir(parents=True)
    (src / "extras" / "project.yaml").write_text("repositories: []\n")
    (src / "extras" / "containers" / "project.yaml").write_text("repositories: []\n")
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    rel = tmp_path / "root/ppg/releases/17"
    (rel / "extras" / "containers").mkdir(parents=True)
    (rel / "extras" / "project.yaml").write_text("keep: me\n")
    (rel / "extras" / "containers" / "project.yaml").write_text("keep: me\n")
    (rel / "containers" / "ubi9").mkdir(parents=True)
    (rel / "containers" / "ubi9" / "project.yaml").write_text("stale: true\n")
    _write_release_tree(
        rel, {"repositories": []}, src, "ppg:staging:17", "ppg:releases:17", "ppg", "17"
    )
    assert (rel / "extras" / "project.yaml").read_text() == "keep: me\n"
    assert (rel / "extras" / "containers" / "project.yaml").read_text() == "keep: me\n"
    assert not (rel / "containers" / "ubi9").exists()
    assert (rel / "containers" / "project.yaml").is_file()
    for name in ("containers", "tarballs"):
        data = yaml.safe_load((rel / name / "project.yaml").read_text())
        for repo in data["repositories"]:
            assert all("subproject" not in p for p in repo["paths"])


def test_write_release_tree_removes_bundled_mirror_whose_source_is_gone(tmp_path, monkeypatch):
    src = _staging_tree(tmp_path)
    import shutil

    shutil.rmtree(src / "tarballs")
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    rel = tmp_path / "root/ppg/releases/17"
    (rel / "tarballs").mkdir(parents=True)
    (rel / "tarballs" / "project.yaml").write_text("stale: true\n")
    _write_release_tree(
        rel, {"repositories": []}, src, "ppg:staging:17", "ppg:releases:17", "ppg", "17"
    )
    assert not (rel / "tarballs").exists()
```

If the existing `_write_release_tree` tests patch more than `_REPO_DIR` (check `test_write_release_tree_creates_all_mirrors_and_deletes_stale`, line ~79), copy their monkeypatch lines into the two new tests.

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/python -m pytest tests/test_project_release.py -q -k "strip_internal or nested_unit_mirror or source_is_gone"`
Expected: `ImportError: cannot import name '_strip_internal_paths'`

- [ ] **Step 3: Replace `_rewrite_subproject_paths`** in `percona_obs/cmd_project.py` with:

```python
def _strip_internal_paths(repos: list[dict], project_id: str) -> list[dict]:
    """Drop ``subproject:`` paths from the repositories of a release mirror.

    Release projects never build, so paths into other projects of the same
    root are unused; without them a release project needs no other release
    project to exist.  ``project:`` paths (base distros) stay, in order: OBS
    takes the repository's base configuration and publish type from them.
    """
    result = []
    for repo in repos:
        kept = [p for p in repo.get("paths", []) if "subproject" not in p]
        if not kept:
            raise SystemExit(
                f"error: {project_id}: repository '{repo.get('name')}' has only "
                "subproject: paths; a release mirror needs at least one "
                "project: path (the base distribution)"
            )
        result.append({**repo, "paths": kept})
    return result
```

- [ ] **Step 4: Rework `_write_release_tree`.** Import `BUNDLED_SUBPROJECTS` from `.common` and `release_unit_members` from `.release_scope`. Replace the loop header and its two `continue` guards with:

```python
    for sub_obs_id, sub_path in release_unit_members(source_path, source_project_id)[
        1:
    ]:
```

Replace the `rewritten_repos = _rewrite_subproject_paths(...)` call with `rewritten_repos = _strip_internal_paths(source_sub_config.get("repositories", []), sub_obs_id)`. Replace the stale computation with:

```python
    # Stale mirrors live under the bundled children only (a removed
    # tarballs/, the pre-restructure containers/ubi9).  Every other
    # directory below release_dir is another release unit's mirror.
    stale = [
        p.parent
        for name in BUNDLED_SUBPROJECTS
        if (release_dir / name).is_dir()
        for p in sorted((release_dir / name).rglob("project.yaml"))
        if p.parent not in expected_dirs
    ]
```

Update the docstring ("one nested mirror dir per bundled child of the unit … never touches another unit's directory"). In `cmd_project_release`, change `"repositories": source_repos,` to `"repositories": _strip_internal_paths(source_repos, args.project),`. Remove `_is_relative_to` if nothing else uses it (`grep -n _is_relative_to percona_obs/`).

- [ ] **Step 5: Remove the hop-1 path redirection.** In `release_copy.py` delete the parameters `branch_rootprj`, `active_projects`, `branch_fallbacks` from `apply_mirror_meta` and `release_tree`, the arguments forwarded to `_apply_project_config`, and the docstring paragraph about redirection (keep the two-pass call; reword "Two passes when OBS stripped paths" to "…when OBS stripped a path to a project it does not know"). In `cmd_sync_prerelease` delete the `prerelease_tree` set, its comment, and the three keyword arguments in both the `apply_mirror_meta` and the `release_tree` call; replace the comment `# Mirror paths are rewritten to the PR root through ${OBS_ROOTPRJ}.` with `# Env for rendering the mirrors on the PR root.`. Delete `tests/test_prerelease_meta.py`. In `tests/test_release_copy.py` (~lines 180-240) and `tests/test_sync_prerelease.py` (~lines 300-330), drop the `branch_rootprj`/`active_projects` arguments and the assertions on them; keep the rest of each test.

- [ ] **Step 6: Check the real tree.** Run from the worktree root; it must print nothing:

```bash
$VENV/python - <<'EOF'
from pathlib import Path
from percona_obs.common import REPO_ROOT, _load_project_config_with_inheritance
from percona_obs.project_config import RepositoryFilter
from percona_obs.release_scope import release_unit_members, nested_unit_roots

def walk(path, pid):
    for mid, mpath in release_unit_members(path, pid):
        cfg = _load_project_config_with_inheritance(mpath, repo_filter=RepositoryFilter.EMPTY)
        for repo in cfg.get("repositories", []):
            if not [p for p in repo.get("paths", []) if "subproject" not in p]:
                print("NO EXTERNAL PATH:", mid, repo.get("name"))
    for child in nested_unit_roots(path, pid):
        walk(path / child.rsplit(":", 1)[1], child)

staging = REPO_ROOT / "ppg" / "staging"
for d in sorted(staging.iterdir()):
    if d.is_dir() and (d / "project.yaml").is_file():
        walk(d, f"ppg:staging:{d.name}")
EOF
```

If it prints a line, stop and report it to the user: that repository needs a base-distro `project:` path in staging before its unit can be released; do not weaken `_strip_internal_paths`.

- [ ] **Step 7: Run, format, type-check, commit**

```bash
$VENV/python -m pytest tests/test_project_release.py tests/test_release_copy.py tests/test_sync_prerelease.py tests/test_sync_release.py -q
$VENV/black percona_obs/ && $VENV/pyright
git add -A percona_obs tests
git commit -s -m "release: mirrors without internal repository paths, bounded to the unit"
```

---

### Task 4: `project release` for nested units

**Goal:** `project release ppg:staging:18:extras` writes `root/ppg/releases/18/extras/{release.yaml,CHANGELOG.md,project.yaml,containers/project.yaml}` with tag `ppg/extras-<minor>-N`; a main release no longer reports extras packages.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`_derive_release_id` ~2319, `_collect_release_obs_data` ~2494, `cmd_project_release` ~2626)
- Modify: `percona_obs/cli.py` (help text of `project release` `project` and `--release-name`)
- Test: `tests/test_project_release.py`

**Acceptance Criteria:**
- [ ] Ids: main unchanged; nested PG mode `extras-18.6-N` with `N = max(own N of that minor) + 1`; first nested release with no own record continues the parent's count; counter mode uses `ReleaseLocation.counter_name`.
- [ ] A bundled child is refused naming its unit root; a unit with no package is refused naming the units below it.
- [ ] "First release" means "no `release.yaml` in the release directory", not "no directory".
- [ ] The changelog baseline is read from the release project whenever it exists on OBS, and only from the unit's own subprojects.

**Verify:** `$VENV/python -m pytest tests/test_project_release.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project_release.py`)

```python
def test_derive_release_id_nested_counts_own_tags():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql": ("UBI_9", "x86_64")},
        existing_releases=["ppg/extras-18.6-6", "ppg/extras-18.6-7", "ppg/extras-18.5-2"],
        release_name="18-extras",
        versrel_lookup=lambda repo, arch, pkg: "18.6-1.1",
        major="18",
        prefix="extras-",
        parent_releases=["ppg/18.6-1", "ppg/18.6-2"],
    )
    assert rid == "extras-18.6-8"


def test_derive_release_id_nested_first_release_continues_parent():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql": ("UBI_9", "x86_64")},
        existing_releases=[],
        release_name="18-extras",
        versrel_lookup=lambda repo, arch, pkg: "18.6-1.1",
        major="18",
        prefix="extras-",
        parent_releases=["ppg/18.5-1", "ppg/18.6-1", "ppg/18.6-2"],
    )
    assert rid == "extras-18.6-3"


def test_derive_release_id_nested_new_minor_starts_at_one():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql": ("UBI_9", "x86_64")},
        existing_releases=["ppg/extras-18.6-6"],
        release_name="18-extras",
        versrel_lookup=lambda repo, arch, pkg: "18.7-1.1",
        major="18",
        prefix="extras-",
        parent_releases=["ppg/18.7-1"],
    )
    assert rid == "extras-18.7-1"


def test_derive_release_id_nested_without_parent_record():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql": ("UBI_9", "x86_64")},
        existing_releases=[],
        release_name="16-tde",
        versrel_lookup=lambda repo, arch, pkg: "16.15-1.1",
        major="16",
        prefix="tde-",
        parent_releases=None,
    )
    assert rid == "tde-16.15-1"


def test_derive_release_id_counter_mode_uses_counter_name():
    rid = cmd_project._derive_release_id(
        pkg_archs={},
        existing_releases=["ppg/common-upgrade-1"],
        release_name="common-upgrade",
        versrel_lookup=lambda repo, arch, pkg: None,
        counter_mode=True,
        prefix="upgrade-",
    )
    assert rid == "common-upgrade-2"


def _release_args(project):
    return argparse.Namespace(
        project=project, rootprj="R", apiurl="http://obs", release_name=None,
        release_id=None, env_overrides=None, source_commit=None,
        also_profiles=None, no_cve_scan=True,
    )


def test_project_release_refuses_bundled_child(tmp_path, monkeypatch):
    _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "REPO_ROOT", tmp_path / "root")
    monkeypatch.setattr(
        cmd_project, "resolve_project_path",
        lambda pid: tmp_path / "root" / Path(*pid.split(":")),
    )
    with pytest.raises(SystemExit, match="part of release unit ppg:staging:17"):
        cmd_project.cmd_project_release(_release_args("ppg:staging:17:containers"))


def test_project_release_refuses_empty_unit(tmp_path, monkeypatch):
    root = tmp_path / "root"
    common_dir = root / "ppg/staging/common"
    (common_dir / "tools" / "percona-haproxy" / "obs").mkdir(parents=True)
    (common_dir / "project.yaml").write_text("title: c\n")
    (common_dir / "tools" / "project.yaml").write_text("title: t\n")
    monkeypatch.setattr(cmd_project, "REPO_ROOT", root)
    monkeypatch.setattr(
        cmd_project, "resolve_project_path", lambda pid: root / Path(*pid.split(":"))
    )
    with pytest.raises(SystemExit, match="nothing to release.*ppg:staging:common:tools"):
        cmd_project.cmd_project_release(_release_args("ppg:staging:common"))
```

Also update the two existing `_collect_release_obs_data` tests (~1272, ~1326): remove the `is_first_release=`/`prev_release_id=` keyword arguments from their calls.

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/python -m pytest tests/test_project_release.py -q -k "nested or counter_name or refuses"`
Expected: `TypeError: _derive_release_id() got an unexpected keyword argument 'prefix'`; the two `refuses` tests fail without the expected message.

- [ ] **Step 3: `_derive_release_id`.** Add keyword parameters `prefix: str = ""` and `parent_releases: "list[str] | None" = None`. Replace the last three lines of the function with:

```python
    ver_parts = versrel.split("-")[0].split(".")
    major_minor = ".".join(ver_parts[:2])
    needle = f"/{prefix}{major_minor}-"
    own = [
        int(t.rsplit("-", 1)[1])
        for t in existing_releases
        if needle in t and t.rsplit("-", 1)[1].isdigit()
    ]
    if own:
        n = max(own) + 1
    elif not existing_releases and parent_releases is not None:
        # First release of a unit that shipped bundled with its parent so
        # far: continue the parent's numbering, so no image tag is reused.
        n = sum(1 for t in parent_releases if f"/{major_minor}-" in t) + 1
    else:
        n = 1
    return f"{prefix}{major_minor}-{n}"
```

Extend the docstring with the three numbering cases. The counter-mode branch stays `f"{release_name}-{len(existing_releases) + 1}"` (callers pass `counter_name`).

- [ ] **Step 4: `_collect_release_obs_data`.** Remove the parameters `is_first_release` and `prev_release_id`. Change `if not is_first_release and _obs_project_exists(apiurl, release_obs_project):` to `if _obs_project_exists(apiurl, release_obs_project):`. Replace the `if not is_first_release and prev_release_id:` block header and loop with:

```python
    if release_versions is not None:
        # Diff against the unit's release subprojects that exist on OBS —
        # this is what makes the ubi9 old-layout → new-layout migration diff
        # correctly instead of dumping every image as "add".  Subprojects
        # outside the bundled children belong to other release units.
        prefix_len = len(release_obs_project) + 1
        for rel_sub in sorted(_fetch_obs_subproject_names(apiurl, release_obs_project)):
            if rel_sub[prefix_len:].split(":", 1)[0] not in BUNDLED_SUBPROJECTS:
                continue
```

(the `_merge_container_pkgs` call inside the loop is unchanged).

- [ ] **Step 5: `cmd_project_release`.** Import `bundled_parent`, `nested_unit_roots`, `release_location`, `release_unit_members`, `unit_packages` from `.release_scope` and `release_tags` from `.release_record`. Replace the head of the function (from `product = …` through `is_first_release = …`) with:

```python
    parts = args.project.split(":")
    if len(parts) < 3 or parts[1] != "staging":
        raise SystemExit(
            "error: project release requires a staging-tier source "
            f"(<product>:staging:<version>[:<unit>]), got: {args.project}"
        )
    unit_root = bundled_parent(args.project)
    if unit_root and len(parts) > 3:
        raise SystemExit(
            f"error: {args.project} is part of release unit {unit_root}; "
            f"release that instead"
        )

    source_path = resolve_project_path(args.project)
    if not source_path.is_dir():
        raise SystemExit(
            f"error: source project directory does not exist: {source_path}"
        )
    if not any(unit_packages(source_path, args.project)):
        below = ", ".join(nested_unit_roots(source_path, args.project)) or "none"
        raise SystemExit(
            f"error: {args.project} has nothing to release (no packages in the "
            f"project or its containers/tarballs); release units below it: {below}"
        )

    if not args.rootprj:
        raise SystemExit(
            "error: rootprj is required for 'project release': "
            "supply -R/--rootprj or -P/--profile"
        )
    osc.conf.get_config(override_apiurl=args.apiurl)
    apiurl: str = osc.conf.config["apiurl"]

    loc = release_location(args.project, args.release_name)
    product, major = loc.product, loc.major
    release_name = loc.counter_name
    release_dir = loc.release_dir
    release_project = loc.release_project
    source_obs_project = f"{args.rootprj}:{args.project}"

    # A nested unit's directory may already exist as a mirror written by a
    # bundled release: only the record makes it a release of its own.
    is_first_release = not (release_dir / "release.yaml").is_file()
    parent_releases: "list[str] | None" = None
    if loc.unit_path:
        parent_record = REPO_ROOT / product / "releases" / loc.top / "release.yaml"
        if parent_record.is_file():
            parent_releases = release_tags(load_yaml(parent_record))
```

In `_derive()`, add `prefix=loc.id_prefix, parent_releases=parent_releases,` to the `_derive_release_id` call (`release_name` and `major=major` are already passed and now carry `counter_name` and the PG major). Replace the `find_projects` classification loop with:

```python
    for sub_obs_id, sub_path in release_unit_members(source_path, args.project)[1:]:
        subproject_name = sub_obs_id[len(args.project) + 1 :]
        if has_container_images(sub_path):
            container_subs.append(subproject_name)
        else:
            noncontainer_subs.append(subproject_name)
```

Remove `is_first_release=` and `prev_release_id=` from the `_collect_release_obs_data` call. In the "Write files" branches, `release_dir.mkdir(parents=True, exist_ok=True)` already tolerates an existing mirror directory; leave both branches otherwise unchanged. The `project_data` title uses `release_name`: change it to `f"{product} releases {':'.join((loc.top, *loc.unit_path))}"`, and pass that same string as the `release_name` argument of both `_write_release_tree` calls (it is only used in child titles).

Run `grep -n "find_projects" percona_obs/cmd_project.py` and remove the import if this was its last use in the file.

- [ ] **Step 6: CLI help.** In `percona_obs/cli.py`, in the `project release` parser, change the `project` help to `"Staging release unit to release (e.g. ppg:staging:18, ppg:staging:18:extras)."` and append to the `--release-name` help: `" For a nested unit it renames the top directory only (releases/<name>/<unit>)."`.

- [ ] **Step 7: Run, format, type-check, commit**

```bash
$VENV/python -m pytest tests/test_project_release.py -q
$VENV/black percona_obs/ && $VENV/pyright
git add percona_obs/cmd_project.py percona_obs/cli.py tests/test_project_release.py
git commit -s -m "project release: nested release units with their own record and id"
```

---

### Task 5: `PPG_RELEASE` follows the unit

**Goal:** Images inside a nested per-major unit take their tag counter from the unit's own record; the pre-release record check watches the right files.

**Files:**
- Modify: `percona_obs/common.py` (`compute_ppg_release` ~324, `inject_computed_macros` ~373-420)
- Modify: `percona_obs/cmd_sync.py` (`_scope_local_paths` ~2769-2778)
- Test: `tests/test_computed_macros.py`, `tests/test_sync_prerelease.py`

**Acceptance Criteria:**
- [ ] `staging/18/extras/containers/<pkg>` with `releases/18/extras/release.yaml` holding `ppg/extras-18.4-6` renders `PPG_RELEASE=7`; with no tag for that version, `1`.
- [ ] Same project with no nested record renders the main-record value (today's behaviour).
- [ ] `staging/18/containers/<pkg>`, `staging/18/<pkg>` and `staging/common/upgrade/containers/<pkg>` are unchanged.
- [ ] `_scope_local_paths` for a nested unit includes the unit's `release.yaml` and the main one.

**Verify:** `$VENV/python -m pytest tests/test_computed_macros.py tests/test_sync_prerelease.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_computed_macros.py`)

```python
def _nested_tree(tmp_path: Path, nested_record: "str | None") -> Path:
    root = _tree(tmp_path)
    extras = root / "ppg" / "staging" / "18" / "extras"
    (extras / "containers" / "img").mkdir(parents=True)
    (root / "ppg" / "staging" / "18" / "project.yaml").write_text("title: m\n")
    (extras / "project.yaml").write_text("title: e\n")
    (extras / "containers" / "project.yaml").write_text("title: c\n")
    if nested_record is not None:
        rel = root / "ppg" / "releases" / "18" / "extras"
        rel.mkdir(parents=True)
        (rel / "release.yaml").write_text(nested_record)
    return root


def _ppg_release(root: Path, rel_path: str) -> str:
    macros = {"PG_MAJOR_VERSION": "18", "PG_VERSION": "18.4"}
    out = inject_computed_macros(
        macros, root / rel_path, common._read_worktree_file, repo_root=root
    )
    return out["PPG_RELEASE"]


def test_ppg_release_nested_unit_uses_own_record(tmp_path):
    root = _nested_tree(
        tmp_path,
        "project: ppg:staging:18:extras\nreleases:\n- ppg/extras-18.4-6\n- ppg/extras-18.3-9\n",
    )
    assert _ppg_release(root, "ppg/staging/18/extras/containers/img") == "7"
    assert _ppg_release(root, "ppg/staging/18/extras/containers") == "7"
    assert _ppg_release(root, "ppg/staging/18/extras") == "7"


def test_ppg_release_nested_unit_new_version_is_one(tmp_path):
    root = _nested_tree(
        tmp_path, "project: ppg:staging:18:extras\nreleases:\n- ppg/extras-18.3-9\n"
    )
    assert _ppg_release(root, "ppg/staging/18/extras/containers/img") == "1"


def test_ppg_release_nested_unit_without_record_uses_main(tmp_path):
    root = _nested_tree(tmp_path, None)
    # main record: ppg/18.4-1 → next is 2
    assert _ppg_release(root, "ppg/staging/18/extras/containers/img") == "2"


def test_ppg_release_main_and_common_projects_unchanged(tmp_path):
    root = _nested_tree(
        tmp_path, "project: ppg:staging:18:extras\nreleases:\n- ppg/extras-18.4-6\n"
    )
    (root / "ppg/staging/18/containers/img").mkdir(parents=True)
    (root / "ppg/staging/18/containers/project.yaml").write_text("title: c\n")
    up = root / "ppg/staging/common/upgrade/containers/img"
    up.mkdir(parents=True)
    for d in ("ppg/staging/common", "ppg/staging/common/upgrade", "ppg/staging/common/upgrade/containers"):
        (root / d / "project.yaml").write_text("title: x\n")
    assert _ppg_release(root, "ppg/staging/18/containers/img") == "2"
    assert _ppg_release(root, "ppg/staging/18") == "2"
    assert _ppg_release(root, "ppg/staging/common/upgrade/containers/img") == "2"
```

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/python -m pytest tests/test_computed_macros.py -q -k ppg_release`
Expected: `test_ppg_release_nested_unit_uses_own_record` and `…new_version_is_one` FAIL (`'2' == '7'`, `'2' == '1'`); the other two pass.

- [ ] **Step 3: Implement in `percona_obs/common.py`.** Give `compute_ppg_release` a keyword parameter and a max-based branch; the main (prefix-less) behaviour must stay byte-for-byte:

```python
def compute_ppg_release(
    product: str,
    pg_version: str,
    release_yaml_text: "str | None",
    unit_prefix: str = "",
) -> str:
```

Extend the docstring: "With *unit_prefix* (a nested release unit, e.g. ``extras-``) the tags are ``<product>/<unit_prefix><pg_version>-<n>`` and the counter is one more than the highest ``n``: a nested unit's first tag continues its parent's numbering, so its tags do not start at 1." Replace the last two lines of the function with:

```python
    prefix = f"{product}/{unit_prefix}{pg_version}-"
    if not unit_prefix:
        return str(sum(1 for t in tags if t.startswith(prefix)) + 1)
    numbers = [
        int(t[len(prefix) :]) for t in tags if t.startswith(prefix) and t[len(prefix) :].isdigit()
    ]
    return str(max(numbers, default=0) + 1)
```

Add above `inject_computed_macros`:

```python
def _nested_unit_record(
    root: Path,
    parts: "tuple[str, ...]",
    major: str,
    read_file: "Callable[[Path], str | None]",
) -> "tuple[Path, str] | None":
    """(release.yaml path, tag prefix) of the nested release unit that holds
    the project or package at *parts* (``<product>/<tier>/<major>/…``), or
    None when it belongs to the major's own unit or is not under a major.

    The unit is the leading run of path components below the major that are
    projects and not bundled children: ``18/extras/containers/img`` →
    ``extras``.
    """
    if len(parts) < 4 or parts[2] != major:
        return None
    unit: list[str] = []
    for seg in parts[3:]:
        if seg in BUNDLED_SUBPROJECTS:
            break
        if read_file(root.joinpath(*parts[:3], *unit, seg, "project.yaml")) is None:
            break
        unit.append(seg)
    if not unit:
        return None
    return (
        root.joinpath(parts[0], "releases", major, *unit, "release.yaml"),
        "".join(f"{u}-" for u in unit),
    )
```

In `inject_computed_macros`, replace the body of `if major:` with:

```python
            release_file = root / product / "releases" / major / "release.yaml"
            text = read_file(release_file)
            unit_prefix = ""
            nested = _nested_unit_record(root, parts, major, read_file)
            if nested is not None:
                # Until the unit has a record of its own it is released with
                # its parent and shares the parent's counter.
                nested_text = read_file(nested[0])
                if nested_text is not None:
                    text, unit_prefix = nested_text, nested[1]
            macros = {
                **macros,
                "PPG_RELEASE": compute_ppg_release(
                    product, pg_version, text, unit_prefix
                ),
            }
```

Add a sentence to the `inject_computed_macros` docstring: "Inside a nested release unit of a PG major the counter comes from that unit's record (``releases/<major>/<unit>/release.yaml``) once it exists."

- [ ] **Step 4: Record-check paths.** In `_scope_local_paths` (`cmd_sync.py`), replace the `if source_path.is_relative_to(common.REPO_ROOT):` block with:

```python
    if source_path.is_relative_to(common.REPO_ROOT):
        rel = source_path.relative_to(common.REPO_ROOT).parts
        # <product>/<tier>/<top>/<unit…>: the unit's own record and, for a
        # nested unit, the parent's (it supplies the counter until the unit
        # has a record of its own).
        if len(rel) >= 3:
            releases = common.REPO_ROOT / rel[0] / "releases"
            _add(releases.joinpath(*rel[2:], "release.yaml"))
            _add(releases / rel[2] / "release.yaml")
```

Update the comment above it: "PPG_RELEASE is computed from the release record of the unit (common.inject_computed_macros) …". Add to `tests/test_sync_prerelease.py`:

```python
def test_scope_local_paths_nested_unit_watches_both_records(tmp_path, monkeypatch):
    import percona_obs.common as common

    root = tmp_path / "root"
    src = root / "ppg/staging/18/extras"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: e\n")
    monkeypatch.setattr(common, "REPO_ROOT", root)
    paths = cmd_sync._scope_local_paths(src, [], {}, "R")
    assert root / "ppg/releases/18/extras/release.yaml" in paths
    assert root / "ppg/releases/18/release.yaml" in paths
```

(If that file imports the module under another name, use it; if `_macros_chain_files` or `_chain` need a `macros.yaml` at the fixture root, create an empty `root/macros.yaml`.)

- [ ] **Step 5: Run, format, type-check, commit**

```bash
$VENV/python -m pytest tests/test_computed_macros.py tests/test_sync_prerelease.py tests/test_macros_changed_since.py -q
$VENV/black percona_obs/ && $VENV/pyright
git add percona_obs/common.py percona_obs/cmd_sync.py tests/test_computed_macros.py tests/test_sync_prerelease.py
git commit -s -m "macros: PPG_RELEASE follows the release unit"
```

---

### Task 6: Prune after copy

**Goal:** `sync release` deletes target packages the source no longer has and target subprojects with no mirror; `--dry-run` lists them.

**Files:**
- Modify: `percona_obs/release_copy.py` (replace `warn_orphans`; `release_tree`)
- Modify: `percona_obs/cmd_sync.py` (`cmd_sync_release`: both `release_tree` calls, hop-2 dry-run)
- Test: `tests/test_release_copy.py`, `tests/test_sync_release.py`

**Acceptance Criteria:**
- [ ] Stale package = in target OBS project, not in source OBS project, for the top project and each pair.
- [ ] Stale subproject = target OBS subproject with no `project.yaml` at the same relative path under the top mirror directory; children of a stale subproject are not deleted separately.
- [ ] Empty source listing with packages in the target → `SystemExit`, nothing deleted.
- [ ] `verify_timeout == 0` → no prune, one warning line.
- [ ] Prune runs after verification and before publishing is restored; only when `prune=True` (`sync release`), never in `sync prerelease`.
- [ ] Hop-2 `--dry-run` prints the deletions and deletes nothing.

**Verify:** `$VENV/python -m pytest tests/test_release_copy.py tests/test_sync_release.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_release_copy.py`)

```python
def _stub_listing(monkeypatch, packages, subprojects):
    deleted = []
    monkeypatch.setattr(
        rc, "_fetch_obs_package_names_or_fail", lambda apiurl, prj: set(packages.get(prj, ()))
    )
    monkeypatch.setattr(
        rc, "_fetch_obs_package_names", lambda apiurl, prj: set(packages.get(prj, ()))
    )
    monkeypatch.setattr(
        rc, "_fetch_obs_subproject_names", lambda apiurl, prj: set(subprojects)
    )
    monkeypatch.setattr(
        rc, "_delete_obs_package",
        lambda apiurl, prj, pkg, dry_run: deleted.append(("pkg", prj, pkg, dry_run)),
    )
    monkeypatch.setattr(
        rc, "_delete_obs_project",
        lambda apiurl, prj, dry_run, recursive=False: deleted.append(
            ("prj", prj, dry_run, recursive)
        ),
    )
    return deleted


def _mirror(tmp_path, *subs):
    top = tmp_path / "releases/18"
    for sub in ("", *subs):
        (top / sub).mkdir(parents=True, exist_ok=True)
        (top / sub / "project.yaml").write_text("build: false\n")
    return top


def test_prune_deletes_stale_packages_per_member(tmp_path, monkeypatch):
    top = _mirror(tmp_path, "containers")
    deleted = _stub_listing(
        monkeypatch,
        {"S": {"a", "b"}, "T": {"a", "b", "gone"},
         "S:containers": {"img"}, "T:containers": {"img", "old-img"}},
        {"T:containers"},
    )
    rc.prune_release_tree("http://obs", "S", "T", [("containers", top / "containers")], top)
    assert deleted == [
        ("pkg", "T", "gone", False),
        ("pkg", "T:containers", "old-img", False),
    ]


def test_stale_subprojects_keeps_projects_with_a_mirror(tmp_path, monkeypatch):
    # extras is another unit: it has a mirror dir (no release.yaml yet) and stays.
    top = _mirror(tmp_path, "containers", "extras", "extras/containers")
    deleted = _stub_listing(
        monkeypatch,
        {"S": {"a"}, "T": {"a"}, "S:containers": {"i"}, "T:containers": {"i"}},
        {"T:containers", "T:extras", "T:extras:containers", "T:old", "T:old:ubi9"},
    )
    rc.prune_release_tree("http://obs", "S", "T", [("containers", top / "containers")], top)
    assert deleted == [("prj", "T:old", False, True)]


def test_prune_refuses_empty_source_with_packages_in_target(tmp_path, monkeypatch):
    top = _mirror(tmp_path)
    deleted = _stub_listing(monkeypatch, {"S": set(), "T": {"a", "b"}}, set())
    with pytest.raises(SystemExit, match="S lists no packages"):
        rc.prune_release_tree("http://obs", "S", "T", [], top)
    assert deleted == []


def test_prune_allows_packageless_root(tmp_path, monkeypatch):
    top = _mirror(tmp_path, "containers")
    deleted = _stub_listing(
        monkeypatch,
        {"S": set(), "T": set(), "S:containers": {"i"}, "T:containers": {"i", "x"}},
        {"T:containers"},
    )
    rc.prune_release_tree("http://obs", "S", "T", [("containers", top / "containers")], top)
    assert deleted == [("pkg", "T:containers", "x", False)]


def test_prune_dry_run_reports_without_deleting(tmp_path, monkeypatch):
    top = _mirror(tmp_path)
    deleted = _stub_listing(monkeypatch, {"S": {"a"}, "T": {"a", "gone"}}, {"T:old"})
    rc.prune_release_tree("http://obs", "S", "T", [], top, dry_run=True)
    assert deleted == [("pkg", "T", "gone", True), ("prj", "T:old", True, True)]


def test_release_tree_prunes_after_verify_and_before_publish(tmp_path, monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, **k: None)
    monkeypatch.setattr(
        rc, "verify_release_landed", lambda *a, **k: calls.append(("verify", a[2]))
    )
    monkeypatch.setattr(
        rc, "prune_release_tree", lambda *a, **k: calls.append(("prune", a[2]))
    )
    rc.release_tree(
        "http://obs", "S", "T", [], "R", {}, top_mirror_path=tmp_path, prune=True
    )
    kinds = [c[0] for c in calls]
    assert kinds.index("verify") < kinds.index("prune")
    assert kinds.index("prune") < len(kinds) - 1 - kinds[::-1].index("publish")


def test_release_tree_skips_prune_without_verify(tmp_path, monkeypatch, capsys):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, **k: None)
    monkeypatch.setattr(
        rc, "prune_release_tree", lambda *a, **k: calls.append(("prune",))
    )
    rc.release_tree(
        "http://obs", "S", "T", [], "R", {}, top_mirror_path=tmp_path,
        prune=True, verify_timeout=0,
    )
    assert ("prune",) not in calls
    assert "not pruned" in capsys.readouterr().out


def test_release_tree_does_not_prune_by_default(tmp_path, monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, **k: None)
    monkeypatch.setattr(rc, "verify_release_landed", lambda *a, **k: None)
    monkeypatch.setattr(
        rc, "prune_release_tree", lambda *a, **k: calls.append(("prune",))
    )
    rc.release_tree("http://obs", "S", "T", [], "R", {}, top_mirror_path=tmp_path)
    assert ("prune",) not in calls
```

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/python -m pytest tests/test_release_copy.py -q -k "prune or stale_subprojects"`
Expected: `AttributeError: module 'percona_obs.release_copy' has no attribute 'prune_release_tree'` / `_fetch_obs_package_names_or_fail`

- [ ] **Step 3: Implement in `release_copy.py`.** Add to the `.obs_api` import: `_delete_obs_package`, `_delete_obs_project`, `_fetch_obs_package_names`, `_fetch_obs_package_names_or_fail`. Delete `warn_orphans` and add:

```python
def _stale_packages(apiurl: str, source: str, target: str) -> "list[str]":
    """Packages of *target* that *source* no longer has."""
    in_source = _fetch_obs_package_names_or_fail(apiurl, source)
    in_target = _fetch_obs_package_names(apiurl, target)
    if not in_source and in_target:
        raise SystemExit(
            f"error: {source} lists no packages but {target} has "
            f"{len(in_target)}; refusing to prune (wrong or deleted source?)"
        )
    return sorted(in_target - in_source)


def _stale_subprojects(
    apiurl: str, target_obs_project: str, top_mirror_path: Path
) -> "list[str]":
    """Target subprojects with no mirror project.yaml in the local release
    tree, outermost only (a recursive delete takes their children along).

    Another release unit below this one keeps its mirror directory, so it is
    never stale here.
    """
    prefix_len = len(target_obs_project) + 1
    stale: list[str] = []
    for obs_sub in sorted(_fetch_obs_subproject_names(apiurl, target_obs_project)):
        rel = obs_sub[prefix_len:].split(":")
        if (top_mirror_path.joinpath(*rel) / "project.yaml").is_file():
            continue
        if any(obs_sub.startswith(s + ":") for s in stale):
            continue
        stale.append(obs_sub)
    return stale


def prune_release_tree(
    apiurl: str,
    source_obs_project: str,
    target_obs_project: str,
    pairs: "list[tuple[str, Path]]",
    top_mirror_path: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Delete what left the release: target packages the source no longer
    has (top project and every pair) and target subprojects without a
    mirror.  All listings are read before the first delete, so a refused
    listing deletes nothing."""
    members = [(source_obs_project, target_obs_project)] + [
        (f"{source_obs_project}:{name}", f"{target_obs_project}:{name}")
        for name, _ in pairs
    ]
    stale_pkgs = [
        (target, pkg)
        for source, target in members
        for pkg in _stale_packages(apiurl, source, target)
    ]
    stale_prjs = _stale_subprojects(apiurl, target_obs_project, top_mirror_path)
    for target, pkg in stale_pkgs:
        _delete_obs_package(apiurl, target, pkg, dry_run)
    for obs_sub in stale_prjs:
        _delete_obs_project(apiurl, obs_sub, dry_run, recursive=True)
```

In `release_tree`: add keyword parameter `prune: bool = False`; document it ("With *prune*, packages and subprojects that left the release are deleted once every copy is verified and before publishing resumes; without verification nothing is deleted."). Replace the tail of the function (from `if verify_timeout > 0:` to the end) with:

```python
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
        if prune:
            prune_release_tree(
                apiurl, source_obs_project, target_obs_project, pairs, top_mirror_path
            )
    elif prune:
        print(
            "warning: copy not verified (--verify-timeout 0): "
            f"{target_obs_project} not pruned",
            flush=True,
        )
    for obs_project, flags in held:
        set_project_publish(apiurl, obs_project, flags)
```

Remove the unused `rootprj`-only use if `warn_orphans` was its last consumer in this function (keep the parameter: `apply_mirror_meta` still needs it).

- [ ] **Step 4: Wire `cmd_sync_release`.** Add `prune=True,` to both `release_tree(...)` calls in `cmd_sync_release` (hop 2 and the legacy lambda). Import `prune_release_tree` from `.release_copy`. In the hop-2 dry-run block, after the `for name, _ in mirror_pairs:` loop and before `_print_ok`, add:

```python
            if _obs_project_exists(apiurl, release_obs_project):
                prune_release_tree(
                    apiurl,
                    from_project,
                    release_obs_project,
                    mirror_pairs,
                    release_path,
                    dry_run=True,
                )
```

Add to `tests/test_sync_release.py` (model the setup on `test_from_prerelease_dry_run_writes_nothing`, line ~574, reusing its argument object and monkeypatches):

```python
def test_from_prerelease_dry_run_lists_prune(tmp_path, monkeypatch, capsys):
    # copy the fixture/monkeypatch block of test_from_prerelease_dry_run_writes_nothing here
    seen = []
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda apiurl, prj: True)
    monkeypatch.setattr(
        cmd_sync, "prune_release_tree",
        lambda *a, **k: seen.append((a[1], a[2], k.get("dry_run"))),
    )
    cmd_sync.cmd_sync_release(args)
    assert seen == [("PR:pr-1:ppg:releases:17", "R:ppg:releases:17", True)]
```

Replace the two project names in the assertion with the ones that fixture uses for `--from` and the release project. Also add `prune=True` expectations where existing tests in this file assert the keyword arguments of `release_tree`, and remove any test of `warn_orphans`.

- [ ] **Step 5: Run, format, type-check, commit**

```bash
$VENV/python -m pytest tests/test_release_copy.py tests/test_sync_release.py tests/test_sync_prerelease.py -q
$VENV/black percona_obs/ && $VENV/pyright
git add percona_obs/release_copy.py percona_obs/cmd_sync.py tests/test_release_copy.py tests/test_sync_release.py
git commit -s -m "sync release: delete packages and subprojects that left the release"
```

---

### Task 7: CI for nested units

**Goal:** Release PR detection, tagging, hop 2 and the PR comment work for `release.yaml` files at any depth; hop 2 finds the release project from the tree.

**Files:**
- Modify: `.github/scripts/release_pr.py` (regexes line 25-26; new `project-for-tag` subcommand)
- Modify: `.github/scripts/post_pr_comment.py` (`render_prerelease_comment`)
- Modify: `.github/scripts/update_version_lists.py` (`get_latest_release_id` ~138)
- Modify: `.github/workflows/obs-release-pr.yml` (line 29 `paths`; populate step ~195-218)
- Modify: `.github/workflows/obs-pr-cleanup.yml` (line 100 jq regex)
- Modify: `.github/workflows/obs-release.yml` (tag validation ~49; mapping step ~122-140)
- Test: `tests/test_release_pr_script.py`, `tests/test_post_pr_comment.py`, `tests/test_update_version_lists.py`

**Acceptance Criteria:**
- [ ] `classify_files` returns nested `release.yaml` paths; `release_projects` maps `root/ppg/releases/18/extras/release.yaml` to `ppg:releases:18:extras`; `changelog_only` accepts nested `CHANGELOG.md`.
- [ ] `release_pr.py project-for-tag ppg/extras-18.6-6` prints `ppg:releases:18:extras`; unknown tag exits 1.
- [ ] `obs-release.yml` accepts tags `ppg/18.7-1`, `ppg/extras-18.6-6`, `ppg/common-upgrade-extras-1` and no longer derives the project from the tag text.
- [ ] The pre-release comment lists removals when a report row has a non-empty `removals` list.
- [ ] `get_latest_release_id("ppg:releases:18:extras")` reads `releases/18/extras/release.yaml`.

**Verify:** `$VENV/python -m pytest tests/test_release_pr_script.py tests/test_post_pr_comment.py tests/test_update_version_lists.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests.** In `tests/test_release_pr_script.py` (the module is loaded as `m` at the top of the file; use the existing name):

```python
def test_nested_release_yaml_is_a_release_file():
    files = ["root/ppg/releases/18/extras/release.yaml", "root/ppg/releases/18/extras/CHANGELOG.md"]
    kind, yamls = m.classify_files(files)
    assert (kind, yamls) == ("release", ["root/ppg/releases/18/extras/release.yaml"])
    assert m.release_projects(yamls) == ["ppg:releases:18:extras"]
    assert m.changelog_only(["root/ppg/releases/common/upgrade/extras/CHANGELOG.md"])


def test_project_for_tag(tmp_path):
    rel = tmp_path / "root/ppg/releases/18"
    (rel / "extras").mkdir(parents=True)
    (rel / "release.yaml").write_text("project: ppg:staging:18\nreleases:\n- ppg/18.6-5\n")
    (rel / "extras" / "release.yaml").write_text(
        "project: ppg:staging:18:extras\nreleases:\n- {tag: ppg/extras-18.6-6, source_commit: abc}\n"
    )
    assert m.project_for_tag("ppg/extras-18.6-6", tmp_path) == "ppg:releases:18:extras"
    assert m.project_for_tag("ppg/18.6-5", tmp_path) == "ppg:releases:18"
    assert m.project_for_tag("ppg/18.6-4", tmp_path) is None
```

In `tests/test_post_pr_comment.py`, next to the existing `render_prerelease_comment` tests (reuse their argument values):

```python
def test_prerelease_comment_lists_removals():
    report = [
        {"project": "ppg:releases:18", "prerelease": "PR:pr-7:ppg:releases:18",
         "outcome": "success", "source_commit": "a" * 40,
         "removals": ["package  isv:percona:ppg:releases:18/percona-pgpool-II"]},
    ]
    out = m.render_prerelease_comment("<!-- m -->", "", report, "https://obs", "https://run", "now", "7", "o/r")
    assert "Removed from the release on merge" in out
    assert "`package  isv:percona:ppg:releases:18/percona-pgpool-II`" in out


def test_prerelease_comment_without_removals_has_no_section():
    report = [{"project": "p", "prerelease": "x", "outcome": "success", "source_commit": ""}]
    out = m.render_prerelease_comment("<!-- m -->", "", report, "https://obs", "https://run", "now", "7", "o/r")
    assert "Removed from the release" not in out
```

In `tests/test_update_version_lists.py` (follow the file's existing way of pointing `ROOT_DIR` at a fixture):

```python
def test_latest_release_id_nested_unit(tmp_path, monkeypatch):
    rel = tmp_path / "ppg/releases/18/extras"
    rel.mkdir(parents=True)
    (rel / "release.yaml").write_text("releases:\n- ppg/extras-18.6-6\n")
    monkeypatch.setattr(m, "ROOT_DIR", tmp_path)
    assert m.get_latest_release_id("ppg:releases:18:extras") == "extras-18.6-6"
    assert m.get_latest_release_id("ppg:releases:18") == "—"
```

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/python -m pytest tests/test_release_pr_script.py tests/test_post_pr_comment.py tests/test_update_version_lists.py -q`
Expected: the five new tests FAIL.

- [ ] **Step 3: `release_pr.py`.** Change the two regexes:

```python
_RELEASE_YAML_RE = re.compile(r"^root/[^/]+/releases/(?:[^/]+/)+release\.yaml$")
_CHANGELOG_RE = re.compile(r"^root/[^/]+/releases/(?:[^/]+/)+CHANGELOG\.md$")
```

Add (with `from pathlib import Path` at the top):

```python
def project_for_tag(tag: str, repo_dir: "Path | str" = ".") -> "str | None":
    """Release project whose release.yaml lists *tag* last, read from the tree.

    The tag is only a label: ``ppg/extras-18.6-6`` does not say which
    directory holds its record.
    """
    import yaml

    root = Path(repo_dir) / "root"
    for record in sorted(root.glob("*/releases/**/release.yaml")):
        data = yaml.safe_load(record.read_text(encoding="utf-8")) or {}
        releases = data.get("releases") or []
        if not releases:
            continue
        last = releases[-1]
        last_tag = last.get("tag", "") if isinstance(last, dict) else str(last)
        if last_tag == tag:
            return ":".join(record.parent.relative_to(root).parts)
    return None
```

In the script's CLI dispatch (bottom of the file, where `classify` is handled) add a `project-for-tag <tag>` subcommand that prints the project or writes `::error::no release.yaml lists <tag> as its last entry` to stdout and exits 1. Follow the argument-parsing style already used there.

- [ ] **Step 4: `post_pr_comment.py`.** In `render_prerelease_comment`, after the table loop and before the `lines += ["", f"Repopulate …` block, add:

```python
    removals = [(r.get("project", ""), x) for r in report for x in r.get("removals") or []]
    if removals:
        lines += [
            "",
            "**Removed from the release on merge** (no longer in the pre-release):",
            "",
        ]
        lines += [f"- `{project}`: `{item}`" for project, item in removals]
```

Update the docstring and the header comment (line ~24) to `{project, prerelease, outcome, source_commit, removals?}`.

- [ ] **Step 5: `update_version_lists.py`.** In `get_latest_release_id` replace the three lines that compute `product, major` and `release_yaml` with:

```python
    product = parts[0]
    release_yaml = ROOT_DIR.joinpath(product, "releases", *parts[2:], "release.yaml")
```

and update its docstring to "Reads root/<product>/releases/<major>[/<unit>…]/release.yaml".

- [ ] **Step 6: Workflows.**

`obs-release-pr.yml` line 29: `paths: ['root/*/releases/**/release.yaml']`. In the populate step, after the `SRC=$(…)` line and before the `jq -c` line, add:

```bash
            REMOVALS='[]'
            if [ "$outcome" = success ]; then
              # What hop 2 will delete from the release project: its dry-run
              # prints one "  - package …" / "  - project …" line per deletion.
              REMOVALS=$(venv/bin/python -u -m percona_obs -P main sync release "$proj" \
                  --from "${OBS_PR_ROOTPRJ}:pr-${PR_NUMBER}:${proj}" --dry-run 2>/dev/null \
                | sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                | sed -nE 's/^[[:space:]]*- ((package|project)[[:space:]].*)$/\1/p' \
                | jq -R . | jq -cs .) || REMOVALS='[]'
            fi
```

and change the `jq -c` invocation to pass `--argjson r "$REMOVALS"` and build `{project: $p, prerelease: $pre, outcome: $o, source_commit: $s, removals: $r}`. Before editing, read `_delete_obs_project` (`percona_obs/obs_api.py` ~917) to confirm the label it prints starts with `project`; if it differs, use its word in the `sed` alternation.

`obs-pr-cleanup.yml` line 100: change the jq test to `test("^root/[^/]+/releases/([^/]+/)+release\\.yaml$")`.

`obs-release.yml`: replace the tag-shape `grep -Eq` pattern with `'^[a-z0-9-]+/[a-z0-9]+([.-][a-z0-9]+)*-[0-9]+$'` and its message with `tag '$TAG' does not match <product>/<id>-<N>`. Replace the mapping step body with:

```bash
          set -euo pipefail
          read -r -a TAG_LIST <<<"$TAGS_IN"
          for TAG in "${TAG_LIST[@]}"; do
            # The tag is a label; the release project is the directory of the
            # release.yaml that lists it last.
            PROJECT=$(venv/bin/python .github/scripts/release_pr.py project-for-tag "$TAG")
            FROM="${OBS_PR_ROOTPRJ}:pr-${PR_NUMBER}:${PROJECT}"
            echo "== sync release ${PROJECT} --from ${FROM}  (${TAG})"
            venv/bin/python -m percona_obs -P main sync release "$PROJECT" --from "$FROM"
          done
```

and the comment above the step with `# Tag → release project: looked up in the tree (release_pr.py project-for-tag).`. Check which ref this job checks out (the `actions/checkout` step of the `release` job): it must be a ref that contains the merged `release.yaml` (`main` or the tag). If it checks out something older, set `ref: refs/tags/${{ needs.validate.outputs.first_tag }}` as the `finalize` job does.

Then `grep -rn "releases/\[\^/\]+/release\|releases/\*/release" .github/` and fix any remaining single-depth pattern the same way. The "release-only PR" tests (`^root/[^/]+/releases/`) are prefix-based: leave them.

- [ ] **Step 7: Run and commit**

```bash
$VENV/python -m pytest tests/test_release_pr_script.py tests/test_post_pr_comment.py tests/test_update_version_lists.py tests/test_list_qa_matrix.py -q
$VENV/python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/obs-release-pr.yml .github/workflows/obs-pr-cleanup.yml .github/workflows/obs-release.yml
git add .github tests
git commit -s -m "ci: release units at any depth, release project looked up from the tag"
```

---

### Task 8: Documentation

**Goal:** The tool reference and the tree README describe release units, path-less mirrors, nested ids and pruning.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md` (sections on `project release`, `sync prerelease`, `sync release`; ~line 1214 counter mode)
- Modify: `.github/copilot-instructions.md` (§ "Release hops" ~547, Workflow 3 ~1110, Workflow 6 ~1156, `obs-release.yml` description)
- Modify: `root/README.md` (release structure; `staging/common/` ~368-432; lines ~109-119)

**Acceptance Criteria:**
- [ ] Each file states the unit rule (project + `containers` + `tarballs`), lists the nested unit commands and tags, and says mirrors carry no `subproject:` paths.
- [ ] `sync release` docs describe the prune, its guards and the PR-comment removal list.
- [ ] `PPG_RELEASE` docs say the counter follows the unit for nested per-major units.
- [ ] No text still says a release is a "full staging snapshot" of every subproject, or that `sync release` only warns about orphans.

**Verify:** `grep -n -i "full staging snapshot\|orphaned release subproject\|remove manually" docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md root/README.md` → no output

**Steps:**

- [ ] **Step 1:** Read the three files' release sections (`grep -n -i "release" <file>` to locate them).

- [ ] **Step 2:** Add this block once to `docs/PERCONA_OBS_TOOL.md` at the start of the release section, and link to it from the other two files instead of repeating it:

```markdown
### Release units

A release covers one **release unit**: a staging project plus its direct
children named `containers` and `tarballs`. Every other subproject is a unit
of its own and is released separately.

| Command | Releases | Release project | Tag |
|---|---|---|---|
| `project release ppg:staging:18` | `18`, `18:containers`, `18:tarballs` | `ppg:releases:18` | `ppg/18.6-N` |
| `project release ppg:staging:18:extras` | `18:extras`, `18:extras:containers` | `ppg:releases:18:extras` | `ppg/extras-18.6-N` |
| `project release ppg:staging:16:tde` | `16:tde` | `ppg:releases:16:tde` | `ppg/tde-16.15-N` |
| `project release ppg:staging:common:tools` | `common:tools`, `common:tools:containers` | `ppg:releases:common:tools` | `ppg/common-tools-N` |

Each unit has its own `release.yaml` and `CHANGELOG.md` in
`root/ppg/releases/<…>/`, mirroring the path below `staging`. A nested unit
does not need its parent to be released and is not compared with it.
`project release` refuses a bundled child (`…:containers`) and a project with
nothing to release (`ppg:staging:common`).

`N` is the unit's own counter per PostgreSQL minor. The first release of a
unit that used to ship with its parent continues the parent's numbering.
`PPG_RELEASE` (image tags) uses the same record: the unit's own for a nested
unit of a PG major, the major's for everything else.

Release mirrors carry no `subproject:` repository paths: release projects
never build, so they depend on no other project of the root.

After copying, `sync release` deletes from the release project the packages
its source no longer has and the subprojects that have no mirror directory.
Nothing is deleted when the copy was not verified (`--verify-timeout 0`) or
when the source lists no packages while the target still has some.
`--dry-run` prints the deletions; the release PR comment lists them.
```

- [ ] **Step 3:** Update the surrounding prose in all three files to match (hop descriptions, Workflow 3 tag/dispatch text: "the release project is looked up from the tag"; Workflow 6 path filter `root/*/releases/**/release.yaml`; `root/README.md` `staging/common/` section: the units under `common` today are `common` (top + `containers`), `common:tools`, `common:extras`).

- [ ] **Step 4: Verify and commit**

```bash
grep -n -i "full staging snapshot\|orphaned release subproject\|remove manually" docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md root/README.md
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md root/README.md
git commit -s -m "docs: release units, path-less mirrors, release pruning"
```

---

### Task 9: Whole-branch verification

**Goal:** Evidence that PR 1 is complete: full test suite, formatting, types, and read-only runs against the real tree.

**Files:** none modified (fixes found here go into a new commit touching the owning task's files).

**Acceptance Criteria:**
- [ ] Full pytest run passes.
- [ ] `black` reports no change, `pyright` reports `0 errors`.
- [ ] `project verify --offline` passes.
- [ ] No reference to removed names remains.

**Verify:** `$VENV/python -m pytest tests -q && $VENV/black --check percona_obs/ && $VENV/pyright` → `passed`, `would be left unchanged`, `0 errors`

**Steps:**

- [ ] **Step 1:** `$VENV/python -m pytest tests -q` → all pass.
- [ ] **Step 2:** `$VENV/black --check percona_obs/ && $VENV/pyright`.
- [ ] **Step 3:** `grep -rn "_rewrite_subproject_paths\|warn_orphans\|_mirror_subproject_pairs\|branch_fallbacks" percona_obs/release_copy.py percona_obs/cmd_project.py tests/` → no output. (`branch_fallbacks` still exists in `obs_api.py`/`cmd_sync.py` for `sync push --branch-from`; that is expected.)
- [ ] **Step 4:** `./percona-obs project verify --offline` from the worktree root with `PATH=$VENV:$PATH` → exit 0. If the wrapper needs `venv/` in the worktree, run `$VENV/python -m percona_obs project verify --offline` instead.
- [ ] **Step 5:** Unit listing against the real tree; expected output is the 13-line list below except that, until Task 10, `common` shows `ppg:staging:common`, `ppg:staging:common:extras`, `ppg:staging:common:tools`:

```bash
$VENV/python - <<'EOF'
from percona_obs.common import REPO_ROOT
from percona_obs.release_scope import nested_unit_roots, unit_packages

def walk(path, pid):
    if any(unit_packages(path, pid)):
        print(pid)
    for child in nested_unit_roots(path, pid):
        walk(path / child.rsplit(":", 1)[1], child)

walk(REPO_ROOT / "ppg" / "staging", "ppg:staging")
EOF
```

- [ ] **Step 6:** Report to the user: test counts, the unit list, and that the production dry-runs (`-P isv sync release ppg:releases:18 --dry-run`) and the labs rehearsal of the runbook are theirs to run or to ask for explicitly. Do not push and do not open a PR.

---

### Task 10 (PR 2): Move the upgrade images under `common:upgrade`

**Goal:** `ppg:staging:common` has no bundled child left; the upgrade images are units `common:upgrade` and `common:upgrade:extras`.

**Precondition:** PR 1 merged. New worktree `.claude/worktrees/common-upgrade-move`, branch off `percona/main`.

**Files:**
- Move: `root/ppg/staging/common/containers/` → `root/ppg/staging/common/upgrade/containers/`
- Move: `root/ppg/staging/common/extras/containers/` → `root/ppg/staging/common/upgrade/extras/containers/`
- Create: `root/ppg/staging/common/upgrade/project.yaml`, `root/ppg/staging/common/upgrade/extras/project.yaml`
- Delete: `root/ppg/staging/common/extras/project.yaml`, `root/ppg/releases/common/release.yaml`, `root/ppg/releases/common/CHANGELOG.md`, `root/ppg/releases/common/containers/`, `root/ppg/releases/common/extras/`
- Modify: `root/ppg/staging/common/project.yaml` (description), the two moved `containers/project.yaml` (`qa:` image references, `subproject:` self-references), `root/macros.yaml:7-8`, `root/README.md`, `.github/copilot-instructions.md`

**Acceptance Criteria:**
- [ ] `ls root/ppg/staging/common` shows `macros.yaml project.yaml subprojects.yaml tools upgrade`.
- [ ] `project verify --offline` passes.
- [ ] The unit listing of Task 9 Step 5 prints `ppg:staging:common:tools`, `ppg:staging:common:upgrade`, `ppg:staging:common:upgrade:extras` and no `ppg:staging:common` line.
- [ ] No file references `staging:common:containers`, `staging:common:extras`, `staging/common/containers` or `staging/common/extras` (outside `docs/superpowers/` history and `CHANGELOG.md` files).
- [ ] Relative symlinks inside the moved directories still resolve.

**Verify:** `$VENV/python -m percona_obs project verify --offline && find root/ppg/staging/common -xtype l` → exit 0 and no output

**Steps:**

- [ ] **Step 1: Move.**

```bash
mkdir -p root/ppg/staging/common/upgrade/extras
git mv root/ppg/staging/common/containers root/ppg/staging/common/upgrade/containers
git mv root/ppg/staging/common/extras/containers root/ppg/staging/common/upgrade/extras/containers
git mv root/ppg/staging/common/extras/project.yaml root/ppg/staging/common/upgrade/extras/project.yaml
cp root/ppg/staging/common/upgrade/extras/project.yaml root/ppg/staging/common/upgrade/project.yaml
```

Edit both namespace `project.yaml` files: keep whatever opt-outs the original `common/extras/project.yaml` carried, and set the titles/descriptions to "Cross-version upgrade images" (`upgrade`) and "Cross-version custom upgrade images" (`upgrade/extras`), each stating that the project holds no packages.

- [ ] **Step 2: Fix links and references.** `find root/ppg/staging/common -xtype l` lists broken symlinks: every moved directory is one or two levels deeper, so re-point each relative link (`ln -sfn`) with the extra `../`. Then:

```bash
grep -rn "staging:common:containers\|staging:common:extras\|staging/common/containers\|staging/common/extras\|common/containers\b\|common:extras:containers" \
  root percona_obs .github docs/PERCONA_OBS_TOOL.md --include="*" | grep -v "CHANGELOG.md\|root/ppg/releases/common/"
```

Rewrite each hit to the `upgrade` path: `subproject:` self-references and `qa:` blocks (`image`/`repository`/`project` values, registry paths `…/common/containers/<ubi>/…` → `…/common/upgrade/containers/<ubi>/…`) in the two moved `containers/project.yaml`, the comment in `root/macros.yaml`, `root/README.md`, `.github/copilot-instructions.md`, and any test fixture or script that names the old projects. `root/common/containers` (the base-image project `common:containers:ubi9`) is a different project: do not touch it.

- [ ] **Step 3: Retire the `common` release record.**

```bash
git rm root/ppg/releases/common/release.yaml root/ppg/releases/common/CHANGELOG.md
git rm -r root/ppg/releases/common/containers root/ppg/releases/common/extras
```

Keep `root/ppg/releases/common/project.yaml` and `root/ppg/releases/common/tools/`. Update `root/ppg/staging/common/project.yaml`'s description (it names `ppg:staging:common:containers`) and the `staging/common/` section of `root/README.md`: three units, `ppg/common-1` was the last `common` tag, and the manual cleanup below.

- [ ] **Step 4: Document the manual cleanup** in the PR description draft (a file `docs/superpowers/plans/2026-11-11-common-upgrade-move-followups.md`, committed):

```markdown
After `ppg/common-upgrade-1` and `ppg/common-upgrade-extras-1` are released
and obs-sync + ppg-testing read the new registry paths, delete on every
instance (no release prunes them, `common` is never released again):

    percona-obs -P <profile> sync delete ppg:releases:common:extras --recursive
    percona-obs -P <profile> sync delete ppg:releases:common:containers

External follow-ups: obs-sync image map and ppg-testing image references
(`…/common/containers/<ubi>/…` → `…/common/upgrade/containers/<ubi>/…`,
`…/common/extras/containers/ubi9/…` → `…/common/upgrade/extras/containers/ubi9/…`).
```

Check the exact `sync delete` flags with `$VENV/python -m percona_obs sync delete --help` and correct the two lines to match.

- [ ] **Step 5: Verify and commit**

```bash
$VENV/python -m percona_obs project verify --offline
find root/ppg/staging/common -xtype l
$VENV/python -m pytest tests -q
git add -A root docs .github tests
git commit -s -m "staging: move the upgrade images under common:upgrade"
```

Report to the user; do not push.
