# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

