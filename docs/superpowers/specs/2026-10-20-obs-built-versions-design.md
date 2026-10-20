# Package versions from OBS builds — design

Date: 2026-10-20. Status: approved in brainstorming, awaiting spec review.

## Problem

`qa` sends Jenkins an `EXPECTED_VERSIONS` parameter (`package=version` lines) so
the test suites check the versions we actually ship instead of their own
tables. Today the versions are derived **locally**, by parsing each package's
`obs/_service` with per-service-type heuristics (`obs_scm` `version`,
`versionformat`, `@PARENT_TAG@` + rewrite, SHA→tag lookup, and since 8f803fe6
`set_version` + `download_url` filenames).

That model failed in release PR #148: pgBackRest 2.60.0 moved to a
`download_url` service, the parser found no version and **silently dropped the
package**, so every container, server and tarball lane fell back to the test
suite's default (2.59.2) and failed against the correct 2.60.0 binaries.
8f803fe6 patched that service type, but the model stays fragile: every new
service style is a new heuristic, and a miss is silent.

OBS already knows the answer: every built binary carries its version in its
file name.

## Decisions (from brainstorming)

1. **Source of truth: what OBS built.** Versions come from the binary file
   names OBS holds for a package, not from local `_service` parsing.
2. **Artifacts:** container-image and tarball projects keep today's selection
   rule — the packages of the projects they build from (`subproject:` paths),
   first provider wins — only the version source moves to OBS.
3. **Timing:** computed at **`qa run`**, from the OBS project the lane tests,
   for every lane (PR, staging, nightly, pre-release). `project release` **stops
   baking** `EXPECTED_VERSIONS` into release-mirror `qa:` entries.
4. **Agreement:** the upstream version of a package must be identical in every
   repository of the instance's slice that has binaries for it; otherwise
   `qa run` fails before triggering Jenkins.
5. **Approach:** one `binarylist` request per OBS project (not per package and
   repository).
6. **`project versions --online`** uses the same fetch for its package rows and
   keeps printing a full versrel (warning, not failing, on disagreement).

## Components

### New module `percona_obs/obs_versions.py`

Owns "which version did OBS build".

```python
def project_binary_versions(
    apiurl: str, obs_project: str, repo_filter: RepositoryFilter | None
) -> dict[str, dict[tuple[str, str], str]]:
    """{package: {(repo, arch): versrel}} for every package of obs_project
    with a readable binary, from one GET /build/<prj>/_result?view=binarylist.
    Repositories outside repo_filter are skipped."""

def upstream_version(versrel: str) -> str:
    """'2.60.0-1.1' -> '2.60.0' (drops the release: everything from the
    last '-')."""

class VersionConflict(Exception):
    package: str
    by_version: dict[str, list[tuple[str, str]]]   # upstream -> [(repo, arch)]

def agreed_version(package: str, per_repo: dict[tuple[str, str], str]) -> str:
    """The upstream version all repositories agree on; raises VersionConflict."""

def first_versrel(per_repo: dict[tuple[str, str], str]) -> str:
    """versrel of the first (repo, arch) in sorted order."""
```

- A per-process cache keyed by `(apiurl, obs_project)` makes each project's
  `binarylist` fetched once per command.
- An HTTP or parse error raises (`SystemExit` naming the project). A partial
  list is the failure mode this design exists to remove, so errors are never
  swallowed.

### Binary file name parsing (`cmd_build._version_from_binary`, extended)

Per repository, one binary decides the package's versrel:

- **Preferred:** the source artifact, whose name is the package's own —
  `name-version-release.src.rpm` or `name_version.dsc`.
- **Otherwise:** the first readable binary in sorted file name order —
  `name-version-release.arch.rpm` or `name_version-release_arch.deb`.
- Unreadable names (`_buildenv`, `_statistics`, image `.tar`/`.containerinfo`,
  tarball `.tar.gz`) are ignored; a package with none in a repository has no
  entry for that repository.

`_version_from_binary` gains `.src.rpm` and `.dsc` support (a pure function;
`_fetch_pkg_versrel` keeps returning the same versrel because every binary of a
package shares it). DEB file names carry no epoch, so versions never include
one. Upstream suffixes such as `~rc1` or `+git…` are kept: they are part of the
version OBS built.

Examples:

| File name | versrel | upstream |
|---|---|---|
| `percona-pgbackrest-2.60.0-1.1.src.rpm` | `2.60.0-1.1` | `2.60.0` |
| `percona-postgresql17-17.11.1-1.18.x86_64.rpm` | `17.11.1-1.18` | `17.11.1` |
| `percona-postgresql-17_17.11.1-1.dsc` | `17.11.1-1` | `17.11.1` |
| `percona-pg-tde18_2.2.2-6_amd64.deb` | `2.2.2-6` | `2.2.2` |

### `cmd_qa` — `EXPECTED_VERSIONS` from OBS

- `_package_versions(project, ctx)` keeps its package selection: the project's
  own packages, plus — for projects without own versions or that build
  artifacts — the packages of the projects named by its repositories'
  `subproject:` paths, in path order, first provider winning. The local tree
  still says *which* projects and packages; OBS says *which version*.
- For each package the version is `agreed_version(...)` over
  `project_binary_versions(<rootprj>:<project>, slice)`.
- **Aggregates** need no special case: OBS lists the aggregated binaries under
  the aggregating package.
- **PR lanes:** a package **absent** from the PR project (not promoted, so the
  `binarylist` has no entry for it) is looked up under the fallback root — the
  existing `image-fallback-rootprj` (profile key or `--image-fallback-rootprj`),
  which CI already sets to the production root. A package that is present but
  has no readable binaries (e.g. its PR build failed) does **not** fall back:
  it is reported in the warning, so a PR never tests against production's
  version of a package it changed. Release lanes need no fallback: the
  pre-release tree is a complete copy.
- **`qa run`** computes the values right before triggering Jenkins (the CI QA
  jobs already run after the builds finished). A `VersionConflict` aborts the
  run before any trigger:

  ```
  error: percona-foo: OBS builds disagree on the version: 1.2.3 (RockyLinux_9/x86_64, Debian_12/x86_64), 1.2.4 (Ubuntu_24.04/x86_64)
  ```

  The conflict scope is the selected lanes: the abort applies only when a
  lane left after `--project-only`/`--package`/`--name`/`--pipeline` would
  send the conflicting package; other conflicts are `warning:` lines. A
  missing OBS project under test is an error.

  Packages with no binaries anywhere are left out and named in **one warning**
  (no silent drop).
- **`qa show`** no longer computes `EXPECTED_VERSIONS` by default, so
  `list_qa_matrix.py` (CI matrix detection, which may run before builds finish)
  stays OBS-free. New flag `qa show --expected-versions` computes them for
  inspection (requires an OBS connection).
- An entry that sets `EXPECTED_VERSIONS` in its own `parameters:` is sent
  unchanged, as today. A package lane (`<pkg>.<segment>`) gets only its own
  package's line, as today.
- Removed from `cmd_qa`: the `_service` route (`_own_package_versions` reading
  `_extract_version_from_service`).

### `project release` — no more baking

`_mirror_qa_entries` stops injecting `EXPECTED_VERSIONS`; mirror `qa:` entries
carry only their declared parameters (macros rendered and package lanes copied
as today). Release lanes get their values from the pre-release at `qa run`.

### `project versions --online`

Package rows on both online paths — normal projects and release projects
(`_fill_release_online_records`) — use `project_binary_versions` (one request per
project) instead of build results plus per-package, per-repository binary
listings.

- Output is unchanged in form: the full versrel, now deterministically from
  the first `(repo, arch)` in sorted order (`first_versrel`).
- Agreement is checked on the upstream part; a conflict prints a warning with
  the per-repository values and the row is still printed.
- Aggregate lookup keeps its order: the source project first, then the
  aggregating project.
- Image rows stay on containerinfo plus the container package list.
- Offline `project versions` (local `_service` parsing) is unchanged;
  `_extract_version_from_service` stays for it and for the CHANGELOG URL
  helpers.

### Out of scope

- The release CHANGELOG already reads versions from OBS
  (`_collect_release_obs_data`); it may adopt the module later.
- Reading artifact manifests (`<image>.packages`, tarball contents) instead of
  source-package versions.

## Testing

Unit tests with OBS mocked by canned `binarylist` XML:

- File name parsing: `.src.rpm`, `.rpm`, `.dsc`, `.deb`, `~rc1`/`+` suffixes,
  unreadable names, source artifact preferred.
- `project_binary_versions`: slice filtering, one request per project per
  command, packages without readable binaries absent, request error raises.
- `agreed_version`: equal values, conflict with the per-repository listing.
- `cmd_qa`: own packages, build-from order with first provider winning, PR
  fallback root, values reach the triggered parameters, a conflict aborts
  before any trigger, one warning for packages without binaries, explicit
  `EXPECTED_VERSIONS` untouched, package-lane single line.
- `qa show`: no OBS request by default; `--expected-versions` computes.
- `project release`: mirror entries no longer gain `EXPECTED_VERSIONS`
  (existing baking tests updated).
- `project versions --online`: first sorted versrel printed, conflict warns
  without failing, aggregate fallback, release-project listing, one request per
  project.

Live, read-only check before merge:

```
percona-obs -P isv qa show ppg:staging:18 --expected-versions --json
percona-obs -P labsmain qa show ppg:staging:18:containers --expected-versions --json
```

Expect `percona-pgbackrest=2.60.0` and no conflict; diff against the values the
local parser produces today to catch surprises.

## Docs

- `docs/PERCONA_OBS_TOOL.md`: rewrite the `EXPECTED_VERSIONS` section (OBS
  binaries at `qa run`, agreement rule, warning, PR fallback, `qa show
  --expected-versions`); drop "baked at cut time" from the releasing steps;
  note the `project versions --online` source.
- `docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md`
  §2: mirrors no longer carry baked `EXPECTED_VERSIONS`.
- `.github/copilot-instructions.md`: same facts in the architecture reference.

## Rollout

Tool-only change. After merge, refresh release PR #148 (`project release` for
17 and 18): the mirrors lose their baked values and the release lanes compute
from the pre-release projects.
