## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:releases:18 | 3.5.30-2.1 |
| percona-haproxy | ppg:releases:18 | 2.8.23-1.1 |
| percona-patroni | ppg:releases:18 | 4.1.3-1.1 |
| percona-pg_cron | ppg:releases:18 | 1.6.7-4.1 |
| percona-pg_gather | ppg:releases:18 | 33-1.1 |
| percona-pg_oidc_validator | ppg:releases:18 | 1.0-3.1 |
| percona-pg_repack | ppg:releases:18 | 1.5.3-4.2 |
| percona-pg_stat_monitor | ppg:releases:18 | 2.3.2-5.1 |
| percona-pg_tde | ppg:releases:18 | 2.2.0-2.1 |
| percona-pgaudit | ppg:releases:18 | 18.0-4.1 |
| percona-pgaudit_set_user | ppg:releases:18 | 4.2.0-4.1 |
| percona-pgbackrest | ppg:releases:18 | 2.58.0-3.1 |
| percona-pgbadger | ppg:releases:18 | 13.2-2.1 |
| percona-pgbouncer | ppg:releases:18 | 1.25.2-1.1 |
| percona-pgpool-II | ppg:releases:18 | 4.7.1-1.1 |
| percona-pgvector | ppg:releases:18 | 0.8.2-3.1 |
| percona-postgis | ppg:releases:18 | 3.5.6-1.1 |
| percona-postgresql | ppg:releases:18 | 18.4-1.2 |
| percona-postgresql-common | ppg:releases:18 | 290-1.1 |
| percona-postgresql18 | ppg:releases:18 | 18.3-4.9 |
| percona-ppg-server | ppg:releases:18 | 18.4-1.1 |
| percona-ppg-server-18 | ppg:releases:18 | 18.3-1.1 |
| percona-ppg-server-ha | ppg:releases:18 | 18.4-1.1 |
| percona-ppg-server-ha-18 | ppg:releases:18 | 18.3-1.1 |
| percona-wal2json | ppg:releases:18 | 2.6-4.1 |
| python3-attrs | ppg:releases:18 | 22.1.0-1.1 |
| python3-blessed | ppg:releases:18 | 1.22.0-1.1 |
| python3-boto3 | ppg:releases:18 | 1.38.19-1.1 |
| python3-botocore | ppg:releases:18 | 1.38.19-1.1 |
| python3-click | ppg:releases:18 | 8.1.7-1.1 |
| python3-dateutil | ppg:releases:18 | 2.9.0.post0-1.1 |
| python3-dns | ppg:releases:18 | 1.15.0-1.1 |
| python3-etcd | ppg:releases:18 | 0.4.5-1.1 |
| python3-kazoo | ppg:releases:18 | 2.8.0-1.1 |
| python3-lz4 | ppg:releases:18 | 4.3.3-1.2 |
| python3-prettytable | ppg:releases:18 | 3.4.0-1.1 |
| python3-psutil | ppg:releases:18 | 6.1.1-1.2 |
| python3-psycopg2 | ppg:releases:18 | 2.9.10-1.3 |
| python3-py-consul | ppg:releases:18 | 1.6.0-1.1 |
| python3-pysyncobj | ppg:releases:18 | 0.3.10-1.1 |
| python3-six | ppg:releases:18 | 1.17.0-1.1 |
| python3-wcwidth | ppg:releases:18 | 0.2.13-1.1 |
| python3-zstandard | ppg:releases:18 | 0.23.0-1.2 |
| sfcgal | ppg:releases:18 | 2.2.0-2.3 |
| ydiff | ppg:releases:18 | 1.4.2-1.3 |
| gosu | ppg:releases:18:containers:ubi9 | (none) |

## Container Images

| Package | Project | Image | Version | Tags | Installed packages |
| ------- | ------- | ----- | ------- | ---- | ------------------ |
| percona-distribution-postgresql | ppg:releases:18:containers:ubi9 | percona-distribution-postgresql | 18.4-1 | `18.4-1-1.1` `18.4-1` `18.4` `18` | gosu 1.19-3.1, percona-patroni 4.1.3-1.1, percona-patroni-etcd 4.1.3-1.1, percona-pg_cron_18 1.6.7-4.1, percona-pg_oidc_validator18 1.0-3.1, percona-pg_repack18 1.5.3-4.2, percona-pg_stat_monitor18 2.3.2-5.1, percona-pg_tde18 2.2.0-2.1, percona-pgaudit18 18.0-4.1, percona-pgaudit18_set_user 4.2.0-4.1, percona-pgbackrest 2.58.0-3.1, percona-pgvector_18 0.8.2-3.1, percona-pgvector_18-llvmjit 0.8.2-3.1, percona-postgresql-client-common 290-1.1, percona-postgresql-common 290-1.1, percona-postgresql18 18.4-1.1, percona-postgresql18-contrib 18.4-1.1, percona-postgresql18-libs 18.4-1.1, percona-postgresql18-llvmjit 18.4-1.1, percona-postgresql18-server 18.4-1.1, percona-wal2json18 2.6-4.1, python3-etcd 0.4.5-1.7, python3-ydiff 1.4.2-1.7, python3.12-click 8.1.7-1.7, python3.12-dateutil 2.9.0.post0-1.7, python3.12-dns 1.15.0-1.7, python3.12-etcd 0.4.5-1.7, python3.12-prettytable 3.4.0-1.7, python3.12-psutil 6.1.1-1.7, python3.12-psycopg2 2.9.10-1.11, python3.12-six 1.17.0-1.7, python3.12-wcwidth 0.2.13-1.7 |
| percona-distribution-postgresql-upgrade | ppg:releases:18:containers:ubi9 | percona-distribution-postgresql-upgrade | 18.4-1 | `18.4-17-1-1.3` `18.4-17-1` `18.4-17` `18-17` | SFCGAL 2.2.0-2.4, percona-pg-telemetry17 1.2.0-4.6, percona-pg_cron_17 1.6.7-2.2, percona-pg_cron_18 1.6.7-4.1, percona-pg_oidc_validator18 1.0-3.1, percona-pg_repack17 1.5.3-5.2, percona-pg_repack18 1.5.3-4.2, percona-pg_stat_monitor17 2.3.2-5.6, percona-pg_stat_monitor18 2.3.2-5.1, percona-pg_tde17 2.2.0-3.1, percona-pg_tde18 2.2.0-2.1, percona-pgaudit17 17.1-5.4, percona-pgaudit17_set_user 4.2.0-5.2, percona-pgaudit18 18.0-4.1, percona-pgaudit18_set_user 4.2.0-4.1, percona-pgvector_17 0.8.2-4.2, percona-pgvector_17-llvmjit 0.8.2-4.2, percona-pgvector_18 0.8.2-3.1, percona-pgvector_18-llvmjit 0.8.2-3.1, percona-postgis35_17 3.5.6-1.3, percona-postgis35_17-client 3.5.6-1.3, percona-postgis35_17-gui 3.5.6-1.3, percona-postgis35_17-llvmjit 3.5.6-1.3, percona-postgis35_17-utils 3.5.6-1.3, percona-postgis35_18 3.5.6-1.2, percona-postgis35_18-client 3.5.6-1.2, percona-postgis35_18-gui 3.5.6-1.2, percona-postgis35_18-llvmjit 3.5.6-1.2, percona-postgis35_18-utils 3.5.6-1.2, percona-postgresql-client-common 290-1.1, percona-postgresql-common 290-1.1, percona-postgresql17 17.10-1.1, percona-postgresql17-contrib 17.10-1.1, percona-postgresql17-libs 17.10-1.1, percona-postgresql17-llvmjit 17.10-1.1, percona-postgresql17-server 17.10-1.1, percona-postgresql18 18.4-1.1, percona-postgresql18-contrib 18.4-1.1, percona-postgresql18-libs 18.4-1.1, percona-postgresql18-llvmjit 18.4-1.1, percona-postgresql18-server 18.4-1.1, percona-telemetry-agent 1.0.13-1.1, percona-wal2json17 2.6-5.1, percona-wal2json18 2.6-4.1 |
| percona-distribution-postgresql-with-postgis | ppg:releases:18:containers:ubi9 | percona-distribution-postgresql-with-postgis | 18.4-1 | `18.4-1-1.3` `18.4-1` `18.4` `18` | SFCGAL 2.2.0-2.4, gosu 1.19-3.1, percona-patroni 4.1.3-1.1, percona-patroni-etcd 4.1.3-1.1, percona-pg_cron_18 1.6.7-4.1, percona-pg_oidc_validator18 1.0-3.1, percona-pg_repack18 1.5.3-4.2, percona-pg_stat_monitor18 2.3.2-5.1, percona-pg_tde18 2.2.0-2.1, percona-pgaudit18 18.0-4.1, percona-pgaudit18_set_user 4.2.0-4.1, percona-pgbackrest 2.58.0-3.1, percona-pgvector_18 0.8.2-3.1, percona-pgvector_18-llvmjit 0.8.2-3.1, percona-postgis35_18 3.5.6-1.2, percona-postgis35_18-client 3.5.6-1.2, percona-postgis35_18-gui 3.5.6-1.2, percona-postgis35_18-llvmjit 3.5.6-1.2, percona-postgis35_18-utils 3.5.6-1.2, percona-postgresql-client-common 290-1.1, percona-postgresql-common 290-1.1, percona-postgresql18 18.4-1.1, percona-postgresql18-contrib 18.4-1.1, percona-postgresql18-libs 18.4-1.1, percona-postgresql18-llvmjit 18.4-1.1, percona-postgresql18-server 18.4-1.1, percona-wal2json18 2.6-4.1, python3-etcd 0.4.5-1.7, python3-ydiff 1.4.2-1.7, python3.12-click 8.1.7-1.7, python3.12-dateutil 2.9.0.post0-1.7, python3.12-dns 1.15.0-1.7, python3.12-etcd 0.4.5-1.7, python3.12-prettytable 3.4.0-1.7, python3.12-psutil 6.1.1-1.7, python3.12-psycopg2 2.9.10-1.11, python3.12-six 1.17.0-1.7, python3.12-wcwidth 0.2.13-1.7 |
| percona-pgbackrest | ppg:releases:18:containers:ubi9 | percona-pgbackrest | 2.58.0 | `2.58.0-4.3` `2.58.0` `latest` | percona-pgbackrest 2.58.0-3.1, percona-postgresql18-libs 18.4-1.1 |
| percona-pgbouncer | ppg:releases:18:containers:ubi9 | percona-pgbouncer | 1.25.2 | `1.25.2-1.2` `1.25.2` `latest` | percona-pgbouncer 1.25.2-1.1, percona-postgresql18-libs 18.4-1.1, python3-psycopg2 2.9.10-1.11, python3.12-psycopg2 2.9.10-1.11 |

# Repository Installation Instructions


### Debian_13

**`isv:percona:ppg:releases:18`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:releases:18.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_releases_18.gpg > /dev/null
apt update
```


### RockyLinux_9

**`isv:percona:ppg:releases:18`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_releases_18.repo << 'EOF'
[isv:percona:ppg:releases:18]
name=isv:percona:ppg:releases:18 - RockyLinux_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/RockyLinux_9/
enabled=1
gpgcheck=0
EOF
```


### Ubuntu_24.04

**`isv:percona:ppg:releases:18`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/Ubuntu_24.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:releases:18.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/Ubuntu_24.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_releases_18.gpg > /dev/null
apt update
```


### Ubuntu_26.04

**`isv:percona:ppg:releases:18`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/Ubuntu_26.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:releases:18.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/Ubuntu_26.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_releases_18.gpg > /dev/null
apt update
```


### openSUSE_Leap_16

**`isv:percona:ppg:releases:18`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/openSUSE_Leap_16/ \
  isv:percona:ppg:releases:18
zypper --gpg-auto-import-keys refresh
```


### openSUSE_Tumbleweed

**`isv:percona:ppg:releases:18`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/releases:/18/openSUSE_Tumbleweed/ \
  isv:percona:ppg:releases:18
zypper --gpg-auto-import-keys refresh
```


### Container Images

**`isv:percona:ppg:releases:18:containers:ubi9`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-distribution-postgresql:18.4
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-distribution-postgresql:18
```

**`percona-distribution-postgresql-upgrade`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-distribution-postgresql-upgrade:18.4-17-1
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-distribution-postgresql-upgrade:18.4-17
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-distribution-postgresql-upgrade:18-17
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-distribution-postgresql-with-postgis:18.4
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-distribution-postgresql-with-postgis:18
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images/percona-pgbouncer:latest
```

