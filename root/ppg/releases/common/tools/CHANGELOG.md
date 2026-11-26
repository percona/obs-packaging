# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [common-tools-2] - 2026-11-26

### Changed
#### Version updates
- percona-pgbackrest: update upstream version 2.60.1 (https://github.com/pgbackrest/pgbackrest/releases/tag/release/2.60.1)
- percona-pgadmin4 [container image]: update image common-tools-1 → common-tools-2
  - [ubi9] updated: python3.12-dns 2.9.0 → 2.9.2
- percona-pgbackrest [container image]: update image common-tools-1 → common-tools-2
  - [ubi8, ubi9, ubi10] updated: percona-pgbackrest 2.60.0 → 2.60.1

#### Packaging updates
- percona-patroni: 4.1.5-5 → 4.1.5-7
  - PG-2956 percona-patroni-consul is not installable on EL8/9/10 ([#313](https://github.com/percona/obs-packaging/pull/313))
  - PG-2954 update packaging files to fix server dependency ([#322](https://github.com/percona/obs-packaging/pull/322))
- percona-pgbouncer: 1.26.1-5 → 1.26.1-6
  - PG-2949 percona-pgbouncer: don't use c-ares on RHEL 8 ([#297](https://github.com/percona/obs-packaging/pull/297))

### Security
- Go toolchain 1.26.10 → 1.26.11 (rebuilds of etcd, gosu, percona-telemetry-agent): fixes
  CVE-2026-97033, CVE-2026-97034, CVE-2026-97035, CVE-2026-97036, CVE-2026-97037, CVE-2026-97038,
  CVE-2026-97039, CVE-2026-97040, CVE-2026-97041, CVE-2026-97042, CVE-2026-97043, CVE-2026-97054,
  plus security fixes in security (https://go.dev/doc/devel/release)
- No CVE fixes mentioned upstream for: percona-pgbackrest (release notes and commit logs scanned for the version range).
- percona-pgadmin4 [container image]: fixes 16 HIGH CVEs
  - [ubi9] dnspython 2.9.0 (fix: 2.9.2): CVE-2026-128089
  - [ubi9] expat 2.5.0-9.el9_9.4 (fix: 2.5.0-9.el9_9.8): CVE-2026-115506
  - [ubi9] krb5-libs 1.21.1-10.el9_8.1 (fix: 1.21.1-10.el9_9.2): CVE-2026-107364, CVE-2026-112315, CVE-2026-112316, CVE-2026-112317, CVE-2026-112318, CVE-2026-112319, CVE-2026-112320, CVE-2026-112321, CVE-2026-112322, CVE-2026-112323, CVE-2026-118380, CVE-2026-119079, CVE-2026-71199, CVE-2026-71200
- percona-pgbackrest [container image]: fixes 17 HIGH CVEs
  - [ubi8] expat 2.5.0-6.el8_10 (fix: 2.5.0-10.el8_10): CVE-2026-115506
  - [ubi9] expat 2.5.0-9.el9_9.4 (fix: 2.5.0-9.el9_9.8): CVE-2026-115506
  - [ubi10] expat 2.7.3-2.el10_3.4 (fix: 2.7.3-2.el10_3.8): CVE-2026-115506
  - [ubi9] krb5-libs 1.21.1-10.el9_8.1 (fix: 1.21.1-10.el9_9.2): CVE-2026-107364, CVE-2026-112315, CVE-2026-112316, CVE-2026-112317, CVE-2026-112318, CVE-2026-112319, CVE-2026-112320, CVE-2026-112321, CVE-2026-112322, CVE-2026-112323, CVE-2026-118380, CVE-2026-119079, CVE-2026-71199, CVE-2026-71200
  - [ubi10] krb5-libs 1.21.3-11.el10 (fix: 1.21.3-11.el10_3.2): CVE-2026-107364, CVE-2026-112315, CVE-2026-112316, CVE-2026-112317, CVE-2026-112318, CVE-2026-112319, CVE-2026-112320, CVE-2026-112321, CVE-2026-112322, CVE-2026-112323, CVE-2026-118380, CVE-2026-119079, CVE-2026-71199, CVE-2026-71200
  - [ubi8] sqlite-libs 3.26.0-21.el8_10 (fix: 3.26.0-28.el8_10): CVE-2026-119373, CVE-2026-119586
- percona-pgbouncer [container image]: fixes 17 HIGH CVEs
  - [ubi8] expat 2.5.0-6.el8_10 (fix: 2.5.0-10.el8_10): CVE-2026-115506
  - [ubi9] expat 2.5.0-9.el9_9.4 (fix: 2.5.0-9.el9_9.8): CVE-2026-115506
  - [ubi10] expat 2.7.3-2.el10_3.4 (fix: 2.7.3-2.el10_3.8): CVE-2026-115506
  - [ubi9] krb5-libs 1.21.1-10.el9_8.1 (fix: 1.21.1-10.el9_9.2): CVE-2026-107364, CVE-2026-112315, CVE-2026-112316, CVE-2026-112317, CVE-2026-112318, CVE-2026-112319, CVE-2026-112320, CVE-2026-112321, CVE-2026-112322, CVE-2026-112323, CVE-2026-118380, CVE-2026-119079, CVE-2026-71199, CVE-2026-71200
  - [ubi10] krb5-libs 1.21.3-11.el10 (fix: 1.21.3-11.el10_3.2): CVE-2026-107364, CVE-2026-112315, CVE-2026-112316, CVE-2026-112317, CVE-2026-112318, CVE-2026-112319, CVE-2026-112320, CVE-2026-112321, CVE-2026-112322, CVE-2026-112323, CVE-2026-118380, CVE-2026-119079, CVE-2026-71199, CVE-2026-71200
  - [ubi8] sqlite-libs 3.26.0-21.el8_10 (fix: 3.26.0-28.el8_10): CVE-2026-119373, CVE-2026-119586

## [common-tools-1] - 2026-11-12

### Added

### Changed
- percona-pgadmin4 (ubi9) [container image]: update image ? → common-tools-1
  - updated: percona-postgresql14 14.24-6.2.el9 -> 14.25-1.1.el9
  - updated: percona-postgresql14-libs 14.24-6.2.el9 -> 14.25-1.1.el9
  - updated: percona-postgresql15 15.19-5.2.el9 -> 15.20-1.1.el9
  - updated: percona-postgresql15-libs 15.19-5.2.el9 -> 15.20-1.1.el9
  - updated: percona-postgresql16 16.15-8.1.el9 -> 16.16-1.1.el9
  - updated: percona-postgresql16-libs 16.15-8.1.el9 -> 16.16-1.1.el9
  - updated: percona-postgresql17 17.11.1-8.3.el9 -> 17.12.1-1.1.el9
  - updated: percona-postgresql17-libs 17.11.1-8.3.el9 -> 17.12.1-1.1.el9
  - updated: percona-postgresql18 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
- percona-pgbackrest (ubi10) [container image]: update image ? → common-tools-1
  - updated: percona-pgbackrest 2.60.0-4.1.el10 -> 2.60.0-4.2.el10
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
  - updated: percona-postgresql18-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
- percona-pgbackrest (ubi8) [container image]: update image ? → common-tools-1
  - updated: curl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: libcurl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: percona-pgbackrest 2.60.0-4.1.el8 -> 2.60.0-4.3.el8
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: percona-postgresql18-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: perl-IO-Socket-SSL 2.066-1.6.el8 -> 2.066-1.8.el8
  - updated: perl-Mozilla-CA 20160104-1.7.el8 -> 20160104-1.9.el8
  - updated: perl-Net-SSLeay 1.88-1.20.el8 -> 1.88-1.23.el8
- percona-pgbackrest (ubi9) [container image]: update image ? → common-tools-1
  - updated: percona-pgbackrest 2.60.0-4.1.el9 -> 2.60.0-4.3.el9
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
- percona-pgbouncer (ubi10) [container image]: update image ? → common-tools-1
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
  - updated: percona-postgresql18-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
  - updated: python3.12-psycopg2 2.9.13-5.5.el10 -> 2.9.13-5.6.el10
- percona-pgbouncer (ubi8) [container image]: update image ? → common-tools-1
  - updated: c-ares 1.19.1-2.2.el8 -> 1.19.1-2.3.el8
  - updated: curl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: libcurl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: percona-pgbouncer 1.26.1-5.1.el8 -> 1.26.1-5.2.el8
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: percona-postgresql18-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: perl-IO-Socket-SSL 2.066-1.6.el8 -> 2.066-1.8.el8
  - updated: perl-Mozilla-CA 20160104-1.7.el8 -> 20160104-1.9.el8
  - updated: perl-Net-SSLeay 1.88-1.20.el8 -> 1.88-1.23.el8
  - updated: python3.12-psycopg2 2.9.13-5.4.el8 -> 2.9.13-5.6.el8
- percona-pgbouncer (ubi9) [container image]: update image ? → common-tools-1
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: python3.12-psycopg2 2.9.13-5.6.el9 -> 2.9.13-5.8.el9

### Security
- UBI base-image package CVEs are not covered by this scan.

