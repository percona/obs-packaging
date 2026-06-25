## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:16 | 3.5.30-1+5.1 |
| percona-haproxy | ppg:16 | 2.8.23-1+1.1 |
| percona-patroni | ppg:16 | 4.1.3-1+1.9 |
| percona-pg-telemetry | ppg:16 | 1.2.0-1+1.9 |
| percona-pg_cron | ppg:16 | 1.6.7-1+1.9 |
| percona-pg_gather | ppg:16 | 33-1+1.1 |
| percona-pg_repack | ppg:16 | 1.5.3-1+1.8 |
| percona-pg_stat_monitor | ppg:16 | 2.3.2-1+1.1 |
| percona-pgaudit | ppg:16 | 16.1-1+1.1 |
| percona-pgaudit_set_user | ppg:16 | 4.2.0-1+1.1 |
| percona-pgbackrest | ppg:16 | 2.58.0-1+1.1 |
| percona-pgbadger | ppg:16 | 13.2-1+1.1 |
| percona-pgbouncer | ppg:16 | 1.25.2-1+1.1 |
| percona-pgpool-II | ppg:16 | 4.7.1-1+1.1 |
| percona-pgvector | ppg:16 | 0.8.3-1+1.1 |
| percona-postgis | ppg:16 | 3.5.7-1+1.1 |
| percona-postgresql | ppg:16 | 16.14-1+11.1 |
| percona-postgresql-common | ppg:16 | 290-1+1.1 |
| percona-ppg-server | ppg:16 | 16.14-1 |
| percona-ppg-server-ha | ppg:16 | 16.14-1 |
| percona-telemetry-agent | ppg:16 | 1.0.14-1+9.1 |
| percona-wal2json | ppg:16 | 2.6-1+1.2 |
| python3-attrs | ppg:16 | 22.1.0-2.2 |
| python3-blessed | ppg:16 | 1.22.0-2.2 |
| python3-boto3 | ppg:16 | 1.38.19-2.2 |
| python3-botocore | ppg:16 | 1.38.19-2.2 |
| python3-click | ppg:16 | 8.1.7-2.2 |
| python3-dateutil | ppg:16 | 2.9.0.post0-3.2 |
| python3-dns | ppg:16 | 1.15.0-2.2 |
| python3-etcd | ppg:16 | 0.4.5-2.2 |
| python3-kazoo | ppg:16 | 2.8.0-2.2 |
| python3-lz4 | ppg:16 | 4.3.3-3.2 |
| python3-prettytable | ppg:16 | 3.4.0-2.2 |
| python3-psutil | ppg:16 | 6.1.1-2.2 |
| python3-psycopg2 | ppg:16 | 2.9.10-1.2 |
| python3-py-consul | ppg:16 | 1.6.0-2.2 |
| python3-pysyncobj | ppg:16 | 0.3.10-1+3.1 |
| python3-six | ppg:16 | 1.17.0-2.2 |
| python3-wcwidth | ppg:16 | 0.2.13-2.2 |
| python3-zstandard | ppg:16 | 0.23.0-2.2 |
| sfcgal | ppg:16 | 2.2.0-4.2 |
| ydiff | ppg:16 | 1.4.2-1+2.1 |

## Container Images

| Package | Project | Image | Version | Tags | Installed packages |
| ------- | ------- | ----- | ------- | ---- | ------------------ |
| percona-distribution-postgresql | ppg:16:containers:ubi8 | percona-distribution-postgresql | 16.14-1 | `16.14-1-1.4` `16.14-1` `16.14` `16` | gosu 1.19-6.5, percona-patroni 4.1.3-1.3, percona-patroni-etcd 4.1.3-1.3, percona-pg-telemetry16 1.2.0-1.10, percona-pg_cron_16 1.6.7-1.10, percona-pg_repack16 1.5.3-1.10, percona-pg_stat_monitor16 2.3.2-1.2, percona-pgaudit16 16.1-1.3, percona-pgaudit16_set_user 4.2.0-1.2, percona-pgbackrest 2.58.0-1.2, percona-pgvector_16 0.8.3-1.1, percona-pgvector_16-llvmjit 0.8.3-1.1, percona-postgresql-client-common 290-1.3, percona-postgresql-common 290-1.3, percona-postgresql16 16.14-11.2, percona-postgresql16-contrib 16.14-11.2, percona-postgresql16-libs 16.14-11.2, percona-postgresql16-llvmjit 16.14-11.2, percona-postgresql16-server 16.14-11.2, percona-telemetry-agent 1.0.14-9.2, percona-wal2json16 2.6-1.2, perl-JSON 4.03-2.4, python3-etcd 0.4.5-2.5, python3-ydiff 1.4.2-2.5, python3.12-click 8.1.7-2.5, python3.12-dateutil 2.9.0.post0-3.2, python3.12-dns 1.15.0-2.5, python3.12-etcd 0.4.5-2.5, python3.12-prettytable 3.4.0-2.5, python3.12-psutil 6.1.1-2.5, python3.12-psycopg2 2.9.10-1.2, python3.12-six 1.17.0-2.5, python3.12-wcwidth 0.2.13-2.5 |
| percona-distribution-postgresql-with-postgis | ppg:16:containers:ubi8 | percona-distribution-postgresql-with-postgis | 16.14-1 | `16.14-1-1.11` `16.14-1` `16.14` `16` | SFCGAL 2.2.0-4.2, blas 3.9.0-1.5, geos 3.13.1-1.5, gosu 1.19-6.5, lapack 3.9.0-1.5, percona-patroni 4.1.3-1.3, percona-patroni-etcd 4.1.3-1.3, percona-pg-telemetry16 1.2.0-1.10, percona-pg_cron_16 1.6.7-1.10, percona-pg_repack16 1.5.3-1.10, percona-pg_stat_monitor16 2.3.2-1.2, percona-pgaudit16 16.1-1.3, percona-pgaudit16_set_user 4.2.0-1.2, percona-pgbackrest 2.58.0-1.2, percona-pgvector_16 0.8.3-1.1, percona-pgvector_16-llvmjit 0.8.3-1.1, percona-postgis35_16 3.5.7-1.1, percona-postgis35_16-client 3.5.7-1.1, percona-postgis35_16-gui 3.5.7-1.1, percona-postgis35_16-llvmjit 3.5.7-1.1, percona-postgis35_16-utils 3.5.7-1.1, percona-postgresql-client-common 290-1.3, percona-postgresql-common 290-1.3, percona-postgresql16 16.14-11.2, percona-postgresql16-contrib 16.14-11.2, percona-postgresql16-libs 16.14-11.2, percona-postgresql16-llvmjit 16.14-11.2, percona-postgresql16-server 16.14-11.2, percona-telemetry-agent 1.0.14-9.2, percona-wal2json16 2.6-1.2, perl-JSON 4.03-2.4, python3-etcd 0.4.5-2.5, python3-ydiff 1.4.2-2.5, python3.12-click 8.1.7-2.5, python3.12-dateutil 2.9.0.post0-3.2, python3.12-dns 1.15.0-2.5, python3.12-etcd 0.4.5-2.5, python3.12-prettytable 3.4.0-2.5, python3.12-psutil 6.1.1-2.5, python3.12-psycopg2 2.9.10-1.2, python3.12-six 1.17.0-2.5, python3.12-wcwidth 0.2.13-2.5 |
| percona-pgbackrest | ppg:16:containers:ubi8 | percona-pgbackrest | 2.58.0 | `2.58.0-1.2` `2.58.0` `latest` | percona-pgbackrest 2.58.0-1.2 |
| percona-pgbouncer | ppg:16:containers:ubi8 | percona-pgbouncer | 1.25.2 | `1.25.2-1.3` `1.25.2` `latest` | c-ares 1.19.1-1.1, percona-pgbouncer 1.25.2-1.2, python3.12-psycopg2 2.9.10-1.2 |
| percona-distribution-postgresql | ppg:16:containers:ubi9 | percona-distribution-postgresql | 16.14-1 | `16.14-1-1.7` `16.14-1` `16.14` `16` | gosu 1.19-6.3, percona-patroni 4.1.3-1.1, percona-patroni-etcd 4.1.3-1.1, percona-pg-telemetry16 1.2.0-1.9, percona-pg_cron_16 1.6.7-1.9, percona-pg_repack16 1.5.3-1.9, percona-pg_stat_monitor16 2.3.2-1.2, percona-pgaudit16 16.1-1.3, percona-pgaudit16_set_user 4.2.0-1.2, percona-pgbackrest 2.58.0-1.2, percona-pgvector_16 0.8.3-1.1, percona-pgvector_16-llvmjit 0.8.3-1.1, percona-postgresql-client-common 290-1.1, percona-postgresql-common 290-1.1, percona-postgresql16 16.14-11.2, percona-postgresql16-contrib 16.14-11.2, percona-postgresql16-libs 16.14-11.2, percona-postgresql16-llvmjit 16.14-11.2, percona-postgresql16-server 16.14-11.2, percona-telemetry-agent 1.0.14-9.2, percona-wal2json16 2.6-1.2, perl-JSON 4.03-2.2, python3-etcd 0.4.5-2.2, python3-ydiff 1.4.2-2.2, python3.12-click 8.1.7-2.2, python3.12-dateutil 2.9.0.post0-3.1, python3.12-dns 1.15.0-2.2, python3.12-etcd 0.4.5-2.2, python3.12-prettytable 3.4.0-2.2, python3.12-psutil 6.1.1-2.2, python3.12-psycopg2 2.9.10-1.2, python3.12-six 1.17.0-2.2, python3.12-wcwidth 0.2.13-2.2 |
| percona-distribution-postgresql-with-postgis | ppg:16:containers:ubi9 | percona-distribution-postgresql-with-postgis | 16.14-1 | `16.14-1-1.11` `16.14-1` `16.14` `16` | SFCGAL 2.2.0-4.2, blas 3.9.0-1.6, flexiblas 3.0.4-2.3, flexiblas-netlib 3.0.4-2.3, flexiblas-netlib64 3.0.4-2.3, flexiblas-openblas-threads 3.0.4-2.3, geos 3.13.1-1.7, gosu 1.19-6.3, lapack 3.9.0-1.6, percona-patroni 4.1.3-1.1, percona-patroni-etcd 4.1.3-1.1, percona-pg-telemetry16 1.2.0-1.9, percona-pg_cron_16 1.6.7-1.9, percona-pg_repack16 1.5.3-1.9, percona-pg_stat_monitor16 2.3.2-1.2, percona-pgaudit16 16.1-1.3, percona-pgaudit16_set_user 4.2.0-1.2, percona-pgbackrest 2.58.0-1.2, percona-pgvector_16 0.8.3-1.1, percona-pgvector_16-llvmjit 0.8.3-1.1, percona-postgis35_16 3.5.7-1.1, percona-postgis35_16-client 3.5.7-1.1, percona-postgis35_16-gui 3.5.7-1.1, percona-postgis35_16-llvmjit 3.5.7-1.1, percona-postgis35_16-utils 3.5.7-1.1, percona-postgresql-client-common 290-1.1, percona-postgresql-common 290-1.1, percona-postgresql16 16.14-11.2, percona-postgresql16-contrib 16.14-11.2, percona-postgresql16-libs 16.14-11.2, percona-postgresql16-llvmjit 16.14-11.2, percona-postgresql16-server 16.14-11.2, percona-telemetry-agent 1.0.14-9.2, percona-wal2json16 2.6-1.2, perl-JSON 4.03-2.2, proj 9.6.0-2.3, proj-data 9.6.0-2.3, python3-etcd 0.4.5-2.2, python3-ydiff 1.4.2-2.2, python3.12-click 8.1.7-2.2, python3.12-dateutil 2.9.0.post0-3.1, python3.12-dns 1.15.0-2.2, python3.12-etcd 0.4.5-2.2, python3.12-prettytable 3.4.0-2.2, python3.12-psutil 6.1.1-2.2, python3.12-psycopg2 2.9.10-1.2, python3.12-six 1.17.0-2.2, python3.12-wcwidth 0.2.13-2.2 |
| percona-pgbackrest | ppg:16:containers:ubi9 | percona-pgbackrest | 2.58.0 | `2.58.0-1.6` `2.58.0` `latest` | percona-pgbackrest 2.58.0-1.2, percona-postgresql16-libs 16.14-11.2 |
| percona-pgbouncer | ppg:16:containers:ubi9 | percona-pgbouncer | 1.25.2 | `1.25.2-1.7` `1.25.2` `latest` | c-ares 1.19.1-1.7, percona-pgbouncer 1.25.2-1.2, percona-postgresql16-libs 16.14-11.2, python3.12-psycopg2 2.9.10-1.2 |

# Repository Installation Instructions


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

