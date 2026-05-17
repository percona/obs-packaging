## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| gosu | ppg:17:containers:ubi9 | 1.19-2.6 |
| etcd | ppg:17 | 3.5.30-1+1.3 |
| percona-haproxy | ppg:17 | 2.8.23-1+2.1 |
| percona-patroni | ppg:17 | 4.1.3-1+2.1 |
| percona-pg-telemetry | ppg:17 | 1.2.0-1+4.5 |
| percona-pg_cron | ppg:17 | 1.6.7-1+2.3 |
| percona-pg_gather | ppg:17 | 33-1+1.2 |
| percona-pg_repack | ppg:17 | 1.5.3-1+5.3 |
| percona-pg_stat_monitor | ppg:17 | 2.3.2-1+5.6 |
| percona-pg_tde | ppg:17 | 2.2.0-1+1.2 |
| percona-pgaudit | ppg:17 | 17.1-1+5.3 |
| percona-pgaudit_set_user | ppg:17 | 4.2.0-1+5.3 |
| percona-pgbackrest | ppg:17 | 2.58.0-1+4.6 |
| percona-pgbadger | ppg:17 | 13.2-1+3.2 |
| percona-pgbouncer | ppg:17 | 1.25.2-1+1.4 |
| percona-pgpool-II | ppg:17 | 4.7.1-1+1.3 |
| percona-pgvector | ppg:17 | 0.8.2-1+4.3 |
| percona-postgis | ppg:17 | 3.5.6-1+1.3 |
| percona-postgresql | ppg:17 | 17.10-1+1.2 |
| percona-postgresql-common | ppg:17 | 290-1+1.2 |
| percona-ppg-server | ppg:17 | 17.10-1 |
| percona-ppg-server-ha | ppg:17 | 17.10-1 |
| percona-telemetry-agent | ppg:17 | 1.0.9-1+5.3 |
| percona-wal2json | ppg:17 | 2.6-1+5.2 |
| python3-attrs | ppg:17 | 22.1.0-1.7 |
| python3-blessed | ppg:17 | 1.22.0-1.7 |
| python3-boto3 | ppg:17 | 1.38.19-1.7 |
| python3-botocore | ppg:17 | 1.38.19-1.7 |
| python3-click | ppg:17 | 8.1.7-1.7 |
| python3-dateutil | ppg:17 | 2.9.0.post0-1.7 |
| python3-dns | ppg:17 | 1.15.0-1.7 |
| python3-etcd | ppg:17 | 0.4.5-1.7 |
| python3-kazoo | ppg:17 | 2.8.0-1.7 |
| python3-lz4 | ppg:17 | 4.3.3-1.7 |
| python3-prettytable | ppg:17 | 3.4.0-1.7 |
| python3-psutil | ppg:17 | 6.1.1-1.7 |
| python3-psycopg2 | ppg:17 | 2.9.10-2.8 |
| python3-py-consul | ppg:17 | 1.6.0-1.6 |
| python3-pysyncobj | ppg:17 | 0.3.10-1+1.2 |
| python3-six | ppg:17 | 1.17.0-1.7 |
| python3-wcwidth | ppg:17 | 0.2.13-1.7 |
| python3-zstandard | ppg:17 | 0.23.0-1.7 |
| sfcgal | ppg:17 | 2.2.0-2.4 |
| ydiff | ppg:17 | 1.4.2-1+1.2 |

## Container Images

| Package | Project | Image | Version | Tags |
| ------- | ------- | ----- | ------- | ---- |
| percona-distribution-postgresql | ppg:17:containers:ubi9 | percona-distribution-postgresql | 17.10-2 | `17.10-2-1.4` `17.10-2` `17` |
| percona-distribution-postgresql-with-postgis | ppg:17:containers:ubi9 | percona-distribution-postgresql-with-postgis | 17.10-2 | `17.10-2-1.4` `17.10-2` `17` |
| percona-pgbackrest | ppg:17:containers:ubi9 | percona-pgbackrest | 2.58.0 | `2.58.0-2.1` `2.58.0` `latest` |
| percona-pgbouncer | ppg:17:containers:ubi9 | percona-pgbouncer | 1.25.2 | `1.25.2-2.1` `1.25.2` `latest` |

# Repository Installation Instructions


### Debian_13

**`isv:percona:ppg:17`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:17.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/17/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_17.gpg > /dev/null
apt update
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

**`isv:percona:ppg:17:containers:ubi9`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-distribution-postgresql:%!{PG_MAJOR_VERSION}
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-distribution-postgresql-with-postgis:%!{PG_MAJOR_VERSION}
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/17/containers/ubi9/images/percona-pgbouncer:latest
```

