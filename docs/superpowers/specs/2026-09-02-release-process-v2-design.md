# Release Process v2 — Design

**Date:** 2026-09-02
**Status:** Approved (design review in session)
**Scope:** `percona_obs/` release path, release-related GitHub workflows, `root/ppg/releases/` tree

## 1. Problem

The last releases (`ppg/17.10-1`, `ppg/18.4-1`, cut 2026-05-19) predate the
three-tier restructure (`root/ppg/{devel,staging,releases}/`), the containers
ubi8/ubi9 rework, and the `extras` / `tarballs` staging subprojects. An audit
(2026-09-02) found the release pipeline runs end-to-end without erroring but
would produce a wrong release. Key findings:

1. **Silent subproject skip.** `_sync_release_subprojects`
   (`percona_obs/cmd_sync.py:2203`) `continue`s when the mirror `project.yaml`
   is missing under `releases/<major>/`. Staging's `containers`, `extras`,
   `extras/containers`, and `tarballs` have no mirrors, so no container
   images, extras packages, or tarballs are released — and CI reports success.
2. **First-release-only generation.** Release subproject mirrors are generated
   only when `releases/<major>/` does not yet exist
   (`percona_obs/cmd_project.py:1792`). Since `releases/17` and `releases/18`
   exist, the gap can never self-heal. The stale `releases/<V>/containers/ubi9/`
   dirs (and their OBS projects, holding the May 2026 images) are orphaned.
3. **Stale release config.** `releases/17/project.yaml` lists 6 of staging's
   13 repos; the top-level release meta is never re-applied on the update
   path, while `_add_release_targets` (`percona_obs/obs_api.py:1817`) adds
   targets for all live source repos, including ones the target lacks.
4. **Tag on the wrong commit.** `sync-main.yml:248` tags `$GITHUB_SHA` (head
   of whatever push the poll job survived on), not the release commit. The
   `git diff <tag>..HEAD` divergence guard in `cmd_sync_release` then passes
   trivially; unrelated staging changes ship silently.
5. **Broken changelog generation.** Previous-release container diff queries
   `…:releases:<V>:containers` (the real project is `…:containers:ubi9`);
   ubi8/ubi9 flavors collapse into one entry (first-repo-wins keying,
   `cmd_project.py:1306`); `extras` and `tarballs` packages never appear
   (top-level-only version collection; `simpleimage` not detected).

Secondary: obs-pr-check advertises a "release dry-run" that does not exist
(`RELEASE_OUTCOME` hardcoded `''`); `post_pr_comment.py` release links use
`--diff-filter=A` (inert for update releases); obs-pr-cleanup computes
`is_release_pr` and never uses it, and the documented `sync release-pr` step
does not exist in the workflow; `obs-release.yml` uses a bare `sleep 60`, a
too-broad `*/*` tag glob, and tag-creation API failures are swallowed;
`project install` hardcodes the `images` repo name; `list_qa_matrix.py:51`
tests `":containers:"` and misclassifies the new `…:containers` projects;
assorted doc drift.

## 2. Decisions

Settled during design review:

| Decision | Choice |
|---|---|
| Release scope | **Full staging snapshot** — everything under `ppg:staging:<V>`, all subprojects included; exclusions must be explicit, never implicit |
| Release config source of truth | **Regenerated mirrors** — `project release` rewrites `releases/<V>/**/project.yaml` from staging on every release; the release PR reviews the snapshot |
| Old `:containers:ubi9` release projects | **Migrate at next release** — new `:containers` (ubi8+ubi9 repos) mirrors staging; old projects and local dirs are removed; registry paths change once |
| Tag creation | **Tag the release-PR merge commit** in obs-pr-cleanup using `GITHUB_TOKEN`; no build-poll gate (release PRs are review-only) |
| Release trigger | **`workflow_dispatch`, not tag push** — no usable PAT exists in the org, and `GITHUB_TOKEN`-created tags never trigger workflows; obs-pr-cleanup dispatches obs-release directly with the tag as input (the documented `workflow_dispatch` exception to trigger suppression) |
| Staging freeze | **Drain → verify green → freeze** inside `sync release`: wait for the OBS scheduler to quiesce, abort unless every staging package succeeded, disable builds for the duration of `osc release`, restore flags in a `finally` |
| Pre-merge validation | **Real `sync release --dry-run`** in obs-pr-check, outcome reported truthfully in the PR comment |
| Non-release PR binaries | **Rebuild on main** (status quo) — delete the dead `is_release_pr`-driven promotion design and the `sync release-pr` docs; PR projects are just deleted |
| Version-list publishing revival | **Out of scope** — separate effort |

## 3. Design

### 3.1 End-to-end flow

1. **Cut** — `percona-obs project release ppg:staging:<V>`. The source project
   must be a `staging`-tier project; any other tier is rejected with an error.
   On **every** release (not only the first) the command regenerates the full
   `root/ppg/releases/<V>/` mirror from staging's current config:
   - top-level `project.yaml` plus one nested mirror dir per staging
     subproject (`containers/`, `extras/`, `extras/containers/`, `tarballs/`);
   - all mirrors get `build: false`; `publish:` flags are carried over;
     subproject paths are rewritten to the release namespace, including
     intra-project sibling paths (the tarballs `ssl1.1`/`ssl3` repos consuming
     `…:tarballs/RockyLinux_8|9` are rewritten, not dropped);
   - mirror dirs whose staging source no longer exists are **deleted** — this
     is how `releases/<V>/containers/ubi9/` is retired;
   - the CHANGELOG section is generated (§3.2), the tag appended to
     `release.yaml`, and everything committed with `git commit -s`.
   Pushing the branch and opening the PR remain manual; docs are corrected to
   say so.
2. **Validate** — obs-pr-check detects a release-only PR and runs
   `sync release <releases-project> --dry-run`: read-only checks that every
   staging subproject has a mirror, the CHANGELOG section for the release ID
   exists, the tag does not already exist, the source OBS project is
   reachable, and every staging package currently reports `succeeded` (the
   drain-free variant of the §3.3 green check — a red staging surfaces at
   review time). The PR comment reports the genuine outcome. This job does
   not require the `obs-sync` label.
3. **Tag + dispatch** — obs-pr-cleanup, on close of a **merged** release PR:
   - tags `merge_commit_sha` using `GITHUB_TOKEN` (workflow permission
     `contents: write`). No PAT is involved — the org does not permit
     creating one, and none is needed because the tag is no longer the
     trigger;
   - dispatches obs-release.yml via `gh workflow run` with the tag as input
     (workflow permission `actions: write`). `workflow_dispatch` calls made
     with `GITHUB_TOKEN` are the documented exception to GitHub's
     workflow-trigger suppression, so the chain fires reliably;
   - tag-creation or dispatch API errors fail the job; only a genuine
     "tag already exists" response is tolerated. sync-main.yml loses its tag
     step entirely.
4. **Ship** — obs-release.yml (**sole trigger**: `workflow_dispatch` with a
   `tag` input; the `push: tags` trigger is removed entirely, so pushing a
   tag is inert by construction and manual recovery is
   `gh workflow run obs-release.yml -f tag=<tag>`) →
   `sync release ppg:releases:<V>`:
   - a staging subproject without a mirror is a **hard error**, never a skip;
   - **freeze sequence** (§3.3): drain the staging scheduler, assert every
     package succeeded, disable builds, release, restore flags;
   - the top-level release project meta is applied on the update path too;
   - release targets are added only for repos present on both sides;
   - release-tier OBS projects with no local mirror are reported loudly as
     orphans; deletion stays a manual `sync delete` (never automatic for
     published artifacts);
   - the `sleep 60` is replaced by a bounded poll verifying each released
     repo actually holds binaries;
   - GitHub release creation uses `GITHUB_TOKEN` (no release-event workflows
     exist, so trigger suppression is irrelevant there).
5. **Guard restored** — with the tag on the release commit,
   `git diff <tag>..HEAD -- <staging path>` is meaningful again.
   `--skip-tag-check` / `--force` remain as escape hatches (needed once for
   the pre-restructure tags, whose staging path did not exist at tag time).

### 3.2 Changelog generation

Follows "full snapshot":

- Package versions are collected from the top-level staging project **and**
  `extras` **and** `tarballs`.
- Container images are reported per flavor — ubi8 and ubi9 as distinct
  entries (per-repo fetch replaces the first-repo-wins keying).
- The previous-release image diff queries the project that actually holds the
  previous release's images: `…:containers:ubi9` for the migration release
  (one-time), `…:containers` thereafter — producing real `prev → new` diffs
  instead of full package dumps. A full dump remains only for a true first
  release.

### 3.3 Staging freeze during release

`osc release` must run against a staging project whose every package built
successfully and whose scheduler is idle — otherwise the release can copy a
mix of old and new binaries. `sync release` therefore wraps the release in a
freeze sequence (applies to manual recovery runs too, since it lives in the
tool, not the workflow):

1. **Drain** — poll `_result` for the staging project and all subprojects
   until no package is `building` / `scheduled` / `dispatching` / `blocked` /
   `finished` / `signing`. Bounded by a generous timeout that **fails the
   release** rather than waiting forever (a package stuck cycling must be
   fixed, not released around).
2. **Assert green** — every package `succeeded` (or legitimately `excluded` /
   `disabled`). Any `failed` / `unresolvable` / `broken` aborts the release.
   This ordering is load-bearing: the check must precede the freeze, because
   a disabled project reports `disabled` for everything and can no longer be
   verified.
3. **Freeze** — snapshot each project's meta, then set the `build disable`
   flag on staging and every subproject. Disabling aborts in-flight builds,
   which is safe only because the drain already emptied the queue. From this
   point a concurrent source upload (e.g. an unrelated merge) cannot change
   the binary state.
4. **Release** — `osc release` for the top level and every subproject,
   copying exactly the verified binaries.
5. **Restore** — in a `finally`, re-apply each project's **snapshotted** meta
   (never a blanket enable: subprojects carry per-repo flags — tarballs'
   publish flags among them — that must survive the round trip).

Complementary CI-side guard: obs-release.yml shares a concurrency group with
sync-main's `sync` job, so no source upload even starts while a release is in
flight. Project locking (`<lock>`) was considered and rejected: unlock is
admin-gated on many OBS instances and a lock does not stop in-flight builds.

The pre-merge dry-run (§3.1 step 2) also runs the drain-free variant of the
green check, so a red staging surfaces at review time, not at ship time.

### 3.4 Code touchpoints

- `percona_obs/cmd_project.py` — mirror regeneration on every release;
  stale-mirror deletion; staging-tier validation of the source argument;
  changelog fixes (§3.2); `_rewrite_subproject_paths` keeps intra-project
  sibling paths; `_container_registry_prefix` / `_repo_pkg_manager` derive
  image repo names from project config instead of the hardcoded `images`.
- `percona_obs/cmd_sync.py` / `percona_obs/obs_api.py` — hard error on
  missing mirror; update-path top-level meta apply; filtered
  `_add_release_targets`; orphan reporting; `--dry-run` mode for
  `sync release`; freeze sequence (drain poll, green assertion, meta
  snapshot/disable/restore — reusing the existing build-status polling).
- Workflows — `sync-main.yml` (remove tag step), `obs-pr-cleanup.yml` (tag on
  merge with `GITHUB_TOKEN` + `gh workflow run` dispatch of obs-release,
  permissions `contents: write` + `actions: write`, drop stale two-path
  comments), `obs-pr-check.yml` + `.github/scripts/post_pr_comment.py` (real
  dry-run outcome, drop `--diff-filter=A`), `obs-release.yml`
  (`workflow_dispatch` with `tag` input as the sole trigger — `push: tags`
  removed, verification poll, `GITHUB_TOKEN` for the GitHub
  release, concurrency group shared with sync-main's `sync` job). All
  remaining `secrets.GH_PAT` references in the release-path workflows
  (checkout steps, `gh release create`) migrate to `GITHUB_TOKEN` — the
  secret exists on the repo but is not an org-approved PAT and cannot be
  relied on.
- `.github/scripts/list_qa_matrix.py` — `:containers` typing fix (project
  names ending in `:containers`, not only containing `":containers:"`).
- Docs — `docs/PERCONA_OBS_TOOL.md` (nested mirror dirs, `project release`
  commits only), `.github/copilot-instructions.md` (tag format `ppg/17.9-1`,
  remove `sync release-pr` cleanup step), `root/README.md`.

### 3.5 Migration (one-time, at next release)

The first `project release` run under the new code regenerates everything;
its release PR **is** the migration — reviewers see the new `containers/`,
`extras/`, `extras/containers/`, `tarballs/` mirrors and the deletion of
`containers/ubi9/`. After the release ships and the new registry paths are
confirmed good, the old `ppg:releases:<V>:containers:ubi9` OBS projects are
removed manually with `sync delete`. Registry paths change once:
`…:containers:ubi9/images` → `…:containers/ubi8|ubi9`.

**Post-landing follow-up**: once the `workflow_dispatch`-only trigger is
live on percona/obs-packaging, the historical tags (`ppg/17.9-1` …
`ppg/18.4-1`) are pushed to the repo (user does this) — safe at that point
because pushed tags no longer trigger anything. Until then, pushing them
would fire the current `push: tags: ['*/*']` obs-release against production
OBS.

### 3.6 Testing

- Unit tests in the existing `tests/` pytest suite:
  - mirror regeneration against a fixture tree (creation, update, stale
    deletion, path rewriting including sibling repos);
  - `sync release` decision logic with mocked OBS responses (hard error on
    missing mirror, orphan detection, release-target filtering, dry-run);
  - freeze sequence: drain timeout aborts, red package aborts before any
    flag change, meta snapshot/restore round-trips per-repo flags exactly;
  - changelog generation per flavor and per subproject.
- Full rehearsal against the dev OBS (`-P dev`) in a scratch rootprj: cut,
  dry-run, tag-less manual `sync release` (including freeze/restore) —
  before trusting the CI path.
- CI pre-flight on percona/obs-packaging (which has **zero tags** and has
  never run obs-release): a one-off `workflow_dispatch` test proving the
  cleanup workflow can create a throwaway tag with `GITHUB_TOKEN` and
  dispatch obs-release with it, then delete the tag.

## 4. Out of scope

- Version-list publishing revival (the three `if: false` publishers) — a
  separate effort; the underlying script is already three-tier-aware.
- Reinstating `sync release-pr` binary promotion for non-release PRs —
  explicitly decided against; production rebuilds from source on main.
