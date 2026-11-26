# Release Unit Build Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a maintainer freeze and unfreeze release units from a GitHub Actions workflow so OS dependency updates stop triggering rebuilds, while a late fix pushed by `sync push` still rebuilds everything that depends on it.

**Architecture:** The freeze is the OBS repository attribute `rebuild="local"`, set by a new `unit_freeze` module and kept by `sync push` when it rewrites project meta. A new `propagate` module computes what depends on the packages a sync changed and sends OBS rebuild triggers in stages (wait until the scheduler has seen one stage before triggering the next). `sync push` calls it after uploads; `build propagate` exposes it for recovery.

**Tech Stack:** Python 3 (`percona_obs` package, `osc` library, `xml.etree.ElementTree`), pytest with monkeypatched OBS calls, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-26-release-unit-build-freeze-design.md`. Read it first; section 3 holds the OBS behaviour this plan relies on.

## Global Constraints

- Work in a git worktree at `.claude/worktrees/unit-build-freeze`, branch `unit-build-freeze`, created off `percona/main`.
- After every code change run, in this order: `venv/bin/black percona_obs/ tests/` then `venv/bin/pyright` (0 errors) then `venv/bin/python -m pytest tests -q`.
- Commit with `git commit -s`. No `Co-Authored-By` or other AI attribution. Do not push and do not open a PR; the user does that.
- Tests never contact an OBS server: fake `osc.core.*`, `osc.connection.*` and module-level helpers with `monkeypatch`, as `tests/test_release_freeze.py` does.
- No write against the `isv` profile. No `sync push` to any instance from this work.
- The frozen marker is exactly the attribute `rebuild="local"` on `<repository>` in project meta. A project is frozen when it has at least one repository and every repository carries it.
- Pending package codes and their meaning come from `release_freeze.PENDING_PKG_CODES`; do not redefine them.
- Stage wait: `SEEN_TIMEOUT_S = 120`, `SEEN_POLL_S = 2` (module constants in `propagate.py`).
- `sync release` / `sync prerelease` and `release_freeze.py` are not modified.

**User decisions (already made):**
- "Yes, I want late fix merged to staging" to still build while frozen.
- Approach A chosen: `rebuild="local"` plus propagation done by the tool, with staged triggers.
- Scratch OBS projects may only be created "in a subproject of home project of the user you use" (labs, `home:rjfd.di:*`).
- Design doc approved as written, including the six author's calls in it.

## Review Focus

1. A name that is not a release unit root (a bundled child such as `ppg:staging:18:containers`, a typo) passed to `freeze`: expect an error naming it and no write to any project. Test in Task 2.
2. A unit project that does not exist on this OBS instance (instances build a slice): expect it reported as `absent`, the others still processed, exit 0. Test in Task 1.
3. A project where only some repositories carry `rebuild="local"`: expect `is_frozen` false, `freeze-status` to report it as `partial`, and `freeze` to complete it. Tests in Tasks 1 and 2.
4. A changed package that never shows as pending (excluded or disabled on every target, or `unresolvable`): expect excluded/disabled targets to be ignored, a warning after the timeout, and the next stage still triggered. Test in Task 7.
5. Dependency data that cannot be fetched for a project: expect every package of the frozen projects that can consume it to be triggered, not silently none. Test in Task 6.

---

## File Structure

| File | Responsibility |
|---|---|
| `percona_obs/unit_freeze.py` (new) | Frozen-state meta transforms, the project scope of a unit, applying freeze/unfreeze, listing frozen projects |
| `percona_obs/propagate.py` (new) | Dependency closure, stage plan, "seen by scheduler" waits, rebuild triggers |
| `percona_obs/obs_api.py` | `_apply_project_config` carries `rebuild` over; `_fetch_combined_depinfo` gains exact/strict mode |
| `percona_obs/cmd_project.py`, `percona_obs/cmd_build.py`, `percona_obs/cli.py` | `project freeze|unfreeze|freeze-status`, `build propagate` |
| `percona_obs/cmd_sync.py` | Calls propagation after uploads; frozen-project notices and warnings |
| `root/project.yaml` | `BuildFlags: aggregate-checklocal` in the inherited prjconf |
| `.github/workflows/obs-freeze.yml` (new), `.github/workflows/sync-main.yml` | Manual workflow; nightly frozen-units warning |
| `docs/PERCONA_OBS_TOOL.md`, `CLAUDE.md`, `.github/copilot-instructions.md` | Reference, key-files rows, rehearsal runbook |

---

### Task 1: Freeze state in project meta (`unit_freeze.py`)

**Goal:** A module that reads, sets and clears the frozen marker on OBS projects and knows which projects make up a unit.

**Files:**
- Create: `percona_obs/unit_freeze.py`
- Test: `tests/test_unit_freeze.py`

**Acceptance Criteria:**
- [ ] `freeze_state` returns `frozen`, `partial`, `unfrozen` or `empty` (no repositories) for a meta XML string.
- [ ] `with_rebuild_mode` changes only the `rebuild` attribute of `<repository>` elements; every other element and attribute of the fetched meta round-trips.
- [ ] `apply_freeze` is idempotent, skips the write when nothing changes, reports a 404 project as `absent`, and writes nothing in dry-run.
- [ ] `unit_obs_projects` returns the unit root and its existing bundled children, and raises `ValueError` for a non-unit name.

**Verify:** `venv/bin/python -m pytest tests/test_unit_freeze.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/test_unit_freeze.py`:

```python
META = (
    '<project name="p"><title>t</title><description/>'
    '<person userid="u" role="maintainer"/>'
    '<build><disable repository="A"/></build>'
    '<repository name="A"><path project="x" repository="r"/><arch>x86_64</arch></repository>'
    '<repository name="B" block="local"><arch>aarch64</arch></repository>'
    "</project>"
)

def test_freeze_state_values():
    assert uf.freeze_state(META) == "unfrozen"
    assert uf.freeze_state(uf.with_rebuild_mode(META, "local")) == "frozen"
    one = META.replace('name="A">', 'name="A" rebuild="local">')
    assert uf.freeze_state(one) == "partial"
    assert uf.freeze_state('<project name="p"/>') == "empty"

def test_with_rebuild_mode_touches_only_the_attribute():
    frozen = ET.fromstring(uf.with_rebuild_mode(META, "local"))
    assert [r.get("rebuild") for r in frozen.findall("repository")] == ["local", "local"]
    assert frozen.find("repository[@name='B']").get("block") == "local"
    assert frozen.find("person").get("userid") == "u"
    assert frozen.find("build/disable").get("repository") == "A"
    back = ET.fromstring(uf.with_rebuild_mode(ET.tostring(frozen, encoding="unicode"), None))
    assert all(r.get("rebuild") is None for r in back.findall("repository"))

def test_apply_freeze_outcomes(monkeypatch):
    # fake show_project_meta: "p1" -> META, "p2" -> already frozen, "p3" -> HTTPError 404
    # fake _edit_project_meta records (project, xml)
    out = uf.apply_freeze("api", ["p1", "p2", "p3"], frozen=True, dry_run=False)
    assert out == [("p1", "changed"), ("p2", "unchanged"), ("p3", "absent")]
    assert [p for p, _ in writes] == ["p1"]

def test_apply_freeze_dry_run_writes_nothing(monkeypatch):
    out = uf.apply_freeze("api", ["p1"], frozen=True, dry_run=True)
    assert out == [("p1", "changed")] and writes == []

def test_apply_freeze_verifies_the_write(monkeypatch):
    # second show_project_meta for p1 still returns unfrozen META
    with pytest.raises(RuntimeError, match="p1"):
        uf.apply_freeze("api", ["p1"], frozen=True, dry_run=False)

def test_unit_obs_projects(tmp_path):
    # tree: ppg/staging/18/{project.yaml,containers/project.yaml,extras/project.yaml}
    assert uf.unit_obs_projects("ppg:staging:18", "isv:percona", root=tmp_path) == [
        "isv:percona:ppg:staging:18", "isv:percona:ppg:staging:18:containers"]
    with pytest.raises(ValueError, match="ppg:staging:18:containers"):
        uf.unit_obs_projects("ppg:staging:18:containers", "isv:percona", root=tmp_path)
```

- [ ] **Step 2: Run** `venv/bin/python -m pytest tests/test_unit_freeze.py -q` → FAIL (module missing)

- [ ] **Step 3: Implement in `percona_obs/unit_freeze.py`**

```python
REBUILD_FROZEN = "local"
def freeze_state(meta_xml: str) -> str
def with_rebuild_mode(meta_xml: str, mode: "str | None") -> str
def unit_obs_projects(unit: str, rootprj: str, root: Path = REPO_ROOT) -> "list[str]"
def apply_freeze(apiurl: str, obs_projects: "list[str]", frozen: bool, dry_run: bool) -> "list[tuple[str, str]]"
def frozen_projects(apiurl: str, obs_projects: "list[str]") -> "dict[str, str]"   # project -> freeze_state, absent projects omitted
```

`unit_obs_projects` validates against `release_scope.list_release_units(root)` and adds each `common.BUNDLED_SUBPROJECTS` child that has a `project.yaml`; project names honour a `name:` override in `project.yaml` the way `cmd_build_trigger` resolves `obs_project_name`. `apply_freeze` fetches with `osc.core.show_project_meta`, writes with `obs_api._edit_project_meta(..., force=True)`, then re-fetches and raises `RuntimeError` naming the project if `freeze_state` is not the requested one. `frozen_projects` fetches in parallel with a `ThreadPoolExecutor`, as `release_freeze` does.

- [ ] **Step 4: Run the Verify command** → PASS. Then black, pyright.

- [ ] **Step 5: Commit** `git commit -s -m "unit_freeze: read, set and clear the rebuild=local freeze marker"`

---

### Task 2: `project freeze`, `project unfreeze`, `project freeze-status`

**Goal:** CLI commands that freeze, unfreeze and list release units.

**Files:**
- Modify: `percona_obs/cli.py` (after the `release-units` parser, ~line 987), `percona_obs/cmd_project.py`
- Test: `tests/test_project_freeze_cmd.py`

**Acceptance Criteria:**
- [ ] `project freeze <unit>...` and `project unfreeze <unit>...` accept `--dry-run`, validate every unit before any OBS call, and print one line per project: `<project>  frozen|unfrozen|already frozen|already unfrozen|absent`.
- [ ] An invalid unit exits non-zero with the name in the message and performs no write.
- [ ] `project freeze-status` prints every release unit whose state is `frozen` or `partial`; with `--github-warning` it also prints one `::warning::` line listing them, and prints nothing extra when none are frozen.

**Verify:** `venv/bin/python -m pytest tests/test_project_freeze_cmd.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (monkeypatch `unit_freeze.apply_freeze`, `unit_freeze.frozen_projects`, `unit_freeze.unit_obs_projects`; drive through `cli.build_parser().parse_args([...])` and `args.func(args)` with `capsys`):

```python
def test_freeze_prints_one_line_per_project(...):
    # apply_freeze -> [("r:ppg:staging:18", "changed"), ("r:ppg:staging:18:containers", "absent")]
    assert "r:ppg:staging:18  frozen" in out and "r:ppg:staging:18:containers  absent" in out

def test_unfreeze_unchanged_wording(...):
    assert "already unfrozen" in out

def test_invalid_unit_makes_no_call(...):
    # unit_obs_projects raises ValueError for the second unit
    with pytest.raises(SystemExit) as e: ...
    assert e.value.code != 0 and apply_calls == []

def test_freeze_status_github_warning(...):
    # frozen_projects -> {"r:ppg:staging:18": "frozen", "r:ppg:staging:17": "unfrozen", "r:ppg:staging:16": "partial"}
    assert "::warning::" in out and "ppg:staging:18" in out and "ppg:staging:16 (partial)" in out
    assert "ppg:staging:17" not in out

def test_freeze_status_silent_when_nothing_frozen(...):
    assert "::warning::" not in out
```

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implement** `cmd_project_freeze(args)` (shared by both subcommands, `args.frozen` set through `set_defaults(frozen=True|False)`) and `cmd_project_freeze_status(args)` in `cmd_project.py`; register the three parsers in `cli.py`. A unit's reported state in `freeze-status` is `frozen` when all its present projects are frozen, `partial` when some are, otherwise omitted.

- [ ] **Step 4: Run the Verify command**, black, pyright → PASS

- [ ] **Step 5: Commit** `git commit -s -m "project: add freeze, unfreeze and freeze-status commands"`

---

### Task 3: `sync push` keeps the freeze when it rewrites project meta

**Goal:** A project meta update from `project.yaml` no longer drops `rebuild` attributes.

**Files:**
- Modify: `percona_obs/unit_freeze.py`, `percona_obs/obs_api.py` (`_apply_project_config`, the "updating project meta" branch ~line 1481)
- Test: `tests/test_unit_freeze.py`, `tests/test_project_meta_rebuild_carry.py`

**Acceptance Criteria:**
- [ ] `carry_rebuild(current_xml, desired_xml)` copies each live repository's `rebuild` value onto the same-named repository in the desired meta.
- [ ] When every live repository is `local`, a repository that exists only in the desired meta also gets `rebuild="local"`.
- [ ] When the live project is not frozen, a new repository gets no attribute.
- [ ] `_apply_project_config` uploads the carried meta on update; `_project_meta_subset_equal` is unchanged, so a `rebuild` difference alone causes no write.

**Verify:** `venv/bin/python -m pytest tests/test_unit_freeze.py tests/test_project_meta_rebuild_carry.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
def test_carry_rebuild_same_names():
    cur = '<project name="p"><repository name="A" rebuild="local"/><repository name="B" rebuild="direct"/></project>'
    des = '<project name="p"><repository name="A"/><repository name="B"/></project>'
    got = ET.fromstring(uf.carry_rebuild(cur, des))
    assert [(r.get("name"), r.get("rebuild")) for r in got.findall("repository")] == [("A", "local"), ("B", "direct")]

def test_carry_rebuild_new_repo_in_frozen_project():
    cur = '<project name="p"><repository name="A" rebuild="local"/></project>'
    des = '<project name="p"><repository name="A"/><repository name="N"/></project>'
    assert ET.fromstring(uf.carry_rebuild(cur, des)).find("repository[@name='N']").get("rebuild") == "local"

def test_carry_rebuild_new_repo_in_unfrozen_project():
    cur = '<project name="p"><repository name="A"/></project>'
    des = '<project name="p"><repository name="A"/><repository name="N"/></project>'
    assert ET.fromstring(uf.carry_rebuild(cur, des)).find("repository[@name='N']").get("rebuild") is None
```

In `tests/test_project_meta_rebuild_carry.py`: fake `show_project_meta` to return a frozen project whose title differs from `project.yaml`, capture `_edit_project_meta`, call `_apply_project_config`, assert the uploaded XML has `rebuild="local"` on every repository. Second test: live meta differs from desired only by `rebuild` → no `_edit_project_meta` call. Use the fixture style of `tests/test_project_config_merge.py` for the on-disk `project.yaml`.

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implement** `carry_rebuild(current_xml: str, desired_xml: str) -> str` in `unit_freeze.py`, and apply it to `meta_to_upload` in the update branch of `_apply_project_config` after `_inject_obs_managed_elements`.

- [ ] **Step 4: Run the Verify command**, the full suite, black, pyright → PASS

- [ ] **Step 5: Commit** `git commit -s -m "sync: carry the repository rebuild mode over project meta updates"`

---

### Task 4: `aggregate-checklocal` in the inherited prjconf

**Goal:** Aggregates in a frozen project stop re-copying when their source rebuilds.

**Files:**
- Modify: `root/project.yaml` (`project-config:` block, ~line 131)
- Test: `tests/test_aggregate_checklocal_prjconf.py`

**Acceptance Criteria:**
- [ ] `BuildFlags: aggregate-checklocal` is at top level of the root `project-config` (outside every `%if`), with a comment saying it only acts under `rebuild="local"`.
- [ ] The resolved prjconf of every release unit project that contains an `_aggregate` package includes the line.

**Verify:** `venv/bin/python -m pytest tests/test_aggregate_checklocal_prjconf.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test.** For every unit from `release_scope.list_release_units()` plus its bundled children, if any package directory under it holds an `_aggregate` file (follow `_shared` symlinks), load the project config the way `_apply_project_config` does (`_load_project_config_with_inheritance(project_path, env_vars)`) and assert `"BuildFlags: aggregate-checklocal" in cfg["project-config"]`. Assert at least one project was checked.

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Add the line** to `root/project.yaml`. If the test still fails for a project whose own `project.yaml` replaces rather than extends the inherited config, add the line there too.

- [ ] **Step 4: Run the Verify command** and `venv/bin/python -m pytest tests -q` → PASS

- [ ] **Step 5: Commit** `git commit -s -m "prjconf: enable aggregate-checklocal so frozen units pin their aggregates"`

---

### Task 5: Exact, strict dependency data

**Goal:** `_fetch_combined_depinfo` can return the union over every repository and architecture and report fetch failures instead of hiding them.

**Files:**
- Modify: `percona_obs/obs_api.py` (`_fetch_combined_depinfo` ~line 661, `_fetch_image_pkg_deps` ~line 610)
- Test: `tests/test_combined_depinfo.py`

**Acceptance Criteria:**
- [ ] New keyword-only parameters `all_targets: bool = False` and `failed: "set[str] | None" = None`. Defaults reproduce today's behaviour exactly (existing tests untouched and green).
- [ ] With `all_targets=True`, edges present only on a non-first repository or architecture are included.
- [ ] With `failed` given, a project whose `_builddepinfo` (or an image's `_buildinfo`) cannot be fetched is added to `failed` and the other projects' edges are still returned.

**Verify:** `venv/bin/python -m pytest tests/test_combined_depinfo.py -q` → all pass

**Steps:**

- [ ] **Step 1: Read `_fetch_combined_depinfo` and `_fetch_image_pkg_deps` in full**, and the existing fakes in `tests/test_combined_depinfo.py`.

- [ ] **Step 2: Write the failing tests**, reusing the file's fake-HTTP helpers:

```python
def test_all_targets_unions_repos_and_archs(...):
    # project P: repo R1/x86_64 has edge b->a; repo R2/aarch64 has edge c->a
    default = _fetch_combined_depinfo(api, {"P"}, local)
    exact = _fetch_combined_depinfo(api, {"P"}, local, all_targets=True)
    assert ("P", "a") in exact[("P", "c")] and ("P", "c") not in default

def test_failed_projects_are_reported(...):
    # _builddepinfo for Q raises HTTPError 500
    failed: set[str] = set()
    got = _fetch_combined_depinfo(api, {"P", "Q"}, local, all_targets=True, failed=failed)
    assert failed == {"Q"} and ("P", "b") in got
```

- [ ] **Step 3: Run** → FAIL

- [ ] **Step 4: Implement** the two parameters. Thread `failed` into the image query path so an image whose `_buildinfo` fails adds its project.

- [ ] **Step 5: Run the Verify command**, full suite, black, pyright → PASS

- [ ] **Step 6: Commit** `git commit -s -m "obs_api: exact and failure-reporting mode for combined depinfo"`

---

### Task 6: Dependency closure and stage plan (`propagate.py`, pure part)

**Goal:** Given the changed packages, the frozen projects and the dependency edges, decide what to trigger and in which order.

**Files:**
- Create: `percona_obs/propagate.py`
- Test: `tests/test_propagate_plan.py`

**Interfaces:**

```python
Pkg = tuple[str, str]                      # (obs_project, package)

@dataclass(frozen=True)
class Stage:
    wait_for: frozenset[Pkg]               # must be seen by the scheduler first
    trigger: dict[str, list[str]]          # frozen project -> packages to rebuild

def closure(seeds: set[Pkg], fwd_deps: dict[Pkg, set[Pkg]]) -> set[Pkg]
def plan_stages(seeds: set[Pkg], fwd_deps: dict[Pkg, set[Pkg]], frozen: set[str],
                project_order: list[str], aggregates: set[Pkg]) -> list[Stage]
def aggregate_edges(targets, env_vars) -> dict[Pkg, set[Pkg]]
def upstream_projects(apiurl: str, frozen: set[str], rootprj: str) -> set[str]
```

`fwd_deps[x]` is the set of packages `x` depends on (the shape `_fetch_combined_depinfo` returns). `closure` returns everything that depends, directly or indirectly, on a seed, seeds excluded.

**Acceptance Criteria:**
- [ ] Only packages in frozen projects are ever in a `trigger`; seeds are never triggered.
- [ ] Closure members in non-frozen projects appear in the `wait_for` of the first stage that follows them.
- [ ] Stages follow `project_order`; within one frozen project the aggregates are a stage of their own before the other packages.
- [ ] A dependency cycle does not loop forever.
- [ ] With no closure member in a frozen project the plan is `[]`.

**Verify:** `venv/bin/python -m pytest tests/test_propagate_plan.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
R, C, I, D = "r:u", "r:u:tarballs", "r:u:containers", "r:deps"
ORDER = [D, R, C, I]

def test_same_project_dependents_one_stage():
    fwd = {(R, "b"): {(R, "a")}, (R, "c"): {(R, "b")}}
    st = pp.plan_stages({(R, "a")}, fwd, {R}, ORDER, set())
    assert st == [pp.Stage(frozenset({(R, "a")}), {R: ["b", "c"]})]

def test_children_come_after_root_and_wait_for_it():
    fwd = {(R, "b"): {(R, "a")}, (I, "img"): {(R, "b")}, (C, "t"): {(R, "a")}}
    st = pp.plan_stages({(R, "a")}, fwd, {R, C, I}, ORDER, set())
    assert [s.trigger for s in st] == [{R: ["b"]}, {C: ["t"]}, {I: ["img"]}]
    assert (R, "b") in st[2].wait_for and (R, "a") in st[1].wait_for

def test_seed_outside_frozen_unit_reaches_it():
    fwd = {(D, "mid"): {(D, "lib")}, (R, "b"): {(D, "mid")}}
    st = pp.plan_stages({(D, "lib")}, fwd, {R}, ORDER, set())
    assert st[0].trigger == {R: ["b"]}
    assert {(D, "lib"), (D, "mid")} <= st[0].wait_for

def test_aggregates_first_within_project():
    fwd = {(R, "agg"): {(D, "lib")}, (R, "b"): {(R, "agg")}}
    st = pp.plan_stages({(D, "lib")}, fwd, {R}, ORDER, {(R, "agg")})
    assert [s.trigger for s in st] == [{R: ["agg"]}, {R: ["b"]}]
    assert (R, "agg") in st[1].wait_for

def test_nothing_frozen_downstream():
    assert pp.plan_stages({(R, "a")}, {(R, "b"): {(R, "a")}}, set(), ORDER, set()) == []

def test_cycle_terminates():
    fwd = {(R, "b"): {(R, "a"), (R, "c")}, (R, "c"): {(R, "b")}}
    assert pp.plan_stages({(R, "a")}, fwd, {R}, ORDER, set())[0].trigger == {R: ["b", "c"]}

def test_aggregate_edges_from_local_files(tmp_path):
    # package dir with obs/_aggregate naming project "${OBS_ROOTPRJ}:deps" and <package>lib</package>
    assert pp.aggregate_edges(targets, {"OBS_ROOTPRJ": "r"}) == {(R, "agg"): {(D, "lib")}}
```

Review Focus 5 lives here too:

```python
def test_failed_depinfo_triggers_whole_frozen_consumers():
    # expand_failed(failed={"r:deps"}, frozen={R, I}, consumers_of={"r:deps": {R}}, packages={R: ["a","b"], I: ["img"]})
    assert pp.expand_failed({D}, {R, I}, {D: {R}}, {R: ["a", "b"], I: ["img"]}) == {(R, "a"), (R, "b")}
```

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implement.** `aggregate_edges` reads each target's `_aggregate` file with the same `${...}` substitution `sync push` applies before upload (see the helper used around `cmd_sync.py:371`); an `<aggregate>` with no `<package>` children depends on every package of that project, represented as `(project, "*")` and matched as a wildcard in `closure`. `upstream_projects` returns the frozen projects plus, transitively, every `<path project>` under `rootprj` in their repositories. Add `expand_failed(failed, frozen, consumers_of, packages) -> set[Pkg]`: every package of each frozen project that is itself in `failed` or consumes a failed project; `plan_stages` callers add these to the closure.

- [ ] **Step 4: Run the Verify command**, black, pyright → PASS

- [ ] **Step 5: Commit** `git commit -s -m "propagate: dependency closure and staged rebuild plan"`

---

### Task 7: Running a plan: waits, triggers, `build propagate`

**Goal:** Execute a stage plan against OBS and expose it as a command.

**Files:**
- Modify: `percona_obs/propagate.py`, `percona_obs/cmd_build.py`, `percona_obs/cli.py` (after the `build status` parser)
- Test: `tests/test_propagate_run.py`

**Interfaces:**

```python
SEEN_TIMEOUT_S = 120
SEEN_POLL_S = 2
def trigger_rebuild(apiurl: str, obs_project: str, packages: list[str]) -> None
def wait_seen(apiurl: str, pkgs: set[Pkg], since: dict[Pkg, str], timeout_s: float = SEEN_TIMEOUT_S,
              poll_s: float = SEEN_POLL_S, sleep=time.sleep, clock=time.monotonic) -> set[Pkg]   # returns the ones NOT seen
def run_stages(apiurl: str, stages: list[Stage], dry_run: bool) -> None
def propagate(apiurl: str, rootprj: str, seeds: set[Pkg], targets, env_vars, dry_run: bool) -> None
```

**Acceptance Criteria:**
- [ ] `trigger_rebuild` POSTs `/build/<project>?cmd=rebuild&package=...` in chunks of at most 50 packages.
- [ ] A package counts as seen on a target when its code is in `release_freeze.PENDING_PKG_CODES`, or its newest `_jobhistory` entry differs from the one recorded in `since`; targets where its code is `excluded` or `disabled` are ignored; a package is seen when all its remaining targets are.
- [ ] `run_stages` records `since` for a stage's packages immediately before triggering them, waits for `wait_for` before each trigger, and on timeout prints a warning naming the unseen packages and continues.
- [ ] `dry_run` prints seeds and every stage and sends no POST.
- [ ] `propagate` prints the equivalent `build propagate` command before the first wait.
- [ ] `percona-obs build propagate <obs_project>/<package> [...]` (full OBS names, the format of the sync report's `promoted` list) runs `propagate`; `--dry-run` supported.

**Verify:** `venv/bin/python -m pytest tests/test_propagate_run.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (fake `release_freeze.fetch_project_results`, the `_jobhistory` GET and `http_POST`; inject `sleep` and `clock` so no real time passes):

```python
def test_trigger_chunks(...):
    pp.trigger_rebuild("api", "P", [f"p{i}" for i in range(120)])
    assert [len(parse_qs(urlsplit(u).query)["package"]) for u in posts] == [50, 50, 20]
    assert all("cmd=rebuild" in u for u in posts)

def test_seen_when_pending_on_all_built_targets(...):
    # a: R1/x86_64 building, R2/x86_64 excluded
    assert pp.wait_seen("api", {("P", "a")}, since={}) == set()

def test_seen_when_jobhistory_moved(...):
    # a: succeeded everywhere, newest job id "7"; since[("P","a")] = "6"
    assert pp.wait_seen("api", {("P", "a")}, since={("P", "a"): "6"}) == set()

def test_timeout_returns_unseen(...):
    # a stays succeeded with unchanged job id; clock advances 2 s per sleep
    assert pp.wait_seen("api", {("P", "a")}, since={("P", "a"): "7"}, timeout_s=6) == {("P", "a")}

def test_run_stages_orders_wait_then_trigger(...):
    pp.run_stages("api", [Stage(frozenset({("P", "a")}), {"P": ["b"]}), Stage(frozenset({("P", "b")}), {"Q": ["img"]})], dry_run=False)
    assert events == ["wait:a", "trigger:P:b", "wait:b", "trigger:Q:img"]

def test_run_stages_continues_after_timeout(capsys, ...):
    # wait_seen returns {("P","a")} for stage 1
    assert "trigger:P:b" in events and "not seen" in capsys.readouterr().out

def test_dry_run_sends_nothing(capsys, ...):
    pp.run_stages("api", stages, dry_run=True)
    assert posts == [] and "P: b" in capsys.readouterr().out
```

Plus a CLI test: `build propagate r:u/a r:deps/lib --dry-run` calls `propagate` with seeds `{("r:u","a"),("r:deps","lib")}`; an argument without `/` exits non-zero.

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implement.** `propagate` composes the pieces: frozen set from `unit_freeze.frozen_projects` over every release unit project (return at once when none is frozen); `upstream_projects`; `_fetch_combined_depinfo(..., all_targets=True, failed=failed)` over seed projects plus upstream projects, with image packages passed the way `cmd_sync` builds `image_pkgs`; merge `aggregate_edges`; apply `expand_failed`; `plan_stages` with projects ordered so a project comes after every project in its repository paths; `run_stages`. For seeds, `since` is empty and "seen" additionally accepts a newest job whose `srcmd5` equals the package's current source `srcmd5`.

- [ ] **Step 4: Run the Verify command**, full suite, black, pyright → PASS

- [ ] **Step 5: Commit** `git commit -s -m "propagate: staged rebuild triggers and the build propagate command"`

---

### Task 8: `sync push` integration

**Goal:** A sync that changes something reaching a frozen unit propagates it, and says so.

**Files:**
- Modify: `percona_obs/cmd_sync.py` (after the orphan cleanup and before `_write_report()`, ~line 2209; and where `rebuild_projects` is filled from `project_changed`)
- Test: `tests/test_sync_push_propagation.py`

**Acceptance Criteria:**
- [ ] After uploads, when `promoted_uploads` is non-empty and the sync is not a `--branch-from` sync, `propagate.propagate` is called once with the uploaded packages as seeds and the sync's `dry_run`.
- [ ] A `--branch-from` sync, or a sync that uploaded nothing, never calls it and makes no freeze-state request for it.
- [ ] For every frozen project whose meta or prjconf this sync changed, one warning line is printed: `warning: <project> is frozen: the project meta/config change rebuilds nothing; run 'build propagate' or unfreeze if it needs a rebuild`.
- [ ] For every frozen project that received an upload, one notice line is printed: `<project>  frozen (rebuild=local): dependents are rebuilt by the tool`.
- [ ] If `propagate` raises, the sync still writes its report and manifest, then exits non-zero.

**Verify:** `venv/bin/python -m pytest tests/test_sync_push_propagation.py -q` → all pass

**Steps:**

- [ ] **Step 1: Extract the decision into a testable function** in `cmd_sync.py`:

```python
def _propagate_after_push(apiurl: str, args, promoted_uploads: "list[str]",
                          config_changed_projects: "set[str]", targets, env_vars, dry_run: bool) -> None
```

- [ ] **Step 2: Write the failing tests** against it (monkeypatch `propagate.propagate` and `unit_freeze.frozen_projects`):

```python
def test_calls_propagate_with_uploaded_seeds(...):
    cs._propagate_after_push("api", args(branch_from=None), ["r:u/a", "r:deps/lib"], set(), [], {}, False)
    assert calls == [({("r:u", "a"), ("r:deps", "lib")}, False)]

def test_skipped_for_branch_from(...):
    cs._propagate_after_push("api", args(branch_from="main"), ["r:u/a"], {"r:u"}, [], {}, False)
    assert calls == [] and frozen_queries == []

def test_skipped_when_nothing_uploaded_and_no_config_change(...):
    cs._propagate_after_push("api", args(branch_from=None), [], set(), [], {}, False)
    assert calls == [] and frozen_queries == []

def test_warns_on_config_change_in_frozen_project(capsys, ...):
    # frozen_projects -> {"r:u": "frozen"}
    cs._propagate_after_push("api", args(branch_from=None), [], {"r:u", "r:x"}, [], {}, False)
    out = capsys.readouterr().out
    assert "warning: r:u is frozen" in out and "r:x" not in out

def test_notice_for_upload_into_frozen_project(capsys, ...):
    assert "r:u  frozen (rebuild=local)" in out
```

- [ ] **Step 3: Run** → FAIL

- [ ] **Step 4: Implement** the function; collect `config_changed_projects` where `_apply_project_config` returns `project_changed`; call it before `_write_report()` inside a `try`/`finally` arrangement that satisfies the last acceptance criterion.

- [ ] **Step 5: Run the Verify command**, full suite, black, pyright → PASS

- [ ] **Step 6: Commit** `git commit -s -m "sync push: propagate changes into frozen units"`

---

### Task 9: Workflows

**Goal:** The manual freeze workflow and the nightly frozen-units warning.

**Files:**
- Create: `.github/workflows/obs-freeze.yml`
- Modify: `.github/workflows/sync-main.yml` (new step after "Sync to OBS")
- Test: `tests/test_obs_freeze_workflow.py`

**Acceptance Criteria:**
- [ ] `obs-freeze.yml` has only a `workflow_dispatch` trigger with inputs `units` (required string, description as in `obs-release-cut.yml`) and `action` (required `choice`: `freeze`, `unfreeze`).
- [ ] It validates the units with `python3 .github/scripts/release_cut.py check -- <units>` before any OBS step.
- [ ] One matrix leg per `fromJSON(vars.OBS_INSTANCES)` entry, with `fail-fast: false`, `concurrency.group: obs-freeze-${{ matrix.instance.name }}`, `cancel-in-progress: false`, the same runner, container, `obs-setup` step and profile-creation step as the `sync` job of `sync-main.yml`.
- [ ] It runs `venv/bin/python -m percona_obs -P main project ${ACTION} <units>` with inputs passed through `env:` (never interpolated into the script) and appends the output to `$GITHUB_STEP_SUMMARY`.
- [ ] `sync-main.yml` runs `project freeze-status --github-warning` on scheduled runs only, with `if: github.event_name == 'schedule'`, and its failure does not fail the job (`continue-on-error: true`).

**Verify:** `venv/bin/python -m pytest tests/test_obs_freeze_workflow.py -q` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**: load both YAML files with `yaml.safe_load` and assert each acceptance criterion structurally (trigger keys, input types and options, concurrency group string, `fail-fast`, that no `run:` block contains `${{ inputs.`, the `if:` and `continue-on-error` of the new step). `tests/test_dashboard_contract.py` shows how workflow files are loaded in this repo.

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Write `obs-freeze.yml`** and add the step to `sync-main.yml`. Copy the profile-creation step from `sync-main.yml` verbatim so the instance slice flags match.

- [ ] **Step 4: Run the Verify command** and `bash -n` on each extracted `run:` block → PASS

- [ ] **Step 5: Commit** `git commit -s -m "ci: manual freeze/unfreeze workflow and nightly frozen-units warning"`

---

### Task 10: Documentation and rehearsal runbook

**Goal:** The tool reference describes the feature and how to rehearse it before production use.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md`, `CLAUDE.md` (Key Files table), `.github/copilot-instructions.md` (key files / architecture section)

**Acceptance Criteria:**
- [ ] `docs/PERCONA_OBS_TOOL.md` has a "Freezing a release unit" section covering: what frozen means, the three `project` commands, the workflow, what `sync push` does for a late fix, `build propagate` and when to run it by hand (a sync that failed after uploading; a prjconf or path change in a frozen project), and that unfreezing starts the postponed rebuilds.
- [ ] The same section has a "Rehearsal before first production use" list with the three checks from spec section 8, each with the exact commands and the observation that means it passed.
- [ ] `CLAUDE.md` and `.github/copilot-instructions.md` list `percona_obs/unit_freeze.py` and `percona_obs/propagate.py` with one-line purposes.

**Verify:** `grep -c "Freezing a release unit\|Rehearsal before first production use" docs/PERCONA_OBS_TOOL.md` → `2`; `grep -c "unit_freeze.py\|propagate.py" CLAUDE.md` → `2`

**Steps:**

- [ ] **Step 1: Write the section**, using the command names and output wording from Tasks 2, 7 and 8 exactly.
- [ ] **Step 2: Add the key-file rows.**
- [ ] **Step 3: Run the Verify commands.**
- [ ] **Step 4: Commit** `git commit -s -m "docs: freezing a release unit"`
