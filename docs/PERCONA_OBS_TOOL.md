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

A release captures a specific point-in-time snapshot of a source OBS project —
copying its built binaries into a separate, immutable release project.

The process has two steps:

1. **`project release`** — records the intent locally: creates `release.yaml`,
   commits it, and tags the repository.
2. **`sync release`** — acts on OBS: creates the release target project,
   configures `osc release` machinery, copies the binaries, and then cleans
   up the source project configuration.

### Step 1 — Cut a release record

```sh
./percona-obs -P local project release ppg:17 17.9
```

`project release <source-project> <release-name>` does the following:

1. Shows a preview of what will be created and asks for confirmation.
2. Creates three files under `root/<product>/releases/<release-name>/`:
   - `release.yaml` — records repository, git tag, and source OBS project.
   - `project.yaml` — title and description for the release project.
   - `Updates/project.yaml` — title and description for the Updates subproject.
3. Commits all three files with `git commit -s -m "Release <release-project> from <source-project>"`.
4. Creates a git tag `<product>/<release-name>` (e.g. `ppg/17.9`).

After the command completes, push both the commit and the tag:

```sh
git push && git push origin ppg/17.9
```

> Pushing the tag triggers the `obs-release.yml` CI workflow which runs
> `sync release` automatically in CI.

### Step 2 — Sync the release to OBS

```sh
./percona-obs -P local sync release ppg:releases:17.9
```

`sync release <release-project>` reads `release.yaml` for the given release
project identifier and performs the following steps:

1. **Idempotency check** — if the release project already exists on OBS, any
   stale configuration left by a partial previous run is cleaned up and the
   command exits early.
2. **Divergence validation** (skipped with `--force`):
   - Checks that no files under the source project have changed since the
     release tag (`git diff <tag>..HEAD`).
   - Runs `sync push --dry-run` against the source project to confirm OBS is
     up-to-date with the local tree.
3. **Creates the release project on OBS** with the same repository names and
   architectures as the source project, but with builds globally disabled.
4. **Adds `<releasetarget>` entries** to each repository of the source project,
   pointing to the new release project with `trigger="manual"`.
5. **Runs `osc release <source-project> --no-delay`** to copy the built binaries.
6. **Restores the source project** by removing the `<releasetarget>` entries,
   so it is ready for the next release.
7. **Creates the `Updates` subproject** (`<release-project>:Updates`) with the
   same repositories and architectures as the release project, builds globally
   disabled, and `<path>` entries pointing to the base release project.

Skip the divergence checks (useful in CI when `--force` is passed by the
PR-check workflow):

```sh
./percona-obs -P local sync release ppg:releases:17.9 --force
```

### Release directory layout

Release records live under `root/<product>/releases/`:

```
root/
└── ppg/
    └── releases/
        └── 17.9/
            ├── release.yaml
            ├── project.yaml
            └── Updates/
                └── project.yaml
```

The `releases/` directory is excluded from normal `sync push` traversal — it is
never synced to OBS as a source project.  However, **targeted syncs into Updates
are supported**:

```sh
./percona-obs -P local sync push ppg:releases:17.9:Updates my-update-package
```

This syncs packages directly into the `<rootprj>:ppg:releases:17.9:Updates` OBS
project without touching the base release project's configuration.

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
