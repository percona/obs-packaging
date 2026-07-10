## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:staging:15 | 3.5.30-1+5.1 |
| percona-haproxy | ppg:staging:15 | 2.8.23-1+1.1 |
| percona-patroni | ppg:staging:15 | 4.1.3-1+1.2 |
| percona-pg-telemetry | ppg:staging:15 | 1.2.0-1+1.1 |
| percona-pg_cron | ppg:staging:15 | 1.6.7-1+1.1 |
| percona-pg_gather | ppg:staging:15 | 33-1+1.1 |
| percona-pg_repack | ppg:staging:15 | 1.5.3-1+1.1 |
| percona-pg_stat_monitor | ppg:staging:15 | 2.3.2-1+1.1 |
| percona-pgaudit | ppg:staging:15 | 1.6.3-1+1.1 |
| percona-pgaudit_set_user | ppg:staging:15 | 4.2.0-1+1.1 |
| percona-pgbackrest | ppg:staging:15 | 2.58.0-1+1.2 |
| percona-pgbadger | ppg:staging:15 | 13.2-1+1.1 |
| percona-pgbouncer | ppg:staging:15 | 1.25.2-1+1.2 |
| percona-pgpool-II | ppg:staging:15 | 4.7.1-1+1.1 |
| percona-pgvector | ppg:staging:15 | 0.8.3-1+1.1 |
| percona-postgis | ppg:staging:15 | 3.5.7-1+1.1 |
| percona-postgresql | ppg:staging:15 | 15.18-1+1.1 |
| percona-postgresql-common | ppg:staging:15 | 290-1+1.1 |
| percona-ppg-server | ppg:staging:15 | 15.18-1 |
| percona-ppg-server-ha | ppg:staging:15 | 15.18-1 |
| percona-telemetry-agent | ppg:staging:15 | 1.0.14-1+9.1 |
| percona-wal2json | ppg:staging:15 | 2.6-1+1.1 |
| python3-attrs | ppg:staging:15 | 22.1.0-2.3 |
| python3-blessed | ppg:staging:15 | 1.22.0-2.3 |
| python3-boto3 | ppg:staging:15 | 1.38.19-2.3 |
| python3-botocore | ppg:staging:15 | 1.38.19-2.3 |
| python3-click | ppg:staging:15 | 8.1.7-2.3 |
| python3-dateutil | ppg:staging:15 | 2.9.0.post0-3.3 |
| python3-dns | ppg:staging:15 | 1.15.0-2.3 |
| python3-etcd | ppg:staging:15 | 0.4.5-2.3 |
| python3-kazoo | ppg:staging:15 | 2.8.0-2.3 |
| python3-lz4 | ppg:staging:15 | 4.3.3-3.3 |
| python3-prettytable | ppg:staging:15 | 3.4.0-2.3 |
| python3-psutil | ppg:staging:15 | 6.1.1-2.3 |
| python3-psycopg2 | ppg:staging:15 | 2.9.10-1.1 |
| python3-py-consul | ppg:staging:15 | 1.6.0-2.3 |
| python3-pysyncobj | ppg:staging:15 | 0.3.10-1+3.1 |
| python3-six | ppg:staging:15 | 1.17.0-2.3 |
| python3-wcwidth | ppg:staging:15 | 0.2.13-2.3 |
| python3-zstandard | ppg:staging:15 | 0.23.0-2.3 |
| sfcgal | ppg:staging:15 | 2.2.0-4.4 |
| ydiff | ppg:staging:15 | 1.4.2-1+2.1 |

## Container Images

| Package | Project | Image | Version | Tags | Installed packages |
| ------- | ------- | ----- | ------- | ---- | ------------------ |
| percona-distribution-postgresql | ppg:staging:15:containers:ubi8 | percona-distribution-postgresql | 15.18-1 | `15.18-1-1.3` `15.18-1` `15.18` `15` | gosu 1.19-6.10, percona-patroni 4.1.3-1.2, percona-patroni-etcd 4.1.3-1.2, percona-pg-telemetry15 1.2.0-1.2, percona-pg_cron_15 1.6.7-1.2, percona-pg_repack15 1.5.3-1.2, percona-pg_stat_monitor15 2.3.2-1.2, percona-pgaudit15 1.6.3-1.3, percona-pgaudit15_set_user 4.2.0-1.2, percona-pgbackrest 2.58.0-1.2, percona-pgvector_15 0.8.3-1.2, percona-pgvector_15-llvmjit 0.8.3-1.2, percona-postgresql-client-common 290-1.2, percona-postgresql-common 290-1.2, percona-postgresql15 15.18-1.2, percona-postgresql15-contrib 15.18-1.2, percona-postgresql15-libs 15.18-1.2, percona-postgresql15-llvmjit 15.18-1.2, percona-postgresql15-server 15.18-1.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json15 2.6-1.2, perl-JSON 4.03-2.7, python3-etcd 0.4.5-2.8, python3-ydiff 1.4.2-2.8, python3.12-click 8.1.7-2.8, python3.12-dateutil 2.9.0.post0-3.5, python3.12-dns 1.15.0-2.8, python3.12-etcd 0.4.5-2.8, python3.12-prettytable 3.4.0-2.8, python3.12-psutil 6.1.1-2.8, python3.12-psycopg2 2.9.10-1.2, python3.12-six 1.17.0-2.8, python3.12-wcwidth 0.2.13-2.8 |
| percona-distribution-postgresql-with-postgis | ppg:staging:15:containers:ubi8 | percona-distribution-postgresql-with-postgis | 15.18-1 | `15.18-1-1.3` `15.18-1` `15.18` `15` | SFCGAL 2.2.0-4.5, blas 3.9.0-1.8, geos 3.13.1-1.8, gosu 1.19-6.10, lapack 3.9.0-1.8, percona-patroni 4.1.3-1.2, percona-patroni-etcd 4.1.3-1.2, percona-pg-telemetry15 1.2.0-1.2, percona-pg_cron_15 1.6.7-1.2, percona-pg_repack15 1.5.3-1.2, percona-pg_stat_monitor15 2.3.2-1.2, percona-pgaudit15 1.6.3-1.3, percona-pgaudit15_set_user 4.2.0-1.2, percona-pgbackrest 2.58.0-1.2, percona-pgvector_15 0.8.3-1.2, percona-pgvector_15-llvmjit 0.8.3-1.2, percona-postgis35_15 3.5.7-1.2, percona-postgis35_15-client 3.5.7-1.2, percona-postgis35_15-gui 3.5.7-1.2, percona-postgis35_15-llvmjit 3.5.7-1.2, percona-postgis35_15-utils 3.5.7-1.2, percona-postgresql-client-common 290-1.2, percona-postgresql-common 290-1.2, percona-postgresql15 15.18-1.2, percona-postgresql15-contrib 15.18-1.2, percona-postgresql15-libs 15.18-1.2, percona-postgresql15-llvmjit 15.18-1.2, percona-postgresql15-server 15.18-1.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json15 2.6-1.2, perl-JSON 4.03-2.7, python3-etcd 0.4.5-2.8, python3-ydiff 1.4.2-2.8, python3.12-click 8.1.7-2.8, python3.12-dateutil 2.9.0.post0-3.5, python3.12-dns 1.15.0-2.8, python3.12-etcd 0.4.5-2.8, python3.12-prettytable 3.4.0-2.8, python3.12-psutil 6.1.1-2.8, python3.12-psycopg2 2.9.10-1.2, python3.12-six 1.17.0-2.8, python3.12-wcwidth 0.2.13-2.8 |
| percona-pgbackrest | ppg:staging:15:containers:ubi8 | percona-pgbackrest | 2.58.0 | `2.58.0-1.2` `2.58.0` `latest` | percona-pgbackrest 2.58.0-1.2 |
| percona-pgbouncer | ppg:staging:15:containers:ubi8 | percona-pgbouncer | 1.25.2 | `1.25.2-1.3` `1.25.2` `latest` | c-ares 1.19.1-1.1, percona-pgbouncer 1.25.2-1.2, python3.12-psycopg2 2.9.10-1.2 |
| percona-distribution-postgresql | ppg:staging:15:containers:ubi9 | percona-distribution-postgresql | 15.18-1 | `15.18-1-1.1` `15.18-1` `15.18` `15` | gosu 1.19-6.6, percona-patroni 4.1.3-1.1, percona-patroni-etcd 4.1.3-1.1, percona-pg-telemetry15 1.2.0-1.1, percona-pg_cron_15 1.6.7-1.1, percona-pg_repack15 1.5.3-1.1, percona-pg_stat_monitor15 2.3.2-1.1, percona-pgaudit15 1.6.3-1.1, percona-pgaudit15_set_user 4.2.0-1.1, percona-pgbackrest 2.58.0-1.1, percona-pgvector_15 0.8.3-1.1, percona-pgvector_15-llvmjit 0.8.3-1.1, percona-postgresql-client-common 290-1.1, percona-postgresql-common 290-1.1, percona-postgresql15 15.18-1.1, percona-postgresql15-contrib 15.18-1.1, percona-postgresql15-libs 15.18-1.1, percona-postgresql15-llvmjit 15.18-1.1, percona-postgresql15-server 15.18-1.1, percona-telemetry-agent 1.0.14-9.5, percona-wal2json15 2.6-1.1, perl-JSON 4.03-2.4, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-1.1, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-distribution-postgresql-with-postgis | ppg:staging:15:containers:ubi9 | percona-distribution-postgresql-with-postgis | 15.18-1 | `15.18-1-1.1` `15.18-1` `15.18` `15` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.8, flexiblas 3.0.4-2.5, flexiblas-netlib 3.0.4-2.5, flexiblas-netlib64 3.0.4-2.5, flexiblas-openblas-threads 3.0.4-2.5, geos 3.13.1-1.9, gosu 1.19-6.6, lapack 3.9.0-1.8, percona-patroni 4.1.3-1.1, percona-patroni-etcd 4.1.3-1.1, percona-pg-telemetry15 1.2.0-1.1, percona-pg_cron_15 1.6.7-1.1, percona-pg_repack15 1.5.3-1.1, percona-pg_stat_monitor15 2.3.2-1.1, percona-pgaudit15 1.6.3-1.1, percona-pgaudit15_set_user 4.2.0-1.1, percona-pgbackrest 2.58.0-1.1, percona-pgvector_15 0.8.3-1.1, percona-pgvector_15-llvmjit 0.8.3-1.1, percona-postgis35_15 3.5.7-1.1, percona-postgis35_15-client 3.5.7-1.1, percona-postgis35_15-gui 3.5.7-1.1, percona-postgis35_15-llvmjit 3.5.7-1.1, percona-postgis35_15-utils 3.5.7-1.1, percona-postgresql-client-common 290-1.1, percona-postgresql-common 290-1.1, percona-postgresql15 15.18-1.1, percona-postgresql15-contrib 15.18-1.1, percona-postgresql15-libs 15.18-1.1, percona-postgresql15-llvmjit 15.18-1.1, percona-postgresql15-server 15.18-1.1, percona-telemetry-agent 1.0.14-9.5, percona-wal2json15 2.6-1.1, perl-JSON 4.03-2.4, proj 9.6.0-2.5, proj-data 9.6.0-2.5, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-1.1, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-pgbackrest | ppg:staging:15:containers:ubi9 | percona-pgbackrest | 2.58.0 | `2.58.0-1.1` `2.58.0` `latest` | percona-pgbackrest 2.58.0-1.1, percona-postgresql15-libs 15.18-1.1 |
| percona-pgbouncer | ppg:staging:15:containers:ubi9 | percona-pgbouncer | 1.25.2 | `1.25.2-1.2` `1.25.2` `latest` | c-ares 1.19.1-1.9, percona-pgbouncer 1.25.2-1.1, percona-postgresql15-libs 15.18-1.1, python3.12-psycopg2 2.9.10-1.1 |

# Repository Installation Instructions


### Debian_11

**`isv:percona:ppg:staging:15`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Debian_11/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:staging:15.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Debian_11/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_staging_15.gpg > /dev/null
apt update
```


### Debian_13

**`isv:percona:ppg:staging:15`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:staging:15.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_staging_15.gpg > /dev/null
apt update
```


### RockyLinux_10

**`isv:percona:ppg:staging:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/RockyLinux_10/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_staging_15.repo << 'EOF'
[isv:percona:ppg:staging:15]
name=isv:percona:ppg:staging:15 - RockyLinux_10
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/RockyLinux_10/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_8

**`isv:percona:ppg:staging:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/RockyLinux_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_staging_15.repo << 'EOF'
[isv:percona:ppg:staging:15]
name=isv:percona:ppg:staging:15 - RockyLinux_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/RockyLinux_8/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_9

**`isv:percona:ppg:staging:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_staging_15.repo << 'EOF'
[isv:percona:ppg:staging:15]
name=isv:percona:ppg:staging:15 - RockyLinux_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/RockyLinux_9/
enabled=1
gpgcheck=0
EOF
```


### UBI_8

**`isv:percona:ppg:staging:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/UBI_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_staging_15.repo << 'EOF'
[isv:percona:ppg:staging:15]
name=isv:percona:ppg:staging:15 - UBI_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/UBI_8/
enabled=1
gpgcheck=0
EOF
```


### UBI_9

**`isv:percona:ppg:staging:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/UBI_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_staging_15.repo << 'EOF'
[isv:percona:ppg:staging:15]
name=isv:percona:ppg:staging:15 - UBI_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/UBI_9/
enabled=1
gpgcheck=0
EOF
```


### Ubuntu_24.04

**`isv:percona:ppg:staging:15`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Ubuntu_24.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:staging:15.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Ubuntu_24.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_staging_15.gpg > /dev/null
apt update
```


### Ubuntu_26.04

**`isv:percona:ppg:staging:15`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Ubuntu_26.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:staging:15.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/Ubuntu_26.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_staging_15.gpg > /dev/null
apt update
```


### openSUSE_Leap_16

**`isv:percona:ppg:staging:15`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/openSUSE_Leap_16/ \
  isv:percona:ppg:staging:15
zypper --gpg-auto-import-keys refresh
```


### openSUSE_Tumbleweed

**`isv:percona:ppg:staging:15`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/15/openSUSE_Tumbleweed/ \
  isv:percona:ppg:staging:15
zypper --gpg-auto-import-keys refresh
```


### Container Images

**`isv:percona:ppg:staging:15:containers:ubi8`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi8/images/percona-distribution-postgresql:15.18
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi8/images/percona-distribution-postgresql:15
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi8/images/percona-distribution-postgresql-with-postgis:15.18
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi8/images/percona-distribution-postgresql-with-postgis:15
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi8/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi8/images/percona-pgbouncer:latest
```

**`isv:percona:ppg:staging:15:containers:ubi9`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi9/images/percona-distribution-postgresql:15.18
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi9/images/percona-distribution-postgresql:15
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi9/images/percona-distribution-postgresql-with-postgis:15.18
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi9/images/percona-distribution-postgresql-with-postgis:15
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi9/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/staging/15/containers/ubi9/images/percona-pgbouncer:latest
```

