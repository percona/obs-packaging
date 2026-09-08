# Shared package sources across PG majors — design

**Date:** 2026-09-08
**Status:** proposed

## Problem

`percona-pg_stat_monitor` is packaged identically in every `ppg:staging:<V>`
subproject (14–18). Every packaging change has to be replicated five times, and
the copies have already drifted (staging/18 carries a `set_version basename`
param and `debian/source/lintian-overrides`; 14–17 carry
`debian/source/options` instead).

The obvious OBS-side fix (one `ppg:staging:extensions` project plus `_link`
packages) does not work for Debian: obs-build's `Build/Deb.pm` parses
`.dsc`/`debian/control` literally, build profiles are stubbed, `debtransform`
substitutes nothing, and `_link <topadd>` touches only `*.spec`. There is no
OBS mechanism to inject the PG major into `debian/control`.

## Observation

The major version already enters the package purely at **sync time**: the
`percona-obs` tool expands `%!{PG_MAJOR_VERSION}` (and every other `%!{VAR}`)
from the cascading `macros.yaml` chain of the package's directory. OBS receives
fully rendered, independent packages. So deduplication belongs in the git tree
and the tool, not in OBS.

## Design

1. **Shared source directory.** A tier-level directory named `_shared/` holds
   complete package directories (`obs/`, `debian/`, `rpm/`, optional
   `package.yaml`), e.g. `root/ppg/staging/_shared/percona-pg_stat_monitor/`.
   `_shared/` is never a project and never a package: `find_packages` and
   `find_projects` skip it.

2. **Per-major entry is a git symlink.**
   `root/ppg/staging/17/percona-pg_stat_monitor -> ../_shared/percona-pg_stat_monitor`.
   `pathlib` resolves `package_path / "obs"` through the link, while
   `package_path.parent` and `load_macros(package_path)` stay lexical, so the
   17 entry renders with staging/17 macros and the 14 entry with staging/14
   macros. No sync/upload code changes are needed for content handling
   (verified: `_copy_local_packaging`, `_run_local_services`, `tar -C`,
   `rglob` on the link top all work).

3. **Change detection must see through the link.** `git diff`, `git log` and
   `git status` scoped to the symlink path report only the link blob itself.
   `git_utils` gains `_package_pathspecs(package_path)` returning the package
   path plus its lexical symlink target, used by
   `_has_package_changes_since`, `_has_package_content_changes_since`,
   `_has_non_obs_package_changes_since` and `_is_path_dirty`. Without this,
   edits to `_shared/` would never trigger a sync, a promote, or a manifest
   invalidation.

4. **Macros referenced by shared files** must be defined at or above the
   per-major directory of *every* linking subproject (true today for
   `PG_MAJOR_VERSION` and `PG_STAT_MONITOR_VERSION`).

## Out of scope

- `ppg:devel:<V>` copies (they deliberately build from a dev branch and are
  Class A copies per `root/README.md`).
- Any change to OBS project layout or `_link` usage.
- A `package.yaml` `source:` key. Rejected: it would require threading a
  separate content path through ~15 call sites (`package_path / "obs"`,
  `obs_dir.parent`, `_content_matches_branch`, …) for the same result.

## Alternatives rejected

- `ppg:staging:extensions` + OBS `_link`: no Debian macro mechanism (see above).
- `_multibuild` flavors: flavor reaches the spec only; binaries would also land
  in the wrong project.
- `pg_buildext` `installed` mode to drop `%!{PG_MAJOR_VERSION}` from
  `debian/pgversions`: still leaves `debian.dsc` and the spec version-specific,
  and depends on `postgresql-server-dev-*` naming.
