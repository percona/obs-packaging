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
| `node_modules` | `obs-service-node-modules` (openSUSE:Tools repo) | `obs-service-node_modules` (openSUSE:Tools repo) |
| `npm_lockfile` | this repo — `tools/obs-services/` (see its README) | same |

`node_modules` and `npm_lockfile` additionally need `npm` (Node.js ≥ 18; the CI image
uses 22) and `cpio` on `PATH`.

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
./percona-obs -P local sync ppg:staging:17 etcd --dry-run
```

Explicit `-A`/`-R` flags always override the profile values when both are given.

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
rootprj: isv:percona
include-repositories: ["UBI_*", "ubi*", "images"]
registry: obs.pg.labs.percona.com   # optional, see below
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

### `registry`: the container registry host

Container images built by an instance are published by *its* registry, so the host cannot be
baked into the tree. The profile key `registry:` is exposed to `${VAR}` substitution as
`${OBS_CONTAINER_REGISTRY}`. The container `project.yaml` QA lanes use image references,
which are rendered against that registry (see *Image references* under *Triggering Jenkins
QA pipelines*).

The default is `registry.opensuse.org`, so profiles and plain `-A`/`-R` invocations that do not
declare the key keep rendering exactly as before. Precedence is
default < profile `registry:` < profile `env:` entry < explicit `-e OBS_CONTAINER_REGISTRY:…`.
Write the key with `profile create --registry HOST`; omitting the flag on
`-P name profile create name` keeps the profile's current value (like the slice flags).

`--narrow-repos RockyLinux_9,ssl*` keeps only the named repositories the profile already accepts
and exits 3 when nothing is left; the PR workflow uses it for repo labels. Entries are matched
against the profile's rules as literal names: a glob such as `ssl*` is kept only if the profile
accepts it literally — an exclude-only profile that does not exclude it, or an include list
containing the same glob.

Inspect a slice offline: `./percona-obs -P labs -e REMOTE_OBS_ORG_INTERCONNECT:x project config --offline --resolved`
(out-of-slice projects print `# project <name>: out of slice`) and `./percona-obs -P labs project verify`
(prints `slice: N project(s), M package(s) out of slice`, `--verbose` lists them, and fails if a kept
repository paths into a repository the slice does not carry). `project verify --offline` skips the
two network checks (obs_scm revisions via `git ls-remote`, `project:` paths against the live OBS)
and runs only the static ones; `--no-scm-validate` skips only the first, so the `project:` path
check runs alone: every `project:` entry of an in-slice project, interconnect references such as
`openSUSE.org:Debian:12` included, must name a project and a repository that exist on the
profile's OBS instance (one meta GET per unique project name; a 401/403 aborts with a credentials
error). The `Project Config Check` workflow runs both forms once per `OBS_INSTANCES` entry on every
PR that touches `root/`: `--offline` together with `project config --offline` for all PRs, and
`--no-scm-validate` with the instance credentials for PRs from branches of the repository itself.

`sync release -P <profile>` releases the subprojects that instance holds; `project release` always
generates the full, instance-agnostic release tree.

CI: the repository variable `OBS_INSTANCES` is a JSON list, one object per instance —
`{"name": "boo", "apiurl": "…", "rootprj": "isv:percona", "pr_rootprj": "isv:percona:pr",
"exclude_repos": "UBI_*,ubi*,images"}` (also `include_repos`, `include_projects`,
`exclude_projects`, optional `user`, optional `registry` — written into the CI profile's
`registry:` key — optional `qa_types`, and optional `env`). The password secret is
`OBS_PASSWORD_<NAME>` (upper-case name). `sync-main`, `obs-pr-check`, `obs-release` and the two
cleanup workflows run their OBS jobs once per entry.

`env` is a JSON object of environment variables for that instance, applied on top of the defaults
every profile gets, so an instance can override one without affecting the others:

```json
{"name": "labs", "apiurl": "https://obs.pg.labs.percona.com", "rootprj": "isv:percona",
 "pr_rootprj": "isv:percona:PR", "include_repos": "UBI_*,ubi*,images",
 "registry": "obs.pg.labs.percona.com", "qa_types": "containers",
 "env": {"REMOTE_OBS_ORG_INTERCONNECT": "openSUSE.org:"}}
```

`REMOTE_OBS_ORG_INTERCONNECT` is the usual reason to set it: an instance that reaches
`RedHat:UBI-9`, `Fedora:EPEL:9` and friends through an interconnect needs the remote's prefix,
while an instance hosting them locally needs the empty default. Values may contain colons — the
`KEY:VALUE` form splits on the first one — and the same map is written into the QA `ci` profile,
so discovery and Jenkins runs render the tree the same way the sync did.

`qa_types` is a comma-separated subset of `packages,containers` naming the QA kinds that live on
that instance. `obs-pr-check` intersects it with the types the `qa-packages`/`qa-containers`
labels ask for; an empty intersection means that instance discovers no QA combos. Leaving it
unset means "everything this instance carries". When two instances discover the same QA
`status_context` — which is the check-run name, so it can only belong to one of them — the merge
step keeps the instance listed first in `OBS_INSTANCES` and reports the dropped one as a warning.
When a project is in slice on more than one instance and both slices classify as the same QA
kind, `qa_types` cannot split them, so instance order is what settles it.

`OBS_INSTANCES` and the matching `OBS_PASSWORD_<NAME>` secrets must be created before the
workflow change merges, or the matrix jobs have nothing to iterate over and no credentials to
authenticate with. Roll out an instance's first sync with `--dry-run` and review the deletion
list before removing that flag — a plain profile-less tree carries everything, so the first
sliced push against a previously-unsliced instance is the one that deletes out-of-slice
projects and packages as orphans. The README build badge now reads
`obs-build-badge-boo.json` from the `badges` branch (one file per instance); the first
`sync-main` run under the new per-instance workflow creates it.

### `image-fallback-rootprj`: where unpromoted images live

`qa:` image references (see *Image references* under *Triggering Jenkins QA pipelines*)
render against the profile's `rootprj`. When the profile also carries
`image-fallback-rootprj: isv:percona`, an image that the current root project does not
hold is rendered against that root instead. CI writes the key into PR profiles only
(`obs-pr-check.yml`, `obs-qa-run.yml` with a PR number); `--image-fallback-rootprj ROOTPRJ`
overrides it on the command line. Setting it makes `qa show` / `qa run` list the packages
of each referenced project once.

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

PG extensions live under a subproject (`ppg/staging/17/`). Pass the subproject and
package name separately. (There is also a `ppg/devel/17/` tier for dev-branch builds —
see [root/README.md](../root/README.md) — not covered further here.)

```sh
./percona-obs -P local sync push ppg:staging:17 percona-pg-telemetry
```

### Vendoring npm dependencies (`npm_lockfile` + `node_modules`)

Packages with a webpack/npm frontend (pgAdmin 4) vendor their npm dependencies for
offline OBS builds with two `mode="manual"` services, run locally by `sync` in this order:

```xml
<service name="npm_lockfile" mode="manual">
  <param name="archive">*percona-pgadmin4*.obscpio</param>   <!-- the upstream obs_scm output -->
  <param name="subdir">web</param>                            <!-- where package.json lives -->
</service>
<service name="node_modules" mode="manual">
  <param name="cpio">node_modules.obscpio</param>
  <param name="output">node_modules.spec.inc</param>
  <param name="source-offset">10000</param>
</service>
```

`npm_lockfile` (repo-owned, `tools/obs-services/`) generates `package-lock.json` with
`npm install --package-lock-only`; `node_modules` (openSUSE) reads it and downloads every
tarball into `node_modules.obscpio`, writing `SourceNNNNN:` lines to `node_modules.spec.inc`
(`%include %{_sourcedir}/node_modules.spec.inc` in the spec; `BuildRequires: local-npm-registry`
serves the tarballs to `npm` at build time). All three files are uploaded to OBS and cached
under `.cache/services/<upstream commit>/` — the lockfile is a function of the upstream commit
plus registry state, so `--no-cache` is the way to deliberately refresh the vendored set.
Each new upstream commit of an npm-vendored package adds a cache entry of roughly the
`.obscpio`'s size (~220 MB for pgAdmin); this is bounded locally by `prune_cache`, which
removes entries unused for 7 days, and in CI additionally by the `actions/cache` size limits.
`npm_lockfile` also accepts an optional `npm-flags` param (default `--legacy-peer-deps --ignore-scripts`; a given value replaces the default set) for upstreams that need different npm resolution flags.

`root/ppg/staging/common/tools/percona-pgadmin4/obs/_service` is the reference user of this chain:
`obs_scm` (tag `REL-9_17`, `versionrewrite-pattern REL-(\d+)_(\d+)` → `9.17`) →
`npm_lockfile` (`subdir web`) → `node_modules` (`source-offset 10000`) → `tar`/`recompress`/
`set_version` at build time. A `sync push --dry-run` of that package runs the whole chain
locally and takes several minutes (it downloads every npm tarball once; later runs hit the
service cache).

Two rules in `percona-obs` make this work:

- `.obscpio` files produced by **manual** services are uploaded as-is (OBS unpacks them into
  `SOURCES` at build time); only `obs_scm` archives are extracted locally.
- **Drift-tolerant artifacts**: outputs whose bytes depend on registry state at generation
  time are compared by presence only in the `--branch-from` content check, so re-resolution
  never promotes a package by itself (absence on either side is still a change):

  | Service | Tolerated files |
  |---|---|
  | `cargo_vendor` | `vendor.tar.*` |
  | `node_modules` | `node_modules.obscpio`, `node_modules.spec.inc`, `*package-lock.json` (names follow the `cpio`/`output`/`input` params) |

  Drift tolerance only affects the `--branch-from` content check's changed/unchanged
  decision — it does not affect what gets uploaded. A sync that is not skipped (no
  matching `--skip-unchanged` manifest entry, or run with `--force`) still uploads
  whatever the local service run produced, so a regenerated drift-tolerant artifact
  (for pgAdmin, a ~220 MB `node_modules.obscpio`) is re-PUT to OBS and commits a new
  revision, triggering a rebuild even though nothing meaningful changed. `--skip-unchanged`
  avoids this in the normal CI path because tag-pinned packages are skipped outright before
  any service reruns; `--no-cache` is the deliberate way to force that refresh.

### Sync all packages under a subproject

```sh
./percona-obs -P local sync push ppg:staging:17
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
  + project meta  home:Admin:percona-test:ppg:staging:17
  = files  home:Admin:percona-test:ppg:staging:17/percona-postgresql17
  @ home:Admin:percona-test:ppg:staging:17/percona-postgresql17  → home:Admin:percona:ppg:staging:17/percona-postgresql17
  ~ 4 files  home:Admin:percona-test:ppg:staging:17/percona-pg-telemetry   ← changed, uploaded
  ✔  sync successful
```

### Promoting branch packages to full sources

After branching, when you want a package (or all packages) to build from local sources instead
of pulling pre-built binaries from the branch project, run `sync promote`:

```sh
./percona-obs -P test sync promote           # promote all branch packages
./percona-obs -P test sync promote ppg:staging:17    # promote all packages under a subproject
./percona-obs -P test sync promote ppg:staging:17 etcd  # promote a single package
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
like adding a new architecture to `root/project.yaml`, which every subproject's
`repositories` list is merged with unless it opts out with `repositories-inherit: false`.

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

### Inspecting the effective project configuration

`project.yaml` files are deltas: repositories, build configuration and flags are merged from
`root/project.yaml` down through tier-level `subprojects.yaml` files (see
`.github/copilot-instructions.md`, "Config inheritance and merging"). To see what a project
actually gets:

```sh
# Meta XML and build config exactly as sync would upload them (no OBS access)
percona-obs -P dev project config ppg:staging:17 --offline

# The merged project.yaml as YAML
percona-obs -P dev project config ppg:staging:17 --offline --resolved

# Unified diff of meta and build config against what OBS holds now
percona-obs -P dev project config ppg:staging:17 --diff
```

`--offline` still needs `${VAR}` tokens resolved (e.g. `${REMOTE_OBS_ORG_INTERCONNECT}` in
`root/project.yaml`), so pass a profile (`-P`) or the matching `-e KEY:VALUE` flags even though no
OBS connection is made. Without a project argument all projects under `root/` are shown. The build
config carries one `# --- from <file> ---` header per contributing file, so a line can be traced to
its source.

### How unchanged packages are detected

`percona-obs` uses a two-level decision for each package:

1. **Fast path** — reads the last OBS revision comment on the branch project. If it
   contains a clean `sync: <branch>@<sha> (...)` message, `git log` checks whether any
   local commits touch that package since that SHA. No commits → aggregate. Commits → upload.

2. **Content check fallback** — used when the revision message is absent, in a different
   format, or was written from an unpushed branch. Compares MD5s of every local `obs/` file against
   what OBS holds, and also verifies that the upstream source commit hash in the `.obsinfo`
   file matches the current remote HEAD via `git ls-remote`. Both must match → aggregate.

Packages stored under a tier's `_shared/` directory and referenced by symlink (see
`root/README.md`) are checked against both the symlink and its target path, so an edit
to the shared copy invalidates every linking package's fast path.

---

## Reducing OBS API traffic

A full-tree `sync push` normally runs services and compares files for every package,
even when almost nothing changed. The features below cut that down to a handful of
API calls on a quiet tree, and keep CI polite towards the OBS traffic limiter.

```sh
venv/bin/python -m percona_obs -P main sync push --skip-unchanged --report-json /tmp/sync-report.json
```

### `sync push --skip-unchanged`

Skips packages whose latest OBS revision comment records a clean
`sync: <branch>@<sha> (...)` from a git SHA with no changes since. "No changes since"
is checked locally against three inputs: commits touching the package directory,
uncommitted edits in it, and the rendered values of the `%!{NAME}` macros the package
references (compared between the SHA and the working tree — moving a macro between
ancestor `macros.yaml` files or bumping a macro the package never uses is not a change). A skipped
package runs no services and uploads nothing — it costs one API call (the
revision-history fetch), or **zero** when the sync-state manifest is warm (see below).
Skipped packages are printed as `= skip <project>/<package> (unchanged)`.

Plain pushes only: combining `--skip-unchanged` with `--branch-from` is rejected
(the branch decision already has its own unchanged detection).

Caveats:

- **Packages tracking a moving upstream ref are never skipped.** If the package's
  `_service` has an upstream `obs_scm` whose `revision` is missing, `HEAD`, or names a
  remote *branch* (the devel-tier pattern of tracking `main`), the tarball must be
  re-resolved from upstream on every sync — upstream-only commits would otherwise
  never reach OBS. Branch-vs-tag classification runs `git ls-remote` once per
  `(url, revision)` pair and is cached persistently in
  `.cache/sync_state/scm_ref_types.json`; full 40-hex SHA revisions are always
  immutable and need no lookup. Classification errors conservatively count as
  "branch" (no skip) and are not cached.
- **Any doubt falls back to the normal promote path.** No revision comment, a
  non-`sync:` comment, a dirty (`local changes on ...`) sync, or changes since the
  recorded SHA all route the package through the regular upload, whose per-file MD5
  comparison is authoritative — an unchanged upload is a no-op anyway.
  `--force` disables skipping entirely.
- **Out-of-band OBS edits are not detected.** Changes made directly on OBS that
  create no source revision (e.g. a manual `_meta` edit) are invisible to the skip
  decision — the same trust model as `--branch-from` aggregates.

### The sync-state manifest

`--skip-unchanged` also maintains a local manifest `.cache/sync_state/<hash>.json`
mapping `project/package` → last-synced git SHA, keyed by `(apiurl, rootprj)` so
different profiles and instances never share entries. When the manifest entry for a
package is present and the same local checks pass — package-directory tree diff
against the recorded SHA, uncommitted edits, referenced macro values — the package is
skipped with **zero** API calls, without even fetching the OBS revision history.

Entries are recorded only for uploads made from a **pushed, clean** HEAD: an unpushed
SHA can be reset away, and dirty inputs would bake in content no SHA represents. In
CI the manifest is persisted between runs by `actions/cache` (it lives in the same
cache entry as the service outputs). A missing, corrupt, or evicted manifest simply
falls back to the OBS revision-comment check above.

### `sync push --report-json PATH`

Writes a JSON sync report:

```json
{
  "rebuild_projects": ["home:Admin:percona:ppg:staging:17", "..."],
  "promoted": ["home:Admin:percona:ppg:staging:17/etcd", "..."],
  "skipped": 42,
  "head_sha": "<full git HEAD sha>"
}
```

`rebuild_projects` lists every project whose builds this run may have triggered —
committed file uploads plus meta/prjconf creates or updates. The CI poll script
(`.github/scripts/poll_obs_builds.py`) consumes the report via the `OBS_SYNC_REPORT`
environment variable and monitors only those projects instead of the full tree,
finishing with one full-tree sweep to adopt cross-project rebuild cascades.
`head_sha` anchors the report to the checkout that produced it; the poll fails
**open** — full-tree polling as before — on a missing, corrupt, or stale (head_sha
mismatch) report. The report is also written in `--dry-run` (it reflects the
computed would-be changes).

### Client-side HTTP pacing and retry

All osc HTTP requests made by `percona-obs` are paced client-side: a shared
minimum interval between request starts reshapes thread-pool bursts into a steady
stream (default 8 requests/s; tune with `PERCONA_OBS_MAX_RPS`, `0` disables pacing).
Requests failing with HTTP 429 or 503 are retried for every method, and 502/504
additionally for GETs, honoring `Retry-After` when present (otherwise exponential
backoff), up to 5 attempts. On any throttling response the shared pacing slot is
pushed forward so **all** threads back off together, not just the throttled one.
Note that osc's internal urllib3 layer performs its own connection-level retries
(500/502/503) beneath this wrapper.

### CI poll backoff and the split sync-main workflow

The CI build poll (`poll_obs_builds.py`) starts at `OBS_POLL_INTERVAL` seconds
between polls (default 30) and ramps the interval ×1.5 per cycle while build states
are unchanged, up to `OBS_POLL_MAX_INTERVAL` (default 300); any state change resets
it to the base.

The `sync-main.yml` workflow is split into two jobs: a `sync` job serialized on its
own concurrency group (never cancelled mid-upload, so back-to-back pushes queue up
short sync runs) and a `poll` job in a cancel-superseding group (newest poll wins —
a newer push's poll replaces an older run's). The version lists and release tags are
diffed from the head SHA of the last *successful* run, so the surviving poll covers
any superseded runs' ranges too.

---

## Triggering and monitoring builds

### Trigger a rebuild

```sh
./percona-obs -P local build trigger                     # all packages
./percona-obs -P local build trigger ppg:staging:17              # all packages under a subproject
./percona-obs -P local build trigger ppg:staging:17 etcd         # single package
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
    └── staging
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
./percona-obs -P local build status ppg:staging:17               # subproject only (tree rooted there)
./percona-obs -P local build status ppg:staging:17 etcd          # single package
./percona-obs -P local build status --repo RockyLinux_9  # all packages, one distro only
```

Set `NO_COLOR=1` to disable color output.

### Show built versions

`project versions` lists the versions of a project. With `--online`, package rows
are read from OBS binary lists, one request per project; the row shows the full
version-release of the first repository in sorted (repository, architecture)
order. When repositories disagree it prints a warning and does not fail. Image
rows are unchanged.

### Show build dependency tree

```sh
./percona-obs -P local build dependency
```

Queries OBS `_builddepinfo` for all packages and prints a dependency tree grouped by
**root packages** — packages that no other local package depends on. Each root package
is shown with its direct and transitive build dependencies indented beneath it.
Packages in the tree are annotated with the OBS project they belong to.

```
etcd (home:Admin:percona:ppg:staging:17)
└── golang-1.25 (home:Admin:percona:common:deps:build)

percona-pg-telemetry (home:Admin:percona:ppg:staging:17)
├── percona-postgresql-common (home:Admin:percona:ppg:staging:17)
└── percona-postgresql17 (home:Admin:percona:ppg:staging:17)

percona-telemetry-agent (home:Admin:percona:common:deps:runtime)
└── golang-1.25 (home:Admin:percona:common:deps:build)

obs-service-recompress (home:Admin:percona:common:deps:build)
obs-service-set_version (home:Admin:percona:common:deps:build)
obs-service-tar_scm (home:Admin:percona:common:deps:build)
```

Packages with no local build dependencies and that nothing else depends on are listed
at the bottom as isolated packages. Scope can be narrowed to a subproject:

```sh
./percona-obs -P local build dependency ppg:staging:17
```

---

## Triggering Jenkins QA pipelines

`qa run` reads a project's QA *lanes* — the optional `qa:` block of its
`project.yaml` plus the optional `qa:` block of each direct package's
`package.yaml` — expands every matrix into one Jenkins job per combination,
triggers each via Jenkins' `buildWithParameters` REST endpoint, and (with
`--wait`) polls every triggered build until it reaches a terminal state.

The same machinery powers the QA jobs of the reusable `.github/workflows/qa-fanout.yml`
(called by `obs-pr-check.yml` for labelled PRs and by `obs-release-pr.yml` for release
PRs): its `detect-qa-matrix` job discovers the QA-enabled subprojects of the PR's
OBS root project, calls `qa show <project> --json` for each, concatenates the
matrices into the GitHub Actions matrix, and the `qa` job runs
`qa run --wait --report-json ... --filter ...` once per combo with one commit
status posted per combo on the PR head.

To run the QA of **one** project on demand, dispatch `.github/workflows/obs-qa-run.yml`
(Actions → "OBS QA Run" → *Run workflow*). It takes the project name (`ppg:staging:18`,
`ppg:staging:18:containers`, …), an optional PR number (tests the PR's OBS subproject
instead of the production root), an optional `qa:` entry `name`, an optional `package` (only that package's
`package.yaml` block) and an optional
`matrix:`-axis `filter` (`IO_METHOD=worker SCENARIO=pg-18`). The OBS instance is resolved
from `OBS_INSTANCES` by the project's include/exclude globs and `qa_types`; the branch
selected in the dispatch dialog supplies the `project.yaml` definitions. A selection that
matches no combo fails before Jenkins is called, listing the names/values that exist. A
`package` that is absent from the PR project fails with a "not present in <project>" error.

### `qa:` block schema

```yaml
# project.yaml
qa:
  name: <entry-name>                    # optional, string
  pipeline: <jenkins-job-name>          # required
  parameters:                           # required
    SCALAR_PARAM: value                 # passed as-is
    LIST_PARAM:                         # if NOT in `matrix:` → joined with \n
      - a                               #   (Jenkins multi-line text param)
      - b                               # if in `matrix:` → expanded combinatorially
    IMAGE_PARAM:                        # image reference: rendered to a registry path
      image: percona-pgbouncer          #   OBS package name of the image (required)
      repository: ubi9                  #   OBS repository = last path segment (required)
      project: ppg:staging:18:containers   # defaults to the lane's project
  matrix:                               # optional, list[str]
    - LIST_PARAM
```

`qa:` may also be a **list** of such entries, one per pipeline lane.

The same schema applies to a package's `package.yaml`. Package blocks are
discovered on disk from the project's direct package directories (symlinks into
`_shared/` are followed and `%!{...}` macros resolve from the link's location,
so one block under `_shared/<pkg>/package.yaml` renders per major), without
descending into subprojects. The package's `obs/_link`, if any, is irrelevant.
The tool calls OBS from `qa show` / `qa run` only to resolve image references when `image-fallback-rootprj` is set (one package listing per project).

```yaml
# root/ppg/staging/_shared/pg_tde/package.yaml
qa:
  pipeline: pg-tde-parallel
  parameters:
    OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:staging:%!{PG_MAJOR_VERSION}
    VERSION: ppg-%!{PG_VERSION}
    PLATFORMS: [rocky-9, debian-13]
  matrix: [PLATFORMS]
```

The segment-uniqueness rule below is checked per block: the project block and
each package block are separate namespaces. One cross-block rule applies: when
the project block has more than one entry, no package that declares `qa:` may
share a name with one of its entry segments (both would render
`OBS QA / <project> / <segment>`); the loader rejects it, so rename the project
entry with `name:`. A single-entry project block renders no segment and is
exempt.

#### Image references

A parameter whose value is a mapping with an `image:` key names a container image by
its OBS package; the parameter name is irrelevant (`REPOSITORY`, `OLD_DOCKER_REPOSITORY`,
…). `qa show` / `qa run` render it to
`<OBS_CONTAINER_REGISTRY>/<rootprj>/<project>/<repository>` (colons → `/`, lower-cased)
and choose the root project per image:

| `image-fallback-rootprj` set? | image listed in `<rootprj>:<project>` on OBS? | root used |
|---|---|---|
| no | not queried | the current rootprj |
| yes | yes (promoted into the PR project) | the current rootprj |
| yes | no | the fallback rootprj |

PR projects hold only promoted packages, and the registry publishes an image only under
the project that built it, so a PR that promotes one image must still pull its siblings
from the production root. CI writes `image-fallback-rootprj: <production root>` into the PR
profiles; the nightly and production dispatches have no fallback and never query OBS.
Each decision is printed on stderr (`image <pkg> (<project>) → <PARAM> = <path> [present|fallback|no-fallback: …]`).
`project verify` checks that `image` is a package directory of `project` and that
`repository` is one of its repositories (references to projects not in the tree are skipped).

Image references are not allowed inside list values, so they cannot be matrix axes. A lane
whose pipeline picks the image from an axis (`docker-server-parallel` appends
`-with-postgis` when `WITH_POSTGIS=true`) names the plain image only.
When only `-with-postgis` was promoted, both combos test the fallback (production) images.
When only the plain image was promoted, the lane resolves to the PR root and the
`WITH_POSTGIS=true` combo pulls a `-with-postgis` image that does not exist there, so it
fails.

#### Status contexts

| lane | entries | `status_context` |
|---|---|---|
| project | one | `OBS QA / <project>[ / <combo>]` |
| project | several | `OBS QA / <project> / <segment>[ / <combo>]` |
| package | one | `OBS QA / <project> / <package>[ / <combo>]` |
| package | several | `OBS QA / <project> / <package> / <segment>[ / <combo>]` |

`<segment>` is the entry `name` when set, else the pipeline; `<combo>` is the
matrix label and is absent for entries without `matrix:`.

#### When package lanes run

* `qa run <project>` with neither `--package` nor `--project-only` triggers the
  project block and every package block. This is what the nightly does. CI's
  per-combo jobs pass `--project-only` for project lanes and `--package <pkg>`
  for package lanes (the `package_filter` field), so a project lane never also
  triggers package lanes that share its pipeline.
* On PR checks (`obs-pr-check.yml`) and on `obs-qa-run` dispatches with a PR
  number, `.github/scripts/list_qa_matrix.py` / `filter_qa_matrix.py` run with
  `QA_PACKAGES_PRESENT_ONLY=true` and drop the package lanes whose package is
  not listed in the PR's OBS subproject (which holds only promoted packages,
  including dep-cascade rebuilds). Project lanes are never dropped. The OBS
  listing is strict: a 404 means no packages, any other OBS error fails the
  detect job instead of silently dropping lanes. The nightly never sets it.
* Testing a new package `qa:` block: a PR that changes only a package's `qa:`
  block does not change its sources, so the package is usually aggregated and
  absent from the PR project and its lane is dropped. To exercise the block,
  dispatch `obs-qa-run` from the feature branch with `package` set and no
  `pr_number` (production root).

#### `name:` — disambiguating two entries

`name` is optional and must be a non-empty string matching
`[A-Za-z0-9][A-Za-z0-9_.+-]*` (it is interpolated into a shell command line in
CI), unique within one `qa:` block (project or package). It changes two things:

* **The check-run name.** For a multi-entry block, the disambiguating segment of
  `status_context` (`OBS QA / <project> / <segment> / <combo>`) is the entry's
  `name` when it has one, and the pipeline name otherwise. Entries without a
  `name` therefore keep their historical contexts unchanged.
* **Selection.** `qa run --name <name>` runs exactly that entry; it combines
  with `--pipeline` (both filters apply).

`name` is **required when two entries in one block share a pipeline** (e.g. the
`ubi8` and `ubi9` container lanes, both on `docker-server-parallel-generic`):
without it both lanes would render the same `status_context`, so `qa show`
rejects the block: one check run cannot carry two lanes, and
`qa run --pipeline …` would trigger both under it.

#### `EXPECTED_VERSIONS` (added automatically)

`qa run` adds one parameter to every entry: `EXPECTED_VERSIONS`, the versions of
the packages under test, one `package=version` per line, sorted, keyed by OBS
package name (`percona-pgbackrest=2.59.2`, `etcd=3.5.33`, ...). The values come
from the binaries OBS built in the project under test, read with one binary-list
request per OBS project (cached for the run). `qa run` therefore needs an OBS
connection and fails without one.

Each value is the upstream version: the built version-release without the
release part (`2.60.0`). Every repository in the profile's slice must agree on
it. When they do not, `qa run` fails before any Jenkins trigger:

```
error: <pkg>: OBS builds disagree on the version: ...
```

A conflict aborts the run only when a selected lane would send the conflicting
package (after `--project-only`, `--package`, `--name` and `--pipeline`
selection): a project entry sends every candidate package, a package lane or a
`package:` entry only its own, and an entry that sets `EXPECTED_VERSIONS` itself
sends nothing computed. Conflicts in packages no selected lane sends are printed
as `warning: <conflict>` lines and the run continues; `qa show
--expected-versions` follows the same rule for the lanes it prints. When the OBS
project under test does not exist, the command fails with `error: <obs project>
does not exist on OBS; cannot compute EXPECTED_VERSIONS`.

Which packages are listed is decided by the local tree. A project entry gets its
own packages; image and tarball recipe packages are not candidates. A project
without own candidates, or one that builds artifacts (an `obs/Dockerfile`,
`obs/simpleimage` or `*.kiwi` recipe), adds the packages of its `subproject:`
path projects, in path order, the first provider winning. A name taken by a
higher-priority project stays taken even when it has no binaries. Aggregates
appear only where the aggregating project has binaries for them; a package
listed without binaries is named in the warning below. An entry of a
package-level `qa:` block (`package.yaml`) gets only that package. A qa entry
can also set `package: <name>` (a non-empty string) to restrict its
`EXPECTED_VERSIONS` to that package.

Packages without binaries are left out of the value and named in one stderr
warning:

```
warning: no OBS binaries for: ... — left out of EXPECTED_VERSIONS
```

In a PR project, a package that is absent from the PR project is read from the
fallback root (`image-fallback-rootprj` / `--image-fallback-rootprj`). A package
that is present but has no binaries never falls back.

Release mirrors (`root/<product>/releases/<major>/**/project.yaml`) take their
structure from the staging project named by the nearest `release.yaml`, and the
versions from the mirror's own OBS projects, i.e. the pre-release. `project
release` does not store `EXPECTED_VERSIONS` in the mirror. Copied package lanes
carry `name: <pkg>.<segment>` and `package: <pkg>`.

`qa show` computes `EXPECTED_VERSIONS` only with `--expected-versions`, so the CI
matrix step makes no OBS request. An entry that sets `EXPECTED_VERSIONS` itself
keeps its value; jobs that do not declare the parameter ignore it.

`${VAR}` tokens in any value are substituted from the active profile's `env:`
section, plus auto-injected `OBS_ROOTPRJ` and `OBS_CONTAINER_REGISTRY_ROOTPRJ` (the root
project name with `:` replaced by `/`, useful for registry URLs).
Image references (mappings with `image:`) are rendered after substitution; see *Image references*.

### Subcommands

| Command | Purpose |
|---|---|
| `qa show <project>` | Print the resolved matrix (humans). `--expected-versions` also computes `EXPECTED_VERSIONS` from OBS (off by default). `--json` emits one entry per combo with `project`, `package` (empty for project lanes), `pipeline`, `name`, `label`, `axis_filters`, `name_filter`, `package_filter` (`--package <pkg>` for package lanes, `--project-only` for project lanes), `status_context`, `params` — used by CI to drive a GitHub matrix. Empty `[]` when the project has no lane. |
| `qa run <project>` | Trigger Jenkins for every matrix combo. Fire-and-forget by default; pass `--wait` to block until terminal results arrive. `--filter AXIS=val[,val…]` narrows the matrix; `--name NAME` selects one entry of a multi-entry `qa:` block (combinable with `--pipeline`); `--package PKG` runs only that package's `package.yaml` block (combinable with `--name`/`--pipeline`; unknown packages are rejected, listing those that declare `qa:`); `--project-only` runs only the project's own `project.yaml` block, ignoring package blocks (mutually exclusive with `--package`); with neither, every lane runs; `--param NAME=VAL` overrides a parameter at runtime; `--dry-run` prints the POST bodies without calling Jenkins; `--report-json PATH` writes the per-combo result table for CI. |
| `qa status --run-id <id>` | Re-poll non-terminal combos of a previous run and print the current state. |
| `qa retry --run-id <id>` | Re-trigger only the combos whose latest attempt is non-`SUCCESS`. Re-uses the recorded `params` so retries are reproducible. By default skips `ABORTED` combos; pass `--include-aborted` to retry them too. |
| `qa list` | Tabulate recent runs (run-id, project or project/package, pipeline, summary). |

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
./percona-obs -P local project install ppg:staging:17
```

### Filter to a single distribution

```sh
./percona-obs -P local project install --repo RockyLinux_9
```

Example output for a Rocky Linux 9 repository:

```
────────────────────────────────────────────────────────────────────────
RockyLinux_9

# home:Admin:percona:ppg:staging:17
rpm --import http://my-obs.local/home:/Admin:/percona:/ppg:/staging:/17/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/home_Admin_percona_ppg_staging_17.repo << 'EOF'
[home:Admin:percona:ppg:staging:17]
name=home:Admin:percona:ppg:staging:17 - RockyLinux_9
baseurl=http://my-obs.local/home:/Admin:/percona:/ppg:/staging:/17/RockyLinux_9/
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
its built binaries into a dedicated release project. The source project is `ppg:staging:<V>`
— the full, tag-built package set (see [root/README.md](../root/README.md) for the
devel/staging/releases tier layout). Release IDs include the PG minor version and a
counter (e.g. `17.9-1`, `17.9-2`, `17.10-1`). A single OBS release project
(`ppg:releases:17`) covers all minor versions for a PG major.

A release is two hops. Hop 1 copies staging into a per-PR **pre-release** project tree
(`<pr_rootprj>:pr-<N>:<product>:releases:<major>`) when the release PR is opened, so QA runs
against exactly the binaries that will ship. Hop 2, after merge, copies the pre-release into
the release project. Hop 2 never touches staging; hop 1 freezes it only for the copy.

The process is PR-based:

1. **`project release`** — auto-derives the release ID from OBS, regenerates the full
   `releases/<name>/` mirror tree from staging's current config, updates `release.yaml`
   and `CHANGELOG.md`, and commits locally. Pushing the branch and opening the review
   PR remain manual steps.
2. **PR populates the pre-release and runs QA** — `obs-release-pr.yml` (release-only PRs
   only) runs `sync prerelease <project> --branch-from main` on every OBS instance, posts a
   per-instance comment listing the pre-release projects. With the `qa-release` label on
   the PR it then runs every QA lane the release mirrors declare against them (the reusable
   `qa-fanout.yml`; check names are prefixed `Release / OBS QA / …`). Adding the label
   later runs QA alone against the already-populated pre-release.
3. **Fix loop** — if QA fails, fix the package in staging through a normal PR; once merged and
   synced, rebase the release branch, re-run `project release` (refreshes the open id, the
   changelog section and `source_commit`) and push. When only staging changed and the
   changelog is unaffected, repopulate without a push:
   `gh workflow run obs-release-pr.yml -f pr_number=N`. Conversely, a push that changes
   only release `CHANGELOG.md` files (a hand edit of the notes) keeps the populated
   pre-release: populate and QA are skipped for that push, since the changelog never
   reaches OBS.
4. **Merge** — `obs-pr-cleanup.yml` tags the merge commit (one tag per changed `release.yaml`,
   e.g. `ppg/17.9-1`) with `GITHUB_TOKEN` and dispatches `obs-release.yml` **once** with
   `pr_number` and all the tags.
5. **`obs-release.yml`** — its sole trigger is `workflow_dispatch`; per instance it runs
   `sync release <project> --from <pr_rootprj>:pr-<N>:<project>` for every tag, then creates
   the GitHub releases (changelog section as notes) and finally deletes the pre-release.

> **Constraint:** a release PR must change **only** files under `root/*/releases/`.
> `obs-release-pr.yml` fails a PR that mixes release and other `root/` changes, and fails
> when an older open PR already changes the same `release.yaml` (one in-flight release PR per
> major). A release PR that changes no `release.yaml` is rejected too.

### The `PPG_RELEASE` counter

`PPG_RELEASE` is the counter part of a release id, the `1` in `18.6-1`, and it is
what the container image tags are built from. It is **computed, never declared**:
`load_macros` sets it to one plus the number of tags in
`root/<product>/releases/<major>/release.yaml` that belong to the project's current
`PG_VERSION`.

Two consequences follow, and both are deliberate:

- Bumping `PG_MINOR_VERSION` resets the counter to 1 on its own, because the new
  `PG_VERSION` matches no existing tag. There is nothing to remember and nothing to
  edit.
- Merging a release PR raises the counter for that PG version, so the staging
  container images are due to be retagged. `sync-main.yml` syncs that push like any
  other; nothing races it, because the released images already sit in the pre-release
  project that `obs-release.yml` copies from.

A project that needs its own pinned counter can still declare `PPG_RELEASE` in its
`macros.yaml`; an explicit declaration always wins over the computed value.

`PG_PREV_MAJOR_VERSION` is computed the same way: whenever the chain defines
`PG_MAJOR_VERSION`, `load_macros` sets it to that major minus one (the server spec's
`prevmajorversion` and the extras upgrade QA job use it). Declare it explicitly only
to override the arithmetic.

### Step 1 — Create or update a release

```sh
# Fully automatic — both release-name and release-id derived from OBS
./percona-obs -P local project release ppg:staging:17

# Override release-name only
./percona-obs -P local project release ppg:staging:17 --release-name 17

# Override both
./percona-obs -P local project release ppg:staging:17 --release-name 17 --release-id 17.9-1

# Name the source commit explicitly (skips the gh lookup)
./percona-obs -P local project release ppg:staging:17 --source-commit <sha>

# Release spans two OBS instances: also query the labs instance (repeatable)
./percona-obs -P isv project release ppg:staging:18 --also-profile labsmain
```

`--also-profile NAME` (repeatable) adds another profile's OBS instance to the CHANGELOG
queries. Production instances hold disjoint slices of a release (build.opensuse.org has
most packages, labs has the UBI repos and container images), so the CHANGELOG is built
from the union of package versions and image lists across all instances (the `-P`
profile wins on a clash), and a package whose directory is still in the source tree is
never reported as removed.

Before cutting, run `git fetch --tags` (or `git fetch percona --tags`): the open-release
detection below reads local git tags and also consults the remote
(`PERCONA_OBS_PACKAGING_REPO`, via `git ls-remote --tags`), so a stale local clone only
matters when the remote is unreachable (the command then warns, and prints a note when it
refreshes an open release). The command
also needs `gh` (logged in, with network access) on every run unless `--source-commit` is
passed, because it resolves the last synced `main` commit through the GitHub API.

`source-project` must be a `staging`-tier project — any other tier is rejected with an
error. `project release <source-project>` does the following:

1. **Auto-derives `release-id`** (if not given with `--release-id`):
   - Queries OBS for the built version of `percona-postgresql<major>` in the source project.
   - Extracts `MAJOR.MINOR` (e.g. `17.9` from `17.9.0-1.1`).
   - Counts existing entries in `release.yaml` whose tag matches `/<MAJOR.MINOR>-*`
     and appends the next counter (e.g. `17.9-1`, or `17.9-2` if `17.9-1` already exists).
   - If no `percona-postgresql` / `percona-postgresqlNN` package directory exists anywhere
     under the source tree (read from git; e.g. `ppg/staging/common`), a plain counter
     `<name>-N` is used instead (tag `ppg/common-<N>`). A PG major whose OBS listing is transiently empty still fails with the old error (use `--release-id` to override), so an OBS blip can never produce a counter tag for a major.
2. **Resolves the source commit** — the head SHA of the last `sync-main.yml` run on
   `main` whose sync jobs succeeded (`gh api`), or `--source-commit <sha>`. It must be
   an ancestor of HEAD. It is recorded in `release.yaml` so the release names the
   staging tree its binaries were built from.
3. **Open-release refresh** — if the last `releases:` entry has no git tag yet, the
   release is still in flight: the same id is kept, the mirror tree is regenerated, the
   `CHANGELOG.md` section for that id is replaced and `source_commit` is updated. Only
   when the tag exists is the next id derived and appended (`--release-id` always wins).
4. **Fetches** the source project's repository topology from OBS.
5. **Regenerates the full mirror tree**, on every release, not just the first: the
   top-level `project.yaml` plus one nested mirror directory per staging subproject
   (`containers/`, `extras/`, `extras/containers/`, `tarballs/`). All mirrors get
   `build: false`, `publish:` flags are carried over, and subproject paths — including
   intra-project sibling paths — are rewritten to the release namespace. A mirror
   directory whose staging source no longer exists is **deleted**. Each mirror also carries
   its staging project's `qa:` entries (macros rendered, project references rewritten to the
   release project), plus the `qa:` entries of its direct packages' `package.yaml` as
   project-level entries named `<package>.<segment>` (segment = the entry's `name` or its
   `pipeline`), since mirrors have no package directories (when a mirror has more than one entry, the entry
   name becomes the check-name segment); a duplicate name fails the cut. Copied package lanes
   get `name: <pkg>.<segment>` and `package: <pkg>`; versions are computed at `qa run`
   from the pre-release.
6. **Builds `CHANGELOG.md`** — compares built package versions from the top-level staging
   project, `extras`, and `tarballs` against the release OBS project (for updates) and
   generates entries with upstream URLs. Container images are listed per flavor (`ubi8`
   and `ubi9` as distinct entries); the previous-release image diff is queried from
   whichever project actually holds the previous release's images, producing real
   `prev → new` diffs instead of full package dumps (a full dump remains only for a true
   first release). With `--also-profile`, every instance is queried and the results are
   merged.
7. **Appends** a `{tag, source_commit}` entry to `release.yaml`'s `releases:` list (or
   updates the open one) and prepends the new section to `CHANGELOG.md` (or replaces the
   open one's).
8. **Commits** the generated files locally with `git commit -s`. Pushing the branch and
   opening the PR remain manual steps — `project release` does not do either.

The git tag (e.g. `ppg/17.9-1`) is created automatically by `obs-pr-cleanup.yml`, on the
**merge commit**, once the release PR is merged. That tag is then passed as input when
`obs-pr-cleanup.yml` dispatches `obs-release.yml` — pushing a tag does not trigger
anything by itself.

### `release.yaml` format

```yaml
repository: ${PERCONA_OBS_PACKAGING_REPO}
project: ppg:staging:17
releases:
  - ppg/17.9-1                       # historical entries stay plain tags
  - tag: ppg/17.10-1                 # written by project release
    source_commit: 9e9d9738c0ffee…   # full SHA of main the binaries were built from
```

The last entry is the current release, in either form (plain tag string or
`{tag, source_commit}` mapping). `sync release` always uses it as the current tag. Old
entries are kept for history. `sync release --from` and `sync prerelease` require the
last entry to carry a `source_commit`. The backward-compat `revision:` field (plain string) is still
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
```

For **update releases**, only packages whose version changed appear (under `### Changed`):

```markdown
## [17.9-2] - 2025-04-10

### Added

### Changed
- percona-postgresql17: updated to upstream version 17.9.1 (https://www.postgresql.org/docs/release/17.9/)
```

Upstream URLs are derived from the package's `obs/_service` upstream `obs_scm` entry:
- **GitHub** (`https://github.com/…`): appends `/releases/tag/<revision>`.
- **PostgreSQL** (`git.postgresql.org`): maps to `https://www.postgresql.org/docs/release/<MAJOR.MINOR>/`.
- **Other**: uses the bare `url` value.

### CHANGELOG Security section (best-effort CVE scan)

Unless `--no-cve-scan` is passed, `project release` also runs a best-effort CVE
scan and appends the findings as a `### Security` section (after `### Changed`).
Four sources are scanned: upstream release notes/commit logs per changed
package (PostgreSQL release notes for PostgreSQL itself; GitHub compare-diff +
releases for packages whose upstream is on GitHub — other upstreams are
reported as not scanned rather than guessed at), and the Go toolchain delta
(`GOLANG_VERSION` in `macros.yaml`, checked against GitHub's Security-labeled
issue search for each intermediate Go patch release), and this repository's own
commit messages: every `CVE-…` / `GHSA-…` id named by a commit since the previous
release tag that touches the changed package's source directory (a staging
`_aggregate` is followed to the package it reuses, e.g. `ppg:common:deps`) and
that the upstream line does not already list, as
`- <pkg>: <old>→<new> fixes <ids> (packaging commit <sha>)`. Name the advisory in
the commit message of a CVE bump and it reaches the changelog. The scan never blocks a
release cut — anything it cannot resolve (unrecognized upstream, network
failure, unrecognized tag scheme) is reported as a "Not scanned: …" line
rather than silently dropped, and UBI base-image CVEs are explicitly flagged
as out of scope for this scan. No `### Security` section is emitted when the
scan produces nothing (e.g. `--no-cve-scan`, or no packages changed).

### Step 2 — CI ships the release

Release-only PRs are handled by `obs-release-pr.yml` (triggered on open/synchronize/reopen
and on adding the `qa-release` label, of a PR that changes a `root/*/releases/*/release.yaml` (PRs touching only mirrors or
READMEs under `releases/` are skipped with a notice), or by `workflow_dispatch` with a
`pr_number`); `obs-pr-check.yml` gates them out and needs no label for this. Its jobs:

- `resolve` — classifies the PR with `.github/scripts/release_pr.py classify`: release-only
  check and the one-in-flight-per-major guard; a PR with no `release.yaml` change is skipped
  (`kind=none`; `--strict` on `workflow_dispatch` fails instead).
- `populate` — one leg per `OBS_INSTANCES` entry, serialized on the instance's
  `sync-main-sync-<name>` concurrency group (never cancelled; no overlap with a staging
  upload). `<sha>` is the head of the newest `sync-main` run whose upload leg for this
  instance succeeded (the run may still be polling builds). Release PRs must come from a
  branch of the repository itself; fork PRs are refused. Runs
  `sync prerelease <project> --branch-from main --synced-commit <sha>` for
  each release project, uploads the `prerelease-report-<instance>` artifact and posts a
  per-instance PR comment.
- `qa` — calls `qa-fanout.yml` when the PR carries the `qa-release` label: after every
  populate leg succeeded, or on its own when the run was triggered by adding the label
  (populate is skipped then; any other label skips the whole run).

On merge:

1. `sync-main.yml` runs `sync push` normally (releases/ directories are excluded from
   traversal). It creates no tag and is not paused.
2. `obs-pr-cleanup.yml`, on close of the merged release PR, tags `merge_commit_sha` with
   `GITHUB_TOKEN` (e.g. `ppg/17.9-1`) and dispatches `obs-release.yml` once via
   `gh workflow run obs-release.yml --ref main -f pr_number=<N> -f tags="<tag> …"`. A
   tag-creation or dispatch API error fails the job; only a genuine "tag already exists"
   response is tolerated, and such a tag is dispatched only when it already points at the
   merge commit (a re-run after a partial failure). The PR's OBS project tree is kept (it is the copy source) and
   deleted by `obs-release.yml`.
3. `obs-release.yml`'s **sole trigger** is `workflow_dispatch` (inputs `pr_number`,
   `tags`; pushing a tag by hand is inert). Per instance it derives each release project
   from its tag (`ppg/17.9-1` → `ppg:releases:17`) and runs `sync release --from` the
   pre-release. Each leg serializes on its own `obs-release-<name>` concurrency group
   (hop 2 writes only `:releases:` projects, so it does not share sync-main's group).
4. `finalize` creates (or updates the notes of) one GitHub release per tag from its
   `CHANGELOG.md` section. If any copy failed it instead fails with an `::error::` and the
   pre-release is kept.
5. `delete` removes the pre-release project tree on every instance, only after every copy
   and the GitHub releases succeeded.

### Failure and recovery

Hop 1 (PR open):

| Failure | Behaviour | Recovery |
|---|---|---|
| Staging not green / drain timeout | `sync prerelease` fails before copying; freeze restored; PR comment names the packages | Fix staging, repopulate |
| Staging moved since the cut | Record check fails before any freeze, printing the staging-path diff | Re-run `project release`, push |
| Partial copy (OBS error mid `osc release`) | Freeze restored; pre-release holds a mix; verify fails loudly | Repopulate (update-in-place, idempotent) |
| Push during population | Second run queues behind the first in the per-instance group | None needed |
| A queued populate displaced by a newer pending run in the same group | Nothing frozen, nothing copied | `gh workflow run obs-release-pr.yml -f pr_number=N` |

Nothing writes to the PR branch, so there is no bot commit and no trigger loop.

Hop 2 (after merge):

| Failure | Behaviour | Recovery |
|---|---|---|
| A leg fails | `finalize` fails with `::error::`, no GitHub releases, no delete; tag exists; pre-release intact; staging untouched | Re-dispatch with the same inputs (idempotent): `gh workflow run obs-release.yml -f pr_number=N -f tags="ppg/17.12-1 ppg/18.7-1"` |
| Record mismatch (pre-release description ≠ tagged entry) | Leg refuses | The merged record is wrong: open a new release PR |
| Pre-release already deleted | Leg fails on missing source project | Cut a new release: re-run `project release` and open a new release PR. Repopulating the merged PR is refused by the record check, because main's `release.yaml` changed at the merge (`PPG_RELEASE` bumped) |
| Dispatch failure in obs-pr-cleanup | Tags exist, nothing copied | Manual dispatch as above |

#### Published repo incomplete on the download host

Symptom: a released repo is `published` on OBS and `osc api /published/<prj>/<repo>`
lists every file, but `download.opensuse.org` / `downloadcontent.opensuse.org` serve only
part of it (e.g. deb `InRelease` and `Release.gpg` return 404 while `Release` and
`Packages.gz` return 200). The OBS publisher's rsync to the download host stopped
half-way; it does not recover on its own. This is not a release-flow failure: do **not**
re-run the release workflow (the pre-release is gone, and the binaries in the release
project are already correct). Fix it directly with `osc`, one repo at a time.

Neither a publish-flag toggle nor a title edit alone helps: the publisher is only
triggered when the repo's binaries change, and it skips the rsync when its state
(binaries + project title) is unchanged. So change the title, then trigger the publisher
for the one broken repo with `unpublish` of a package that has **no** binaries in that
repo (nothing is removed, but the publisher still runs):

```sh
A="osc -A https://api.opensuse.org"; P=isv:percona:ppg:releases:18; R=Ubuntu_22.04
$A meta prj $P > meta.orig.xml
# 1. bump the title only (triggers nothing by itself)
sed 's|<title>\(.*\)</title>|<title>\1 (republish)</title>|' meta.orig.xml > meta.new.xml
$A meta prj $P -F meta.new.xml
# 2. pick a package with no binaries in $R (empty output = none), e.g. an RPM-only one
$A api /build/$P/$R/x86_64/python3-six | grep '<binary '
$A api -X POST "/build/$P?cmd=unpublish&repository=$R&package=python3-six"
# 3. wait for the download host (≈1 min), then check the files are back
curl -sI https://download.opensuse.org/repositories/${P//:/:\/}/$R/InRelease | head -1
# 4. restore the title (triggers nothing; other repos are untouched)
$A meta prj $P -F meta.orig.xml
```

OBS deb repos are flat: `<arch>/Packages.gz` never exists, so its 404 is expected.

### `sync prerelease` — hop 1 (staging → PR pre-release)

Run with the PR profile; `--branch-from` names the production profile holding staging:

```sh
./percona-obs -P pr-12 sync prerelease ppg:releases:18 --branch-from main
```

Steps: (1) require a `source_commit` on the last `release.yaml` entry; (2) **record
check** — the freeze-scope paths (source tree, its `macros.yaml` chain,
`root/<product>/releases/<major>/release.yaml` — `PPG_RELEASE` is computed from it, so
a merged release refuses a repopulate — every whole-frozen project, every
aggregate-frozen package) must be identical between
`source_commit` and the last synced `main` (`--synced-commit`, else `gh api`), or it
fails with "staging changed since the cut"; edits under `root/<product>/staging/_shared/...`
count as staging changes because the check follows the `_shared/` symlink targets of
packages; (3) an existing pre-release tree (the project and every subproject under it) is
**deleted**, so a repopulate always starts from scratch; refused when the profile's
`rootprj` equals the `--branch-from` root; (4) pre-release meta from the mirrors, **publish forced on**; (5) drain, assert
green, freeze, `osc release`, verify, restore; (6) `source_commit: <sha>` and
`release_id: <id>` appended, in that order, to each pre-release project description.

**`release_id` marker.** Every release hop (this one, `sync release --from` and the
legacy single-hop `sync release`) writes `release_id: <id>` as the **last line** of each
target project's description, so tools reading a release project can tell which release
its binaries belong to. The id is the last `release.yaml` tag without its product
prefix: `ppg/18.7-1` → `18.7-1`, `ppg/common-1` → `common-1`. It is written after the
project's mirror meta is applied (which rewrites the description) and **before** that
project's `osc release`, so the description already names the release when the binaries
land. On pre-release projects `source_commit` is written after the copy, because its
presence marks a complete populate; `release_id` is re-appended with it so it stays the
last line. On release projects the hop-2 meta apply drops the pre-release
`source_commit`, so they end with `release_id` alone. `sync push` never touches
`:releases:` projects, so the marker stays until the next release.

| Flag | Default | Effect |
|---|---|---|
| `--branch-from PROFILE` | required | Profile of the production instance holding the staging source. |
| `--synced-commit SHA` | `gh` lookup | Head SHA of the newest sync-main run whose sync jobs succeeded (the run may still be polling builds; CI passes the per-instance value). |
| `--source-commit SHA` | last entry's | Override the `source_commit` from `release.yaml`. |
| `--force` | off | Skips the record check (2). |
| `--no-freeze` | off | Skips the drain/green-check/freeze sequence. |
| `--freeze-timeout` | `3600` | Bound on the drain step, seconds. |
| `--verify-timeout` | `600` | Bound on the post-release verify poll (`0` disables). |
| `--dry-run` | off | Runs (1), (2), the mirror/changelog/tag checks and the green check only. |

`obs-release-pr.yml` calls this once per release project on every OBS instance.

### `sync release --from` — hop 2 (pre-release → release project)

```sh
./percona-obs -P main sync release ppg:releases:18 --from isv:percona:PR:pr-12:ppg:releases:18
```

No freeze, no git divergence check. The last `release.yaml` entry must have a
`source_commit` and the pre-release description's marker must equal it; a missing or
different marker, or an entry without `source_commit`, is refused (`--force` skips both
checks). Then the release project meta is applied from the mirrors, `release_id: <id>` is
appended to each project description and binaries are copied with `osc release`. Known limitation: `--dry-run` together with `--from` still only runs
the staging-side dry-run checks.

### Running `sync release` manually

For local testing or recovery from a failed CI run:

```sh
./percona-obs -P local sync release ppg:releases:17 --skip-tag-check
```

Flags:

| Flag | Default | Effect |
|---|---|---|
| `--dry-run` | off | Read-only: checks that every staging subproject has a mirror, the `CHANGELOG.md` section for the release ID exists, the tag does not already exist, the source OBS project is reachable, and every staging package currently reports `succeeded`. Does not freeze, release, or write anything. |
| `--force` | off | Skips the divergence (tag) check entirely. |
| `--skip-tag-check` | off | Skips only the `git diff <tag>..HEAD` check — use when the tag doesn't exist locally yet. |
| `--no-freeze` | off | Skips the drain/freeze/restore sequence (§ below) — for recovery scenarios where staging is already known idle. |
| `--freeze-timeout` | `3600` (seconds) | Bound on the drain step; the release fails rather than waiting forever for a stuck package. |
| `--verify-timeout` | `600` (seconds, `0` disables) | Bound on the post-release poll that confirms each released repo actually holds binaries. |
| `--from OBS_PROJECT` | off | Hop 2: copy from this pre-release OBS project (full name) instead of staging; no freeze, no git divergence check. See above. |

`sync release <release-project>` reads `release.yaml` and performs:

1. **Divergence check** (skipped with `--force`):
   - Checks that no files under the source project have changed since the release tag
     (`git diff <tag>..HEAD`). This check runs on both the first-release and update paths.
     Pass `--skip-tag-check` when the tag doesn't exist locally.
2. **Mirror check** — a staging subproject with no corresponding local mirror directory
   is a **hard error** (never silently skipped).
3. **Applies the release project config** — the top-level release project meta is
   re-applied on the update path too, not just on first creation, and this happens
   *before* the freeze sequence below. Release targets are added only for repos
   present on both sides.
4. **Freeze sequence** (skipped with `--no-freeze`), applying to every release, first or
   update:
   1. **Drain** — poll `_result` for the staging project and all subprojects until no
      package is `building` / `scheduled` / `dispatching` / `blocked` / `finished` /
      `signing`, bounded by `--freeze-timeout`.
   2. **Assert green** — every package is `succeeded` (or legitimately `excluded` /
      `disabled`); any `failed` / `unresolvable` / `broken` aborts the release.
   3. **Freeze** — snapshot each project's meta, then disable builds on staging and
      every subproject.

      **Freeze scope.** Before `osc release` the command drains and green-checks, then
      build-disables for the duration of the copy:

      - the release source project and its subprojects (whole);
      - every local aggregate source referenced by an `obs/_aggregate` under the
        source tree — `ppg:staging:common:tools`, `ppg:common:deps` — restricted to the
        aggregated packages (package `_meta` build disable);
      - for a `common` release (a source without a server package), every image-holding
        project under the source: the `subproject:` entries of its repository paths (whole),
        since an image may consume any package of them; per-major releases freeze only the
        aggregated packages.

      `--dry-run` prints the extra sources as `+ <project>  (whole)` or
      `+ <project>  (<pkg>, …)` and includes them in the green check.
   4. **Release** — `osc release` for the top-level project and every subproject.
   5. **Verify** — still inside the freeze window, polls (bounded by
      `--verify-timeout`) until each released repo holds binaries.
   6. **Restore** — in a `finally` (so it still runs even if verify times out or
      raises), re-apply each project's exact snapshotted meta last (never a blanket
      enable, since subprojects carry per-repo flags — e.g. tarballs' `publish:`
      flags — that must survive the round trip).
5. Release-tier OBS projects with no local mirror are reported loudly as orphans;
   deletion is never automatic — run `sync delete` manually.

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
            ├── containers/         # nested, mirrors staging's containers/ subproject
            │   └── project.yaml    # builds disabled, paths → release project
            ├── extras/
            │   ├── project.yaml
            │   └── containers/
            │       └── project.yaml
            └── tarballs/
                └── project.yaml
```

Subproject mirrors are nested directories, never colon-named — `containers:ubi9/`
describes only the pre-restructure layout and no longer reflects reality.
`project release` **regenerates the entire mirror tree from staging's current
config on every release**, not just the first: mirrors for subprojects that still
exist in staging are refreshed in place, and mirror directories whose staging
source no longer exists are deleted.

The `releases/` directory is excluded from `sync push` traversal — release
directories (identified by `release.yaml`) are never synced to OBS as source
projects.

### Non-release PR: copying binaries to production on merge

`sync release-pr` still exists, but no workflow invokes it anymore — it is a
manual/recovery-only command. Previously `obs-pr-cleanup.yml` ran it before deleting
the PR project; that step has been removed from the workflow.

`sync release-pr` copies the PR's built binaries to the corresponding production OBS
projects via the `<releasetarget>` entries that `sync push --branch-from` added to
every active PR project's repository configuration.

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
./percona-obs -P local sync delete ppg:staging:17 --dry-run
```

### Delete a full project tree

```sh
./percona-obs -P local sync delete --yes --recursive
```

Deletes the root project and all sub-projects (deepest first). Prompts for confirmation
unless `--yes` is given. Use `--recursive` to delete projects that still contain packages.

### Delete a single subproject

```sh
./percona-obs -P local sync delete ppg:staging:17 --yes --recursive
```

### Delete a single package

```sh
./percona-obs -P local sync delete ppg:staging:17 etcd --yes
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
   cp -r root/ppg/staging/17/percona-pg-telemetry root/ppg/staging/17/my-pg-extension
   ```
2. Replace all `percona-pg-telemetry` references with `my-pg-extension` throughout the
   copied files.
3. Update `obs/_service` to point to the new package's upstream repo.
4. Update `obs/_multibuild` with the PG major versions to build for.
5. Update `rpm/*.spec` and `debian/control` — keep `@BUILD_FLAVOR@` placeholders.
6. Sync to OBS:
   ```sh
   ./percona-obs -P local sync push ppg:staging:17 my-pg-extension
   ```
