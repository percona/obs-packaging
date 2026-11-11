# Dashboard Release Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a release drivable from the OBS dashboard: a dispatchable cut workflow, a label-gated pre-release sync, a Jenkins build annotation per QA lane, stable names, and a machine-readable release unit list.

**Architecture:** Tool changes live in `percona_obs/` (unit list, GitHub annotations, `project release --yes`). Workflow decisions that can be wrong in costly ways (populate gate, cut summary) are pure functions in `.github/scripts/` with pytest tables; the YAML only wires them. A contract test reads the workflow files and pins every name the dashboard depends on.

**Tech Stack:** Python 3 (`percona_obs`, stdlib + pyyaml), GitHub Actions YAML, bash, jq, `gh`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-11-dashboard-release-contract-design.md`

## Global Constraints

- Work in a git worktree `.claude/worktrees/dashboard-release-contract` off `percona/main`; copy the spec and this plan into it (both are untracked in the primary checkout).
- After every Python change: `venv/bin/black percona_obs/ tests/` then `venv/bin/pyright` (0 errors), then the task's pytest command.
- Commits: `git commit -s`, no `Co-Authored-By`, no Claude attribution anywhere.
- Never `git push`, `gh pr create`, add a label, or dispatch a workflow without asking the user first. Never run a write operation with `-P isv`.
- Contract strings (spec § 4) are exact: `obs-release-cut.yml`, `obs-release-pr.yml`, `obs-release.yml`, labels `obs-sync` / `qa-release`, run names `Cut <branch>` / `Release PR #<pr_number>`, job names `Populate pre-release (<instance>)`, `Wait for download CDN (<instance>)`, `Release to OBS (<instance>)`, `Publish GitHub releases and delete the pre-release`, `Delete the pre-release (<instance>)`, QA lane prefix `Release / OBS QA / `, artifacts `prerelease-report-<instance>` / `generated-changelogs`, annotation title `Jenkins build`, file `docs/versions/release-units.json`.
- No change to release contents, ids, tags, the freeze, the record check or hop 2. The CLI flow keeps working.
- Workflow inputs reach scripts through `env:`, never `${{ }}` interpolation inside a `run:` body.

**User decisions (already made):** none beyond the spec.

**Decisions this plan makes (flagged for approval):**

1. Three PRs, in spec delivery order: PR 1 = Tasks 1-3 (no behaviour change), PR 2 = Task 4 (sync gate, changes the manual flow), PR 3 = Task 5 (cut workflow). Task 6 (rehearsal) runs after PR 3 is on `main`, because `workflow_dispatch` needs the workflow file on the default branch.
2. The populate decision moves into `release_pr.py` (`should_populate`, output `populate`), as the spec allows; `run_sync` is still a `resolve` output.
3. The cut job is one job that needs credentials for every instance. `secrets[format(...)]` cannot be looped outside a matrix, so one step receives `toJSON(secrets)` and writes the extra oscrc sections. Only that step sees the secrets.
4. `::error::` reasons come from one place: `cli.main()` turns a `SystemExit("error: …")` into an annotation when `GITHUB_ACTIONS=true`. This covers `project release`, `sync prerelease` and the hop-2 dry-run without per-workflow log scraping.
5. "The PR comment says the sync starts once `obs-sync` is added": the comment is posted by the populate job, which no longer runs before the label. So `resolve` prints a `::notice::` when a release PR has no `obs-sync`, and the populate comment's repopulate line names the label. No comment is posted before the first populate.
6. `project release` gets `--yes` (it prompts today; `sync delete` already has `--yes`).
7. Spec § 7 "Amended commit": the optional tree comparison is not built.

## Review Focus

1. `units` input that is empty, repeats a unit, names a bundled child (`ppg:staging:18:containers`) or an unknown project: the cut fails before any OBS call with an `::error::` naming the unit (Task 5, `check_units` tests).
2. Changelog section extraction when the id is the last section of the file, and when one id is a prefix of another (`18.6-1` vs `18.6-10`): exact section returned, nothing from the neighbour (Task 5, `changelog_section` tests).
3. Annotation text containing a newline, `%` or `::`: one well-formed workflow command, nothing leaks into a second line (Task 2 tests).
4. `labeled` with `qa-release` on a PR that already carries `obs-sync` must not repopulate; `labeled` with `obs-sync` must; `workflow_dispatch` populates without the label (Task 4 table test).
5. A staging namespace root whose only packages sit in nested units (`ppg:staging:common`) is not listed, and a unit with packages only in `containers/` is (Task 1 tests).

---

### Task 1: `project release-units` and `docs/versions/release-units.json`

**Goal:** A git-only subcommand prints the release unit list as JSON, the output is committed, and CI fails when the two differ.

**Files:**
- Modify: `percona_obs/release_scope.py` (new `list_release_units`)
- Modify: `percona_obs/cmd_project.py` (new `cmd_project_release_units`), `percona_obs/cli.py` (parser, next to `project release`)
- Create: `docs/versions/release-units.json`
- Create: `tests/test_release_units.py`
- Modify: `.github/workflows/project-config-check.yml` (check step in the static job; add `docs/versions/release-units.json` to `paths`)
- Modify: `docs/PERCONA_OBS_TOOL.md` (subcommand reference)

**Acceptance Criteria:**
- [ ] `venv/bin/python -m percona_obs project release-units` needs no profile and prints a JSON list of `{unit, members, release_project, release_dir}`, sorted by `unit`, two-space indent, trailing newline.
- [ ] On the current tree the units are exactly: `ppg:staging:14`, `:15`, `:16`, `:16:extras`, `:16:tde`, `:17`, `:17:extras`, `:18`, `:18:extras`, `:19`, `ppg:staging:common:tools`, `ppg:staging:common:upgrade` (plus any unit nested below those that has packages). `ppg:staging`, `ppg:staging:common`, `_shared` and bundled children are absent.
- [ ] `ppg:staging:18` has members `[ppg:staging:18, ppg:staging:18:containers, ppg:staging:18:tarballs]`, `release_project` `ppg:releases:18`, `release_dir` `root/ppg/releases/18`.
- [ ] The committed file is byte-identical to the command output; the CI step fails with a message naming `percona-obs project release-units` when it is not.

**Verify:** `venv/bin/python -m pytest tests/test_release_units.py -q` → all pass; `venv/bin/python -m percona_obs project release-units | diff - docs/versions/release-units.json` → no output.

**Steps:**

- [ ] **Step 1: Write failing tests** in `tests/test_release_units.py`. Build fake trees under `tmp_path` the way `tests/test_release_scope.py` does (read it for the package fixture shape). Tests, each calling `list_release_units(root)`:
  - `test_major_bundles_containers_and_tarballs`: `ppg/staging/18` with a package, `containers/` and `tarballs/` projects → one entry, `members == ["ppg:staging:18", "ppg:staging:18:containers", "ppg:staging:18:tarballs"]`, `release_project == "ppg:releases:18"`, `release_dir == "root/ppg/releases/18"`.
  - `test_nested_units_listed_separately`: `18/extras` (own package + `containers/`) and `16/tde` → `ppg:staging:18:extras` with members `[…:extras, …:extras:containers]`, `release_dir == "root/ppg/releases/18/extras"`.
  - `test_namespace_root_omitted`: `staging/common` with `project.yaml` and no packages, `common/tools` with a package → only `ppg:staging:common:tools`, `release_project == "ppg:releases:common:tools"`.
  - `test_unit_with_packages_only_in_containers_listed`.
  - `test_shared_dir_and_bundled_children_omitted`: `_shared/` and `18/containers` never appear as `unit`.
  - `test_never_released_unit_listed`: no `releases/` directory at all → unit still listed.
  - `test_sorted_by_unit`.
  - `test_committed_file_matches_tree`: `Path("docs/versions/release-units.json").read_text() == json.dumps(list_release_units(), indent=2) + "\n"` (repo root resolved from `__file__`).
- [ ] **Step 2: Run** `venv/bin/python -m pytest tests/test_release_units.py -q` → FAIL (`list_release_units` missing).
- [ ] **Step 3: Implement** `list_release_units(root: Path = REPO_ROOT) -> "list[dict]"` in `release_scope.py`. For every `<root>/<product>/staging` directory, walk depth-first with the existing `nested_unit_dirs`; a directory is a unit when `any(unit_packages(path, project_id))`; members come from `release_unit_members`; `release_project` from `release_location(project_id).release_project`; `release_dir` is `"root/" + release_project.replace(":", "/")` (do not use `ReleaseLocation.release_dir`: it is absolute and bound to the real tree). Recurse into every directory, unit or not. Return sorted by `unit`.
- [ ] **Step 4: Add** `cmd_project_release_units(args)` (writes `json.dumps(units, indent=2) + "\n"` to stdout, nothing else) and the `release-units` parser with help "Print every releasable staging unit as JSON (reads the git tree only)."
- [ ] **Step 5: Generate** `venv/bin/python -m percona_obs project release-units > docs/versions/release-units.json`; check the acceptance list by eye.
- [ ] **Step 6: CI check.** In `project-config-check.yml`, static job, after `project verify --offline`:

```yaml
      - name: Check docs/versions/release-units.json is current
        run: |
          venv/bin/python -m percona_obs project release-units \
            | diff -u docs/versions/release-units.json - \
            || { echo "::error file=docs/versions/release-units.json::out of date; run: percona-obs project release-units > docs/versions/release-units.json"; exit 1; }
```

  Run it once per workflow run, not per matrix leg, if the static job is a matrix: guard with `if: strategy.job-index == 0`.
- [ ] **Step 7:** black, pyright, pytest (whole `tests/`), document the subcommand, commit `project: release-units subcommand and committed unit list`.

---

### Task 2: GitHub annotations (`Jenkins build` notice, error reasons)

**Goal:** `qa run` exposes the Jenkins build URL as a notice annotation, and every tool failure in Actions ends with an `::error::` line that states the reason.

**Files:**
- Modify: `percona_obs/common.py` (new `github_annotation`)
- Modify: `percona_obs/cmd_qa.py` (`_wait_and_record`, at the `started:` print, line ~991)
- Modify: `percona_obs/cli.py` (`main`, around `args.func(args)`)
- Modify: `percona_obs/cmd_sync.py` (the two `"error: prerelease dry-run failed"` / release dry-run raises near lines 2725 and 3029, and any other bare-reason raise found in Step 5)
- Create: `tests/test_github_annotations.py`

**Acceptance Criteria:**
- [ ] With `GITHUB_ACTIONS=true`, the first build that starts in a `qa run` process prints exactly `::notice title=Jenkins build::<project> <build_url>` on its own line, uncoloured; later builds in the same process print none; without the variable nothing is printed. `<project>` is the `qa run` project argument (`ppg:releases:18:containers`), which carries neither instance root nor PR prefix.
- [ ] With `GITHUB_ACTIONS=true`, a command that exits with `SystemExit("error: X")` also prints `::error::<project>: X` (just `X` when the command has no `project` argument) and the exit status is unchanged. Integer exits print nothing extra.
- [ ] Newlines, `\r` and `%` in a message are encoded (`%0A`, `%0D`, `%25`).
- [ ] The not-green and dry-run failure messages of `sync prerelease` and `sync release` contain the failing items themselves, not only in preceding `✗` lines.
- [ ] No other `qa run` output changes.

**Verify:** `venv/bin/python -m pytest tests/test_github_annotations.py tests/test_sync_prerelease.py tests/test_sync_release.py -q` → all pass.

**Steps:**

- [ ] **Step 1: Failing tests** (`capsys`, `monkeypatch.setenv/delenv("GITHUB_ACTIONS")`):
  - `test_annotation_noop_outside_actions`: `github_annotation("notice", "x")` prints nothing.
  - `test_annotation_formats`: `github_annotation("notice", "p u", title="Jenkins build")` → `"::notice title=Jenkins build::p u\n"`; `github_annotation("error", "a\nb 50%")` → `"::error::a%0Ab 50%25\n"`.
  - `test_jenkins_notice_once_per_process`: call the new `_emit_jenkins_notice("ppg:releases:18", "https://j/job/x/1/")` twice (reset the module flag first) → exactly one line `::notice title=Jenkins build::ppg:releases:18 https://j/job/x/1/`.
  - `test_wait_and_record_emits_notice`: monkeypatch `cmd_qa.wait_for_start` to return a URL and `wait_for_finish` to return `"SUCCESS"`, `save_state` to a no-op; a `RunState` with `project="ppg:releases:18:containers"` and one combo → the notice line is in stdout with that project.
  - `test_main_annotates_string_exit`: `monkeypatch.setattr(sys, "argv", ["percona-obs", "project", "release", "ppg:nope:1"])`, run `cli.main()` under `pytest.raises(SystemExit)` → stdout contains `::error::ppg:nope:1: project release requires a staging-tier source`.
  - `test_main_does_not_annotate_outside_actions`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `github_annotation(level: str, message: str, title: "str | None" = None) -> None` in `common.py`: returns unless `os.environ.get("GITHUB_ACTIONS") == "true"`; prints to stdout with `flush=True`.
- [ ] **Step 4: Implement** in `cmd_qa.py` a module flag `_jenkins_notice_emitted` and `_emit_jenkins_notice(project: str, build_url: str) -> None`; call it with `state.project` right after the `started:` print. In `cli.main()`, wrap `args.func(args)`: on `SystemExit` whose `code` is a `str`, strip a leading `error: `, prefix `f"{args.project}: "` when `getattr(args, "project", None)` is a string, call `github_annotation("error", …)`, re-raise.
- [ ] **Step 5: Audit** every `raise SystemExit` reachable from `cmd_sync_prerelease`, from `cmd_sync_release` with `--from` / `--dry-run`, and in `release_copy.py`. Where the reason is printed only in earlier lines (the `failures` lists), append it: `"error: prerelease dry-run failed: " + "; ".join(failures)`. Adjust the existing tests that match those strings.
- [ ] **Step 6:** black, pyright, full pytest, commit `tool: GitHub annotations for Jenkins builds and failure reasons`.

---

### Task 3: Stable names, `obs-release.yml` run name, report format, contract test

**Goal:** Every name the dashboard depends on is marked as a contract and pinned by a test; the final sync run is findable by name; the populate report format is documented.

**Files:**
- Modify: `.github/workflows/obs-release.yml` (`run-name`, contract comments)
- Modify: `.github/workflows/obs-release-pr.yml`, `.github/workflows/obs-pr-cleanup.yml` (contract / behaviour comments only)
- Create: `tests/test_dashboard_contract.py`
- Modify: `docs/PERCONA_OBS_TOOL.md` (report format, stable names table), `.github/copilot-instructions.md`

**Acceptance Criteria:**
- [ ] `obs-release.yml` has `run-name: Release PR #${{ inputs.pr_number }}`.
- [ ] A comment `# Dashboard contract (docs/superpowers/specs/2026-11-11-dashboard-release-contract-design.md § 4): do not rename.` sits next to each contract name in the three workflows.
- [ ] `tests/test_dashboard_contract.py` fails when any § 4 string in `obs-release-pr.yml` or `obs-release.yml` changes.
- [ ] `obs-pr-cleanup.yml` carries a comment stating that neither it nor `obs-release.yml` needs the release branch after the merge or after an abandon (they use `merge_commit_sha`, the PR number, tags and `main`); verified by reading both files, with any use of `head.ref` reported instead of commented.
- [ ] `docs/PERCONA_OBS_TOOL.md` documents the report: JSON list, fields `project`, `prerelease`, `outcome` (`success`|`failure`), `source_commit`, `removals` (strings prefixed `package ` / `project `); fields may be added, these five are stable.

**Verify:** `venv/bin/python -m pytest tests/test_dashboard_contract.py -q` → all pass.

**Steps:**

- [ ] **Step 1: Failing test.** Load each workflow with `yaml.safe_load` (the `on:` key loads as `True`) and assert:

```python
PR = load("obs-release-pr.yml"); REL = load("obs-release.yml")
assert PR["jobs"]["populate"]["name"] == "Populate pre-release (${{ matrix.instance.name }})"
assert PR["jobs"]["cdn-wait"]["name"] == "Wait for download CDN (${{ matrix.instance.name }})"
assert PR["jobs"]["qa"]["name"] == "Release"            # + "OBS QA / …" from qa-fanout = "Release / OBS QA / "
assert PR["jobs"]["qa"]["uses"] == "./.github/workflows/qa-fanout.yml"
assert REL["run-name"] == "Release PR #${{ inputs.pr_number }}"
assert REL["jobs"]["release"]["name"] == "Release to OBS (${{ matrix.instance.name }})"
assert REL["jobs"]["finalize"]["name"] == "Publish GitHub releases and delete the pre-release"
assert REL["jobs"]["delete"]["name"] == "Delete the pre-release (${{ matrix.instance.name }})"
assert set(REL[True]["workflow_dispatch"]["inputs"]) == {"pr_number", "tags"}
```

  Also: the upload step of `populate` has `name: prerelease-report-${{ matrix.instance.name }}`; the raw text of `obs-release-pr.yml` contains `{project: $p, prerelease: $pre, outcome: $o, source_commit: $s, removals: $r}` and the label `'qa-release'` (the `obs-sync` assertions are added in Task 4); `percona_obs.cmd_qa` builds lane names starting with `"OBS QA"` (assert on the function at `cmd_qa.py:486`); `Path("docs/versions/release-units.json")` exists.
- [ ] **Step 2: Run** → FAIL on `run-name` only.
- [ ] **Step 3:** Add `run-name`, the comments, the docs. Confirm the § 7 behaviours by reading `obs-pr-cleanup.yml` and `obs-release.yml` and write the comment.
- [ ] **Step 4:** pytest, commit `workflows: pin the names the dashboard depends on`.

---

### Task 4: Sync gate on `obs-release-pr.yml`

**Goal:** A release PR populates only when it carries `obs-sync` (or on `workflow_dispatch`); adding the label starts the sync.

**Files:**
- Modify: `.github/scripts/release_pr.py` (`should_populate`, `populate` output)
- Modify: `.github/workflows/obs-release-pr.yml`
- Modify: `.github/scripts/post_pr_comment.py` (repopulate line)
- Modify: `tests/test_release_pr_script.py`, `tests/test_post_pr_comment.py`, `tests/test_dashboard_contract.py`
- Modify: `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md`, `root/ppg/releases/README.md`

**Acceptance Criteria:**
- [ ] The event table of spec § 2 holds (test below).
- [ ] `resolve` still runs classify, the one-in-flight guard and the fork refusal on every `opened` / `synchronize` / `reopened`, labelled or not; it outputs `run_sync` and `populate`.
- [ ] A release PR without `obs-sync` gets `::notice::pre-release sync not started: add the obs-sync label to this PR`.
- [ ] `unlabeled` is still not a subscribed event type.
- [ ] A changelog-only push still yields `kind=changelog` and `populate=false`.
- [ ] `cdn-wait` and `qa` conditions are unchanged.
- [ ] Docs state that a hand-opened release PR needs `obs-sync` to populate and that retry is remove-then-add.

**Verify:** `venv/bin/python -m pytest tests/test_release_pr_script.py tests/test_post_pr_comment.py tests/test_dashboard_contract.py -q` → all pass.

**Steps:**

- [ ] **Step 1: Failing table test** in `tests/test_release_pr_script.py`:

```python
@pytest.mark.parametrize("kind,event,action,label,run_sync,want", [
    ("release", "pull_request", "opened",      "",           False, False),
    ("release", "pull_request", "synchronize", "",           False, False),
    ("release", "pull_request", "reopened",    "",           True,  True),
    ("release", "pull_request", "synchronize", "",           True,  True),
    ("release", "pull_request", "labeled",     "obs-sync",   True,  True),
    ("release", "pull_request", "labeled",     "qa-release", True,  False),
    ("release", "pull_request", "labeled",     "qa-release", False, False),
    ("release", "workflow_dispatch", "",       "",           False, True),
    ("changelog", "pull_request", "synchronize", "",         True,  False),
    ("none",    "workflow_dispatch", "",       "",           True,  False),
])
def test_should_populate(kind, event, action, label, run_sync, want):
    assert release_pr.should_populate(kind, event, action, label, run_sync) is want
```

  Extend `test_cli_classify_push_reads_head_sha` (or add a sibling) to assert the `populate=` line written to `$GITHUB_OUTPUT` for env `EVENT_NAME` / `EVENT_ACTION` / `EVENT_LABEL` / `RUN_SYNC`. Contract test: `PR[True]["pull_request"]["types"] == ["opened", "synchronize", "reopened", "labeled"]`; the `resolve` `if` contains both `'obs-sync'` and `'qa-release'`; `PR["jobs"]["populate"]["if"] == "needs.resolve.outputs.populate == 'true'"`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `should_populate(kind: str, event_name: str, action: str, label: str, run_sync: bool) -> bool` and have `_cli_classify` write `populate=true|false` on every path that writes `kind=` (reading the four env vars; `RUN_SYNC == "true"`), plus the notice when `kind == "release"`, the event is not `workflow_dispatch` and `run_sync` is false.
- [ ] **Step 4: Workflow.**
  - `resolve.if`: `github.event.action != 'labeled' || github.event.label.name == 'qa-release' || github.event.label.name == 'obs-sync'`.
  - `ctx` step: add `echo "run_sync=$(echo "$DATA" | jq -r '[.labels[].name] | index("obs-sync") != null')"`; job outputs `run_sync` and `populate` (`steps.classify.outputs.populate`).
  - `classify` step env: `EVENT_NAME: ${{ github.event_name }}`, `EVENT_ACTION: ${{ github.event.action }}`, `EVENT_LABEL: ${{ github.event.label.name }}`, `RUN_SYNC: ${{ steps.ctx.outputs.run_sync }}`.
  - `populate.if`: `needs.resolve.outputs.populate == 'true'`.
  - Rewrite the header comment (populate is label-gated; retry = remove and re-add `obs-sync`; `unlabeled` must stay unsubscribed).
- [ ] **Step 5:** `post_pr_comment.py`: the repopulate line becomes "Repopulate: remove and re-add the `obs-sync` label, or `gh workflow run obs-release-pr.yml -f pr_number=N`". Update its test.
- [ ] **Step 6:** Read `obs-pr-check.yml` lines 70-150 and confirm that `obs-sync` on a release-only PR gates `sync` out there (`is_release_pr`); note it in `copilot-instructions.md`. Docs. pytest, commit `release PR: populate only with the obs-sync label`.

---

### Task 5: Cut workflow `obs-release-cut.yml`

**Goal:** Dispatching the workflow with `units` and `branch` produces a release branch holding exactly one commit on top of `main` and the `generated-changelogs` artifact, or pushes nothing.

**Files:**
- Modify: `percona_obs/cli.py`, `percona_obs/cmd_project.py` (`project release --yes`)
- Create: `.github/scripts/release_cut.py`
- Create: `.github/workflows/obs-release-cut.yml`
- Create: `tests/test_release_cut_script.py`
- Modify: `tests/test_project_release.py` (`--yes`), `tests/test_dashboard_contract.py`
- Modify: `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md`, `root/ppg/releases/README.md`

**Interfaces** (`.github/scripts/release_cut.py`, stdlib + yaml, no `percona_obs` import):
- `load_units(repo_dir: Path) -> dict[str, dict]` — `docs/versions/release-units.json` keyed by `unit`.
- `check_units(units: list[str], known: dict[str, dict]) -> list[str]` — error strings; empty list means valid.
- `release_id(release_dir: Path) -> str` — last `releases:` entry of `release.yaml` (string or `{tag: …}`), text after the first `/`.
- `changelog_section(text: str, release_id: str) -> "str | None"` — from the `## [<id>]` line up to, not including, the next line starting `## [`; ends with exactly one `\n`.
- CLI `release_cut.py check <unit>…` — prints `::error::<unit>: <reason>` per problem, exit 1.
- CLI `release_cut.py summarize --out <file> <unit>…` — writes `{unit: section}` JSON, prints `release: <id>, <id>…` (input order); exit 1 with `::error::` when a unit has no section for its id.

**Acceptance Criteria:**
- [ ] `project release --yes` skips the confirmation prompt; without it the prompt is unchanged.
- [ ] `check_units` rejects: no units, a repeated unit, a unit absent from the unit list (message says "not a release unit root"; a bundled child is absent by construction).
- [ ] The workflow has sole trigger `workflow_dispatch`, inputs `units` and `branch` (both required), `run-name: Cut ${{ inputs.branch }}`, concurrency group `obs-release-cut-${{ inputs.branch }}` with `cancel-in-progress: false`, permissions `contents: write`, `actions: read`, `packages: read`.
- [ ] A `branch` not matching `^release/[A-Za-z0-9._-]+$` fails in the first step.
- [ ] The push happens only after every unit was cut, the squash produced one commit and the summary succeeded; the artifact upload has no `if: always()`.
- [ ] The commit subject is `release: <id>, <id>…`, signed off, author `github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>`.
- [ ] The workflow never opens a pull request.

**Verify:** `venv/bin/python -m pytest tests/test_release_cut_script.py tests/test_project_release.py tests/test_dashboard_contract.py -q` → all pass; `venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/obs-release-cut.yml'))"` → no error.

**Steps:**

- [ ] **Step 1: Failing tests** in `tests/test_release_cut_script.py` (load the script with `importlib.util`, as `tests/test_release_pr_script.py` does):
  - `check_units([], known)` → one error; `check_units(["a", "a"], {"a": {}})` → error naming `a` as repeated; `check_units(["ppg:staging:18:containers"], {"ppg:staging:18": {}})` → `["ppg:staging:18:containers: not a release unit root"]`; valid input → `[]`.
  - `changelog_section("# h\n\n## [18.6-10] - d\n\nA\n\n## [18.6-1] - d\n\nB\n", "18.6-1")` → `"## [18.6-1] - d\n\nB\n"`; same text, id `18.6-10` → `"## [18.6-10] - d\n\nA\n"`; unknown id → `None`; an id containing `.` is matched literally (`18x6-1` must not match).
  - `release_id` for `releases: [ppg/18.6-5, {tag: ppg/18.6-6, source_commit: abc}]` → `"18.6-6"`; for `ppg/extras-18.6-6` → `"extras-18.6-6"`.
  - `summarize` over a tmp repo with two units → JSON has both unit keys, stdout is `release: 18.6-6, extras-18.6-6`.
  - `tests/test_project_release.py`: with `--yes`, `input` is never called (monkeypatch it to raise); follow the file's existing fixture for a cut.
  - Contract test: `CUT = load("obs-release-cut.yml")`; `CUT["run-name"] == "Cut ${{ inputs.branch }}"`; `list(CUT[True]) == ["workflow_dispatch"]`; inputs `{"units", "branch"}`; an upload step with `name: generated-changelogs`; raw text contains no `gh pr create`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `--yes` (`dest="yes"`, `action="store_true"`; the prompt block runs only when `not args.yes`) and `release_cut.py`.
- [ ] **Step 4: Write the workflow.**

```yaml
name: OBS Release Cut

# Cuts a release branch for the dashboard's Release tab (docs/superpowers/
# specs/2026-11-11-dashboard-release-contract-design.md § 1): one commit on
# top of main for every unit, force-pushed to <branch>.  Never opens the PR
# (a PR opened with the workflow token triggers nothing) and the push
# triggers nothing either: the sync starts when `obs-sync` is added.
# Dashboard contract (§ 4): file name, run-name, artifact name. Do not rename.

on:
  workflow_dispatch:
    inputs:
      units:
        description: "Release unit roots, space-separated (e.g. ppg:staging:18 ppg:staging:17:extras)"
        required: true
      branch:
        description: "Release branch to create or reset (release/<name>)"
        required: true

run-name: Cut ${{ inputs.branch }}

concurrency:
  group: obs-release-cut-${{ inputs.branch }}
  cancel-in-progress: false

permissions: {}

jobs:
  cut:
    name: Cut release
    runs-on: ubuntu-latest
    container: ghcr.io/${{ github.repository_owner }}/obs-tools:latest
    timeout-minutes: 60
    permissions:
      contents: write
      actions: read
      packages: read
    env:
      UNITS: ${{ inputs.units }}
      BRANCH: ${{ inputs.branch }}
    steps:
      - name: Validate the branch name
        shell: bash
        run: |
          [[ "$BRANCH" =~ ^release/[A-Za-z0-9._-]+$ ]] \
            || { echo "::error::branch '$BRANCH' must match release/[A-Za-z0-9._-]+"; exit 1; }

      - uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0
          fetch-tags: true

      - name: Validate the units
        shell: bash
        run: |
          read -r -a UNIT_LIST <<<"$UNITS"
          python3 .github/scripts/release_cut.py check "${UNIT_LIST[@]}"

      - uses: ./.github/actions/obs-setup
        with:
          obs-apiurl: ${{ fromJSON(vars.OBS_INSTANCES)[0].apiurl }}
          obs-user: ${{ fromJSON(vars.OBS_INSTANCES)[0].user || vars.OBS_USER }}
          obs-password: ${{ secrets[format('OBS_PASSWORD_{0}', fromJSON(vars.OBS_INSTANCES)[0].name)] }}

      # The changelog is built from every instance, so this one job needs
      # credentials for all of them.  secrets[...] cannot be looped outside a
      # matrix; this step alone receives the secrets and adds one oscrc
      # section per further instance.
      - name: Add osc credentials for the other instances
        shell: bash
        env:
          OBS_INSTANCES: ${{ vars.OBS_INSTANCES }}
          OBS_USER: ${{ vars.OBS_USER }}
          SECRETS: ${{ toJSON(secrets) }}
        run: |
          python3 - <<'PYEOF'
          import configparser, json, os, pathlib
          secrets = json.loads(os.environ["SECRETS"])
          p = pathlib.Path.home() / ".config" / "osc" / "oscrc"
          c = configparser.RawConfigParser()
          c.read(p)
          for inst in json.loads(os.environ["OBS_INSTANCES"])[1:]:
              c[inst["apiurl"]] = {
                  "user": inst.get("user") or os.environ["OBS_USER"],
                  "pass": secrets[f"OBS_PASSWORD_{inst['name']}".upper()],
              }
          with open(p, "w") as f:
              c.write(f)
          PYEOF

      # First OBS_INSTANCES entry = `main` (ids and versions come from it);
      # every further entry = `also-<name>`.  Same slice flags and instance
      # env as obs-release-pr.yml's populate job.
      - name: Create percona-obs profiles
        shell: bash
        env:
          OBS_INSTANCES: ${{ vars.OBS_INSTANCES }}
          MAIN_REPO_URL: ${{ github.server_url }}/${{ github.repository }}.git
        run: |
          set -euo pipefail
          n=$(jq length <<<"$OBS_INSTANCES")
          : > "$RUNNER_TEMP/also-profiles"
          for i in $(seq 0 $((n - 1))); do
            inst=$(jq -c ".[$i]" <<<"$OBS_INSTANCES")
            name=$(jq -r .name <<<"$inst")
            profile=main
            if [ "$i" -gt 0 ]; then profile="also-${name}"; echo "$profile" >> "$RUNNER_TEMP/also-profiles"; fi
            args=()
            for key in include_repos exclude_repos include_projects exclude_projects; do
              val=$(jq -r ".${key} // empty" <<<"$inst")
              if [ -n "$val" ]; then args+=("--${key//_/-}" "$val"); fi
            done
            env_args=()
            while IFS= read -r kv; do
              if [ -n "$kv" ]; then env_args+=(-e "$kv"); fi
            done <<<"$(jq -r '(.env // {}) | to_entries[] | "\(.key):\(.value)"' <<<"$inst")"
            venv/bin/python -m percona_obs -A "$(jq -r .apiurl <<<"$inst")" -R "$(jq -r .rootprj <<<"$inst")" \
              -e "REMOTE_OBS_ORG_INTERCONNECT:" -e "PERCONA_OBS_PACKAGING_BRANCH:main" \
              -e "PERCONA_OBS_PACKAGING_REPO:${MAIN_REPO_URL}" "${env_args[@]}" \
              profile create "$profile" "${args[@]}"
          done

      # Nothing is pushed unless every unit is cut: a partial release branch
      # must never exist.  The tool's SystemExit reason becomes an ::error::
      # annotation that names the unit (cli.main).
      - name: Cut every unit
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git rev-parse HEAD > "$RUNNER_TEMP/base"
          git switch -C "$BRANCH"
          also=()
          while IFS= read -r p; do
            if [ -n "$p" ]; then also+=(--also-profile "$p"); fi
          done < "$RUNNER_TEMP/also-profiles"
          read -r -a UNIT_LIST <<<"$UNITS"
          for unit in "${UNIT_LIST[@]}"; do
            echo "== project release ${unit}"
            venv/bin/python -u -m percona_obs -P main project release "$unit" --yes "${also[@]}"
          done

      - name: Squash into one commit and summarize
        shell: bash
        run: |
          set -euo pipefail
          BASE=$(cat "$RUNNER_TEMP/base")
          read -r -a UNIT_LIST <<<"$UNITS"
          SUBJECT=$(venv/bin/python .github/scripts/release_cut.py summarize \
            --out "$RUNNER_TEMP/changelogs.json" "${UNIT_LIST[@]}")
          git reset --soft "$BASE"
          git commit -s -m "$SUBJECT"
          [ "$(git rev-list --count "${BASE}..HEAD")" = 1 ] \
            || { echo "::error::expected exactly one release commit on top of main"; exit 1; }
          git status --porcelain | grep -q . \
            && { echo "::error::working tree not clean after the cut"; git status --short; exit 1; }
          echo "$SUBJECT"

      - name: Push the release branch
        shell: bash
        run: git push --force origin "HEAD:refs/heads/${BRANCH}"

      - name: Upload the generated changelogs
        uses: actions/upload-artifact@v4
        with:
          name: generated-changelogs
          path: ${{ runner.temp }}/changelogs.json
          retention-days: 30
```

  Check while writing: `profile create` flag spellings against `cli.py` (`--include-repos` …); that `summarize` runs with the venv python (it needs `yaml`); that `_resolve_source_commit` finds `gh` in the image and reads `PERCONA_OBS_PACKAGING_REPO` from the `main` profile.
- [ ] **Step 5:** Docs: the cut workflow, its inputs, that the PR is opened by the caller, the `gh workflow run obs-release-cut.yml -f units=… -f branch=release/…` form. black, pyright, full pytest, commit `workflows: obs-release-cut, a dispatchable release cut`.

---

### Task 6: Rehearsal on labs

**Goal:** The nine end-to-end steps of the spec's Testing section pass, driven by hand with `gh` exactly as the dashboard will.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-prerelease-rehearsal-runbook.md` (add the dashboard-flow steps)

**Acceptance Criteria:**
- [ ] `gh workflow run obs-release-cut.yml -f units=… -f branch=release/test1` → run named `Cut release/test1` succeeds; branch is `main` + 1 commit; artifact `generated-changelogs` present; no PR; no `obs-release-pr.yml` run.
- [ ] PR opened by hand → `Resolve release PR` runs, populate jobs skipped, notice about `obs-sync` shown.
- [ ] Changelog amended and force-pushed → no populate.
- [ ] `obs-sync` added → `Populate pre-release (<instance>)` runs; `prerelease-report-<instance>` present.
- [ ] `obs-sync` removed and re-added → populate runs again; the removal alone starts no run.
- [ ] `qa-release` added → QA-only run; every `Release / OBS QA / …` job has one `Jenkins build` notice with `<release project> <url>`.
- [ ] Cut dispatched again for the same branch (with a workflow-file change merged to `main` in between, to prove the workflow token can force-push over it) → branch reset on `main`, same release id.
- [ ] Merge (rebase) → run named `Release PR #N`; then deleting the branch breaks nothing.
- [ ] Separately: cut, open PR, delete the branch → PR closes, pre-release tree deleted by `obs-pr-cleanup.yml`.

**Verify:** `gh run list --workflow obs-release-cut.yml --json displayTitle,conclusion --limit 5` and `gh api repos/percona/obs-packaging/check-runs/<id>/annotations` output captured for each criterion.

**Steps:**

- [ ] **Step 1:** Ask the user which instance set and units to rehearse with, and for a go-ahead before each dispatch, label and merge (all outward-facing).
- [ ] **Step 2:** Run the nine steps, capture the output, record deviations.
- [ ] **Step 3:** Update the runbook; commit.
