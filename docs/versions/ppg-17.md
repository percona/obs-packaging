## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:17 | 3.5.30-1+5.1 |
| h3 | ppg:17:extras | 4.5.0-1.1 |
| percona-h3-pg | ppg:17:extras | 4.5.0-1.2 |
| percona-hll | ppg:17:extras | 2.21-1.2 |
| percona-ip4r | ppg:17:extras | 2.4.3-1.2 |
| percona-pg_partman | ppg:17:extras | 5.4.3-1.2 |
| percona-pg_similarity | ppg:17:extras | pg_similarity_1_0-1.2 |
| percona-pgrouting | ppg:17:extras | 4.0.1-1.2 |
| percona-pgvectorscale | ppg:17:extras | 0.9.0-2.1 |
| percona-postgresql | ppg:17:extras | 17.10-1.1 |
| percona-postgresql-unit | ppg:17:extras | 7.10-1.1 |
| percona-postgresql_anonymizer | ppg:17:extras | 3.1.1-3.1 |
| percona-rum | ppg:17:extras | 1.3.15-1.1 |
| percona-timescaledb | ppg:17:extras | 2.28.1-1.1 |
| percona-haproxy | ppg:17 | 2.8.23-1+2.1 |
| percona-patroni | ppg:17 | 4.1.3-1+3.4 |
| percona-pg-telemetry | ppg:17 | 1.2.0-1+6.3 |
| percona-pg_cron | ppg:17 | 1.6.7-1+6.3 |
| percona-pg_gather | ppg:17 | 33-1+1.1 |
| percona-pg_repack | ppg:17 | 1.5.3-1+8.3 |
| percona-pg_stat_monitor | ppg:17 | 2.3.2-1+7.3 |
| percona-pg_tde | ppg:17 | 2.2.0-1+11.2 |
| percona-pgaudit | ppg:17 | 17.1-1+8.3 |
| percona-pgaudit_set_user | ppg:17 | 4.2.0-1+8.3 |
| percona-pgbackrest | ppg:17 | 2.58.0-1+6.4 |
| percona-pgbadger | ppg:17 | 13.2-1+3.1 |
| percona-pgbouncer | ppg:17 | 1.25.2-1+3.4 |
| percona-pgpool-II | ppg:17 | 4.7.1-1+3.3 |
| percona-pgvector | ppg:17 | 0.8.3-1+1.3 |
| percona-postgis | ppg:17 | 3.5.7-1+2.3 |
| percona-postgresql | ppg:17 | 17.10-1+11.1 |
| percona-postgresql-common | ppg:17 | 290-1+1.1 |
| percona-ppg-server | ppg:17 | 17.10-1 |
| percona-ppg-server-ha | ppg:17 | 17.10-1 |
| percona-telemetry-agent | ppg:17 | 1.0.14-1+9.1 |
| percona-wal2json | ppg:17 | 2.6-1+7.3 |
| python3-attrs | ppg:17 | 22.1.0-2.3 |
| python3-blessed | ppg:17 | 1.22.0-2.3 |
| python3-boto3 | ppg:17 | 1.38.19-2.3 |
| python3-botocore | ppg:17 | 1.38.19-2.3 |
| python3-click | ppg:17 | 8.1.7-2.3 |
| python3-dateutil | ppg:17 | 2.9.0.post0-3.3 |
| python3-dns | ppg:17 | 1.15.0-2.3 |
| python3-etcd | ppg:17 | 0.4.5-2.3 |
| python3-kazoo | ppg:17 | 2.8.0-2.3 |
| python3-lz4 | ppg:17 | 4.3.3-3.3 |
| python3-prettytable | ppg:17 | 3.4.0-2.3 |
| python3-psutil | ppg:17 | 6.1.1-2.3 |
| python3-psycopg2 | ppg:17 | 2.9.10-3.7 |
| python3-py-consul | ppg:17 | 1.6.0-2.3 |
| python3-pysyncobj | ppg:17 | 0.3.10-1+3.1 |
| python3-six | ppg:17 | 1.17.0-2.3 |
| python3-wcwidth | ppg:17 | 0.2.13-2.3 |
| python3-zstandard | ppg:17 | 0.23.0-2.3 |
| sfcgal | ppg:17 | 2.2.0-4.4 |
| ydiff | ppg:17 | 1.4.2-1+2.1 |

## Container Images

| Package | Project | Image | Version | Tags | Installed packages |
| ------- | ------- | ----- | ------- | ---- | ------------------ |
| percona-distribution-postgresql | ppg:17:containers:ubi8 | percona-distribution-postgresql | 17.10-1 | `17.10-1-1.28` `17.10-1` `17.10` `17` | gosu 1.19-6.8, percona-patroni 4.1.3-3.7, percona-patroni-etcd 4.1.3-3.7, percona-pg-telemetry17 1.2.0-6.9, percona-pg_cron_17 1.6.7-6.9, percona-pg_repack17 1.5.3-8.9, percona-pg_stat_monitor17 2.3.2-7.9, percona-pg_tde17 2.2.0-11.3, percona-pgaudit17 17.1-8.8, percona-pgaudit17_set_user 4.2.0-8.9, percona-pgbackrest 2.58.0-6.5, percona-pgvector_17 0.8.3-1.7, percona-pgvector_17-llvmjit 0.8.3-1.7, percona-postgresql-client-common 290-1.7, percona-postgresql-common 290-1.7, percona-postgresql17 17.10-11.2, percona-postgresql17-contrib 17.10-11.2, percona-postgresql17-libs 17.10-11.2, percona-postgresql17-llvmjit 17.10-11.2, percona-postgresql17-server 17.10-11.2, percona-telemetry-agent 1.0.14-9.4, percona-wal2json17 2.6-7.8, perl-JSON 4.03-2.6, python3-etcd 0.4.5-2.7, python3-ydiff 1.4.2-2.7, python3.12-click 8.1.7-2.7, python3.12-dateutil 2.9.0.post0-3.4, python3.12-dns 1.15.0-2.7, python3.12-etcd 0.4.5-2.7, python3.12-prettytable 3.4.0-2.7, python3.12-psutil 6.1.1-2.7, python3.12-psycopg2 2.9.10-3.18, python3.12-six 1.17.0-2.7, python3.12-wcwidth 0.2.13-2.7 |
| percona-distribution-postgresql-with-postgis | ppg:17:containers:ubi8 | percona-distribution-postgresql-with-postgis | 17.10-1 | `17.10-1-1.46` `17.10-1` `17.10` `17` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.7, geos 3.13.1-1.7, gosu 1.19-6.8, lapack 3.9.0-1.7, percona-patroni 4.1.3-3.7, percona-patroni-etcd 4.1.3-3.7, percona-pg-telemetry17 1.2.0-6.9, percona-pg_cron_17 1.6.7-6.9, percona-pg_repack17 1.5.3-8.9, percona-pg_stat_monitor17 2.3.2-7.9, percona-pg_tde17 2.2.0-11.3, percona-pgaudit17 17.1-8.8, percona-pgaudit17_set_user 4.2.0-8.9, percona-pgbackrest 2.58.0-6.5, percona-pgvector_17 0.8.3-1.7, percona-pgvector_17-llvmjit 0.8.3-1.7, percona-postgis35_17 3.5.7-2.7, percona-postgis35_17-client 3.5.7-2.7, percona-postgis35_17-gui 3.5.7-2.7, percona-postgis35_17-llvmjit 3.5.7-2.7, percona-postgis35_17-utils 3.5.7-2.7, percona-postgresql-client-common 290-1.7, percona-postgresql-common 290-1.7, percona-postgresql17 17.10-11.2, percona-postgresql17-contrib 17.10-11.2, percona-postgresql17-libs 17.10-11.2, percona-postgresql17-llvmjit 17.10-11.2, percona-postgresql17-server 17.10-11.2, percona-telemetry-agent 1.0.14-9.4, percona-wal2json17 2.6-7.8, perl-JSON 4.03-2.6, python3-etcd 0.4.5-2.7, python3-ydiff 1.4.2-2.7, python3.12-click 8.1.7-2.7, python3.12-dateutil 2.9.0.post0-3.4, python3.12-dns 1.15.0-2.7, python3.12-etcd 0.4.5-2.7, python3.12-prettytable 3.4.0-2.7, python3.12-psutil 6.1.1-2.7, python3.12-psycopg2 2.9.10-3.18, python3.12-six 1.17.0-2.7, python3.12-wcwidth 0.2.13-2.7 |
| percona-pgbackrest | ppg:17:containers:ubi8 | percona-pgbackrest | 2.58.0 | `2.58.0-2.4` `2.58.0` `latest` | percona-pgbackrest 2.58.0-6.5 |
| percona-pgbouncer | ppg:17:containers:ubi8 | percona-pgbouncer | 1.25.2 | `1.25.2-2.4` `1.25.2` `latest` | c-ares 1.19.1-1.1, percona-pgbouncer 1.25.2-3.8, python3.12-psycopg2 2.9.10-3.18 |
| percona-distribution-postgresql | ppg:17:containers:ubi9 | percona-distribution-postgresql | 17.10-1 | `17.10-1-3.42` `17.10-1` `17.10` `17` | gosu 1.19-6.6, percona-patroni 4.1.3-3.4, percona-patroni-etcd 4.1.3-3.4, percona-pg-telemetry17 1.2.0-6.8, percona-pg_cron_17 1.6.7-6.8, percona-pg_repack17 1.5.3-8.8, percona-pg_stat_monitor17 2.3.2-7.8, percona-pg_tde17 2.2.0-11.3, percona-pgaudit17 17.1-8.9, percona-pgaudit17_set_user 4.2.0-8.8, percona-pgbackrest 2.58.0-6.6, percona-pgvector_17 0.8.3-1.6, percona-pgvector_17-llvmjit 0.8.3-1.6, percona-postgresql-client-common 290-1.8, percona-postgresql-common 290-1.8, percona-postgresql17 17.10-11.2, percona-postgresql17-contrib 17.10-11.2, percona-postgresql17-libs 17.10-11.2, percona-postgresql17-llvmjit 17.10-11.2, percona-postgresql17-server 17.10-11.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json17 2.6-7.7, perl-JSON 4.03-2.4, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-3.14, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-distribution-postgresql-with-postgis | ppg:17:containers:ubi9 | percona-distribution-postgresql-with-postgis | 17.10-1 | `17.10-1-3.58` `17.10-1` `17.10` `17` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.8, flexiblas 3.0.4-2.5, flexiblas-netlib 3.0.4-2.5, flexiblas-netlib64 3.0.4-2.5, flexiblas-openblas-threads 3.0.4-2.5, geos 3.13.1-1.9, gosu 1.19-6.6, lapack 3.9.0-1.8, percona-patroni 4.1.3-3.4, percona-patroni-etcd 4.1.3-3.4, percona-pg-telemetry17 1.2.0-6.8, percona-pg_cron_17 1.6.7-6.8, percona-pg_repack17 1.5.3-8.8, percona-pg_stat_monitor17 2.3.2-7.8, percona-pg_tde17 2.2.0-11.3, percona-pgaudit17 17.1-8.9, percona-pgaudit17_set_user 4.2.0-8.8, percona-pgbackrest 2.58.0-6.6, percona-pgvector_17 0.8.3-1.6, percona-pgvector_17-llvmjit 0.8.3-1.6, percona-postgis35_17 3.5.7-2.9, percona-postgis35_17-client 3.5.7-2.9, percona-postgis35_17-gui 3.5.7-2.9, percona-postgis35_17-llvmjit 3.5.7-2.9, percona-postgis35_17-utils 3.5.7-2.9, percona-postgresql-client-common 290-1.8, percona-postgresql-common 290-1.8, percona-postgresql17 17.10-11.2, percona-postgresql17-contrib 17.10-11.2, percona-postgresql17-libs 17.10-11.2, percona-postgresql17-llvmjit 17.10-11.2, percona-postgresql17-server 17.10-11.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json17 2.6-7.7, perl-JSON 4.03-2.4, proj 9.6.0-2.5, proj-data 9.6.0-2.5, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-3.14, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-pgbackrest | ppg:17:containers:ubi9 | percona-pgbackrest | 2.58.0 | `2.58.0-5.5` `2.58.0` `latest` | percona-pgbackrest 2.58.0-6.6, percona-postgresql17-libs 17.10-11.2 |
| percona-pgbouncer | ppg:17:containers:ubi9 | percona-pgbouncer | 1.25.2 | `1.25.2-5.5` `1.25.2` `latest` | c-ares 1.19.1-1.9, percona-pgbouncer 1.25.2-3.7, percona-postgresql17-libs 17.10-11.2, python3.12-psycopg2 2.9.10-3.14 |
| percona-distribution-postgresql-with-postgis | ppg:17:extras:containers:ubi9 | percona-distribution-postgresql-with-postgis | 17.10-1 | `17.10-1-1.6` `17.10-1` `17.10` `17` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.8, flexiblas 3.0.4-2.5, flexiblas-netlib 3.0.4-2.5, flexiblas-netlib64 3.0.4-2.5, flexiblas-openblas-threads 3.0.4-2.5, geos 3.13.1-1.9, gosu 1.19-6.6, h3 4.5.0-1.1, lapack 3.9.0-1.8, percona-h3-pg_17 4.5.0-1.2, percona-hll_17 2.21-1.2, percona-ip4r_17 2.4.3-1.2, percona-patroni 4.1.3-3.4, percona-patroni-etcd 4.1.3-3.4, percona-pg-telemetry17 1.2.0-6.8, percona-pg_cron_17 1.6.7-6.8, percona-pg_partman_17 5.4.3-1.2, percona-pg_repack17 1.5.3-8.8, percona-pg_similarity_17 pg_similarity_1_0-1.2, percona-pg_stat_monitor17 2.3.2-7.8, percona-pg_tde17 2.2.0-11.3, percona-pgaudit17 17.1-8.9, percona-pgaudit17_set_user 4.2.0-8.8, percona-pgbackrest 2.58.0-6.6, percona-pgrouting_17 4.0.1-1.2, percona-pgvector_17 0.8.3-1.6, percona-pgvector_17-llvmjit 0.8.3-1.6, percona-pgvectorscale_17 0.9.0-2.1, percona-postgis35_17 3.5.7-2.9, percona-postgis35_17-client 3.5.7-2.9, percona-postgis35_17-gui 3.5.7-2.9, percona-postgis35_17-llvmjit 3.5.7-2.9, percona-postgis35_17-utils 3.5.7-2.9, percona-postgresql-client-common 290-1.8, percona-postgresql-common 290-1.8, percona-postgresql-unit_17 7.10-1.1, percona-postgresql17 17.10-1.1, percona-postgresql17-contrib 17.10-1.1, percona-postgresql17-libs 17.10-1.1, percona-postgresql17-llvmjit 17.10-1.1, percona-postgresql17-server 17.10-1.1, percona-postgresql_anonymizer_17 3.1.1-3.1, percona-rum_17 1.3.15-1.1, percona-telemetry-agent 1.0.14-9.5, percona-timescaledb_17 2.28.1-1.1, percona-wal2json17 2.6-7.7, perl-JSON 4.03-2.4, proj 9.6.0-2.5, proj-data 9.6.0-2.5, python3-etcd 0.4.5-2.4, python3-psycopg2 2.9.10-3.14, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-3.14, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |

# Repository Installation Instructions


### Debian_11

**`isv:percona:ppg:17`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Debian_11/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:17.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Debian_11/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_17.gpg > /dev/null
apt update
```


### Debian_13

**`isv:percona:ppg:17`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:17.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_17.gpg > /dev/null
apt update
```


### RockyLinux_10

**`isv:percona:ppg:17`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/RockyLinux_10/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_17.repo << 'EOF'
[isv:percona:ppg:17]
name=isv:percona:ppg:17 - RockyLinux_10
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/RockyLinux_10/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_8

**`isv:percona:ppg:17`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/RockyLinux_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_17.repo << 'EOF'
[isv:percona:ppg:17]
name=isv:percona:ppg:17 - RockyLinux_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/RockyLinux_8/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_9

**`isv:percona:ppg:17`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_17.repo << 'EOF'
[isv:percona:ppg:17]
name=isv:percona:ppg:17 - RockyLinux_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/RockyLinux_9/
enabled=1
gpgcheck=0
EOF
```


### UBI_8

**`isv:percona:ppg:17`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/UBI_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_17.repo << 'EOF'
[isv:percona:ppg:17]
name=isv:percona:ppg:17 - UBI_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/UBI_8/
enabled=1
gpgcheck=0
EOF
```


### UBI_9

**`isv:percona:ppg:17`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/UBI_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_17.repo << 'EOF'
[isv:percona:ppg:17]
name=isv:percona:ppg:17 - UBI_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/UBI_9/
enabled=1
gpgcheck=0
EOF
```

**`isv:percona:ppg:17:extras`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/17:/extras/UBI_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_17_extras.repo << 'EOF'
[isv:percona:ppg:17:extras]
name=isv:percona:ppg:17:extras - UBI_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/17:/extras/UBI_9/
enabled=1
gpgcheck=0
EOF
```


### Ubuntu_24.04

**`isv:percona:ppg:17`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Ubuntu_24.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:17.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Ubuntu_24.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_17.gpg > /dev/null
apt update
```


### Ubuntu_26.04

**`isv:percona:ppg:17`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Ubuntu_26.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:17.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Ubuntu_26.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_17.gpg > /dev/null
apt update
```


### openSUSE_Leap_16

**`isv:percona:ppg:17`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/openSUSE_Leap_16/ \
  isv:percona:ppg:17
zypper --gpg-auto-import-keys refresh
```


### openSUSE_Tumbleweed

**`isv:percona:ppg:17`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/openSUSE_Tumbleweed/ \
  isv:percona:ppg:17
zypper --gpg-auto-import-keys refresh
```


### Container Images

**`isv:percona:ppg:17:containers:ubi8`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi8/images/percona-distribution-postgresql:17.10
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi8/images/percona-distribution-postgresql:17
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi8/images/percona-distribution-postgresql-with-postgis:17.10
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi8/images/percona-distribution-postgresql-with-postgis:17
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi8/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi8/images/percona-pgbouncer:latest
```

**`isv:percona:ppg:17:containers:ubi9`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-distribution-postgresql:17.10
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-distribution-postgresql:17
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-distribution-postgresql-with-postgis:17.10
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-distribution-postgresql-with-postgis:17
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-pgbouncer:latest
```

**`isv:percona:ppg:17:extras:containers:ubi9`**

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/extras/containers/ubi9/images/percona-distribution-postgresql-with-postgis:17.10
docker pull registry.opensuse.org/isv/percona/ppg/17/extras/containers/ubi9/images/percona-distribution-postgresql-with-postgis:17
```

