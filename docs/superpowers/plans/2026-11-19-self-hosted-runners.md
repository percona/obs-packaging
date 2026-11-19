# Self-Hosted Runners Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every workflow job in this repository runs on the team's self-hosted runner pool, with a one-variable switch back to GitHub-hosted runners.

**Architecture:** Each job's `runs-on` reads a repository variable and falls back to `ubuntu-latest` when the variable is unset. A unit test keeps new jobs from hardcoding a runner. The pool itself is built and operated elsewhere; this repository knows only two runner labels.

**Tech Stack:** GitHub Actions workflow YAML, pytest, `gh` CLI.

**Spec:** The runner pool design lives in the private infrastructure repository. This plan implements its "what obs-packaging changes" section, restated in full under Global Constraints. Nothing else from that design belongs in this public repository.

## Global Constraints

- Runner labels: `obs-ci` (30 small runners) and `obs-ci-large` (2 larger runners).
- Repository variables: `CI_RUNNER` and `CI_RUNNER_LARGE`.
- Exact expressions, no variations:
  - `runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}`
  - `runs-on: ${{ vars.CI_RUNNER_LARGE || 'ubuntu-latest' }}`
- Only the `build` job in `build-obs-image.yml` uses the large expression. The other 31 jobs use the small one.
- Jobs that call a reusable workflow (`uses:`) have no `runs-on` and stay as they are.
- No host names, addresses or infrastructure details in any file, commit message or PR text.
- Commits: `git commit -s`, no Claude attribution. No push, PR, variable or setting change without the owner's go.

**User decisions (already made):**
- "all worflows, I don't want to compete for runners against other percona repos."
- Prepare for external contributions: fork PR approval becomes "all external contributors" before any pull-request workflow uses the pool.
- Rollout starts with `python-tests`.

## Review Focus

1. A fork PR may not receive repository variables. Expected: the job then falls back to `ubuntu-latest`, which is safe. Confirm on the first fork PR; do not rely on it for security.
2. `actions/setup-python` on a self-hosted runner downloads Python 3.13 instead of finding it preinstalled. Expected: `python-tests` passes; covered by the canary in Task 3.
3. Job containers need Docker on the runner. Expected: `project-config-check` passes; covered by the canary in Task 3.
4. `cache-from: type=gha` in `build-obs-image.yml` on a self-hosted runner. Expected: build and push succeed; covered in Task 4.
5. A burst above 30 jobs queues instead of running at once. Expected: release QA fan-out finishes, somewhat later. Watch the first release.

---

### Task 1: Guard test

**Goal:** A pytest that fails when any workflow job hardcodes its runner.

**Files:**
- Create: `tests/test_workflow_runners.py`
- Modify: `.github/workflows/python-tests.yml` (add `'.github/workflows/**'` to `on.pull_request.paths`, replacing the single `python-tests.yml` entry)

**Acceptance Criteria:**
- [ ] The test fails on the unchanged tree, naming offending `file:job` pairs.
- [ ] `python-tests` runs on any PR that touches a workflow file.

**Verify:** `venv/bin/python -m pytest tests/test_workflow_runners.py -q` → 1 failed, listing 32 jobs.

**Steps:**

- [ ] **Step 1: Write the test.** Follow `tests/test_dashboard_contract.py` for locating `.github/workflows` and loading YAML.

```python
SMALL = "${{ vars.CI_RUNNER || 'ubuntu-latest' }}"
LARGE = "${{ vars.CI_RUNNER_LARGE || 'ubuntu-latest' }}"
LARGE_JOBS = {("build-obs-image.yml", "build")}


def test_every_job_uses_the_runner_variable():
    bad = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        jobs = yaml.safe_load(path.read_text())["jobs"]
        for name, job in jobs.items():
            if "uses" in job:
                continue
            want = LARGE if (path.name, name) in LARGE_JOBS else SMALL
            if job.get("runs-on") != want:
                bad.append(f"{path.name}:{name}")
    assert not bad, f"jobs not using the runner variable: {bad}"
```

- [ ] **Step 2: Run it.** Expected: FAIL listing 32 jobs.
- [ ] **Step 3: Widen the `python-tests.yml` path filter.**
- [ ] **Step 4: Commit** (`ci: guard test for workflow runner selection`). The test is red until Task 2; both land in one PR.

### Task 2: Switch all jobs to the variable

**Goal:** All 32 jobs select their runner through the variable.

**Files:**
- Modify: all 14 files in `.github/workflows/*.yml` (32 `runs-on: ubuntu-latest` lines)
- Modify: `docs/PERCONA_OBS_TOOL.md` or the CI section of `.github/copilot-instructions.md`, whichever already describes CI: add three lines on the two variables and how to return to hosted runners.

**Acceptance Criteria:**
- [ ] `grep -c "runs-on: ubuntu-latest" .github/workflows/*.yml` sums to 0.
- [ ] Guard test passes.
- [ ] The diff touches only `runs-on` lines in workflow files.

**Verify:** `venv/bin/python -m pytest tests -q` → all pass; `venv/bin/black --check percona_obs/ tests/` and `venv/bin/pyright` → clean.

**Steps:**

- [ ] **Step 1:** Replace every `runs-on: ubuntu-latest` with the small expression.
- [ ] **Step 2:** Change `build-obs-image.yml` job `build` to the large expression.
- [ ] **Step 3:** Add the documentation lines.
- [ ] **Step 4:** Run Verify, then commit (`ci: select runners through repository variables`).

### Task 3: Canary on the pull request

**Goal:** Prove a plain job and a container job pass on the pool before `main` changes.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none.

**Acceptance Criteria:**
- [ ] Fork approval policy reads `all_external_contributors`.
- [ ] At least 30 `obs-ci` runners are online.
- [ ] On the PR, `python-tests` and `project-config-check` each ran on a runner whose name is not GitHub-hosted, and passed.
- [ ] `main` workflows still ran on hosted runners meanwhile.

**Verify:** `gh run view <run-id> --json jobs --jq '.jobs[] | [.name, .conclusion, .runnerName] | @tsv'` for both PR runs → `success`, runner name from the pool.

**Steps (each needs the owner's go):**

- [ ] **Step 1:** `gh api -X PUT repos/percona/obs-packaging/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors`, then read it back.
- [ ] **Step 2:** Confirm the pool: `gh api repos/percona/obs-packaging/actions/runners --paginate --jq '[.runners[] | select(.status=="online")] | length'`.
- [ ] **Step 3:** `gh variable set CI_RUNNER --body obs-ci -R percona/obs-packaging`. `main` does not read it yet, so nothing else moves.
- [ ] **Step 4:** Push the branch to the `percona` remote and open the PR. It touches `python-tests.yml` and `project-config-check.yml`, so both run from the PR's own workflow files.
- [ ] **Step 5:** Run Verify. On failure: `gh variable delete CI_RUNNER`, re-run to confirm the hosted fallback, report what the runner image lacks to the pool's owner.

### Task 4: Merge and switch the large runner

**Goal:** `main` runs on the pool, including the image build.

**Files:** none.

**Acceptance Criteria:**
- [ ] PR merged by the owner.
- [ ] `gh variable set CI_RUNNER_LARGE --body obs-ci-large` done.
- [ ] One `build-obs-image` run on `main` (`gh workflow run build-obs-image.yml`) succeeded on an `obs-ci-large` runner.
- [ ] The next scheduled `sync-main` and `obs-stale-cleanup` runs succeeded on the pool.

**Verify:** same `gh run view` query as Task 3 for each run.

**Rollback at any time:** `gh variable delete CI_RUNNER` and `gh variable delete CI_RUNNER_LARGE`. No commit needed.
