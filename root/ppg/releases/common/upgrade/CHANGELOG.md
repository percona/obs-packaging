# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [common-upgrade-3] - 2026-11-26

### Added
<!-- TODO: fill in manually -->

### Changed
<!-- TODO: fill in manually -->

### Security
- Go toolchain 1.26.10 → 1.26.11 (rebuilds of etcd, gosu, percona-telemetry-agent): fixes
  CVE-2026-97033, CVE-2026-97034, CVE-2026-97035, CVE-2026-97036, CVE-2026-97037, CVE-2026-97038,
  CVE-2026-97039, CVE-2026-97040, CVE-2026-97041, CVE-2026-97042, CVE-2026-97043, CVE-2026-97054,
  plus security fixes in security (https://go.dev/doc/devel/release)
- percona-distribution-postgresql-upgrade [container image]: fixes 4 HIGH CVEs
  - [ubi8] expat 2.5.0-6.el8_10 (fix: 2.5.0-10.el8_10): CVE-2026-115506
  - [ubi9] expat 2.5.0-9.el9_9.4 (fix: 2.5.0-9.el9_9.8): CVE-2026-115506
  - [ubi10] expat 2.7.3-2.el10_3.4 (fix: 2.7.3-2.el10_3.8): CVE-2026-115506
  - [ubi10] liblerc 4.0.0-8.el10 (fix: 4.3.0-1.el10_3): CVE-2026-10758
  - [ubi8] sqlite-libs 3.26.0-21.el8_10 (fix: 3.26.0-28.el8_10): CVE-2026-119373, CVE-2026-119586

## [common-upgrade-2] - 2026-11-19

### Added
<!-- TODO: fill in manually -->

### Changed
<!-- TODO: fill in manually -->

### Security
- UBI base-image package CVEs are not covered by this scan.

## [common-upgrade-1] - 2026-11-12

### Added
<!-- TODO: fill in manually -->

### Changed
<!-- TODO: fill in manually -->

### Security
- UBI base-image package CVEs are not covered by this scan.

