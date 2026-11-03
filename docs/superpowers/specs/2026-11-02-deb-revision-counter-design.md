# Computed package revision counter (`PKG_REVISION`)

Date: 2026-11-02, revised 2026-11-03
Status: design for review, not yet implemented

## Problem

Every Debian package built by OBS carries the revision `1`: the dsc either has
no revision (`Version: 1:%!{PGAUDIT_VERSION}`, so debtransform appends `-1`),
hardcodes it (`Version: 1:%!{PG_VERSION}-1`), or is rewritten by `set_version`
to `<ver>` / `<ver>-0`. `Debtransform-Release: 1` then appends
`+<CI_CNT>.<B_CNT>.<codename>` from the prjconf `Release:` line.

Every RPM built by OBS gets `Release: <CI_CNT>.<B_CNT>%{?dist}` from the
prjconf `spec:` override (PR #194); the spec's own `Release:` line is ignored.
`CI_CNT` is the number of source commits OBS has seen for the package, and it
restarts from 1 when a package is deleted and re-added to a project.

The old process (`percona/postgres-packaging`, one branch per PPG minor) kept
a hand-maintained revision per component in `versions.sh`, used for both the
deb revision and the rpm `Release:`. It went up every time a minor shipped a
rebuild of an extension whose upstream version did not change, and back to 1
when the upstream version changed. Production repos on `repo.percona.com`
therefore hold counters of 2 to 7 for most components.

dpkg compares epoch, then upstream version, then revision; rpm compares epoch,
version, release with every non-alphanumeric character as an equal separator.
When the upstream version is the same on both sides, the OBS build loses:

| OBS                         | Production           | Result | Why                                   |
|-----------------------------|----------------------|--------|---------------------------------------|
| `1:17.1-1+5.4.bookworm`     | `1:17.1-4.bookworm`  | older  | revision `1 < 4`                      |
| `1:293-1+4.1.bookworm`      | `1:293-1.bookworm`   | older  | same `1`, then `+` sorts below `.`    |
| `2:17.11.1-1+4.1.bookworm`  | `2:17.11-1.bookworm` | newer  | upstream differs, revision never read |
| `4.2.0-5.4.el9` (set_user)  | `4.2.0-6.el9`        | older  | `5 < 6`                               |
| `17.1-7.1.el9` (pgaudit)    | `17.1-4.el9`         | newer  | only because CI_CNT happens to be 7   |

The consumer upgrade tests (obs-sync sandbox, 2026-11-02) show 34 deb binaries
per codename in each of `ppg-17` and `ppg-18` that `apt full-upgrade` leaves
on the production build, silently. The RPM side was not checked exhaustively;
set_user above is one confirmed miss, and every RPM "win" rests on CI_CNT
luck that a package delete/re-add erases.

The migration to OBS-built packages happens at the next minor of PG 14–18 and
at the PG 19 GA. At that point every OBS package must sort strictly above
whatever a user already has installed from production.

## Goals

1. Every deb and rpm binary published from OBS sorts above the highest version
   of the same binary in any production vault, for every codename and EL
   major, from the migration release onward.
2. Nobody manages revision numbers by hand. The revision is computed from the
   git tree exactly like `PPG_RELEASE` is today.
3. The revision resets to 1 by itself when a package's upstream version
   changes, and climbs by itself across release cuts at the same upstream
   version.
4. The seed values that carry the old process's counters forward are a
   one-off, live in code, and are dead weight that can be deleted once every
   seeded upstream version has moved.
5. Builds and the sync content check stay reproducible: the value is a pure
   function of the git tree, computable at any historical commit.
6. One macro serves both formats.

## Non-goals

- A version-order gate in `percona-obs`. The obs-sync consumer harness already
  compares real `Packages` indexes against production per codename; that is
  where the invariant is proven, against the release QA lane of the migration
  minors. The harness grows the same comparison for RPM repodata.
- Changing the `+<CI_CNT>.<B_CNT>.<codename>` deb suffix, the rpm
  `.<CI_CNT>.<B_CNT>` suffix, or `Debtransform-Release`.
- The devel tier. Its packages are never published to users.
- Bumping epochs. Permanent, and it changes how Percona packages compare with
  PGDG forever.
- Container tags, tarballs, aggregates: nothing with a `_service`-driven
  version is excluded, nothing without one is touched.

## Design

### The counter

For a package in OBS project `P` whose upstream version is `V`:

```
PKG_REVISION = floor(P, package, V) + 1 + past_releases(V)
```

- `floor(P, package, V)`: the production counter carried forward, from the
  hardcoded seed table (below). 0 when there is no entry.
- `past_releases(V)`: the number of entries in the project's `release.yaml`
  whose released tree built this package at upstream version `V`.

Properties:

- **Reset by itself.** A new `V` matches no seed and no past release, so the
  counter is 1. Exactly the old process's rule, without a human.
- **Climb by itself.** Each `project release` cut appends an entry to
  `release.yaml`; the next build at the same `V` counts one more. Between
  cuts, rebuilds are ordered by the OBS counters as today. Users only consume
  `ppg:releases:*`, so a CI_CNT reset in staging between two cuts never
  reaches them: the next cut carries a higher revision regardless.
  Between cuts the revision stays put: a rebuild caused by a dependency
  change is a new OBS build (`B_CNT`), not a new revision.
- **Distinct from `PPG_RELEASE`.** `PPG_RELEASE` is the ordinal of the
  product release of `PG_VERSION` (`17.12-2` → 2) and resets at every minor;
  `PKG_REVISION` climbs for as long as the package's own `V` stands still
  (pgaudit 17.1 across 17.12-1, 17.12-2, 17.13-1 → 5, 6, 7). Images and the
  cross-major upgrade images have no `_service`, so they keep `PPG_RELEASE`
  for `LABEL version`/`release`, `ENV PPG_VERSION` and the server call-home.
  For the server family the two numbers coincide, because `V` changes every
  minor and the family has no production floor, but the dsc and spec use
  `PKG_REVISION` like every other package.
- **Eager, not lazy.** Like `PPG_RELEASE`, the macro changes at each cut and
  `_macros_changed_since` sees it, so sync-main re-pushes every package of
  the project and OBS rebuilds it with the new revision. A lazy variant
  (exclude `PKG_REVISION` from the change check, so only packages touched
  for another reason pick up the new value) was rejected: a package rebuilt
  by a dependency change alone, e.g. a base-image or golang CVE fix, would
  ship in two consecutive releases at the same revision with different
  bytes. Invariant: no two releases contain the same (package, `V`,
  revision). The cost is one full-project rebuild per cut.
- **Pure.** Inputs are the package's `obs/_service`, the macros chain,
  `release.yaml` and the trees at the released commits. All reachable through
  `git show`, so `git_utils._macros_changed_since` can compute the identical
  value at the last synced commit. This is the same constraint PR #58 solved
  for `PPG_RELEASE`; without it every package would compare unequal on every
  sync.

An explicitly declared `PKG_REVISION` in a `macros.yaml` wins, as it does for
`PPG_RELEASE`. Nothing declares it; the escape hatch costs nothing.

### Where the upstream version comes from

Neither packaging file is a usable source: spec `Version:` is a placeholder
(`1.0.0`) that OBS `set_version` overwrites at build time, and 40 dsc files
carry the same kind of placeholder. `package.yaml` is absent on 81 built
packages. The one file every built package has, and the one OBS itself reads
to decide the version, is `obs/_service`.

`V` is therefore what `cmd_project._extract_version_from_service` returns for
the package's `obs/_service`, rendered through the macro chain. That helper
already mirrors OBS for `project versions` and for QA `EXPECTED_VERSIONS`:
obs_scm `version` param; `versionformat`; `@PARENT_TAG@` with
`versionrewrite-pattern` applied to `revision`; set_version `version` param
or `basename` + download_url filename. It moves to `common.py` (or a small
`versions.py`) so `inject_computed_macros` and `cmd_project` share it.

Checked offline (2026-11-03) over every package under a `release.yaml`
project — staging 14–19 including extras, tde and tarballs, and
`staging:common:tools`: all resolve to a concrete version, none needs the
network. Two values are wrong because the helper ignores
`versionrewrite-replacement`: pgadmin4 renders `9` (tag `REL-9_17`, should
be `9.17`) and pg_similarity renders `pg_similarity_1_0` (should be `1.0`).
That fix is part of this work; the counter needs `V` to equal what OBS
writes so that seed keys match.

Two rules keep it pure:

- **Offline only.** The helper's SHA → git tag lookup (network) is disabled
  on this path. A package whose `V` would need it fails `project verify`:
  "pin a tag or add a `version` param". No package under a `release.yaml`
  project hits this today.
- **No `_service`, no macro.** Aggregates, images, simpleimage tarballs and
  `_link` packages get nothing injected. `V` carries no epoch; the epoch stays
  in the dsc/spec where it is today.

`inject_computed_macros` already receives the package path from every
`load_macros` caller; it gains the per-package computation next to
`PPG_RELEASE`.

### Which `release.yaml`

`PPG_RELEASE` derives `root/<product>/releases/<major>/release.yaml` from the
major of `PG_VERSION`. `PKG_REVISION` instead reverse-maps the package's OBS
project to the `release.yaml` whose `project:` field names it (or an ancestor
of it, so `ppg:staging:17:extras` resolves to `releases/17`). This also covers
`ppg:staging:common:tools` (`ppg/common-<N>` releases, none cut yet) and any
project that has never been released: no matching file means
`past_releases = 0`.

For each entry, the released tree is `source_commit` when recorded, otherwise
the commit the tag points at. The package's `obs/_service` and macros chain
are read at that commit through the lexically resolved path (`_shared/`
symlinks are blobs to git; the resolver in `git_utils` already handles this),
`V` is computed, and the entry counts when it equals the current one. A
package absent at that commit is not counted; a package present but not yet
carrying the `PKG_REVISION` token is counted all the same: the counter must
keep climbing across the commit that introduces this feature.

Cost: one `git show` of `_service` and of the macros chain per release entry
(seven today for 17 and 18, cached per process).

### Seed table

```python
# percona_obs/common.py
#
# Production counters carried forward across the OBS migration. Keyed by OBS
# project, package and upstream version (no epoch). Each value is
# max(deb revision, rpm release) over every production vault, codename and
# EL major. An entry is dead once that package ships a different upstream
# version; delete the table when every entry is dead.
_PKG_REVISION_FLOORS: dict[tuple[str, str, str], int] = {
    ("ppg:staging:14", "percona-pgaudit", "1.6.3"): 7,
    ("ppg:staging:17", "percona-pgaudit", "17.1"): 4,
    ("ppg:staging:17", "percona-pgaudit_set_user", "4.2.0"): 6,
    ("ppg:staging:17", "percona-pg_repack", "1.5.3"): 5,
    ...
}
```

- Keyed by OBS project and package name, the identity the tool already uses
  everywhere, rather than by rendered dsc `Source:` (which RPM-only packages
  lack).
- Each value is the **maximum over every production vault, both formats**.
  Where deb and rpm disagree the higher one wins for both: pgaudit 14/15 are
  4 on deb and 7 on rpm → 7; pgpool2 is 2 on deb and 1 on rpm → 2.
- Shared binaries (`percona-postgresql-common`, `percona-patroni`,
  `percona-pgbadger`, `percona-pg-gather`, `python3-ydiff`, PostGIS doc
  packages) take the cross-major maximum so a user installing PG 19 next to
  PG 18 never sees a lower version from the 19 repo.
- The one source of truth for the values is the dump of the production
  indexes taken 2026-11-02/03 (203 deb `Packages` indexes, 149 rpm listings
  over 65 vaults; full table in the review artifact). If production ships a
  hotfix with a higher counter before the migration, the table is regenerated
  and committed; after the migration it is never touched again.
- The table is in code, so both sides of `_macros_changed_since` evaluate the
  same constants.

Resulting first-migration values (ppg-17): pgaudit `17.1-5`, set_user
`4.2.0-7`, pg_repack `1.5.3-6`, postgresql-common `293-2`, pg_tde `2.2.2-2`;
metapackage `17.12-1` (upstream moved, no floor needed).

### Cross-major divergence

Each major counts its own releases, so `percona-postgresql-common 1:293` can
be `-3` in `ppg-17` and `-2` in `ppg-18` at some point. apt/dnf install the
highest among enabled repos; both are above production because the floor is
the global maximum. This mirrors how the OBS counters already differ per
major today.

### Debian packaging files

Every Debian source converges on one template for the dsc and the changelog
header:

```
Version: [<epoch>:]%!{<PKG>_VERSION}-%!{PKG_REVISION}
percona-pgaudit (1:%!{PGAUDIT_VERSION}-%!{PKG_REVISION}) unstable; urgency=low
```

| Style                                   | Packages                                                                  | Change                                                                          |
|-----------------------------------------|---------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| `Version: 1:%!{X_VERSION}` (no revision) | most `_shared/`, `common/tools`, `common/deps` (etcd, pysyncobj, ydiff) | append `-%!{PKG_REVISION}`; same in `debian/changelog`                          |
| `Version: 1:%!{PG_VERSION}-1`           | ppg-server, ppg-server-ha                                                  | `-1` → `-%!{PKG_REVISION}`                                                      |
| placeholder (`1.0.0`, `1.0`, `1`) rewritten by `set_version` | server 14–19, staging/19 pgaudit/postgis/address-standardizer/tiger-geocoder, staging/16/tde pg_tde | real `Version:` with macros **and** restrict `set_version` to the spec file |

The third row is load-bearing for rendering, not for `V`: `set_version` with
no `file` parameter rewrites the dsc `Version:` and the changelog first line
to `<ver>` or `<ver>-0`, dropping the epoch and any revision (verified in
obs-service-set_version sources). That is a latent epoch bug today
independent of this work. Those packages get `<param name="file"><spec></param>`
on their `set_version` service, the way `_shared/` packages already do, so
only the spec is touched. The server already runs two `set_version` services;
the dsc-rewriting one is dropped and its epoch moves into the dsc template.

`Debtransform-Release: 1` stays everywhere. With a revision present
debtransform no longer inserts `-1`, so the result is
`[epoch:]V-<PKG_REVISION>+<CI_CNT>.<B_CNT>.<codename>`.

### RPM packaging files

obs-build's `substitutedeps` replaces a `<SPEC_REL>` token in the prjconf
`Release:` line with the spec's own `Release:` value (`substitutedeps`
lines 211–214, `Build.pm` 432/524). That is the whole mechanism:

```
# root/project.yaml project-config, RockyLinux_* / UBI_* block
# today: Release: <CI_CNT>.<B_CNT> spec:<CI_CNT>.<B_CNT>%%{?dist}
Release: <CI_CNT>.<B_CNT> spec:<SPEC_REL>.<CI_CNT>.<B_CNT>%%{?dist}

# every spec (today: 1%{?dist}, 3%{?dist}, 42001%{?dist} … all ignored)
Release:        %!{PKG_REVISION}
```

- The spec drops its own `%{?dist}`; the prjconf appends it once. Keeping it
  in the spec would yield `5.el9.1.1.el9`.
- 46 spec `Release:` lines across the staging tier change. All are dead today
  under the `spec:` override, so no built package changes except by the
  intended revision.
- Spec `Epoch:` lines match production (`Epoch: 1` wherever the old process
  had one). No change.
- The prjconf line is duplicated verbatim in six places (`root/project.yaml`,
  `staging/16/tde`, and the four `releases/17|18[/extras]` mirrors). The
  mirrors regenerate at the next cut; `staging/16/tde` is edited by hand.
- A prjconf `Release:` change rebuilds nothing by itself (not part of the
  build input hash). The spec edits do trigger rebuilds, so the two land
  together.

Result: `V-<PKG_REVISION>.<CI_CNT>.<B_CNT>.elN`, e.g.
`percona-pgaudit17-17.1-5.1.1.el9`. rpmvercmp reads `5 > 4` before it reaches
the OBS counters, so the ordering no longer depends on CI_CNT.

### The OBS counters stay

With `PKG_REVISION` ordering releases, the `+<CI_CNT>.<B_CNT>` (deb) and
`.<CI_CNT>.<B_CNT>` (rpm) suffixes are no longer needed for that purpose and
could be dropped (`1:17.1-5+bookworm` via prjconf `Release: <codename>`, or
`17.1-5` without `Debtransform-Release`; `17.1-5.el9` via
`spec:<SPEC_REL>%%{?dist}`). They are kept because inside staging the
revision does not move between cuts, so two rebuilds of the same package
would carry the same version with different bytes: apt would report Hash Sum
mismatches on the staging repos, the release verify step could not tell a
stale binary from a fresh one, and QA lanes could not say which build they
ran. Dropping them later is a prjconf-only change that needs no tool work.

### Projects without a `release.yaml`

`ppg:common:deps` sources (`etcd`, `python3-pysyncobj`, `ydiff`, the pgadmin
and PostGIS dependency sets) build in a project no `release.yaml` names. They
get `floor + 1` with no climb; the floor alone makes them sort above
production, and their upstream versions move independently of PPG releases.
How their binaries reach `ppg:releases:*` is unchanged by this design.
Decided: no climb is acceptable for these packages; a rebuild at the same
version is ordered by the OBS counters.

### Rendered example

pgaudit in `ppg:staging:17`, at the first migration release (17.12-1):

```
V = 17.1  (obs_scm version %!{PGAUDIT_VERSION})
PKG_REVISION = 4 + 1 + 0 = 5
deb: 1:17.1-5+1.1.bookworm   → percona-postgresql-17-pgaudit_17.1-5+1.1.bookworm_amd64.deb
rpm: 17.1-5.1.1.el9          → percona-pgaudit17-17.1-5.1.1.el9.x86_64.rpm
```

After 17.12-1 is cut and the next sync at the same upstream version: `-6`.
After pgaudit moves to 17.2: `17.2-1`.

## Rollback

The production repos keep the lower versions. A user who re-points at
production can only downgrade explicitly, which is the normal expectation.
Within OBS, reverting the packaging change restores `-1` revisions and
CI_CNT-only releases, which then sort below the already-published OBS builds
at the same upstream version; that is the same situation as today and only
matters before the first migration release goes out.

## Verification

In this repository (pytest, `tests/`):

- `compute_pkg_revision`: seed hit, seed miss after an upstream bump,
  release count at the same `V`, entries whose tree predates the package or
  the `PKG_REVISION` token, `source_commit` vs tag commit, project with no
  `release.yaml`, declared `PKG_REVISION` wins.
- `V` extraction per `_service` style: `version` param, `revision` +
  `versionrewrite-pattern`/`-replacement` (pgadmin4 → `9.17`, pg_similarity
  → `1.0`), set_version `version`, set_version `basename` + download_url, and
  the offline guard (SHA revision without a tag → error).
- `_macros_changed_since` symmetry: a package referencing `PKG_REVISION`
  compares equal to itself at the last synced commit when nothing changed,
  and unequal after a release cut at the same `V`.
- Rendering tests: the dsc `Version:`, the changelog first line and the spec
  `Release:` render the same revision for one package of each style.

Outside this repository: the obs-sync consumer harness re-runs the three
upgrade scenarios (fresh, same release old → OBS build, previous minor → new
minor) against the release QA lane of the migration minors, on all five deb
codenames and the three EL majors, and reports zero binaries left behind. The
index comparison in that harness (deb `Packages` today, rpm repodata to add)
is the gate for the invariant in goal 1.

## Open questions

1. Macro name `PKG_REVISION` (serves both formats).

## Related

- `docs/superpowers/plans/2026-09-17-computed-ppg-release-macro.md` — the
  `PPG_RELEASE` precedent, including the symmetry requirement.
- PR #32 (`+<CI_CNT>.<B_CNT>.<codename>` suffix), PR #194 (rpm `.elN` dist
  tag via prjconf `spec:` override), PR #200 (ppg-server
  `Debtransform-Release`), PR #209 (`percona-postgresql-NN` Depends on
  `percona-pg-tdeNN`, separate migration blocker).
- obs-sync sandbox report, consumer upgrade tests, 2026-11-02.
- Review artifact (version strings, seed table, production dumps):
  https://claude.ai/artifact/P2RabutpPmSkHvFMBrfNw3
