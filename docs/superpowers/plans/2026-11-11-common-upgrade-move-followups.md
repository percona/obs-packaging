# `common:upgrade` move: follow-ups

The upgrade images moved from `ppg:staging:common:containers` and
`ppg:staging:common:extras:containers` to `ppg:staging:common:upgrade:containers`
and `ppg:staging:common:upgrade:extras:containers`. These steps are not done by
the move itself.

## Outside this repository

Registry paths changed, in staging now and in releases from the first release
of the new units:

    …/common/containers/<ubi>/…          → …/common/upgrade/containers/<ubi>/…
    …/common/extras/containers/ubi9/…    → …/common/upgrade/extras/containers/ubi9/…

Update the obs-sync image map (registry to Docker Hub copier) and the
ppg-testing image references.

## First releases of the new units

    ./percona-obs -P <profile> project release ppg:staging:common:upgrade
    ./percona-obs -P <profile> project release ppg:staging:common:upgrade:extras

They create `root/ppg/releases/common/upgrade/` and
`root/ppg/releases/common/upgrade/extras/` and tag `ppg/common-upgrade-1` and
`ppg/common-upgrade-extras-1`.

## Old release projects

`ppg:releases:common:containers`, `ppg:releases:common:extras` and
`ppg:releases:common:extras:containers` still hold the images released by
`ppg/common-1`. Their mirrors are gone from git, and no release prunes them:
`ppg:staging:common` is no longer a release unit. Once the new units are
released and the external consumers read the new paths, delete them on every
instance. Their local definitions are gone, so the projects are listed from
OBS (`--from-obs` also takes the subprojects of the one named). Run with
`--dry-run` first:

    ./percona-obs -P <profile> sync delete --from-obs --recursive ppg:releases:common:extras
    ./percona-obs -P <profile> sync delete --from-obs --recursive ppg:releases:common:containers

## Kept on purpose

`root/ppg/releases/common/release.yaml` and `CHANGELOG.md` stay. The record is
the marker that makes `releases/common/` a release directory; without it
`sync push` would discover `ppg:releases:common` and its subprojects as
projects to sync.
