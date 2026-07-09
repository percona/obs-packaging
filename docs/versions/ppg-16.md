## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:16 | 3.5.30-1+5.1 |
| h3 | ppg:16:extras | 4.5.0-1.1 |
| percona-h3-pg | ppg:16:extras | 4.5.0-1.1 |
| percona-hll | ppg:16:extras | 2.21-1.2 |
| percona-ip4r | ppg:16:extras | 2.4.3-1.2 |
| percona-pg_partman | ppg:16:extras | 5.4.3-1.2 |
| percona-pg_similarity | ppg:16:extras | pg_similarity_1_0-1.2 |
| percona-pgrouting | ppg:16:extras | 4.0.1-1.2 |
| percona-pgvectorscale | ppg:16:extras | 0.9.0-2.1 |
| percona-postgresql | ppg:16:extras | 16.14-1.1 |
| percona-postgresql-unit | ppg:16:extras | 7.10-1.1 |
| percona-postgresql_anonymizer | ppg:16:extras | 3.1.1-3.1 |
| percona-rum | ppg:16:extras | 1.3.15-1.1 |
| percona-timescaledb | ppg:16:extras | 2.28.1-1.1 |
| percona-haproxy | ppg:16 | 2.8.23-1+1.1 |
| percona-patroni | ppg:16 | 4.1.3-1+1.4 |
| percona-pg-telemetry | ppg:16 | 1.2.0-1+1.3 |
| percona-pg_cron | ppg:16 | 1.6.7-1+1.3 |
| percona-pg_gather | ppg:16 | 33-1+1.1 |
| percona-pg_repack | ppg:16 | 1.5.3-1+1.3 |
| percona-pg_stat_monitor | ppg:16 | 2.3.2-1+1.3 |
| percona-pgaudit | ppg:16 | 16.1-1+1.3 |
| percona-pgaudit_set_user | ppg:16 | 4.2.0-1+1.3 |
| percona-pgbackrest | ppg:16 | 2.58.0-1+2.4 |
| percona-pgbadger | ppg:16 | 13.2-1+1.1 |
| percona-pgbouncer | ppg:16 | 1.25.2-1+1.4 |
| percona-pgpool-II | ppg:16 | 4.7.1-1+1.3 |
| percona-pgvector | ppg:16 | 0.8.3-1+1.3 |
| percona-postgis | ppg:16 | 3.5.7-1+2.3 |
| percona-postgresql | ppg:16 | 16.14-1+14.1 |
| percona-postgresql-common | ppg:16 | 290-1+1.1 |
| percona-ppg-server | ppg:16 | 16.14-1 |
| percona-ppg-server-ha | ppg:16 | 16.14-1 |
| percona-telemetry-agent | ppg:16 | 1.0.14-1+9.1 |
| percona-wal2json | ppg:16 | 2.6-1+1.3 |
| python3-attrs | ppg:16 | 22.1.0-2.3 |
| python3-blessed | ppg:16 | 1.22.0-2.3 |
| python3-boto3 | ppg:16 | 1.38.19-2.3 |
| python3-botocore | ppg:16 | 1.38.19-2.3 |
| python3-click | ppg:16 | 8.1.7-2.3 |
| python3-dateutil | ppg:16 | 2.9.0.post0-3.3 |
| python3-dns | ppg:16 | 1.15.0-2.3 |
| python3-etcd | ppg:16 | 0.4.5-2.3 |
| python3-kazoo | ppg:16 | 2.8.0-2.3 |
| python3-lz4 | ppg:16 | 4.3.3-3.3 |
| python3-prettytable | ppg:16 | 3.4.0-2.3 |
| python3-psutil | ppg:16 | 6.1.1-2.3 |
| python3-psycopg2 | ppg:16 | 2.9.10-1.7 |
| python3-py-consul | ppg:16 | 1.6.0-2.3 |
| python3-pysyncobj | ppg:16 | 0.3.10-1+3.1 |
| python3-six | ppg:16 | 1.17.0-2.3 |
| python3-wcwidth | ppg:16 | 0.2.13-2.3 |
| python3-zstandard | ppg:16 | 0.23.0-2.3 |
| sfcgal | ppg:16 | 2.2.0-4.4 |
| ydiff | ppg:16 | 1.4.2-1+2.1 |

## Container Images

| Package | Project | Image | Version | Tags | Installed packages |
| ------- | ------- | ----- | ------- | ---- | ------------------ |
| percona-distribution-postgresql | ppg:16:containers:ubi8 | percona-distribution-postgresql | 16.14-1 | `16.14-1-1.12` `16.14-1` `16.14` `16` | gosu 1.19-6.8, percona-patroni 4.1.3-1.5, percona-patroni-etcd 4.1.3-1.5, percona-pg-telemetry16 1.2.0-1.16, percona-pg_cron_16 1.6.7-1.16, percona-pg_repack16 1.5.3-1.16, percona-pg_stat_monitor16 2.3.2-1.8, percona-pgaudit16 16.1-1.9, percona-pgaudit16_set_user 4.2.0-1.8, percona-pgbackrest 2.58.0-2.5, percona-pgvector_16 0.8.3-1.7, percona-pgvector_16-llvmjit 0.8.3-1.7, percona-postgresql-client-common 290-1.5, percona-postgresql-common 290-1.5, percona-postgresql16 16.14-14.2, percona-postgresql16-contrib 16.14-14.2, percona-postgresql16-libs 16.14-14.2, percona-postgresql16-llvmjit 16.14-14.2, percona-postgresql16-server 16.14-14.2, percona-telemetry-agent 1.0.14-9.4, percona-wal2json16 2.6-1.8, perl-JSON 4.03-2.6, python3-etcd 0.4.5-2.7, python3-ydiff 1.4.2-2.7, python3.12-click 8.1.7-2.7, python3.12-dateutil 2.9.0.post0-3.4, python3.12-dns 1.15.0-2.7, python3.12-etcd 0.4.5-2.7, python3.12-prettytable 3.4.0-2.7, python3.12-psutil 6.1.1-2.7, python3.12-psycopg2 2.9.10-1.8, python3.12-six 1.17.0-2.7, python3.12-wcwidth 0.2.13-2.7 |
| percona-distribution-postgresql-with-postgis | ppg:16:containers:ubi8 | percona-distribution-postgresql-with-postgis | 16.14-1 | `16.14-1-1.27` `16.14-1` `16.14` `16` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.7, geos 3.13.1-1.7, gosu 1.19-6.8, lapack 3.9.0-1.7, percona-patroni 4.1.3-1.5, percona-patroni-etcd 4.1.3-1.5, percona-pg-telemetry16 1.2.0-1.16, percona-pg_cron_16 1.6.7-1.16, percona-pg_repack16 1.5.3-1.16, percona-pg_stat_monitor16 2.3.2-1.8, percona-pgaudit16 16.1-1.9, percona-pgaudit16_set_user 4.2.0-1.8, percona-pgbackrest 2.58.0-2.5, percona-pgvector_16 0.8.3-1.7, percona-pgvector_16-llvmjit 0.8.3-1.7, percona-postgis35_16 3.5.7-2.7, percona-postgis35_16-client 3.5.7-2.7, percona-postgis35_16-gui 3.5.7-2.7, percona-postgis35_16-llvmjit 3.5.7-2.7, percona-postgis35_16-utils 3.5.7-2.7, percona-postgresql-client-common 290-1.5, percona-postgresql-common 290-1.5, percona-postgresql16 16.14-14.2, percona-postgresql16-contrib 16.14-14.2, percona-postgresql16-libs 16.14-14.2, percona-postgresql16-llvmjit 16.14-14.2, percona-postgresql16-server 16.14-14.2, percona-telemetry-agent 1.0.14-9.4, percona-wal2json16 2.6-1.8, perl-JSON 4.03-2.6, python3-etcd 0.4.5-2.7, python3-ydiff 1.4.2-2.7, python3.12-click 8.1.7-2.7, python3.12-dateutil 2.9.0.post0-3.4, python3.12-dns 1.15.0-2.7, python3.12-etcd 0.4.5-2.7, python3.12-prettytable 3.4.0-2.7, python3.12-psutil 6.1.1-2.7, python3.12-psycopg2 2.9.10-1.8, python3.12-six 1.17.0-2.7, python3.12-wcwidth 0.2.13-2.7 |
| percona-pgbackrest | ppg:16:containers:ubi8 | percona-pgbackrest | 2.58.0 | `2.58.0-2.4` `2.58.0` `latest` | percona-pgbackrest 2.58.0-2.5 |
| percona-pgbouncer | ppg:16:containers:ubi8 | percona-pgbouncer | 1.25.2 | `1.25.2-2.4` `1.25.2` `latest` | c-ares 1.19.1-1.1, percona-pgbouncer 1.25.2-1.4, python3.12-psycopg2 2.9.10-1.8 |
| percona-distribution-postgresql | ppg:16:containers:ubi9 | percona-distribution-postgresql | 16.14-1 | `16.14-1-1.24` `16.14-1` `16.14` `16` | gosu 1.19-6.6, percona-patroni 4.1.3-1.3, percona-patroni-etcd 4.1.3-1.3, percona-pg-telemetry16 1.2.0-1.14, percona-pg_cron_16 1.6.7-1.14, percona-pg_repack16 1.5.3-1.14, percona-pg_stat_monitor16 2.3.2-1.7, percona-pgaudit16 16.1-1.10, percona-pgaudit16_set_user 4.2.0-1.7, percona-pgbackrest 2.58.0-2.6, percona-pgvector_16 0.8.3-1.6, percona-pgvector_16-llvmjit 0.8.3-1.6, percona-postgresql-client-common 290-1.3, percona-postgresql-common 290-1.3, percona-postgresql16 16.14-14.2, percona-postgresql16-contrib 16.14-14.2, percona-postgresql16-libs 16.14-14.2, percona-postgresql16-llvmjit 16.14-14.2, percona-postgresql16-server 16.14-14.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json16 2.6-1.7, perl-JSON 4.03-2.4, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-1.7, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-distribution-postgresql-with-postgis | ppg:16:containers:ubi9 | percona-distribution-postgresql-with-postgis | 16.14-1 | `16.14-1-1.35` `16.14-1` `16.14` `16` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.8, flexiblas 3.0.4-2.5, flexiblas-netlib 3.0.4-2.5, flexiblas-netlib64 3.0.4-2.5, flexiblas-openblas-threads 3.0.4-2.5, geos 3.13.1-1.9, gosu 1.19-6.6, lapack 3.9.0-1.8, percona-patroni 4.1.3-1.3, percona-patroni-etcd 4.1.3-1.3, percona-pg-telemetry16 1.2.0-1.14, percona-pg_cron_16 1.6.7-1.14, percona-pg_repack16 1.5.3-1.14, percona-pg_stat_monitor16 2.3.2-1.7, percona-pgaudit16 16.1-1.10, percona-pgaudit16_set_user 4.2.0-1.7, percona-pgbackrest 2.58.0-2.6, percona-pgvector_16 0.8.3-1.6, percona-pgvector_16-llvmjit 0.8.3-1.6, percona-postgis35_16 3.5.7-2.9, percona-postgis35_16-client 3.5.7-2.9, percona-postgis35_16-gui 3.5.7-2.9, percona-postgis35_16-llvmjit 3.5.7-2.9, percona-postgis35_16-utils 3.5.7-2.9, percona-postgresql-client-common 290-1.3, percona-postgresql-common 290-1.3, percona-postgresql16 16.14-14.2, percona-postgresql16-contrib 16.14-14.2, percona-postgresql16-libs 16.14-14.2, percona-postgresql16-llvmjit 16.14-14.2, percona-postgresql16-server 16.14-14.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json16 2.6-1.7, perl-JSON 4.03-2.4, proj 9.6.0-2.5, proj-data 9.6.0-2.5, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-1.7, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-pgbackrest | ppg:16:containers:ubi9 | percona-pgbackrest | 2.58.0 | `2.58.0-2.5` `2.58.0` `latest` | percona-pgbackrest 2.58.0-2.6, percona-postgresql16-libs 16.14-14.2 |
| percona-pgbouncer | ppg:16:containers:ubi9 | percona-pgbouncer | 1.25.2 | `1.25.2-2.6` `1.25.2` `latest` | c-ares 1.19.1-1.9, percona-pgbouncer 1.25.2-1.6, percona-postgresql16-libs 16.14-14.2, python3.12-psycopg2 2.9.10-1.7 |
| percona-distribution-postgresql-with-postgis | ppg:16:extras:containers:ubi9 | percona-distribution-postgresql-with-postgis | 16.14-1 | `16.14-1-1.6` `16.14-1` `16.14` `16` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.8, flexiblas 3.0.4-2.5, flexiblas-netlib 3.0.4-2.5, flexiblas-netlib64 3.0.4-2.5, flexiblas-openblas-threads 3.0.4-2.5, geos 3.13.1-1.9, gosu 1.19-6.6, h3 4.5.0-1.1, lapack 3.9.0-1.8, percona-h3-pg_16 4.5.0-1.1, percona-hll_16 2.21-1.2, percona-ip4r_16 2.4.3-1.2, percona-patroni 4.1.3-1.3, percona-patroni-etcd 4.1.3-1.3, percona-pg_cron_16 1.6.7-1.14, percona-pg_partman_16 5.4.3-1.2, percona-pg_repack16 1.5.3-1.14, percona-pg_similarity_16 pg_similarity_1_0-1.2, percona-pg_stat_monitor16 2.3.2-1.7, percona-pgaudit16 16.1-1.10, percona-pgaudit16_set_user 4.2.0-1.7, percona-pgbackrest 2.58.0-2.6, percona-pgrouting_16 4.0.1-1.2, percona-pgvector_16 0.8.3-1.6, percona-pgvector_16-llvmjit 0.8.3-1.6, percona-pgvectorscale_16 0.9.0-2.1, percona-postgis35_16 3.5.7-2.9, percona-postgis35_16-client 3.5.7-2.9, percona-postgis35_16-gui 3.5.7-2.9, percona-postgis35_16-llvmjit 3.5.7-2.9, percona-postgis35_16-utils 3.5.7-2.9, percona-postgresql-client-common 290-1.3, percona-postgresql-common 290-1.3, percona-postgresql-unit_16 7.10-1.1, percona-postgresql16 16.14-1.1, percona-postgresql16-contrib 16.14-1.1, percona-postgresql16-libs 16.14-1.1, percona-postgresql16-llvmjit 16.14-1.1, percona-postgresql16-server 16.14-1.1, percona-postgresql_anonymizer_16 3.1.1-3.1, percona-rum_16 1.3.15-1.1, percona-timescaledb_16 2.28.1-1.1, percona-wal2json16 2.6-1.7, perl-JSON 4.03-2.4, proj 9.6.0-2.5, proj-data 9.6.0-2.5, python3-etcd 0.4.5-2.4, python3-psycopg2 2.9.10-1.7, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-1.7, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |

# Repository Installation Instructions


### Debian_11

**`isv:percona:ppg:16`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Debian_11/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:16.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Debian_11/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_16.gpg > /dev/null
apt update
```


### Debian_13

**`isv:percona:ppg:16`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:16.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_16.gpg > /dev/null
apt update
```


### RockyLinux_10

**`isv:percona:ppg:16`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/RockyLinux_10/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_16.repo << 'EOF'
[isv:percona:ppg:16]
name=isv:percona:ppg:16 - RockyLinux_10
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/RockyLinux_10/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_8

**`isv:percona:ppg:16`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/RockyLinux_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_16.repo << 'EOF'
[isv:percona:ppg:16]
name=isv:percona:ppg:16 - RockyLinux_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/RockyLinux_8/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_9

**`isv:percona:ppg:16`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_16.repo << 'EOF'
[isv:percona:ppg:16]
name=isv:percona:ppg:16 - RockyLinux_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/RockyLinux_9/
enabled=1
gpgcheck=0
EOF
```


### UBI_8

**`isv:percona:ppg:16`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/UBI_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_16.repo << 'EOF'
[isv:percona:ppg:16]
name=isv:percona:ppg:16 - UBI_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/UBI_8/
enabled=1
gpgcheck=0
EOF
```


### UBI_9

**`isv:percona:ppg:16`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/UBI_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_16.repo << 'EOF'
[isv:percona:ppg:16]
name=isv:percona:ppg:16 - UBI_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/UBI_9/
enabled=1
gpgcheck=0
EOF
```

**`isv:percona:ppg:16:extras`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/16:/extras/UBI_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_16_extras.repo << 'EOF'
[isv:percona:ppg:16:extras]
name=isv:percona:ppg:16:extras - UBI_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/16:/extras/UBI_9/
enabled=1
gpgcheck=0
EOF
```


### Ubuntu_24.04

**`isv:percona:ppg:16`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Ubuntu_24.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:16.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Ubuntu_24.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_16.gpg > /dev/null
apt update
```


### Ubuntu_26.04

**`isv:percona:ppg:16`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Ubuntu_26.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:16.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/Ubuntu_26.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_16.gpg > /dev/null
apt update
```


### openSUSE_Leap_16

**`isv:percona:ppg:16`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/openSUSE_Leap_16/ \
  isv:percona:ppg:16
zypper --gpg-auto-import-keys refresh
```


### openSUSE_Tumbleweed

**`isv:percona:ppg:16`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/16/openSUSE_Tumbleweed/ \
  isv:percona:ppg:16
zypper --gpg-auto-import-keys refresh
```


### Container Images

**`isv:percona:ppg:16:containers:ubi8`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi8/images/percona-distribution-postgresql:16.14
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi8/images/percona-distribution-postgresql:16
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi8/images/percona-distribution-postgresql-with-postgis:16.14
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi8/images/percona-distribution-postgresql-with-postgis:16
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi8/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi8/images/percona-pgbouncer:latest
```

**`isv:percona:ppg:16:containers:ubi9`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi9/images/percona-distribution-postgresql:16.14
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi9/images/percona-distribution-postgresql:16
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi9/images/percona-distribution-postgresql-with-postgis:16.14
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi9/images/percona-distribution-postgresql-with-postgis:16
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi9/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/containers/ubi9/images/percona-pgbouncer:latest
```

**`isv:percona:ppg:16:extras:containers:ubi9`**

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/16/extras/containers/ubi9/images/percona-distribution-postgresql-with-postgis:16.14
docker pull registry.opensuse.org/isv/percona/ppg/16/extras/containers/ubi9/images/percona-distribution-postgresql-with-postgis:16
```

