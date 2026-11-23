# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [extras-16.16-2] - 2026-11-23

### Added

### Changed
- percona-pg_partman: update upstream version 5.5.1 (https://github.com/pgpartman/pg_partman/releases/tag/v5.5.1)
- percona-postgresql: update upstream version 16.16 (https://github.com/postgres/postgres/releases/tag/REL_16_16)
- percona-postgresql_anonymizer: update upstream version 3.3.2 (https://gitlab.com/dalibo/postgresql_anonymizer.git/)
- percona-timescaledb: update upstream version 2.32.1 (https://github.com/timescale/timescaledb/releases/tag/2.32.1)
- percona-distribution-postgresql-custom (ubi9) [container image]: update image ? → extras-16.16-2
  - added: percona-credcheck16 6.0-2.3.el9
  - updated: SFCGAL 2.3.0-3.1.el9 -> 2.3.0-3.3.el9
  - updated: blas 3.9.0-2.2.el9 -> 3.9.0-2.4.el9
  - updated: boost-serialization 1.75.0-2.2.el9 -> 1.75.0-2.4.el9
  - updated: curl 8.23.0-3.1.el9 -> 8.23.0-3.3.el9
  - updated: flexiblas 3.0.4-1.21.el9 -> 3.0.4-1.23.el9
  - updated: flexiblas-netlib 3.0.4-1.21.el9 -> 3.0.4-1.23.el9
  - updated: flexiblas-netlib64 3.0.4-1.21.el9 -> 3.0.4-1.23.el9
  - updated: flexiblas-openblas-threads 3.0.4-1.21.el9 -> 3.0.4-1.23.el9
  - updated: gdal313-libs 3.13.3-3.9.el9 -> 3.13.3-3.15.el9
  - updated: geos315 3.15.0-2.2.el9 -> 3.15.0-2.4.el9
  - updated: gosu 1.19-5.2.el9 -> 1.19-6.2.el9
  - updated: h3 4.5.0-2.2.el9 -> 4.5.0-2.4.el9
  - updated: lapack 3.9.0-2.2.el9 -> 3.9.0-2.4.el9
  - updated: libcurl 8.23.0-3.1.el9 -> 8.23.0-3.3.el9
  - updated: libgeotiff17 1.7.4-2.5.el9 -> 1.7.4-2.7.el9
  - updated: libicu 67.1-11.2.el9 -> 67.1-11.4.el9
  - updated: libproxy 0.4.15-36.3.el9 -> 0.4.15-36.6.el9
  - updated: libqhull_r 7.2.1-12.2.el9 -> 7.2.1-12.4.el9
  - updated: librttopo 1.1.0-46.2.el9 -> 1.1.0-46.4.el9
  - updated: libspatialite50 5.1.0-2.5.el9 -> 5.1.0-2.7.el9
  - updated: libusbx 1.0.30-1.11.el9 -> 1.0.30-1.13.el9
  - updated: percona-h3-pg_16 4.5.0-2.6.el9 -> 4.5.0-3.3.el9
  - updated: percona-hll_16 2.21-2.6.el9 -> 2.21-3.3.el9
  - updated: percona-ip4r_16 2.4.3-2.6.el9 -> 2.4.3-3.3.el9
  - updated: percona-patroni 4.1.5-6.1.el9 -> 4.1.5-6.4.el9
  - updated: percona-patroni-etcd 4.1.5-6.1.el9 -> 4.1.5-6.4.el9
  - updated: percona-pg-telemetry16 1.2.0-4.8.el9 -> 1.2.0-4.15.el9
  - updated: percona-pg_cron_16 1.6.8-3.7.el9 -> 1.6.8-5.3.el9
  - updated: percona-pg_partman_16 5.5.0-2.6.el9 -> 5.5.1-1.2.el9
  - updated: percona-pg_repack16 1.5.3-7.5.el9 -> 1.5.3-9.3.el9
  - updated: percona-pg_similarity_16 1.0-2.6.el9 -> 1.0-3.3.el9
  - updated: percona-pg_stat_monitor16 2.4.0-3.2.el9 -> 2.4.0-3.9.el9
  - updated: percona-pgaudit16 16.1-5.7.el9 -> 16.2-2.2.el9
  - updated: percona-pgaudit16_set_user 4.2.0-5.8.el9 -> 4.3.0-2.8.el9
  - updated: percona-pgbackrest 2.60.0-4.1.el9 -> 2.60.1-2.2.el9
  - updated: percona-pgrouting_16 4.0.2-2.6.el9 -> 4.0.2-2.11.el9
  - updated: percona-pgvector_16 0.8.7-2.7.el9 -> 0.8.7-4.3.el9
  - updated: percona-pgvector_16-llvmjit 0.8.7-2.7.el9 -> 0.8.7-4.3.el9
  - updated: percona-pgvectorscale_16 0.9.1-2.6.el9 -> 0.9.1-3.2.el9
  - updated: percona-postgis35_16 3.5.7-4.10.el9 -> 3.5.7-6.4.el9
  - updated: percona-postgis35_16-client 3.5.7-4.10.el9 -> 3.5.7-6.4.el9
  - updated: percona-postgis35_16-gui 3.5.7-4.10.el9 -> 3.5.7-6.4.el9
  - updated: percona-postgis35_16-llvmjit 3.5.7-4.10.el9 -> 3.5.7-6.4.el9
  - updated: percona-postgis35_16-utils 3.5.7-4.10.el9 -> 3.5.7-6.4.el9
  - updated: percona-postgresql-client-common 293-5.1.el9 -> 297-1.2.el9
  - updated: percona-postgresql-common 293-5.1.el9 -> 297-1.2.el9
  - updated: percona-postgresql-unit_16 7.10-2.6.el9 -> 7.10-3.2.el9
  - updated: percona-postgresql16 16.15-5.1.el9 -> 16.16-2.2.el9
  - updated: percona-postgresql16-contrib 16.15-5.1.el9 -> 16.16-2.2.el9
  - updated: percona-postgresql16-libs 16.15-5.1.el9 -> 16.16-2.2.el9
  - updated: percona-postgresql16-llvmjit 16.15-5.1.el9 -> 16.16-2.2.el9
  - updated: percona-postgresql16-server 16.15-5.1.el9 -> 16.16-2.2.el9
  - updated: percona-postgresql_anonymizer_16 3.2.3-2.6.el9 -> 3.3.2-1.4.el9
  - updated: percona-rum_16 1.3.15-2.6.el9 -> 1.3.15-3.2.el9
  - updated: percona-timescaledb_16 2.30.2-2.6.el9 -> 2.32.1-1.2.el9
  - updated: percona-wal2json16 2.7-2.7.el9 -> 2.7-3.8.el9
  - updated: perl-JSON 4.03-1.20.el9 -> 4.03-1.22.el9
  - updated: proj98 9.8.1-3.5.el9 -> 9.8.1-3.8.el9
  - updated: python3-ydiff 1.4.2-4.2.el9 -> 1.4.2-4.5.el9
  - updated: python3.12-click 8.1.7-3.2.el9 -> 8.1.7-3.5.el9
  - updated: python3.12-dateutil 2.9.0.post0-3.2.el9 -> 2.9.0.post0-3.5.el9
  - updated: python3.12-dns 2.9.0-3.2.el9 -> 2.9.2-1.2.el9
  - updated: python3.12-etcd 0.4.5-3.2.el9 -> 0.4.5-3.5.el9
  - updated: python3.12-prettytable 3.4.0-3.2.el9 -> 3.4.0-3.5.el9
  - updated: python3.12-psutil 6.1.1-3.2.el9 -> 6.1.1-3.5.el9
  - updated: python3.12-psycopg2 2.9.13-5.5.el9 -> 2.9.13-6.2.el9
  - updated: python3.12-six 1.17.0-3.2.el9 -> 1.17.0-3.5.el9
  - updated: python3.12-systemd 235-2.2.el9 -> 235-2.5.el9
  - updated: python3.12-wcwidth 0.2.13-3.2.el9 -> 0.2.13-3.5.el9
  - updated: qt5-qtbase 5.15.9-12.3.el9 -> 5.15.9-12.6.el9
  - updated: qt5-qtbase-common 5.15.9-12.3.el9 -> 5.15.9-12.6.el9
  - updated: snappy 1.1.8-9.2.el9 -> 1.1.8-9.4.el9

### Security
- percona-postgresql: PostgreSQL 16.16 fixes 44 CVEs
  (https://www.postgresql.org/docs/release/16.16/): CVE-2026-116303, CVE-2026-116304,
  CVE-2026-116306, CVE-2026-116307, CVE-2026-116308, CVE-2026-116309, CVE-2026-116311,
  CVE-2026-116312, CVE-2026-116314, CVE-2026-116315, CVE-2026-116316, CVE-2026-116317,
  CVE-2026-116319, CVE-2026-116320, CVE-2026-116321, CVE-2026-116323, CVE-2026-116326,
  CVE-2026-116327, CVE-2026-116328, CVE-2026-116330, CVE-2026-116331, CVE-2026-116332,
  CVE-2026-116335, CVE-2026-116336, CVE-2026-120139, CVE-2026-120141, CVE-2026-120143,
  CVE-2026-120145, CVE-2026-120146, CVE-2026-120147, CVE-2026-120148, CVE-2026-120149,
  CVE-2026-120150, CVE-2026-120151, CVE-2026-120152, CVE-2026-120153, CVE-2026-120154,
  CVE-2026-14661, CVE-2026-16237, CVE-2026-16240, CVE-2026-18447, CVE-2026-6460, CVE-2026-6464,
  CVE-2026-6467
- No CVE fixes mentioned upstream for: percona-pg_partman, percona-timescaledb (release notes and commit logs scanned for the version range).
- Not scanned: percona-postgresql_anonymizer (no scanner for gitlab.com)
- UBI base-image package CVEs are not covered by this scan.

