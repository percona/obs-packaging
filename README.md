# percona-obs-packaging

[![OBS Build](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rjd15372/percona-obs-packaging/badges/obs-build-badge.json)](https://github.com/rjd15372/percona-obs-packaging/actions/workflows/sync-main.yml)

RPM and Debian **packaging metadata** for building Percona software packages against an
[OpenSUSE Build Service (OBS)](https://build.opensuse.org/) instance.

This repository does **not** contain upstream source code — only packaging files
(`debian/`, `rpm/`, `obs/_service`, etc.). Sources are fetched at build time by the
OBS services declared in each package's `obs/_service` file.

---

## Documentation

| Document | Description |
|---|---|
| [root/README.md](root/README.md) | Packaging tree structure — how `root/` maps to OBS projects and packages |
| [docs/PERCONA_OBS_TOOL.md](docs/PERCONA_OBS_TOOL.md) | `percona-obs` tool reference — profiles, sync, build status, branching |
| [docs/PACKAGING_HOWTO.md](docs/PACKAGING_HOWTO.md) | Step-by-step guide for adding a new package from scratch |
| [docs/HOWTO_IMPORT_PACKAGES_FROM_PERCONA_PACKAGING.md](docs/HOWTO_IMPORT_PACKAGES_FROM_PERCONA_PACKAGING.md) | Step-by-step guide for importing a package from `percona/postgres-packaging` |

