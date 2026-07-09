# Spec: Three-Tier Per-Version OBS Project Structure (PG-2518)

**Date:** 2026-07-08
**Status:** Approved design, pending implementation plan
**Ticket:** [PG-2518](https://perconadev.atlassian.net/browse/PG-2518) (epic PG-2412)
**Supersedes:** the 2026-07-02 design-proposal attachment on PG-2518 (this spec resolves
its open decisions; where they differ, this spec wins — notably Class A packages carry
their own full packaging copies instead of symlinks).

## 1. Motivation

Each ppg major version currently has a two-tier OBS structure: `ppg:<V>` (all packages
build from git tags) and `ppg:releases:<V>` (builds disabled, binaries copied on
release). This cannot model components that must build from **development branches**
(unreleased code — PostgreSQL Server, pg_tde, pg_oidc_validator) while a stable
tag-based release candidate is maintained in parallel. The fix is a three-tier
promotion pipeline that separates in-development builds from the tag-based candidate.

## 2. Decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Spec scope | Structure + `root/` migration + `percona_obs` tooling changes. Nightly trigger mechanism is future work. |
| D2 | Version scope | All versions (ppg 14–18) move to `staging/`; every version gets a devel project (14–17 empty). |
| D3 | Devel seeding | `ppg:devel:18` is the worked reference: Class A packages for the three PG-2518 components **plus `percona-pg_stat_monitor` (added by user, 2026-07-09)** + one Class B dependent. |
| D4 | Seed branches | User-confirmed (2026-07-09): percona-postgresql = `release-18.4` (Percona's `release-X.Y` branches are the working dev lines); pg_tde, pg_oidc_validator, pg_stat_monitor = `main`. |
| D9 | Devel publishing | Devel projects keep OBS default publishing (user decision, 2026-07-09), accepting the documented caveats: devel binaries carry the same NEVRA as staging's (ambiguous pick for consumers with both repos enabled; same-EVR devel snapshots never appear as upgrades — reinstall required). |
| D10 | Package-less projects | Never synced to OBS (user decision, 2026-07-09): empty projects (devel/14..17, the ppg:releases container) exist in the git tree only and are created on OBS when they gain their first package via the normal ancestor-chain sync. |
| D5 | Class A packaging | Class A devel packages carry **full copies** of `rpm/` and `debian/` (plus `devel/<V>/macros.yaml`), duplicated from staging at seeding time and maintained by hand. Deliberate: dev branches often need packaging changes before staging does, so devel packaging must be independently editable. (Symlinks and obs_scm-subdir reuse were considered and rejected; the sync uploads packaging from the local `rpm/`/`debian/` dirs via `_copy_local_packaging` — `_service` is never uploaded to OBS.) |
| D6 | Migration sequencing | Four staged PRs: tooling → staging pilot (18) → devel pilot (18) → remaining versions. |
| D7 | Naming | `devel` / `staging` / `releases` (per the design doc; `stable` rejected — collides with `releases`). |
| D8 | CLI compatibility | No aliases: after migration the CLI accepts only the new names (`ppg:staging:18`, `ppg:devel:18`). |

## 3. OBS project structure

For every version V ∈ {14, 15, 16, 17, 18}, under `<rootprj>`:

| Project | Builds from | Build enabled | Membership | Purpose |
|---|---|---|---|---|
| `ppg:devel:<V>` | dev branches (and links to staging) | yes | manual subset | development against unreleased code |
| `ppg:staging:<V>` | git tags only | yes | full (today's `ppg:<V>`, renamed) | QA / release candidate |
| `ppg:releases:<V>` | nothing (binaries copied) | no | full, copied on release | published release (unchanged) |

Two container projects, `ppg:devel` and `ppg:staging`, are created as directory
levels with a `project.yaml` (title/description only) so the OBS hierarchy matches the
tree and ancestor path injection has valid targets.

### 3.1 Devel repository paths

`build_project_meta()` auto-injects ancestor paths (`ppg:devel`, `ppg`, rootprj —
closest-first) into every repository of every non-root subproject. Staging is **not**
an ancestor of devel, so each `devel/<V>/project.yaml` defines its repositories
explicitly (no inheritance from `ppg/project.yaml`):

- `subproject: ppg:staging:<V>` **first**,
- then a copy of staging's full upstream path list, distro base **last**.

This satisfies the OBS last-path-only transitive-expansion rule: only the final path
is expanded transitively, so every repo that staging's path list names must appear
explicitly in devel's list too. Resulting OBS meta per devel repository:

```xml
<repository name="RockyLinux_9">
  <path project="…:ppg:devel"      repository="RockyLinux_9"/>   <!-- injected; empty, harmless -->
  <path project="…:ppg"            repository="RockyLinux_9"/>   <!-- injected -->
  <path project="…"                repository="RockyLinux_9"/>   <!-- injected rootprj -->
  <path project="…:ppg:staging:18" repository="RockyLinux_9"/>   <!-- explicit: staging binaries -->
  <path project="…PGDG…"           repository="…"/>              <!-- explicit: copy of staging's list -->
  <path project="openSUSE.org:RockyLinux:9" repository="standard"/> <!-- explicit: base, last -->
</repository>
```

Repository names and arch lists in devel mirror staging's exactly, so `_link`
rebuilds land in identically-named repositories.

### 3.2 Membership hazard (documented limitation)

Membership is manual. Omitting a direct dependent of a dev-branch package does not
fail loudly: devel-repo consumers receive that dependent from staging, built against
staging's library — a potential ABI mismatch. Whoever adds a package to devel is
responsible for also adding its direct dependents. A `project check`-style lint
comparing devel membership against the actual reverse-dependency set is future work.

## 4. Tree layout and package anatomy

```
root/ppg/
├── common/                          # unchanged
├── releases/                        # unchanged location
│   ├── 17/release.yaml              #   project: ppg:staging:17   ← updated field
│   └── 18/release.yaml              #   project: ppg:staging:18   ← updated field
├── devel/
│   ├── project.yaml                 # container project ppg:devel
│   ├── 14/project.yaml … 17/project.yaml   # empty devel projects (repos per §3.1)
│   └── 18/
│       ├── project.yaml
│       ├── macros.yaml              # copy of staging/18/macros.yaml
│       ├── percona-postgresql/      # Class A — PostgreSQL Server dev branch
│       ├── percona-pg_tde/          # Class A — pg_tde dev branch
│       ├── percona-pg_oidc_validator/  # Class A — pg_oidc_validator dev branch
│       ├── percona-pg_stat_monitor/ # Class A — pg_stat_monitor dev branch (D3)
│       └── percona-ppg-server/      # Class B — _link dependent
└── staging/
    ├── project.yaml                 # container project ppg:staging
    └── 14/ … 18/                    # moved verbatim from root/ppg/<V>/
```

### 4.1 Class A — dev-branch package

A full, self-contained package copied from its staging counterpart at seeding time
(D5):

- `obs/_service` — same shape as staging's, with the upstream `obs_scm` `revision`
  retargeted to the **dev branch**. Any other `obs/` files (`_multibuild`, …) are
  copied too.
- `rpm/`, `debian/`, `package.yaml` — full copies of staging's, maintained by hand.
  They may deliberately diverge when the dev branch requires packaging changes
  (new files, new subpackages) before staging does.
- `devel/<V>/macros.yaml` — a copy of staging's, so `%!{VAR}` version macros
  resolve identically (same version scheme as staging, per user decision).

**Maintenance rule:** devel's `macros.yaml` and the hardcoded `_service` branch
revisions must be reviewed together whenever staging bumps its versions — the copy
is independent, so a staging `PG_MINOR_VERSION` bump would otherwise relabel
devel's unchanged branch build with the new version string.

The sync uploads packaging from these local directories (`_copy_local_packaging`);
`_service` is never uploaded to OBS, and the cache/content-check/`git ls-remote`
machinery already handles branch revisions (`refs/heads/<rev>` is tried first).
Class A therefore needs **no tooling changes**.

### 4.2 Class B — dependent rebuilt against devel

Contains **only** `obs/_link`:

```xml
<link project="${OBS_ROOTPRJ}:ppg:staging:18" package="percona-ppg-server"/>
```

`_link` is already env-substitutable (`_OBS_SUBSTITUTABLE`), so `${OBS_ROOTPRJ}`
resolves per profile. OBS expands the link to staging's sources and builds them in
devel's context, where the §3.1 path order resolves build dependencies against
devel's own binaries. An `_aggregate` would be wrong here — it copies binaries and
never rebuilds.

### 4.3 Graduation (devel → staging)

A package graduates when the staging package's `_service` is retargeted from branch
to tag (staging already requires tag builds — existing behavior). The devel entry is
then removed, or repointed at the next dev branch. staging → releases is unchanged
(`project release`).

## 5. Tooling changes (`percona_obs/`)

Project names derive from directory paths, so `targets.py`, `cmd_build.py`, and
`cmd_profile.py` need **no changes** — `sync push ppg:staging:18` and
`build status ppg:devel:18` work as-is. The changes make `_link` a first-class
citizen in `cmd_sync.py`:

1. **Unexpanded comparison for `_link` packages.** Wherever sync compares local
   files against OBS (`_content_matches_branch`, the plain-push aggregate check,
   orphan-cleanup inputs), a package whose local `obs/` contains `_link` must fetch
   the OBS file list with `expanded=False` and compare the `_link` file itself.
   Today's `expanded=True` fetch returns the link *target's* files, producing a
   permanent mismatch and a spurious re-upload on every sync. The upstream-commit
   sub-check is skipped for link packages (no `_service`).

2. **`_link` target rewriting in branch mode.** In PR namespaces
   (`--branch-from`), a link to `${OBS_ROOTPRJ}:ppg:staging:18` resolves to the PR
   staging project, where the target is usually an `_aggregate` of main's binaries —
   expanding a link onto an aggregate copies binaries instead of rebuilding,
   silently defeating the Class B rebuild. Fix: extend the
   `_rewrite_aggregates_in_dir` mechanism to also rewrite `_link` `project=`
   references, with the same rule as aggregates: if the target project is not active
   (promoted) in the PR namespace, repoint the link at the branch (main) project's
   staging, which holds real sources.

3. **Class B in the decision engine.** `_resolve_branch_decision`'s git-log primary
   path already works (the package path `obs/_link` is git-tracked). With change 1,
   Phase 1 classifies link packages correctly; Phase 2 dependency propagation is
   unchanged — a promoted Class A dependency promotes its Class B dependent through
   the existing `_builddepinfo` fixed-point loop.

4. **Release flow.** `project release` derives the release project as
   `<product>:releases:<name>` (unchanged) and reads the source project from
   `release.yaml`'s `project:` field, so `project: ppg:staging:<V>` is a data
   change. Implementation includes an audit of `cmd_project.py` for residual
   `ppg:<V>`-shaped assumptions (e.g. version derivation from project names), fixed
   as found.

5. **Docs.** `root/README.md`, `docs/PERCONA_OBS_TOOL.md`,
   `docs/PACKAGING_HOWTO.md`, and `.github/copilot-instructions.md` updated for the
   three-tier layout, the two devel package classes, and new project names in
   examples.

No changes to `services.py` (link packages run no services; Class A services are
ordinary), `obs_api.py` (the `expanded` parameter already exists), profile handling,
or `project verify` (path-based; `_link` env-var coverage is already checked).

## 6. CI impact

No workflow file changes. All four workflows trigger on `root/**` and are
shape-agnostic:

- `sync-main.yml` creates and rebuilds renamed projects on merge.
- `obs-pr-check.yml`'s `--branch-from` handles devel packages once §5 lands. In the
  migration PRs every renamed path classifies as "changed" (new git paths), so those
  PRs build from source — expected, correct, and slow once each.
- `obs-pr-cleanup.yml` / `obs-stale-cleanup.yml` operate on the PR namespace,
  unaffected.

## 7. Migration plan — four PRs, in order

1. **PR 1 — tooling.** All §5 changes + docs. Lands against the current two-tier
   tree (inert until a `_link` package exists). Gate: `black` + `pyright` clean,
   dry-run syncs against the dev profile behave identically to before.
2. **PR 2 — staging pilot (version 18).**
   `git mv root/ppg/18 root/ppg/staging/18`; add `staging/project.yaml` container;
   update `releases/18/release.yaml` to `project: ppg:staging:18`. After merge,
   `sync-main` creates `ppg:staging:18` and rebuilds. Gate: see §8 staging gates.
   Then delete the old `ppg:18` OBS project manually (`osc rdelete`) — orphan
   cleanup never deletes projects whose directory is gone.
3. **PR 3 — devel pilot (version 18).** Add `devel/project.yaml` container and
   `devel/18/` with its `project.yaml` and the four seed packages. Gate: see §8
   devel gates.
4. **PR 4 — remaining versions.** `git mv` versions 14–17 to `staging/`; add empty
   `devel/<V>/project.yaml` for each; update `releases/17/release.yaml`. After
   verification, delete old `ppg:14`…`ppg:17` OBS projects manually.

## 8. Verification gates

**Staging gates (after PR 2, before PR 3):**
- `build status ppg:staging:18` — every package reaches the same status it had in
  `ppg:18`.
- `project release ppg:staging:18` runs successfully end-to-end (it reads the source
  project from `release.yaml`, generates the changelog, and opens a review PR); the
  review PR is inspected for correctness and closed unmerged — an actual release cut
  is not required for migration.

**Devel gates (after PR 3, before PR 4):**
- Class A packages in `ppg:devel:18` build from their dev branches.
- The Class B `percona-ppg-server` build links against **devel-built** dependencies
  — confirmed via build log / installed dependency versions, not merely "succeeded".
- Idempotence: a second `sync push` of the Class B package prints `=` (proves the
  unexpanded content check).
- A throwaway PR touching a devel Class A package shows correct promote/aggregate
  decisions in the PR comment.

**Final gates (PR 4):**
- Empty devel projects exist in the git tree only (per D10); they are NOT created
  on OBS.

**Tooling verification (PR 1):** `venv/bin/black percona_obs/` and
`venv/bin/pyright` pass; behavior exercised with `-P dev` dry-run syncs.

## 9. Out of scope

- Nightly trigger mechanism (future work — until then devel rebuilds occur on
  `build trigger` or when a sync uploads changes). OBS does not poll git branches.
- Automatic reverse-dependency membership lint (§3.2).
- Changes to `common/` shared projects.
- Migration automation beyond the four PRs.
- CLI aliases for the old project names (D8).

## 10. References

- [PG-2518](https://perconadev.atlassian.net/browse/PG-2518) — ticket.
- Design-proposal attachment (2026-07-02, revised 2026-07-08) on PG-2518.
- `.github/copilot-instructions.md` — ancestor path injection, `--branch-from`
  decision process, service-file env vars.
- `root/README.md` — tree ↔ OBS name mirroring rule.
