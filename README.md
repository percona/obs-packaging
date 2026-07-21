# percona-obs-packaging

[![OBS Build](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/percona/obs-packaging/badges/obs-build-badge.json)](https://github.com/percona/obs-packaging/actions/workflows/sync-main.yml)

RPM and Debian **packaging metadata** for building Percona software packages against an
[OpenSUSE Build Service (OBS)](https://build.opensuse.org/) instance.

This repository does **not** contain upstream source code — only packaging files
(`debian/`, `rpm/`, `obs/_service`, etc.). Sources are fetched at build time by the
OBS services declared in each package's `obs/_service` file.

---

## Development Projects

Per-distribution package version lists, updated automatically after every successful OBS build. Each file lists all packages and container images with the version and release number last successfully built on OBS.

| Distribution | OBS Project | Package List | QA Status |
|---|---|---|---|
| `ppg:staging:14` | [isv:percona:ppg:staging:14](https://build.opensuse.org/project/show/isv:percona:ppg:staging:14) | [docs/versions/ppg-staging-14.md](docs/versions/ppg-staging-14.md) | [![QA ppg:staging:14](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/percona/obs-packaging/badges/qa-badge-ppg-staging-14.json)](https://github.com/percona/obs-packaging/actions/workflows/obs-nightly-qa.yml) |
| `ppg:staging:15` | [isv:percona:ppg:staging:15](https://build.opensuse.org/project/show/isv:percona:ppg:staging:15) | [docs/versions/ppg-staging-15.md](docs/versions/ppg-staging-15.md) | [![QA ppg:staging:15](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/percona/obs-packaging/badges/qa-badge-ppg-staging-15.json)](https://github.com/percona/obs-packaging/actions/workflows/obs-nightly-qa.yml) |
| `ppg:staging:16` | [isv:percona:ppg:staging:16](https://build.opensuse.org/project/show/isv:percona:ppg:staging:16) | [docs/versions/ppg-staging-16.md](docs/versions/ppg-staging-16.md) | [![QA ppg:staging:16](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/percona/obs-packaging/badges/qa-badge-ppg-staging-16.json)](https://github.com/percona/obs-packaging/actions/workflows/obs-nightly-qa.yml) |
| `ppg:staging:17` | [isv:percona:ppg:staging:17](https://build.opensuse.org/project/show/isv:percona:ppg:staging:17) | [docs/versions/ppg-staging-17.md](docs/versions/ppg-staging-17.md) | [![QA ppg:staging:17](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/percona/obs-packaging/badges/qa-badge-ppg-staging-17.json)](https://github.com/percona/obs-packaging/actions/workflows/obs-nightly-qa.yml) |
| `ppg:staging:18` | [isv:percona:ppg:staging:18](https://build.opensuse.org/project/show/isv:percona:ppg:staging:18) | [docs/versions/ppg-staging-18.md](docs/versions/ppg-staging-18.md) | [![QA ppg:staging:18](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/percona/obs-packaging/badges/qa-badge-ppg-staging-18.json)](https://github.com/percona/obs-packaging/actions/workflows/obs-nightly-qa.yml) |

## Current Releases

Released package versions, published to the release OBS projects after each successful release tag.

| Distribution | OBS Project | Package List | Version |
|---|---|---|---|
| `ppg:releases:17` | [isv:percona:ppg:releases:17](https://build.opensuse.org/project/show/isv:percona:ppg:releases:17) | [docs/versions/ppg-releases-17.md](docs/versions/ppg-releases-17.md) | 17.10-1 |
| `ppg:releases:18` | [isv:percona:ppg:releases:18](https://build.opensuse.org/project/show/isv:percona:ppg:releases:18) | [docs/versions/ppg-releases-18.md](docs/versions/ppg-releases-18.md) | 18.4-1 |

## Documentation

| Document | Description |
|---|---|
| [root/README.md](root/README.md) | Packaging tree structure — how `root/` maps to OBS projects and packages |
| [docs/PERCONA_OBS_TOOL.md](docs/PERCONA_OBS_TOOL.md) | `percona-obs` tool reference — profiles, sync, build status, branching |
| [docs/PACKAGING_HOWTO.md](docs/PACKAGING_HOWTO.md) | Step-by-step guide for adding a new package from scratch |
| [docs/HOWTO_IMPORT_PACKAGES_FROM_PERCONA_PACKAGING.md](docs/HOWTO_IMPORT_PACKAGES_FROM_PERCONA_PACKAGING.md) | Step-by-step guide for importing a package from `percona/postgres-packaging` |

