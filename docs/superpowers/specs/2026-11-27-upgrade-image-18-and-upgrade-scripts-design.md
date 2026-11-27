# Restore the PG 18 upgrade image; build upgrade-scripts.tar.gz from git

## Intent

When PG 19 was added, `percona-distribution-postgresql-upgrade` in
`ppg:staging:common:upgrade:containers` was changed in place: target 18 → 19,
tags `18-17-16-15-14` → `19-18-17-16-15`. Docker Hub still serves the old tags,
but nothing builds them any more, so their CVEs are never fixed. We restore the
old image as a second package that is rebuilt and released next to the new one,
so both tag sets keep getting CVE fixes.

At the same time the scripts baked into the upgrade images stop living in an
opaque `upgrade-scripts.tar.gz` blob committed to git. They become plain files
under revision control, and the `source_script` OBS service (run locally by
`percona-obs sync`) builds the tarball.

## Goals

- A new OBS package in `ppg:staging:common:upgrade:containers` builds the image
  `percona-distribution-postgresql-upgrade` with the pre-PG-19 tag set, and is
  QA'd and released with the `common:upgrade` unit.
- One checked-in scripts tree feeds all three upgrade images:
  `percona-distribution-postgresql-upgrade` (19 target),
  the restored 18-target image, and `percona-distribution-postgresql-upgrade-custom`
  (`common:upgrade:extras:containers`).
- `source_script` can pack a directory of the package instead of an `obs_scm`
  checkout; the tarball bytes depend only on the file contents.
- Editing a shared script is detected as a change of every package that uses it
  (`--skip-unchanged`, branch decisions).

## Non-goals

- Changing what the 19-target image installs or tags (it still installs PG 14
  though its tag dropped 14; the project-level `ubi*-14-to-15` QA lanes run
  against tag `19-18-17-16-15`). Noted, not touched here.
- Docker Hub publishing itself: obs-sync lives outside this repo (see
  Dependencies).
- Any change to `PPG_RELEASE` or `UNIT_RELEASE` (already on `main`).

## Anti-goals

- A tarball that changes on every merge to `main` (would promote and rebuild
  all three images every time). This is why the scripts are not fetched with
  `obs_scm` from this repo.
- Macro or `${VAR}` substitution applied to the scripts (they are shell and use
  `${NEW_VERSION}` etc.).
- Breaking the existing `--archive` mode of `source_script` (pgbackrest).

## Approaches considered

- **A. `obs_scm` on this repo (`subdir`) → `source_script` with a copy script.**
  No tool change. Rejected: the sync tool would treat that `obs_scm` as the
  package's upstream, so the cache key and the tarball timestamp follow the
  repo HEAD, not the scripts; every merge to `main` would change the tarball
  and rebuild all three images. A local sync would also pack the pushed branch,
  not the working tree.
- **B. `source_script` packs a directory of the package (chosen).**
  `percona-obs` copies `obs/` subdirectories into the service work directory;
  `source_script --source <dir>` packs it with a fixed timestamp. Costs a tool
  change and an obs-tools image rebuild before the packaging can use it.
- **C. No tarball: `COPY` the 8 files flat from `obs/`.** Simplest, but the
  user explicitly wants the tarball built by the service. Dropped.

## Design

### 1. `source_script --source` (tools/obs-services/source_script)

- New parameter `source`: a directory name in the work directory (a plain
  name, same validation as `--script`: no path separators, not `.`/`..`).
  Exactly one of `--archive` and `--source` must be given.
- `--script` becomes optional with `--source` (still required with
  `--archive`). Without a script, the directory is packed as is; with one, the
  script runs on a copy of the directory exactly as it runs on an unpacked
  checkout today.
- The tarball's single top-level directory is named after `--source` (when no
  script runs) — `upgrade-scripts/…`.
- `--output` is required with `--source` (there is no `.obsinfo` to derive
  `name-version` from).
- Timestamps: every entry's mtime is `0` (epoch) in `--source` mode, so the
  bytes are a function of the contents only (same on a laptop and in CI). The
  script environment gets `NAME` = source dir name, `VERSION` = empty, `COMMIT`
  = empty, `SOURCE_DATE_EPOCH` = `0`.
- Symlinks inside the source directory are not followed by `pack()` as today;
  the scripts tree has none.
- `source_script.service` documents the new parameter; README table updated.

### 2. `percona-obs` (percona_obs/services.py, percona_obs/git_utils.py)

- `_run_local_services` work-directory setup copies subdirectories of `obs/`
  too (`shutil.copytree(..., symlinks=False)` so a symlinked directory is
  copied as its target's contents), **verbatim**: no macro or env substitution.
  No package has `obs/` subdirectories today. Directories are already removed
  from the work directory before upload, and every upload path filters
  `is_file()`, so nothing new reaches OBS.
- `_manual_cache_key` also hashes the contents of `obs/` subdirectories
  (relative paths + bytes, followed through symlinks), so changed scripts can
  never restore stale manual outputs. (These packages have no upstream
  `obs_scm`, so they are not cached at all; the key change is for
  correctness.)
- `_package_pathspecs` also adds, for each symlink directly inside the
  package's `obs/`, its lexical target (`os.readlink` + `normpath`, as for
  package-directory links). Every git-based change check (`--skip-unchanged`,
  `_has_non_obs_package_changes_since`, sync-state input checks) then sees an
  edit under `_shared/upgrade-scripts/` as a change of each linking package.
- `_scope_local_paths` (`percona_obs/cmd_sync.py`, the release-unit source
  paths used by the repopulate and freeze checks) today follows only package
  directories that are themselves symlinks. It must also add the targets of
  `obs/` symlinks of every package in its project directories (recursively, so
  `containers` children are covered). Otherwise the `common:upgrade:extras`
  unit, whose source path excludes `staging/common/upgrade/_shared/`, never
  sees a scripts-only edit. *(Builder-check finding; added as the designer's
  call: a shared-scripts edit is a change of every unit that ships it.)*
  Test it with a nested unit that links to its parent's `_shared/`.
- Tests: extend `tests/test_source_script.py` (source mode with and without a
  script, mutual exclusion, missing `--output`, byte-identical output for the
  same contents, top-level dir name) and `tests/test_run_local_services.py`
  (subdirectory and symlinked subdirectory reach the service; not uploaded;
  cache key changes when a file in it changes); a git_utils test for the
  `obs/` symlink pathspec.
- Docs: `docs/PERCONA_OBS_TOOL.md` (source_script section, `obs/`
  subdirectories), `tools/obs-services/README.md`, `.github/copilot-instructions.md`
  where it describes what is copied from `obs/`.

### 3. Packaging layout

```
root/ppg/staging/common/upgrade/
  _shared/upgrade-scripts/                     # new: the tree of the current 19 tarball
    bin/relocate-extensions.sh
    bin/common/{common_lib,nss_wrapper,nss_wrapper_env,uid_postgres,uid_postgres_no_exec}.sh
    bin/upgrade/start.sh
    conf/upgrade/{group,passwd}.template
  containers/
    percona-distribution-postgresql-upgrade/obs/
      _service                                 # new
      upgrade-scripts -> ../../../_shared/upgrade-scripts
      (upgrade-scripts.tar.gz removed)
    percona-distribution-postgresql-upgrade-18/   # new package
      package.yaml                              # title, description, qa:
      obs/ _service, Dockerfile, LICENSE,
           upgrade-scripts -> ../../../_shared/upgrade-scripts
  extras/containers/
    percona-distribution-postgresql-upgrade-custom/obs/
      _service                                 # new
      upgrade-scripts -> ../../../../_shared/upgrade-scripts
      (upgrade-scripts.tar.gz removed)
```

- The shared tree is the content of the current 19-image tarball (file modes
  kept: scripts 0755, templates 0644). Its `start.sh` is a superset of the
  other two copies: it adds the `19`/`18` cases, and over the custom image's
  copy it also has the PG-2868 fix (`--no-data-checksums` only when
  `NEW_VERSION >= 18`). So the custom image gains that fix.
- `_shared/` is already skipped by package discovery and release scoping.
- Each `_service`:

  ```xml
  <services>
    <!-- Packs obs/upgrade-scripts (a link to the tier's shared scripts tree)
         into upgrade-scripts.tar.gz; run by percona-obs sync. -->
    <service name="source_script" mode="manual">
      <param name="source">upgrade-scripts</param>
      <param name="output">upgrade-scripts.tar.gz</param>
    </service>
  </services>
  ```

- All three Dockerfiles: the tarball now has an `upgrade-scripts/` top
  directory; extract with `tar -xzf … -C /tmp/upgrade-scripts --strip-components=1`
  and keep the existing `cp` lines unchanged.

### 4. The restored image (`percona-distribution-postgresql-upgrade-18`)

- Dockerfile restored from `d4602b6e^` (target 18, `{{FOR}}` over 17,16,15,14,
  `percona-pg_tde17`, postgis35 everywhere), with every later non-PG-19 change
  to the 19 image's Dockerfile carried over (currently: the `UNIT_RELEASE`
  tag/label/BuildVersion changes of 3f7fa8af and 9273aa4e, plus the tarball
  extraction above). Diff it against the current 19 Dockerfile at
  implementation time; any difference must be PG-19-specific.
- Macros are per project and the project's `PG_MAJOR_VERSION`/`PG_VERSION`/
  `POSTGIS_RPM_MAJOR` are 19-based, so this Dockerfile hardcodes the 18 target:
  `18` for the target major, `18.%!{PG_18_MINOR_VERSION}` for the version,
  `postgis35`.
- Tags (image name unchanged, so Docker Hub keeps the same repository):

  ```
  #!BuildVersion: 18.%!{PG_18_MINOR_VERSION}-17.%!{PG_17_MINOR_VERSION}-16.%!{PG_16_MINOR_VERSION}-15.%!{PG_15_MINOR_VERSION}-14.%!{PG_14_MINOR_VERSION}-%!{UNIT_RELEASE}
  #!BuildTag: percona-distribution-postgresql-upgrade:18-17-16-15-14-%!{UNIT_RELEASE}
  #!BuildTag: percona-distribution-postgresql-upgrade:18.<m>-17.<m>-16.<m>-15.<m>-14.<m>-%!{UNIT_RELEASE}
  #!BuildTag: percona-distribution-postgresql-upgrade:18-17-16-15-14
  #!BuildTag: percona-distribution-postgresql-upgrade:18.<m>-17.<m>-16.<m>-15.<m>-14.<m>
  ```

  Labels: `version="18.%!{PG_18_MINOR_VERSION}-%!{UNIT_RELEASE}"`,
  `release="%!{UNIT_RELEASE}"`; `ENV PPG_VERSION` and `PPG_MAJOR_VERSION` (18)
  likewise. The numbered tags continue the unit's counter (`ppg/common-upgrade-3`
  is already recorded, so the first is `-4`), not the old PG-18 numbering.
- QA: the 12 lanes of `d4602b6e^`'s project `qa:` (`ubi{8,9,10}-{14-to-15,
  15-to-16,16-to-17,17-to-18}`, `UPGRADE_DOCKER_TAG: "18-17-16-15-14"`) go in
  this package's `package.yaml` `qa:`, with `UPGRADE_REPOSITORY.image:
  percona-distribution-postgresql-upgrade-18` (image refs name the OBS
  package). Lane names must not collide with the project lanes of the same
  name; suffix them (e.g. `ubi8-14-to-15-u18`).
- `package.yaml` title/description say it is the PG-18-target upgrade image
  kept for CVE fixes of the `18-17-16-15-14` tags.

### 5. Rollout

Two PRs, tool first (obs-tools image is rebuilt from `main` only):

1. Tool PR: `source_script --source`, `percona-obs` changes, tests, docs.
   After merge, the obs-tools image rebuild must finish before PR 2's CI.
   Developers reinstall the service locally (`tools/obs-services/README.md`).
2. Packaging PR: `_shared/upgrade-scripts`, the three `_service`s and symlinks,
   tarball removals, Dockerfile extraction change, the new package. Merged
   only once obs-sync is confirmed (see Dependencies) and a labs rehearsal
   shows both packages' tags published side by side under the one image name
   in the OBS registry, in staging and in the release copy
   (`project release` + verify), with QA pulling `18-17-16-15-14` and
   `19-18-17-16-15` from it.

## Dependencies

- **obs-sync** (outside this repo; the user checks it): it must publish both
  tag sets of `percona-distribution-postgresql-upgrade` when two OBS packages
  in the same repository produce that image name. If it maps images to
  packages, it needs a change first. PR 2 is blocked on this.
- **OBS registry, two packages → one image name**: nothing in this repo does
  it yet. SUSE's BCI images (separate per-version packages publishing one image
  name with different tags) suggest OBS supports it; the labs rehearsal above
  confirms it. If it fails, fall back to `_multibuild` flavours of one package
  and revisit with the user.

## Left to the builder

- Exact argparse shape and error messages in `source_script`.
- Test structure and fixtures.
- Whether `obs/` subdirectory copying lives in a small helper shared with the
  cache-key hashing.
