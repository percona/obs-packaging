# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [17.11-1] - 2026-09-03

### Added
- h3 (extras): add upstream version 4.5.0 (https://github.com/uber/h3/releases/tag/v4.5.0)
- percona-h3-pg (extras): add upstream version 4.5.0 (https://github.com/postgis/h3-pg/releases/tag/v4.5.0)
- percona-hll (extras): add upstream version 2.21 (https://github.com/citusdata/postgresql-hll/releases/tag/v2.21)
- percona-ip4r (extras): add upstream version 2.4.3 (https://github.com/RhodiumToad/ip4r/releases/tag/2.4.3)
- percona-pg_partman (extras): add upstream version 5.4.3 (https://github.com/pgpartman/pg_partman/releases/tag/v5.4.3)
- percona-pg_similarity (extras): add upstream version pg_similarity_1_0 (https://github.com/eulerto/pg_similarity/releases/tag/pg_similarity_1_0)
- percona-pgrouting (extras): add upstream version 4.0.1 (https://github.com/pgRouting/pgrouting/releases/tag/v4.0.1)
- percona-pgvectorscale (extras): add upstream version 0.9.0 (https://github.com/timescale/pgvectorscale/releases/tag/0.9.0)
- percona-postgresql (extras): add upstream version 17.11 (https://github.com/postgres/postgres/releases/tag/REL_17_11)
- percona-postgresql-unit (extras): add upstream version 7.10 (https://github.com/df7cb/postgresql-unit/releases/tag/7.10)
- percona-postgresql_anonymizer (extras): add upstream version 3.1.1 (https://gitlab.com/dalibo/postgresql_anonymizer.git/)
- percona-rum (extras): add upstream version 1.3.15 (https://github.com/postgrespro/rum/releases/tag/1.3.15)
- percona-timescaledb (extras): add upstream version 2.28.1 (https://github.com/timescale/timescaledb/releases/tag/2.28.1)
- percona-distribution-postgresql (ubi8) [container image]: add image 17.11-1
  - gosu 1.19-13.4
  - percona-patroni 4.1.5-2.1
  - percona-patroni-etcd 4.1.5-2.1
  - percona-pg_cron_17 1.6.7-1.26
  - percona-pg_repack17 1.5.3-2.20
  - percona-pg_stat_monitor17 2.3.2-1.26
  - percona-pg_tde17 2.2.2-1.3
  - percona-pgaudit17 17.1-2.23
  - percona-pgaudit17_set_user 4.2.0-1.26
  - percona-pgbackrest 2.59.0-2.2
  - percona-pgvector_17 0.8.6-1.3
  - percona-pgvector_17-llvmjit 0.8.6-1.3
  - percona-postgresql-client-common 293-1.2
  - percona-postgresql-common 293-1.2
  - percona-postgresql17 17.11-2.2
  - percona-postgresql17-contrib 17.11-2.2
  - percona-postgresql17-libs 17.11-2.2
  - percona-postgresql17-llvmjit 17.11-2.2
  - percona-postgresql17-server 17.11-2.2
  - percona-wal2json17 2.6-1.26
  - perl-JSON 4.03-2.22
  - python3-ydiff 1.4.2-2.25
  - python3.12-click 8.1.7-2.25
  - python3.12-dateutil 2.9.0.post0-3.22
  - python3.12-dns 1.15.0-2.25
  - python3.12-etcd 0.4.5-2.25
  - python3.12-prettytable 3.4.0-2.25
  - python3.12-psutil 6.1.1-2.25
  - python3.12-psycopg2 2.9.10-2.20
  - python3.12-six 1.17.0-2.25
  - python3.12-systemd 235-1.1
  - python3.12-wcwidth 0.2.13-2.25
- percona-distribution-postgresql-with-postgis (ubi8) [container image]: add image 17.11-1
  - SFCGAL 2.2.0-4.22
  - blas 3.9.0-1.23
  - geos 3.13.1-2.14
  - gosu 1.19-13.4
  - lapack 3.9.0-1.23
  - percona-patroni 4.1.5-2.1
  - percona-patroni-etcd 4.1.5-2.1
  - percona-pg_cron_17 1.6.7-1.26
  - percona-pg_repack17 1.5.3-2.20
  - percona-pg_stat_monitor17 2.3.2-1.26
  - percona-pg_tde17 2.2.2-1.3
  - percona-pgaudit17 17.1-2.23
  - percona-pgaudit17_set_user 4.2.0-1.26
  - percona-pgbackrest 2.59.0-2.2
  - percona-pgvector_17 0.8.6-1.3
  - percona-pgvector_17-llvmjit 0.8.6-1.3
  - percona-postgis35_17 3.5.7-1.36
  - percona-postgis35_17-client 3.5.7-1.36
  - percona-postgis35_17-gui 3.5.7-1.36
  - percona-postgis35_17-llvmjit 3.5.7-1.36
  - percona-postgis35_17-utils 3.5.7-1.36
  - percona-postgresql-client-common 293-1.2
  - percona-postgresql-common 293-1.2
  - percona-postgresql17 17.11-2.2
  - percona-postgresql17-contrib 17.11-2.2
  - percona-postgresql17-libs 17.11-2.2
  - percona-postgresql17-llvmjit 17.11-2.2
  - percona-postgresql17-server 17.11-2.2
  - percona-wal2json17 2.6-1.26
  - perl-JSON 4.03-2.22
  - python3-ydiff 1.4.2-2.25
  - python3.12-click 8.1.7-2.25
  - python3.12-dateutil 2.9.0.post0-3.22
  - python3.12-dns 1.15.0-2.25
  - python3.12-etcd 0.4.5-2.25
  - python3.12-prettytable 3.4.0-2.25
  - python3.12-psutil 6.1.1-2.25
  - python3.12-psycopg2 2.9.10-2.20
  - python3.12-six 1.17.0-2.25
  - python3.12-systemd 235-1.1
  - python3.12-wcwidth 0.2.13-2.25
- percona-pgbackrest (ubi8) [container image]: add image 17.11-1
  - percona-pgbackrest 2.59.0-2.2
- percona-pgbouncer (ubi8) [container image]: add image 17.11-1
  - c-ares 1.19.1-1.1
  - percona-pgbouncer 1.25.2-1.20
  - python3.12-psycopg2 2.9.10-2.20

### Changed
- etcd: update upstream version 3.5.33
- percona-haproxy: update upstream version 2.8.27 (http://git.haproxy.org/git/haproxy-2.8.git/)
- percona-patroni: update upstream version 4.1.5 (https://github.com/zalando/patroni/releases/tag/v4.1.5)
- percona-pg_tde: update upstream version 2.2.2 (https://github.com/percona/pg_tde/releases/tag/2.2.2)
- percona-pgbackrest: update upstream version 2.59.0 (https://github.com/pgbackrest/pgbackrest/releases/tag/release/2.59.0)
- percona-pgpool-II: update upstream version 4.7.2 (https://github.com/pgpool/pgpool2/releases/tag/V4_7_2)
- percona-pgvector: update upstream version 0.8.6 (https://github.com/pgvector/pgvector/releases/tag/v0.8.6)
- percona-postgis: update upstream version 3.5.7 (https://github.com/postgis/postgis/releases/tag/3.5.7)
- percona-postgresql: update upstream version 17.11 (https://github.com/percona/postgres/releases/tag/PSP-17.11.1)
- percona-postgresql-common: update upstream version 293 (https://salsa.debian.org/postgresql/postgresql-common.git)
- percona-ppg-server: update upstream version 17.11
- percona-ppg-server-ha: update upstream version 17.11
- percona-telemetry-agent: update upstream version 1.0.15
- percona-distribution-postgresql (ubi9) [container image]: update image 17.10-1 → 17.11-1
  - added: perl-JSON 4.03-2.22
  - added: python3.12-systemd 235-1.1
  - updated: gosu 1.19-3.1 -> 1.19-13.2
  - updated: percona-patroni 4.1.3-2.1 -> 4.1.5-2.1
  - updated: percona-patroni-etcd 4.1.3-2.1 -> 4.1.5-2.1
  - updated: percona-pg_cron_17 1.6.7-2.2 -> 1.6.7-1.25
  - updated: percona-pg_repack17 1.5.3-5.2 -> 1.5.3-2.20
  - updated: percona-pg_stat_monitor17 2.3.2-5.6 -> 2.3.2-1.25
  - updated: percona-pg_tde17 2.2.0-3.1 -> 2.2.2-1.2
  - updated: percona-pgaudit17 17.1-5.4 -> 17.1-2.23
  - updated: percona-pgaudit17_set_user 4.2.0-5.2 -> 4.2.0-1.25
  - updated: percona-pgbackrest 2.58.0-4.6 -> 2.59.0-2.1
  - updated: percona-pgvector_17 0.8.2-4.2 -> 0.8.6-1.2
  - updated: percona-pgvector_17-llvmjit 0.8.2-4.2 -> 0.8.6-1.2
  - updated: percona-postgresql-client-common 290-1.1 -> 293-1.1
  - updated: percona-postgresql-common 290-1.1 -> 293-1.1
  - updated: percona-postgresql17 17.10-1.1 -> 17.11-2.1
  - updated: percona-postgresql17-contrib 17.10-1.1 -> 17.11-2.1
  - updated: percona-postgresql17-libs 17.10-1.1 -> 17.11-2.1
  - updated: percona-postgresql17-llvmjit 17.10-1.1 -> 17.11-2.1
  - updated: percona-postgresql17-server 17.10-1.1 -> 17.11-2.1
  - updated: percona-wal2json17 2.6-5.1 -> 2.6-1.25
  - updated: python3-ydiff 1.4.2-1.7 -> 1.4.2-2.23
  - updated: python3.12-click 8.1.7-1.7 -> 8.1.7-2.23
  - updated: python3.12-dateutil 2.9.0.post0-1.7 -> 2.9.0.post0-3.22
  - updated: python3.12-dns 1.15.0-1.7 -> 1.15.0-2.23
  - updated: python3.12-etcd 0.4.5-1.7 -> 0.4.5-2.23
  - updated: python3.12-prettytable 3.4.0-1.7 -> 3.4.0-2.23
  - updated: python3.12-psutil 6.1.1-1.7 -> 6.1.1-2.23
  - updated: python3.12-psycopg2 2.9.10-2.8 -> 2.9.10-2.20
  - updated: python3.12-six 1.17.0-1.7 -> 1.17.0-2.23
  - updated: python3.12-wcwidth 0.2.13-1.7 -> 0.2.13-2.23
  - removed: percona-pg-telemetry17
  - removed: percona-telemetry-agent
  - removed: python3-etcd
- percona-distribution-postgresql-with-postgis (ubi9) [container image]: update image 17.10-1 → 17.11-1
  - added: blas 3.9.0-1.26
  - added: flexiblas 3.0.4-2.25
  - added: flexiblas-netlib 3.0.4-2.25
  - added: flexiblas-netlib64 3.0.4-2.25
  - added: flexiblas-openblas-threads 3.0.4-2.25
  - added: geos 3.13.1-2.15
  - added: h3 4.5.0-1.20
  - added: lapack 3.9.0-1.26
  - added: percona-h3-pg_17 4.5.0-1.25
  - added: percona-hll_17 2.21-1.24
  - added: percona-ip4r_17 2.4.3-1.24
  - added: percona-pg_partman_17 5.4.3-1.24
  - added: percona-pg_similarity_17 pg_similarity_1_0-1.24
  - added: percona-pgrouting_17 4.0.1-1.30
  - added: percona-pgvectorscale_17 0.9.0-6.4
  - added: percona-postgresql-unit_17 7.10-1.24
  - added: percona-postgresql_anonymizer_17 3.1.1-2.26
  - added: percona-rum_17 1.3.15-1.24
  - added: percona-timescaledb_17 2.28.1-1.25
  - added: perl-JSON 4.03-2.22
  - added: proj 9.6.0-2.27
  - added: proj-data 9.6.0-2.27
  - added: python3-psycopg2 2.9.10-2.20
  - added: python3.12-systemd 235-1.1
  - updated: SFCGAL 2.2.0-2.4 -> 2.2.0-4.23
  - updated: gosu 1.19-3.1 -> 1.19-13.2
  - updated: percona-patroni 4.1.3-2.1 -> 4.1.5-2.1
  - updated: percona-patroni-etcd 4.1.3-2.1 -> 4.1.5-2.1
  - updated: percona-pg-telemetry17 1.2.0-4.6 -> 1.2.0-2.1
  - updated: percona-pg_cron_17 1.6.7-2.2 -> 1.6.7-1.25
  - updated: percona-pg_repack17 1.5.3-5.2 -> 1.5.3-2.20
  - updated: percona-pg_stat_monitor17 2.3.2-5.6 -> 2.3.2-1.25
  - updated: percona-pg_tde17 2.2.0-3.1 -> 2.2.2-1.2
  - updated: percona-pgaudit17 17.1-5.4 -> 17.1-2.23
  - updated: percona-pgaudit17_set_user 4.2.0-5.2 -> 4.2.0-1.25
  - updated: percona-pgbackrest 2.58.0-4.6 -> 2.59.0-2.1
  - updated: percona-pgvector_17 0.8.2-4.2 -> 0.8.6-1.2
  - updated: percona-pgvector_17-llvmjit 0.8.2-4.2 -> 0.8.6-1.2
  - updated: percona-postgis35_17 3.5.6-1.3 -> 3.5.7-1.54
  - updated: percona-postgis35_17-client 3.5.6-1.3 -> 3.5.7-1.54
  - updated: percona-postgis35_17-gui 3.5.6-1.3 -> 3.5.7-1.54
  - updated: percona-postgis35_17-llvmjit 3.5.6-1.3 -> 3.5.7-1.54
  - updated: percona-postgis35_17-utils 3.5.6-1.3 -> 3.5.7-1.54
  - updated: percona-postgresql-client-common 290-1.1 -> 293-1.1
  - updated: percona-postgresql-common 290-1.1 -> 293-1.1
  - updated: percona-postgresql17 17.10-1.1 -> 17.11-1.2
  - updated: percona-postgresql17-contrib 17.10-1.1 -> 17.11-1.2
  - updated: percona-postgresql17-libs 17.10-1.1 -> 17.11-1.2
  - updated: percona-postgresql17-llvmjit 17.10-1.1 -> 17.11-1.2
  - updated: percona-postgresql17-server 17.10-1.1 -> 17.11-1.2
  - updated: percona-wal2json17 2.6-5.1 -> 2.6-1.25
  - updated: python3-ydiff 1.4.2-1.7 -> 1.4.2-2.23
  - updated: python3.12-click 8.1.7-1.7 -> 8.1.7-2.23
  - updated: python3.12-dateutil 2.9.0.post0-1.7 -> 2.9.0.post0-3.22
  - updated: python3.12-dns 1.15.0-1.7 -> 1.15.0-2.23
  - updated: python3.12-etcd 0.4.5-1.7 -> 0.4.5-2.23
  - updated: python3.12-prettytable 3.4.0-1.7 -> 3.4.0-2.23
  - updated: python3.12-psutil 6.1.1-1.7 -> 6.1.1-2.23
  - updated: python3.12-psycopg2 2.9.10-2.8 -> 2.9.10-2.20
  - updated: python3.12-six 1.17.0-1.7 -> 1.17.0-2.23
  - updated: python3.12-wcwidth 0.2.13-1.7 -> 0.2.13-2.23
  - removed: percona-telemetry-agent
  - removed: python3-etcd
- percona-pgbackrest (ubi9) [container image]: update image 17.10-1 → 17.11-1
  - updated: percona-pgbackrest 2.58.0-4.6 -> 2.59.0-2.1
  - updated: percona-postgresql17-libs 17.10-1.1 -> 17.11-2.1
- percona-pgbouncer (ubi9) [container image]: update image 17.10-1 → 17.11-1
  - added: c-ares 1.19.1-1.28
  - updated: percona-pgbouncer 1.25.2-2.1 -> 1.25.2-1.30
  - updated: percona-postgresql17-libs 17.10-1.1 -> 17.11-2.1
  - updated: python3.12-psycopg2 2.9.10-2.8 -> 2.9.10-2.20
  - removed: python3-psycopg2

### Security
- percona-postgresql: PostgreSQL 17.11 fixes 28 CVEs (https://www.postgresql.org/docs/release/17.11/), notably
  CVE-2026-15741 (SQL injection in EXTRACT() deparsing), CVE-2026-14681 (GSSEncRequest accepted after direct
  SSL connection), CVE-2026-14666 (role-dependent cached plans not invalidated), and CVE-2026-6471 (logical
  decoding output plugin whitelist). Full list: CVE-2026-6464, CVE-2026-6469, CVE-2026-6470, CVE-2026-6471,
  CVE-2026-14662, CVE-2026-14663, CVE-2026-14664, CVE-2026-14666, CVE-2026-14668, CVE-2026-14669,
  CVE-2026-14670, CVE-2026-14671, CVE-2026-14672, CVE-2026-14673, CVE-2026-14676, CVE-2026-14677,
  CVE-2026-14678, CVE-2026-14679, CVE-2026-14680, CVE-2026-14681, CVE-2026-15741, CVE-2026-15742,
  CVE-2026-16238, CVE-2026-16239, CVE-2026-16241, CVE-2026-18024, CVE-2026-18408, CVE-2026-19385.
- Go toolchain 1.26.3 → 1.26.6 (rebuilds of gosu, etcd, percona-telemetry-agent in the container
  images): fixes CVE-2026-39822 (os: Root escape via symlink + trailing slash), CVE-2026-33818,
  CVE-2026-56864, CVE-2026-56865, plus unnumbered upstream security fixes in crypto/x509,
  crypto/tls, mime, net/textproto, html/template, encoding/xml, net, net/http and net/url
  (https://go.dev/doc/devel/release#go1.26.6).
- No CVE fixes mentioned upstream for: etcd, percona-haproxy, percona-patroni, percona-pg_tde,
  percona-pgbackrest, percona-pgpool-II, percona-pgvector, percona-postgis, percona-postgresql-common,
  percona-telemetry-agent (release notes, changelogs, and commit logs scanned for this version range).
  UBI base-image package CVEs are not covered by this scan.

## [17.10-1] - 2026-05-19

### Added
- percona-pg_cron: add upstream version 1.6.7 (https://github.com/citusdata/pg_cron/releases/tag/v1.6.7)
- percona-pgbackrest [container image]: add image 17.10-1
  - percona-pgbackrest 2.58.0-4.6
  - percona-postgresql17-libs 17.10-1.1
- percona-pgbouncer [container image]: add image 17.10-1
  - percona-pgbouncer 1.25.2-2.1
  - percona-postgresql17-libs 17.10-1.1
  - python3-psycopg2 2.9.10-2.8
  - python3.12-psycopg2 2.9.10-2.8

### Changed
- etcd: update upstream version 3.5.30 (https://github.com/etcd-io/etcd/releases/tag/v3.5.30)
- percona-haproxy: update upstream version 2.8.23 (https://www.haproxy.org/download/2.8/src/CHANGELOG)
- percona-patroni: update upstream version 4.1.3 (https://github.com/zalando/patroni/releases/tag/v4.1.3)
- percona-pg_gather: update upstream version 33 (https://github.com/jobinau/pg_gather/releases/tag/v33)
- percona-pg_tde: update upstream version 2.2.0 (https://github.com/percona/pg_tde/releases/tag/2.2.0)
- percona-pgbouncer: update upstream version 1.25.2 (https://github.com/pgbouncer/pgbouncer/releases/tag/pgbouncer_1_25_2)
- percona-pgpool-II: update upstream version 4.7.1 (https://www.pgpool.net/docs/4.7/en/html/release-4-7-1.html)
- percona-postgis: update upstream version 3.5.6 (https://github.com/postgis/postgis/blob/3.5.6/NEWS)
- percona-postgresql-common: update upstream version 290 (https://salsa.debian.org/postgresql/postgresql-common/-/tags/debian%2F290)
- percona-postgresql: update upstream version 17.10 (https://www.postgresql.org/docs/release/17.10/)
- percona-telemetry-agent: update upstream version 1.0.13 (https://github.com/percona/telemetry-agent/releases/tag/v1.0.13)
- percona-distribution-postgresql [container image]: update image 17.9-2 → 17.10-1
  - added: percona-pg_cron_17 1.6.7-2.2
  - updated: gosu 1.19-2.5 -> 1.19-3.1
  - updated: percona-patroni 4.1.1-5.1 -> 4.1.3-2.1
  - updated: percona-patroni-etcd 4.1.1-5.1 -> 4.1.3-2.1
  - updated: percona-pg-telemetry17 1.2.0-3.4 -> 1.2.0-4.6
  - updated: percona-pg_repack17 1.5.3-4.7 -> 1.5.3-5.2
  - updated: percona-pg_stat_monitor17 2.3.2-4.3 -> 2.3.2-5.6
  - updated: percona-pg_tde17 2.1.2-4.3 -> 2.2.0-3.1
  - updated: percona-pgaudit17 17.1-4.7 -> 17.1-5.4
  - updated: percona-pgaudit17_set_user 4.2.0-4.7 -> 4.2.0-5.2
  - updated: percona-pgbackrest 2.58.0-3.5 -> 2.58.0-4.6
  - updated: percona-pgvector_17 0.8.2-3.3 -> 0.8.2-4.2
  - updated: percona-pgvector_17-llvmjit 0.8.2-3.3 -> 0.8.2-4.2
  - updated: percona-postgresql-client-common 289-2.4 -> 290-1.1
  - updated: percona-postgresql-common 289-2.4 -> 290-1.1
  - updated: percona-postgresql17 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-contrib 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-libs 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-llvmjit 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-server 17.9-4.3 -> 17.10-1.1
  - updated: percona-telemetry-agent 1.0.9-5.6 -> 1.0.13-1.1
  - updated: percona-wal2json17 2.6-4.3 -> 2.6-5.1
  - updated: python3-etcd 0.4.5-1.6 -> 0.4.5-1.7
  - updated: python3-ydiff 1.4.2-1.6 -> 1.4.2-1.7
  - updated: python3.12-click 8.1.7-1.6 -> 8.1.7-1.7
  - updated: python3.12-dateutil 2.9.0.post0-1.6 -> 2.9.0.post0-1.7
  - updated: python3.12-dns 1.15.0-1.6 -> 1.15.0-1.7
  - updated: python3.12-etcd 0.4.5-1.6 -> 0.4.5-1.7
  - updated: python3.12-prettytable 3.4.0-1.6 -> 3.4.0-1.7
  - updated: python3.12-psutil 6.1.1-1.6 -> 6.1.1-1.7
  - updated: python3.12-psycopg2 2.9.10-2.6 -> 2.9.10-2.8
  - updated: python3.12-six 1.17.0-1.6 -> 1.17.0-1.7
  - updated: python3.12-wcwidth 0.2.13-1.6 -> 0.2.13-1.7
- percona-distribution-postgresql-with-postgis [container image]: update image 17.9-2 → 17.10-1
  - added: percona-pg_cron_17 1.6.7-2.2
  - updated: SFCGAL 2.2.0-2.3 -> 2.2.0-2.4
  - updated: gosu 1.19-2.5 -> 1.19-3.1
  - updated: percona-patroni 4.1.1-5.1 -> 4.1.3-2.1
  - updated: percona-patroni-etcd 4.1.1-5.1 -> 4.1.3-2.1
  - updated: percona-pg-telemetry17 1.2.0-3.4 -> 1.2.0-4.6
  - updated: percona-pg_repack17 1.5.3-4.7 -> 1.5.3-5.2
  - updated: percona-pg_stat_monitor17 2.3.2-4.3 -> 2.3.2-5.6
  - updated: percona-pg_tde17 2.1.2-4.3 -> 2.2.0-3.1
  - updated: percona-pgaudit17 17.1-4.7 -> 17.1-5.4
  - updated: percona-pgaudit17_set_user 4.2.0-4.7 -> 4.2.0-5.2
  - updated: percona-pgbackrest 2.58.0-3.5 -> 2.58.0-4.6
  - updated: percona-pgvector_17 0.8.2-3.3 -> 0.8.2-4.2
  - updated: percona-pgvector_17-llvmjit 0.8.2-3.3 -> 0.8.2-4.2
  - updated: percona-postgis35_17 3.5.5-3.5 -> 3.5.6-1.3
  - updated: percona-postgis35_17-client 3.5.5-3.5 -> 3.5.6-1.3
  - updated: percona-postgis35_17-gui 3.5.5-3.5 -> 3.5.6-1.3
  - updated: percona-postgis35_17-llvmjit 3.5.5-3.5 -> 3.5.6-1.3
  - updated: percona-postgis35_17-utils 3.5.5-3.5 -> 3.5.6-1.3
  - updated: percona-postgresql-client-common 289-2.4 -> 290-1.1
  - updated: percona-postgresql-common 289-2.4 -> 290-1.1
  - updated: percona-postgresql17 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-contrib 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-libs 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-llvmjit 17.9-4.3 -> 17.10-1.1
  - updated: percona-postgresql17-server 17.9-4.3 -> 17.10-1.1
  - updated: percona-telemetry-agent 1.0.9-5.6 -> 1.0.13-1.1
  - updated: percona-wal2json17 2.6-4.3 -> 2.6-5.1
  - updated: python3-etcd 0.4.5-1.6 -> 0.4.5-1.7
  - updated: python3-ydiff 1.4.2-1.6 -> 1.4.2-1.7
  - updated: python3.12-click 8.1.7-1.6 -> 8.1.7-1.7
  - updated: python3.12-dateutil 2.9.0.post0-1.6 -> 2.9.0.post0-1.7
  - updated: python3.12-dns 1.15.0-1.6 -> 1.15.0-1.7
  - updated: python3.12-etcd 0.4.5-1.6 -> 0.4.5-1.7
  - updated: python3.12-prettytable 3.4.0-1.6 -> 3.4.0-1.7
  - updated: python3.12-psutil 6.1.1-1.6 -> 6.1.1-1.7
  - updated: python3.12-psycopg2 2.9.10-2.6 -> 2.9.10-2.8
  - updated: python3.12-six 1.17.0-1.6 -> 1.17.0-1.7
  - updated: python3.12-wcwidth 0.2.13-1.6 -> 0.2.13-1.7

### Fixed

## [17.9-2] - 2026-05-13

### Added

### Changed
- etcd: update upstream version 3.5.29 (https://github.com/etcd-io/etcd/releases/tag/v3.5.29)
- percona-patroni: update upstream version 4.1.1 (https://github.com/zalando/patroni/releases/tag/v4.1.1)

### Fixed

## [17.9-1] - 2026-05-11

### Added
- etcd: add upstream version 3.5.26 (https://github.com/etcd-io/etcd/releases/tag/v3.5.26)
- percona-haproxy: add upstream version 2.8.18 (https://www.haproxy.org/download/2.8/src/CHANGELOG)
- percona-patroni: add upstream version 4.1.0 (https://github.com/zalando/patroni/releases/tag/v4.1.0)
- percona-pg-telemetry: add upstream version 1.2.0 (https://github.com/percona/percona_pg_telemetry/releases/tag/1.2.0)
- percona-pg_gather: add upstream version 32 (https://github.com/jobinau/pg_gather/releases/tag/v32)
- percona-pg_repack: add upstream version 1.5.3 (https://github.com/reorg/pg_repack/releases/tag/ver_1.5.3)
- percona-pg_stat_monitor: add upstream version 2.3.2 (https://github.com/percona/pg_stat_monitor/releases/tag/2.3.2)
- percona-pg_tde: add upstream version 2.1.2 (https://github.com/percona/pg_tde/releases/tag/2.1.2)
- percona-pgaudit: add upstream version 17.1 (https://github.com/pgaudit/pgaudit/releases/tag/17.1)
- percona-pgaudit_set_user: add upstream version 4.2.0 (https://github.com/pgaudit/set_user/releases/tag/REL4_2_0)
- percona-pgbackrest: add upstream version 2.58.0 (https://github.com/pgbackrest/pgbackrest/releases/tag/release/2.58.0)
- percona-pgbadger: add upstream version 13.2 (https://github.com/darold/pgbadger/releases/tag/v13.2)
- percona-pgbouncer: add upstream version 1.25.1 (https://github.com/pgbouncer/pgbouncer/releases/tag/pgbouncer_1_25_1)
- percona-pgpool-II: add upstream version 4.7.0 (https://www.pgpool.net/docs/4.7/en/html/release-4-7-0.html)
- percona-pgvector: add upstream version 0.8.2 (https://github.com/pgvector/pgvector/blob/v0.8.2/CHANGELOG.md)
- percona-postgis: add upstream version 3.5.5 (https://github.com/postgis/postgis/blob/3.5.5/NEWS)
- percona-postgresql-common: add upstream version 289 (https://salsa.debian.org/postgresql/postgresql-common/-/tags/debian%2F289)
- percona-postgresql17: add upstream version 17.9 (https://www.postgresql.org/docs/release/17.9/)
- percona-ppg-server-17: add version 17.9 (meta-package: base selection of PostgreSQL 17 components)
- percona-ppg-server-ha-17: add version 17.9 (meta-package: selection of PostgreSQL 17 HA components)
- percona-telemetry-agent: add version 1.0.9 (https://github.com/percona/telemetry-agent/releases/tag/v1.0.9)
- percona-wal2json: add upstream version 2.6 (https://github.com/eulerto/wal2json/releases/tag/wal2json_2_6)
- python3-attrs: add upstream version 22.1.0 (https://github.com/python-attrs/attrs/releases/tag/22.1.0)
- python3-blessed: add upstream version 1.22.0 (https://github.com/jquast/blessed/releases/tag/1.22.0)
- python3-boto3: add upstream version 1.38.19 (https://github.com/boto/boto3/releases/tag/1.38.19)
- python3-botocore: add upstream version 1.38.19 (https://github.com/boto/botocore/releases/tag/1.38.19)
- python3-click: add upstream version 8.1.7 (https://github.com/pallets/click/releases/tag/8.1.7)
- python3-dateutil: add upstream version 2.9.0.post0 (https://github.com/dateutil/dateutil/releases/tag/2.9.0.post0)
- python3-dns: add upstream version 1.15.0 (https://github.com/rthalley/dnspython/releases/tag/v1.15.0)
- python3-etcd: add upstream version 0.4.5 (https://github.com/jplana/python-etcd/releases/tag/0.4.5)
- python3-kazoo: add upstream version 2.8.0 (https://github.com/python-zk/kazoo/releases/tag/2.8.0)
- python3-lz4: add upstream version 4.3.3 (https://github.com/python-lz4/python-lz4/releases/tag/v4.3.3)
- python3-prettytable: add upstream version 3.4.0 (https://github.com/jazzband/prettytable/releases/tag/3.4.0)
- python3-psutil: add upstream version 6.1.1 (https://github.com/giampaolo/psutil/releases/tag/release-6.1.1)
- python3-psycopg2: add upstream version 2.9.10 (https://github.com/psycopg/psycopg2/releases/tag/2.9.10)
- python3-py-consul: add upstream version 1.6.0 (https://github.com/criteo/py-consul/releases/tag/v1.6.0)
- python3-pysyncobj: add upstream version 0.3.10 (https://github.com/bakwc/PySyncObj/releases/tag/0.3.10)
- python3-six: add upstream version 1.17.0 (https://github.com/benjaminp/six/releases/tag/1.17.0)
- python3-wcwidth: add upstream version 0.2.13 (https://github.com/jquast/wcwidth/releases/tag/0.2.13)
- python3-zstandard: add upstream version 0.23.0 (https://github.com/indygreg/python-zstandard/releases/tag/0.23.0)
- sfcgal: add upstream version 2.2.0 (https://gitlab.com/sfcgal/SFCGAL/-/releases/v2.2.0)
- ydiff: add upstream version 1.4.2 (https://github.com/ymattw/ydiff/releases/tag/1.4.2)

### Changed

### Fixed

