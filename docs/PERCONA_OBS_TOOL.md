# percona-obs Tool Reference

`percona-obs` is the management tool for syncing the local `root/` packaging tree to an OBS instance.

---

## Requirements

### System packages

The following OBS service binaries must be installed on the machine running `percona-obs`.
They are invoked locally for packages that declare `mode="manual"` services (e.g. Go
dependency vendoring):

| Binary | Package (Debian/Ubuntu) | Package (RPM) |
|---|---|---|
| `obs_scm` | `obs-service-obs-scm` | `obs-service-obs_scm` |
| `go_modules` | `obs-service-go_modules` | `obs-service-go_modules` |
| `download_url` | `obs-service-download_url` | `obs-service-download_url` |

Binaries are expected at `/usr/lib/obs/service/<name>`.

> Services that are not installed are skipped with a warning. Only `mode="manual"`
> service outputs (e.g. `vendor.tar.gz`) need to be produced locally — all other
> services run server-side on OBS.

### Python environment

Python 3.8+ is required. Create a virtualenv and install dependencies:

```sh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### OBS credentials

Credentials are read from `~/.config/osc/oscrc`. Run the `osc` first-run wizard to
create the file:

```sh
osc -A http://<your-obs-host>:8000 list
```

Follow the prompts to enter your username and password. The file is created once and
reused by all subsequent `osc` and `percona-obs` invocations.

---

## Usage

Every `percona-obs` command needs to know the OBS API URL (`-A`) and the root
project (`-R`). The recommended way to avoid typing these on every invocation is
to create a **connection profile** once and then use `-P <name>` to activate it.

### Connection profiles

A profile stores `apiurl` and `rootprj` in `.profile/<name>.yaml` (git-ignored).
Create one with the `profile create` command, passing `-A` and `-R` explicitly:

```sh
./percona-obs -A http://my-obs.local:8000 -R home:Admin profile create local
#   + local  (.profile/local.yaml)
#   ✔  profile create: local
```

Running the same command again with different values overwrites the profile
(shown with `~` instead of `+`).

List all available profiles and their settings:

```sh
./percona-obs profile list
#   local
#     apiurl:   http://my-obs.local:8000
#     rootprj:  home:Admin
```

Once a profile exists, activate it with `-P`:

```sh
./percona-obs -P local sync ppg:17 etcd --dry-run
```

Explicit `-A`/`-R` flags always override the profile values when both are given.

---

## Examples

### Preview all changes without writing to OBS

```sh
./percona-obs -P local sync push --dry-run
```

Runs all services locally and shows what would be uploaded to OBS. Nothing is written.

### Sync all packages

```sh
./percona-obs -P local sync push
```

Walks the entire `root/` tree, creates or updates all OBS projects and packages, and
uploads any changed `obs/` files as a single revision per package.

### Sync a single package

```sh
./percona-obs -P local sync push common:deps:runtime percona-telemetry-agent
```

### Sync a single PostgreSQL extension

PG extensions live under a subproject (`ppg/17/`). Pass the subproject and package
name separately:

```sh
./percona-obs -P local sync push ppg:17 percona-pg-telemetry
```

### Sync all packages under a subproject

```sh
./percona-obs -P local sync push ppg:17
```

---

## Branching from an existing profile

### What it does

`--branch-from <profile>` speeds up syncing a new environment by reusing already-built
binaries from an existing OBS project instead of re-uploading sources and waiting for
every package to build again from scratch.

For each package that is **unchanged** since the branch profile's last sync, `percona-obs`
uploads only a small `_aggregate` file. OBS then pulls the pre-built binaries directly
from the branch project's repository — no source fetch, no compilation, no wait.
Only packages that have **actually changed** are uploaded with their full source files
and built fresh.

### Typical workflow

Suppose you maintain a stable production profile `prod` (`home:Admin:percona`) and want
to spin up a test environment (`home:Admin:percona-test`) that tracks a feature branch.
Most packages are identical; only one or two have been modified.

**Step 1 — Create a profile for the new environment:**

```sh
./percona-obs -A http://my-obs.local:8000 -R home:Admin:percona-test profile create test
```

**Step 2 — Sync the test environment, branching from prod:**

```sh
./percona-obs -P test sync push --branch-from prod
```

For every unchanged package, `percona-obs` uploads an `_aggregate` pointing at
`home:Admin:percona` — the prod project — and OBS serves the binaries from there
instantly. Modified packages get their sources uploaded and build normally.

Output example:

```
  + project meta  home:Admin:percona-test
  + project meta  home:Admin:percona-test:ppg
  + project meta  home:Admin:percona-test:ppg:17
  = files  home:Admin:percona-test:ppg:17/percona-postgresql17
  @ home:Admin:percona-test:ppg:17/percona-postgresql17  → home:Admin:percona:ppg:17/percona-postgresql17
  ~ 4 files  home:Admin:percona-test:ppg:17/percona-pg-telemetry   ← changed, uploaded
  ✔  sync successful
```

### Promoting branch packages to full sources

After branching, when you want a package (or all packages) to build from local sources instead
of pulling pre-built binaries from the branch project, run `sync promote`:

```sh
./percona-obs -P test sync promote           # promote all branch packages
./percona-obs -P test sync promote ppg:17    # promote all packages under a subproject
./percona-obs -P test sync promote ppg:17 etcd  # promote a single package
```

For each package whose latest OBS revision was created by a `--branch-from` sync,
`percona-obs` replaces the `_aggregate` with the full local `obs/` source files
(running any `mode="manual"` services as needed).  Packages that already hold
real sources are skipped with `=`.

Preview what would be promoted without writing to OBS:

```sh
./percona-obs -P test sync promote --dry-run
```

### Build dependency propagation

When branching, packages that depend on a changed package must also be rebuilt from
source — otherwise they might link against stale binaries from the branch project.
`percona-obs` handles this automatically.

After the initial changed/unchanged classification, `percona-obs` queries OBS
`_builddepinfo` for the branch project to determine which packages build-depend on
which others. It then applies **bidirectional dep propagation**:

- If package **A** is promoted (uploaded with sources), every package that **depends
  on A** (directly or transitively) is also promoted.
- Conversely, every package that **A depends on** is also promoted, so A builds
  against fresh locally-controlled binaries rather than the branch copy.

This fixed-point iteration continues until no more promotions are triggered. The
result is a minimal set of packages that must be built from source, with all others
remaining as lightweight aggregates.

**Example**: if `golang-1.25` has changed locally, `percona-telemetry-agent` and
`etcd` (which both build-depend on it) are automatically promoted even if their own
source files are identical to what was last synced to the branch project.

Use `build dependency` to inspect these relationships before syncing:

```sh
./percona-obs -P local build dependency
```

### Project configuration change detection

In addition to per-package file comparisons, `percona-obs` detects when a **project's
configuration has changed** and promotes all packages in that project for rebuild —
even if their source files are identical to the branch project. This handles scenarios
like adding a new architecture to `root/project.yaml`, which is inherited by every
subproject that does not define its own `repositories:` list.

Two cases are handled:

- **Re-sync of an existing PR project**: the local desired config is compared against
  the PR project's current meta on OBS. If they differ (e.g. a new arch was added),
  all packages in that project are promoted.
- **New PR project** (first sync of a new PR): since the PR project does not exist on
  OBS yet, the local desired config is compared against the **corresponding production
  project** instead. If the production project exists and its config differs from local,
  the affected PR projects are created and all their packages promoted.

This ensures that an architecture or repository change introduced in a PR is always
built and tested for the packages that belong to affected projects, even when those
packages have no direct source file changes.

### How unchanged packages are detected

`percona-obs` uses a two-level decision for each package:

1. **Fast path** — reads the last OBS revision comment on the branch project. If it
   contains a clean `sync: <branch>@<sha> (...)` message, `git log` checks whether any
   local commits touch that package since that SHA. No commits → aggregate. Commits → upload.

2. **Content check fallback** — used when the revision message is absent, in a different
   format, or was written from an unpushed branch. Compares MD5s of every local `obs/` file against
   what OBS holds, and also verifies that the upstream source commit hash in the `.obsinfo`
   file matches the current remote HEAD via `git ls-remote`. Both must match → aggregate.

---

## Triggering and monitoring builds

### Trigger a rebuild

```sh
./percona-obs -P local build trigger                     # all packages
./percona-obs -P local build trigger ppg:17              # all packages under a subproject
./percona-obs -P local build trigger ppg:17 etcd         # single package
```

Sends an OBS service run request (`runservice`) for each targeted package, causing
OBS to re-fetch sources and queue a new build.

### Check build status

```sh
./percona-obs -P local build status
```

Prints a color-coded tree of live build statuses fetched from OBS. Succeeded packages
display the built version next to the status:

```
home:Admin:percona
├── common
│   ├── deps
│   │   ├── build
│   │   │   ├── golang-1.25
│   │   │   │   ├── RockyLinux_9       ✔ succeeded
│   │   │   │   ├── Debian_13          ✔ succeeded
│   │   │   │   └── xUbuntu_24.04      ✔ succeeded
│   │   │   └── obs-service-tar_scm
│   │   │       ├── RockyLinux_9       ✔ succeeded
│   │   │       ├── Debian_13          ✗ failed
│   │   │       └── xUbuntu_24.04      ✔ succeeded
│   │   └── runtime
│   │       └── percona-telemetry-agent
│   │           ├── RockyLinux_9       ✔ succeeded     3.5.26-6.1
│   │           ├── Debian_13          ✔ succeeded     3.5.26-6.1
│   │           └── xUbuntu_24.04      ✔ succeeded     3.5.26-6.1
└── ppg
    └── 17
        ├── etcd
        │   ├── RockyLinux_9           ✔ succeeded     3.5.26-6.1
        │   ├── Debian_13              ✔ succeeded     3.5.26-6.1
        │   └── xUbuntu_24.04          ✔ succeeded     3.5.26-6.1
        └── percona-pg-telemetry:17
            ├── RockyLinux_9           ✔ succeeded     1.0.0-1.1
            ├── Debian_13              ✔ succeeded     1.0.0-1.1
            └── xUbuntu_24.04          ◌ scheduled
```

| Symbol | Color | Meaning |
|---|---|---|
| `✔` | green | `succeeded` |
| `✗` | red | `failed` / `unresolvable` / `broken` |
| `●` | cyan | `building` / `dispatching` |
| `◌` | yellow | `scheduled` / `blocked` |
| `–` | dim | `excluded` / `disabled` |

Scope can be narrowed the same way as other commands:

```sh
./percona-obs -P local build status ppg:17               # subproject only (tree rooted there)
./percona-obs -P local build status ppg:17 etcd          # single package
./percona-obs -P local build status --repo RockyLinux_9  # all packages, one distro only
```

Set `NO_COLOR=1` to disable color output.

### Show build dependency tree

```sh
./percona-obs -P local build dependency
```

Queries OBS `_builddepinfo` for all packages and prints a dependency tree grouped by
**root packages** — packages that no other local package depends on. Each root package
is shown with its direct and transitive build dependencies indented beneath it.
Packages in the tree are annotated with the OBS project they belong to.

```
etcd (home:Admin:percona:ppg:17)
└── golang-1.25 (home:Admin:percona:common:deps:build)

percona-pg-telemetry (home:Admin:percona:ppg:17)
├── percona-postgresql-common (home:Admin:percona:ppg:17)
└── percona-postgresql17 (home:Admin:percona:ppg:17)

percona-telemetry-agent (home:Admin:percona:common:deps:runtime)
└── golang-1.25 (home:Admin:percona:common:deps:build)

obs-service-recompress (home:Admin:percona:common:deps:build)
obs-service-set_version (home:Admin:percona:common:deps:build)
obs-service-tar_scm (home:Admin:percona:common:deps:build)
```

Packages with no local build dependencies and that nothing else depends on are listed
at the bottom as isolated packages. Scope can be narrowed to a subproject:

```sh
./percona-obs -P local build dependency ppg:17
```

---

## Triggering Jenkins QA pipelines

`qa run` reads a project's `qa:` block from `project.yaml`, expands its matrix
into one Jenkins job per combination, triggers each via Jenkins'
`buildWithParameters` REST endpoint, and (with `--wait`) polls every triggered
build until it reaches a terminal state.

The same machinery powers the QA jobs in `.github/workflows/obs-pr-check.yml`:
the `detect-qa-matrix` job discovers the QA-enabled subprojects of the PR's
OBS root project, calls `qa show <project> --json` for each, concatenates the
matrices into the GitHub Actions matrix, and the `qa` job runs
`qa run --wait --report-json ... --filter ...` once per combo with one commit
status posted per combo on the PR head.

### `qa:` block schema

```yaml
# project.yaml
qa:
  pipeline: <jenkins-job-name>          # required
  parameters:                           # required
    SCALAR_PARAM: value                 # passed as-is
    LIST_PARAM:                         # if NOT in `matrix:` → joined with \n
      - a                               #   (Jenkins multi-line text param)
      - b                               # if in `matrix:` → expanded combinatorially
  matrix:                               # optional, list[str]
    - LIST_PARAM
```

`${VAR}` tokens in any value are substituted from the active profile's `env:`
section, plus auto-injected `OBS_ROOTPRJ` and `OBS_CONTAINER_REGISTRY_ROOTPRJ` (the root
project name with `:` replaced by `/`, useful for registry URLs).

### Subcommands

| Command | Purpose |
|---|---|
| `qa show <project>` | Print the resolved matrix (humans). `--json` emits one entry per combo with `project`, `pipeline`, `label`, `axis_filters`, `status_context`, `params` — used by CI to drive a GitHub matrix. Empty `[]` when the project has no `qa:` block. |
| `qa run <project>` | Trigger Jenkins for every matrix combo. Fire-and-forget by default; pass `--wait` to block until terminal results arrive. `--filter AXIS=val[,val…]` narrows the matrix; `--param NAME=VAL` overrides a parameter at runtime; `--dry-run` prints the POST bodies without calling Jenkins; `--report-json PATH` writes the per-combo result table for CI. |
| `qa status --run-id <id>` | Re-poll non-terminal combos of a previous run and print the current state. |
| `qa retry --run-id <id>` | Re-trigger only the combos whose latest attempt is non-`SUCCESS`. Re-uses the recorded `params` so retries are reproducible. By default skips `ABORTED` combos; pass `--include-aborted` to retry them too. |
| `qa list` | Tabulate recent runs (run-id, project, pipeline, summary). |

State files for `qa run` / `qa retry` live at `.percona-obs/qa/<run-id>.json`
(gitignored). Each combo records every trigger attempt, so the file accumulates
history across `qa retry` invocations.

### Jenkins credentials

`qa run` resolves Jenkins URL + user from (in order) the env vars
`JENKINS_URL`, `JENKINS_USER`, then the optional `jenkins:` section of
`.profile/<name>.yaml`:

```yaml
# .profile/dev.yaml
jenkins:
  url: https://jenkins.example.com
  user: ricardo
# token never stored in the profile
```

`JENKINS_API_TOKEN` is read **only** from the environment, never the profile.

### Re-running failed jobs from the PR UI

Each matrix combo runs as its own GitHub Actions job, so the PR's "Checks" tab
"Re-run failed jobs" button re-runs only the combos that failed. The detect
job's matrix output is reused across attempts, so the set of combos stays
identical between the original run and the re-run.

For local invocations, `qa retry --run-id <id>` does the equivalent — re-triggers
only the failed combos of the named run, appending a new attempt to each combo's
history in `.percona-obs/qa/<run-id>.json`.

---

## Getting repository installation instructions

`project install` prints the shell commands needed to configure the OBS-hosted package
repositories on a target machine, grouped by distribution.

> This command contacts the OBS instance to resolve the download URL, so it requires a
> profile (or explicit `-A`/`-R`).

### Show instructions for all distributions

```sh
./percona-obs -P local project install
```

### Show instructions for a specific subproject

```sh
./percona-obs -P local project install ppg:17
```

### Filter to a single distribution

```sh
./percona-obs -P local project install --repo RockyLinux_9
```

Example output for a Rocky Linux 9 repository:

```
────────────────────────────────────────────────────────────────────────
RockyLinux_9

# home:Admin:percona:ppg:17
rpm --import http://my-obs.local/home:/Admin:/percona:/ppg:/17/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/home_Admin_percona_ppg_17.repo << 'EOF'
[home:Admin:percona:ppg:17]
name=home:Admin:percona:ppg:17 - RockyLinux_9
baseurl=http://my-obs.local/home:/Admin:/percona:/ppg:/17/RockyLinux_9/
enabled=1
gpgcheck=0
EOF

```

For Debian-based distributions, instructions use `echo … | tee` + `curl … | gpg --dearmor | tee`
followed by `apt update`. For openSUSE/SLE repositories, `zypper addrepo` +
`zypper --gpg-auto-import-keys refresh` is emitted instead.

Projects that set `install: false` in their `project.yaml`, or that contain no packages,
are silently excluded from the output.

---

## Releasing packages

A release captures a point-in-time snapshot of a source OBS project by copying
its built binaries into a dedicated release project. Release IDs include the PG
minor version and a counter (e.g. `17.9-1`, `17.9-2`, `17.10-1`). A single OBS
release project (`ppg:releases:17`) covers all minor versions for a PG major.

The process is PR-based:

1. **`project release`** — auto-derives the release ID from OBS, creates or updates
   `release.yaml` and `CHANGELOG.md`, commits, pushes a branch, and opens a review PR.
2. **PR review** — the PR is review-only (no OBS build). Check `CHANGELOG.md` and merge.
3. **`sync-main.yml`** — after the merge commit lands, detects the changed `release.yaml`
   and creates the git tag (e.g. `ppg/17.9-1`).
4. **`obs-release.yml`** — triggered by the tag, runs `sync release` in CI, then creates
   a GitHub release with the changelog contents.

### Step 1 — Create or update a release

```sh
# Fully automatic — both release-name and release-id derived from OBS
./percona-obs -P local project release ppg:17

# Override release-name only
./percona-obs -P local project release ppg:17 --release-name 17

# Override both
./percona-obs -P local project release ppg:17 --release-name 17 --release-id 17.9-1
```

`project release <source-project>` does the following:

1. **Auto-derives `release-id`** (if not given with `--release-id`):
   - Queries OBS for the built version of `percona-postgresql<major>` in the source project.
   - Extracts `MAJOR.MINOR` (e.g. `17.9` from `17.9.0-1.1`).
   - Counts existing entries in `release.yaml` whose tag matches `/<MAJOR.MINOR>-*`
     and appends the next counter (e.g. `17.9-1`, or `17.9-2` if `17.9-1` already exists).
2. **Fetches** the source project's repository topology from OBS.
3. **Builds `CHANGELOG.md`** — compares built package versions in the source OBS project
   against the release OBS project (for updates) and generates entries with upstream URLs.
4. **First release** (`root/<product>/releases/<release-name>/` does not exist):
   - Creates `release.yaml`, `project.yaml`, `CHANGELOG.md`.
   - Creates `<subproject>/project.yaml` for each source subproject (e.g. `containers:ubi9/`)
     with builds disabled and paths rewritten to point directly at the release project.
5. **Update release** (directory already exists):
   - Appends the new tag to `release.yaml`'s `releases:` list.
   - Prepends a new section to `CHANGELOG.md`.
6. **Commits** the generated files locally. Push the branch and open a PR manually.

The git tag (e.g. `ppg/17.9-1`) is created automatically by `sync-main.yml` when
the merge commit lands on `main`. That tag then triggers `obs-release.yml`.

### `release.yaml` format

```yaml
repository: ${PERCONA_OBS_PACKAGING_REPO}
project: ppg:17
releases:
  - ppg/17.9-1          # first release
  - ppg/17.9-2          # update release
  - ppg/17.10-1         # minor version bump
```

`sync release` always uses the **last** entry as the current tag. Old entries are
kept for history. The backward-compat `revision:` field (plain string) is still
accepted and treated as a single-element list.

### CHANGELOG.md format

Each release creates a section following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
New sections are prepended above previous ones. Package entries are auto-populated:

```markdown
## [17.9-1] - 2025-03-01

### Added
- percona-pg_tde: updated to upstream version 2.0.0 (https://github.com/percona/pg_tde/releases/tag/2.0.0)
- percona-postgresql17: updated to upstream version 17.9.0 (https://www.postgresql.org/docs/release/17.9/)

### Changed

### Fixed
```

For **update releases**, only packages whose version changed appear (under `### Changed`):

```markdown
## [17.9-2] - 2025-04-10

### Added

### Changed
- percona-postgresql17: updated to upstream version 17.9.1 (https://www.postgresql.org/docs/release/17.9/)

### Fixed
```

Upstream URLs are derived from the package's `obs/_service` upstream `obs_scm` entry:
- **GitHub** (`https://github.com/…`): appends `/releases/tag/<revision>`.
- **PostgreSQL** (`git.postgresql.org`): maps to `https://www.postgresql.org/docs/release/<MAJOR.MINOR>/`.
- **Other**: uses the bare `url` value.

### Step 2 — CI ships the release

Release PRs are review-only — `obs-pr-check.yml` detects them and posts a comment
instead of running an OBS build. On merge:

1. `sync-main.yml` runs `sync push` normally (releases/ directories are excluded from
   traversal), then creates the git tag from the last entry in `release.yaml`.
2. The tag triggers `obs-release.yml`, which derives the OBS release project name
   (e.g. `ppg/17.9-1` → `ppg:releases:17`) and runs `sync release`.
3. After `sync release` finishes, `obs-release.yml` polls OBS (resolves immediately
   since all builds are disabled), updates version list docs, and creates a GitHub
   release with the `CHANGELOG.md` section for that release ID.

### Running `sync release` manually

For local testing or recovery from a failed CI run:

```sh
./percona-obs -P local sync release ppg:releases:17 --skip-tag-check
```

`sync release <release-project>` reads `release.yaml` and performs:

1. **Divergence check** (skipped with `--force`):
   - Checks that no files under the source project have changed since the release tag
     (`git diff <tag>..HEAD`). Pass `--skip-tag-check` when the tag doesn't exist locally.
   - Runs `sync push --dry-run` to confirm OBS is up-to-date (first release only).
2. **If the OBS release project does NOT exist** (first release):
   - Creates the release project with builds globally disabled.
   - Copies the source project's `prjconf`.
   - Runs `osc release <source-project> --no-delay` to copy binaries.
   - Creates each release subproject (e.g. `containers:ubi9`) with builds disabled.
3. **If the OBS release project already exists** (update release or re-run):
   - Runs `osc release` again to copy updated binaries in place.
   - Re-releases each subproject.
   - Re-runs are safe — `osc release` is idempotent.

Skip all divergence checks:

```sh
./percona-obs -P local sync release ppg:releases:17 --force
```

### Release directory layout

```
root/
└── ppg/
    └── releases/
        └── 17/                     # one directory per PG major version
            ├── release.yaml        # releases: list of tags
            ├── project.yaml        # ppg:releases:17 (builds disabled)
            ├── CHANGELOG.md        # keep-a-changelog, all releases
            └── containers:ubi9/    # colon-named, mirrors source subproject
                └── project.yaml    # builds disabled, paths → release project
```

The `releases/` directory is excluded from `sync push` traversal — release
directories (identified by `release.yaml`) are never synced to OBS as source
projects.

### Non-release PR: copying binaries to production on merge

When a PR that updates packages (rather than creating a release snapshot) is merged,
`obs-pr-cleanup.yml` runs `sync release-pr` before deleting the PR project. This copies
the PR's built binaries to the corresponding production OBS projects via the
`<releasetarget>` entries that `sync push --branch-from` added to every active PR
project's repository configuration.

Before copying binaries, `sync release-pr` automatically:

1. Reads the `<releasetarget>` entries from each PR project's live OBS meta to
   discover the production project counterparts — no naming convention is assumed.
2. Applies any pending project configuration changes (new repositories, added
   architectures) to those production projects. This ensures that a config change
   introduced by the PR takes effect in production at the same time as the new binaries.
3. Runs `osc release <pr-project> --no-delay` for each PR project that exists on OBS.

To run manually for recovery (replace `<pr-rootprj>` with e.g. `home:Admin:percona:PR:pr-42`):

```sh
./percona-obs -A <apiurl> -R <pr-rootprj> sync release-pr
```

---

## Deleting a project from OBS

### Preview what would be deleted

```sh
./percona-obs -P local sync delete --dry-run
./percona-obs -P local sync delete ppg:17 --dry-run
```

### Delete a full project tree

```sh
./percona-obs -P local sync delete --yes --recursive
```

Deletes the root project and all sub-projects (deepest first). Prompts for confirmation
unless `--yes` is given. Use `--recursive` to delete projects that still contain packages.

### Delete a single subproject

```sh
./percona-obs -P local sync delete ppg:17 --yes --recursive
```

### Delete a single package

```sh
./percona-obs -P local sync delete ppg:17 etcd --yes
```

---

## Adding a new package

### Standalone service (Go or other)

1. Copy an existing standalone package as a template:
   ```sh
   cp -r root/common/deps/runtime/percona-telemetry-agent root/common/deps/runtime/my-new-service
   ```
2. Edit `obs/_service` — update the upstream source URL and any service parameters.
3. Edit `rpm/*.spec` and `debian/control`, `debian/changelog` with the new package name
   and version.
4. Optionally create `package.yaml` with a title and description.
5. Sync to OBS:
   ```sh
   ./percona-obs -P local sync push common:deps:runtime my-new-service
   ```

### PostgreSQL extension

1. Copy an existing PG extension as a template:
   ```sh
   cp -r root/ppg/17/percona-pg-telemetry root/ppg/17/my-pg-extension
   ```
2. Replace all `percona-pg-telemetry` references with `my-pg-extension` throughout the
   copied files.
3. Update `obs/_service` to point to the new package's upstream repo.
4. Update `obs/_multibuild` with the PG major versions to build for.
5. Update `rpm/*.spec` and `debian/control` — keep `@BUILD_FLAVOR@` placeholders.
6. Sync to OBS:
   ```sh
   ./percona-obs -P local sync push ppg:17 my-pg-extension
   ```
