# Package revision floor (`PKG_REVISION`) on top of the OBS commit counter

Date: 2026-11-02, rewritten 2026-11-03
Status: implemented (branch deb-revision-counter), 2026-11-03

## Problem

Every Debian package built by OBS carries the revision `1`: the dsc either has
no revision (`Version: 1:%!{PGAUDIT_VERSION}`, so debtransform appends `-1`),
hardcodes it (`Version: 1:%!{PG_VERSION}-1`), or is rewritten by `set_version`
to `<ver>` / `<ver>-0`. `Debtransform-Release: 1` then appends
`+<CI_CNT>.<B_CNT>.<codename>` from the prjconf `Release:` line.

Every RPM built by OBS gets `Release: <CI_CNT>.<B_CNT>%{?dist}` from the
prjconf `spec:` override (PR #194); the spec's own `Release:` line never
reaches the binary.

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
set_user above is one confirmed miss.

The migration to OBS-built packages happens at the next minor of PG 14–18 and
at the PG 19 GA. At that point every OBS package must sort strictly above
whatever a user already has installed from production.

## What OBS already counts

`CI_CNT` is the package's `vrev` ("version revision") in the OBS source
server. Read from the OBS backend sources (`bs_srcserver` `getcommitinfo`,
`BSRevision::addrev`, `BSFileDB::fdb_add_i2`) and confirmed on the labs
instance with a scratch package (2026-11-03):

1. At every commit OBS parses the committed spec (the dsc only when there is
   no spec) and records its `Version:` and the leading digits of its
   `Release:` in the package's revision log.
2. The new `vrev` is `max(vrev of the last revision with the same version + 1,
   release parsed from the spec)`. A version seen for the first time has no
   previous record, so it starts at `max(1, release)`.
3. The scheduler substitutes `<CI_CNT>` with that `vrev` and `<B_CNT>` with
   the build count for that (version, vrev).

Labs run (`home:rjfd.di:vrev-test`, deleted afterwards):

| commit | spec Version / Release | vrev | rule                                    |
|--------|------------------------|------|-----------------------------------------|
| 1      | 1.0 / 9                | 9    | max(0 + 1, 9)                           |
| 2      | 1.0 / 9                | 10   | max(9 + 1, 9)                           |
| 3      | 1.0 / 3                | 11   | lowering the floor changes nothing      |
| 4      | 1.1 / 9                | 9    | new version restarts at the floor       |
| 5      | 1.1 / 9                | 10   |                                         |
| 6      | 1.0 / 1                | 12   | keyed by version string, not by order   |

Production histories agree: `isv:percona:ppg:staging:17` shows pgbackrest
`2.59.0` vrev 3, 4 → `2.59.1` vrev 1, 2 → `2.59.2` vrev 1, 2, 3; the server
`17.11` vrev 5, 6 → `17.11.1` vrev 1…5. The recorded version is the real one
because `sync` runs `set_version` locally and commits the rewritten spec.

So OBS already provides a per-package counter that climbs once per commit at
the same upstream version and resets when that version changes. Two things
are missing:

- **A floor.** Every spec uploaded today says `Release: 0%{?dist}`, whatever
  git says, because obs-service-set_version resets the line unconditionally
  (`_replace_tag(filename, 'Release', "0")`, version 0.6.6 and upstream
  master alike; there is no parameter to control it). The same code rewrites
  a placeholder dsc to `<ver>-0`, dropping epoch and revision. The counter
  therefore always starts at 1 and can sit below the production number.
- **A deb revision that survives `+`.** dpkg sorts `+` below `.`, so
  `V-1+<anything>` loses against production `V-1.codename` and
  `V-1+7.1` loses against `V-4`. The dsc revision itself must exceed the
  production counter; the OBS counters after the `+` only order builds among
  themselves.

## Goals

1. Every deb and rpm binary published from OBS sorts above the highest version
   of the same binary in any production vault, for every codename and EL
   major, from the migration release onward.
2. Nobody manages revision numbers by hand. The one number the tool renders
   is a constant per (project, package, upstream version), computed from the
   git tree like `PPG_RELEASE` is today.
3. The counter resets by itself when a package's upstream version changes and
   climbs by itself with every commit at the same upstream version. Both
   already hold in OBS; the design must not break them.
4. The seed values that carry the old process's counters forward are a
   one-off, live in code, and are dead weight that can be deleted once every
   seeded upstream version has moved.
5. Builds and the sync content check stay reproducible: the rendered value is
   a pure function of the git tree, computable at any historical commit.
6. One macro serves both formats.

## Non-goals

- A version-order gate in `percona-obs`. The obs-sync consumer harness already
  compares real `Packages` indexes against production per codename; that is
  where the invariant is proven, against the release QA lane of the migration
  minors. The harness grows the same comparison for RPM repodata.
- Counting release cuts. The counter climbs per commit (OBS `vrev`), not per
  `project release`; a rebuild without a commit is a new `B_CNT`, and that is
  enough to tell two releases of the same source apart.
- Changing the prjconf `Release:` lines, the `+<CI_CNT>.<B_CNT>.<codename>`
  deb suffix, the rpm `.<CI_CNT>.<B_CNT>` suffix, or `Debtransform-Release`.
- Replacing `PPG_RELEASE`. It is the ordinal of the product release
  (`17.12-2` → 2), keyed by PG major, used by image labels, `ENV PPG_VERSION`
  and the server call-home; those packages have no `_service` and no
  upstream `V`. Different number, different consumers.
- The devel tier. Its packages are never published to users.
- Bumping epochs. Permanent, and it changes how Percona packages compare with
  PGDG forever.
- Container tags, tarballs, aggregates: nothing without a `_service` is
  touched.

## Design

### The rule

For a package in OBS project `P` whose upstream version is `V`:

```
PKG_REVISION = floor(P, package, V) + 1
```

`floor` is the production counter carried forward from the hardcoded seed
table (below), 0 when there is no entry. The value is rendered into the spec
`Release:` and the dsc/changelog revision before upload, and OBS does the
rest:

- **rpm:** the committed spec says `Release: <PKG_REVISION>%{?dist}`, so
  `vrev = max(previous + 1, PKG_REVISION)`. The binary gets
  `V-<vrev>.<B_CNT>.elN` from the prjconf as today. The spec's number is a
  lower bound, not the counter: after the first commit `vrev` climbs on its
  own and the spec keeps saying the same number without effect.
- **deb:** the committed dsc says `[epoch:]V-<PKG_REVISION>`, the binary gets
  `[epoch:]V-<PKG_REVISION>+<vrev>.<B_CNT>.<codename>`. The revision beats
  production outright; `+<vrev>.<B_CNT>` orders OBS builds among themselves
  exactly as it does today. The dsc revision never has to climb.

Properties:

- **Constant until something real changes.** `PKG_REVISION` changes only when
  `V` changes (new floor lookup) or the table changes. No release cut, no
  rebuild and no dependency change moves it, so `_macros_changed_since` never
  sees a spurious difference and no project-wide re-push happens.
- **Reset by itself.** A new `V` is a new OBS version record: `vrev` restarts
  at `max(1, PKG_REVISION)`, and `PKG_REVISION` is 1 unless the new `V` is in
  the table.
- **Climb by itself.** Every commit at the same `V` is one more `vrev`, on
  both formats. Rebuilds without a commit are `B_CNT`.
- **No two releases carry the same version string for different bytes.** A
  release cut copies binaries; a later cut either has a new commit (higher
  `vrev`) or a rebuild (higher `B_CNT`) or the identical binary.
- **Same rule for every project.** `ppg:common:deps`, `common:tools`, the
  staging majors and their `extras`/`tde` subprojects all get `floor + 1`;
  nothing depends on `release.yaml`.
- **Pure.** Inputs are the package's `obs/_service`, the macros chain and the
  table in code. `git_utils._macros_changed_since` computes the identical
  value at the last synced commit, the constraint PR #58 solved for
  `PPG_RELEASE`.

An explicitly declared `PKG_REVISION` in a `macros.yaml` wins, as it does for
`PPG_RELEASE`. Nothing declares it; the escape hatch costs nothing.

### Where the upstream version comes from

Neither packaging file is a usable source: spec `Version:` is a placeholder
(`1.0.0`) that `set_version` overwrites, and 40 dsc files carry the same kind
of placeholder. `package.yaml` is absent on 81 built packages. The one file
every built package has, and the one that decides what OBS records as the
version, is `obs/_service`.

`V` is therefore what `cmd_project._extract_version_from_service` returns for
the package's `obs/_service`, rendered through the macro chain. That helper
already mirrors OBS for `project versions` and for QA `EXPECTED_VERSIONS`:
obs_scm `version` param; `versionformat`; `@PARENT_TAG@` with
`versionrewrite-pattern` applied to `revision`; set_version `version` param
or `basename` + download_url filename. It moves to `common.py` (or a small
`versions.py`) so `inject_computed_macros` and `cmd_project` share it.

Checked offline (2026-11-03) over every package in staging 14–19 including
extras, tde and tarballs, and `staging:common:tools`: all resolve to a
concrete version, none needs the network. Two values are wrong because the
helper ignores `versionrewrite-replacement`: pgadmin4 renders `9` (tag
`REL-9_17`, should be `9.17`) and pg_similarity renders `pg_similarity_1_0`
(should be `1.0`). That fix is part of this work; the seed keys must match
what OBS writes.

Two rules keep it pure:

- **Offline only.** The helper's SHA → git tag lookup (network) is disabled
  on this path. A package whose `V` would need it fails `project verify`:
  "pin a tag or add a `version` param". No package hits this today.
- **No upstream version, revision 1.** A source package (spec or dsc present)
  whose `_service` yields no version, or has no `_service`, gets 1: the floor
  cannot key it (download_url-only rebuilds, the ppg-server metapackages,
  gis-compat). Aggregates, images, simpleimage tarballs and `_link` packages
  get nothing injected. `V` carries no epoch; the epoch stays in the dsc/spec
  where it is today.

`inject_computed_macros` already receives the package path from every
`load_macros` caller; it gains the per-package lookup next to `PPG_RELEASE`.

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
    ("ppg:common:deps", "ydiff", "1.4.2"): 3,
    ...
}
```

- Keyed by OBS project and package name, the identity the tool already uses
  everywhere, rather than by rendered dsc `Source:` (which RPM-only packages
  lack).
- Each value is the **maximum over every production vault, both formats**.
  Where deb and rpm disagree the higher one wins for both: pgaudit 14/15 are
  4 on deb and 7 on rpm → 7; pgpool2 is 2 on deb and 1 on rpm → 2.
- Packages at production counter 1 need an entry too (floor 1 → `-2`): on deb
  `V-1+…` sorts below `V-1.codename`.
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
  same constants. A table-only edit therefore changes no upload by itself: the affected packages are re-pushed with a forced sync.

Resulting values at the first migration sync (ppg-17): pgaudit `17.1-5`,
set_user `4.2.0-7`, pg_repack `1.5.3-6`, postgresql-common `293-2`, pg_tde
`2.2.2-2`; metapackage `17.12-1` (upstream moved, no floor).

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

The third row exists because `set_version` with no `file` parameter rewrites
the dsc `Version:` and the changelog first line to `<ver>` or `<ver>-0`,
dropping the epoch and any revision. Those packages get
`<param name="file"><spec></param>` on their `set_version` service, the way
`_shared/` packages already do, so only the spec is touched. The server
already runs two `set_version` services; the dsc-rewriting one is dropped and
its epoch moves into the dsc template.

`Debtransform-Release: 1` stays everywhere. With a revision present
debtransform no longer inserts `-1`, so the result is
`[epoch:]V-<PKG_REVISION>+<CI_CNT>.<B_CNT>.<codename>`.

### RPM packaging files

Every spec in the staging and common tiers (200 files today, with `Release:`
values from `1%{?dist}` to `42001%{?dist}`, all dead under the prjconf
override) gets the same line:

```
Release:        %!{PKG_REVISION}%{?dist}
```

The prjconf stays `Release: <CI_CNT>.<B_CNT> spec:<CI_CNT>.<B_CNT>%%{?dist}`.
The spec's `Release:` is consumed by the OBS source server at commit time
only, as the `vrev` floor; obs-build still replaces it in the build. Result:
`V-<vrev>.<B_CNT>.elN` with `vrev >= PKG_REVISION`.

Eleven rebuilds without a `set_version` keep their literal `Release:`
(`# Release pinned by hand`): krb5 and libssh beat the distro package of the
same name in the tarball chroots, the PostGIS deps icu, qt5-qtbase, qhull,
libproxy, librttopo and snappy carry RHEL release numbers that back exact-EVR
`-devel` pins, and atlas, percona-python3 and percona-gis-compat keep the
floors they already had. With no `set_version` nothing zeroes those lines, so
they already are the `vrev` floor.

Spec `Epoch:` lines match production (`Epoch: 1` wherever the old process had
one). No change.

Normalising the other 189 lines is what makes the next item safe: after it, the
spec `Release:` in git is meaningful again and never a stray `42001`.

### Tool: keep the floor through `set_version`

`sync` renders macros, copies `rpm/` and `debian/` into the work dir, then
runs the buildtime services locally (`services.py`, phase 3) and uploads the
result with `_service` removed. `set_version` runs in that phase and resets
every spec `Release:` to `0`, which is why production specs all say `0` while
git says `2`. One post-step after phase 3 fixes it:

- for every `*.spec` in the work dir, restore the `Release:` line from the
  rendered source spec.

Nothing else: dsc and changelog are not touched by `set_version` once every
package restricts it to the spec (previous section). The post-step is
unconditional and format-local, so the content check (which compares the
rendered git tree, not the service output) is unaffected.

### Rendered example

pgaudit in `ppg:staging:17`, production `17.1-4`, floor 4, `vrev` 5 today:

| event                                | spec `Release` uploaded | OBS record (version / vrev) | deb                        | rpm              |
|--------------------------------------|-------------------------|-----------------------------|----------------------------|------------------|
| today                                | `0`                     | 17.1 / 5                    | `1:17.1-1+5.1.bookworm`    | `17.1-5.1.el9`   |
| first sync with `PKG_REVISION`       | `5`                     | 17.1 / max(5+1, 5) = **6**  | `1:17.1-5+6.1.bookworm`    | `17.1-6.1.el9`   |
| dependency CVE rebuild, no commit    | —                       | 17.1 / 6                    | `1:17.1-5+6.2.bookworm`    | `17.1-6.2.el9`   |
| packaging fix, commit                | `5`                     | 17.1 / **7**                | `1:17.1-5+7.1.bookworm`    | `17.1-7.1.el9`   |
| pgaudit moves to 17.2                | `1`                     | 17.2 / max(0+1, 1) = **1**  | `1:17.2-1+1.1.bookworm`    | `17.2-1.1.el9`   |
| next commit at 17.2                  | `1`                     | 17.2 / **2**                | `1:17.2-1+2.1.bookworm`    | `17.2-2.1.el9`   |

set_user in `ppg:staging:17`, production `4.2.0-6.el9`, floor 6, `vrev` 5:

| event                          | spec `Release` | vrev                | rpm              |
|--------------------------------|----------------|---------------------|------------------|
| today                          | `0`            | 5                   | `4.2.0-5.4.el9` (loses) |
| first sync with `PKG_REVISION` | `7`            | max(5+1, 7) = **7** | `4.2.0-7.1.el9`  |
| later commit                   | `7`            | 8                   | `4.2.0-8.1.el9`  |

### Edge cases

- **Delete and re-add a package in OBS.** The revision log is gone, so `vrev`
  restarts at `max(1, PKG_REVISION)`: above production, but possibly below
  the package's own earlier OBS builds at the same `V` (`-5+1.1` after
  `-5+7.1`). Same hole as today, now bounded from below. Repair at that
  moment with the `vrev=` parameter of the OBS commit API, which `addrev`
  honours verbatim, or by raising the table entry. Not automated.
- **Revert to an older `V`.** OBS keys the counter on the version string, so
  going back continues from the last record of that version (labs row 6).
  The floor lookup also keys on `V`, so the two agree.
- **`_link` and `_aggregate` packages** are recorded as version `unknown`,
  `vrev` 0 by OBS and get no macro from the tool. Unchanged.
- **Cross-major divergence.** Each major's `vrev` runs independently, so
  `percona-postgresql-common 1:293` can carry `-2+6.1` in `ppg-17` and
  `-2+4.1` in `ppg-18`. Both exceed production because the floor is the
  global maximum. Same as today's OBS counters.

## Rollback

The production repos keep the lower versions. A user who re-points at
production can only downgrade explicitly, which is the normal expectation.
Within OBS, reverting the packaging change restores `-1` revisions and a
`vrev` floor of 0; `vrev` itself does not go down, so already-built binaries
keep sorting above production until the next upstream bump. Only matters
before the first migration release goes out.

## Verification

In this repository (pytest, `tests/`):

- `compute_pkg_revision`: seed hit, seed miss after an upstream bump, no
  `_service`, declared `PKG_REVISION` wins.
- `V` extraction per `_service` style: `version` param, `revision` +
  `versionrewrite-pattern`/`-replacement` (pgadmin4 → `9.17`, pg_similarity
  → `1.0`), set_version `version`, set_version `basename` + download_url, and
  the offline guard (SHA revision without a tag → error).
- `_macros_changed_since` symmetry: a package referencing `PKG_REVISION`
  compares equal to itself at the last synced commit when nothing changed,
  and unequal after a `V` change (a table-only change is invisible by design, see Seed table).
- Rendering tests: the dsc `Version:`, the changelog first line and the spec
  `Release:` render the same revision for one package of each style, and the
  spec `Release:` survives a local `set_version` run.

On labs, before the PR: push one floored package (`percona-pgaudit_set_user`
in `staging:17`) to a PR project and check `_history` shows
`vrev >= PKG_REVISION` and the built RPM/deb names match the tables above.

Outside this repository: the obs-sync consumer harness re-runs the three
upgrade scenarios (fresh, same release old → OBS build, previous minor → new
minor) against the release QA lane of the migration minors, on all five deb
codenames and the three EL majors, and reports zero binaries left behind. The
index comparison in that harness (deb `Packages` today, rpm repodata to add)
is the gate for the invariant in goal 1.

## Rejected alternatives

- **Count release cuts in the tool** (`floor + 1 + past_releases(V)` from
  `release.yaml` and `git show` at released commits). Correct but needs a
  full-project re-push and rebuild at every cut, a `<SPEC_REL>` prjconf
  change in six places, and a reverse map from projects to `release.yaml`.
  OBS's `vrev` gives the climb for free.
- **Lazy variant of the above** (exclude the macro from the change check):
  a package rebuilt only by a dependency change would ship in two releases at
  the same revision with different bytes.
- **Drop the OBS counters** (`1:17.1-5+bookworm`, `17.1-5.el9`): with the
  dsc revision constant, two staging rebuilds would share a version string
  with different bytes (apt Hash Sum mismatch, release verify blind).
- **Seed `vrev` through the commit API** (`vrev=` parameter) instead of the
  spec `Release:`: the tool would have to read `_history` before every
  commit and compute the number itself. Kept only as the manual repair for
  the re-add case.
- **prjconf `CICntStart:`**: exists, but one value per project, not per
  package.
- **A repo-owned `set_version` variant** that keeps `Release:`: forks a
  500-line upstream script for one line; the post-step in `services.py` is
  smaller.
- **`CI_CNT` as the Debian revision.** obs-build only ever appends the
  prjconf release after a `+` (`debtransform` line 589, `OBS-DCH-RELEASE` in
  `build-recipe-dsc`); a dsc without a revision is rejected by dpkg-source
  for `3.0 (quilt)`. A letter-led revision (`V-obs+<CI_CNT>.<B_CNT>`) does
  beat every numeric production revision in dpkg, verified, but leaves the
  rpm side on the floor anyway and bakes `obs` into public versions.
- **Tool predicts `vrev` and renders it** (`V-N+<B_CNT>.<codename>`, deb
  prjconf without `<CI_CNT>`): same number on both formats and old-process
  looks, but the macro would depend on an OBS `_history` read at upload
  time, need a placeholder on both sides of the content check and offline
  renders, a `vrev=N` commit parameter to close the read/commit race, and a
  deb prjconf edit in six places. Cosmetics only; the floor gives the same
  ordering.

## Open questions

1. Macro name `PKG_REVISION` (serves both formats).

## Related

- `docs/superpowers/plans/2026-09-17-computed-ppg-release-macro.md` — the
  `PPG_RELEASE` precedent, including the symmetry requirement.
- OBS backend: `src/backend/bs_srcserver` (`getcommitinfo`, commit path),
  `src/backend/BSRevision.pm` (`addrev`), `src/backend/BSFileDB.pm`
  (`fdb_add_i2`), `src/backend/BSSched/BuildJob.pm` (`<CI_CNT>`/`<B_CNT>`
  substitution). obs-service-set_version 0.6.6 lines 490–505 (`Release` and
  dsc reset).
- PR #32 (`+<CI_CNT>.<B_CNT>.<codename>` suffix), PR #194 (rpm `.elN` dist
  tag via prjconf `spec:` override), PR #200 (ppg-server
  `Debtransform-Release`), PR #209 (`percona-postgresql-NN` Depends on
  `percona-pg-tdeNN`, separate migration blocker).
- obs-sync sandbox report, consumer upgrade tests, 2026-11-02.
- Review artifact (version strings, seed table, production dumps):
  https://claude.ai/artifact/P2RabutpPmSkHvFMBrfNw3
