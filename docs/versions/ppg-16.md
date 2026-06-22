## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:16 | 3.5.30-1+5.1 |
| percona-haproxy | ppg:16 | (none) |
| percona-patroni | ppg:16 | 4.1.3-1+1.9 |
| percona-pg-telemetry | ppg:16 | 1.2.0-1+1.9 |
| percona-pg_cron | ppg:16 | 1.6.7-1+1.9 |
| percona-pg_gather | ppg:16 | 33-1+1.1 |
| percona-pg_repack | ppg:16 | 1.5.3-1+1.8 |
| percona-pg_stat_monitor | ppg:16 | (none) |
| percona-pgaudit | ppg:16 | (none) |
| percona-pgaudit_set_user | ppg:16 | (none) |
| percona-pgbackrest | ppg:16 | (none) |
| percona-pgbadger | ppg:16 | (none) |
| percona-pgbouncer | ppg:16 | (none) |
| percona-pgpool-II | ppg:16 | (none) |
| percona-pgvector | ppg:16 | (none) |
| percona-postgis | ppg:16 | (none) |
| percona-postgresql | ppg:16 | 16.14-1+11.1 |
| percona-postgresql-common | ppg:16 | 290-1+1.1 |
| percona-ppg-server | ppg:16 | (none) |
| percona-ppg-server-ha | ppg:16 | (none) |
| percona-telemetry-agent | ppg:16 | 1.0.14-1+8.1 |
| percona-wal2json | ppg:16 | (none) |
| python3-attrs | ppg:16 | 22.1.0-2.2 |
| python3-blessed | ppg:16 | 1.22.0-2.2 |
| python3-boto3 | ppg:16 | 1.38.19-2.2 |
| python3-botocore | ppg:16 | 1.38.19-2.2 |
| python3-click | ppg:16 | 8.1.7-2.2 |
| python3-dateutil | ppg:16 | 2.9.0.post0-2.2 |
| python3-dns | ppg:16 | 1.15.0-2.2 |
| python3-etcd | ppg:16 | 0.4.5-2.2 |
| python3-kazoo | ppg:16 | 2.8.0-2.2 |
| python3-lz4 | ppg:16 | 4.3.3-2.2 |
| python3-prettytable | ppg:16 | 3.4.0-2.2 |
| python3-psutil | ppg:16 | 6.1.1-2.2 |
| python3-psycopg2 | ppg:16 | (none) |
| python3-py-consul | ppg:16 | 1.6.0-2.2 |
| python3-pysyncobj | ppg:16 | 0.3.10-1+3.1 |
| python3-six | ppg:16 | 1.17.0-2.2 |
| python3-wcwidth | ppg:16 | 0.2.13-2.2 |
| python3-zstandard | ppg:16 | 0.23.0-2.2 |
| sfcgal | ppg:16 | 2.2.0-3.2 |
| ydiff | ppg:16 | 1.4.2-1+2.1 |

## Container Images

| Package | Project | Image | Version | Tags | Installed packages |
| ------- | ------- | ----- | ------- | ---- | ------------------ |
| percona-distribution-postgresql | ppg:16:containers:ubi8 | percona-distribution-postgresql | (none) | `<VERSION>-<RELEASE>` | (none) |
| percona-distribution-postgresql-with-postgis | ppg:16:containers:ubi8 | percona-distribution-postgresql-with-postgis | (none) | `<VERSION>-<RELEASE>` | (none) |
| percona-pgbackrest | ppg:16:containers:ubi8 | percona-pgbackrest | (none) | `<VERSION>-<RELEASE>` | (none) |
| percona-pgbouncer | ppg:16:containers:ubi8 | percona-pgbouncer | (none) | `<VERSION>-<RELEASE>` | (none) |
| percona-distribution-postgresql | ppg:16:containers:ubi9 | percona-distribution-postgresql | (none) | `<VERSION>-<RELEASE>` | (none) |
| percona-distribution-postgresql-with-postgis | ppg:16:containers:ubi9 | percona-distribution-postgresql-with-postgis | (none) | `<VERSION>-<RELEASE>` | (none) |
| percona-pgbackrest | ppg:16:containers:ubi9 | percona-pgbackrest | (none) | `<VERSION>-<RELEASE>` | (none) |
| percona-pgbouncer | ppg:16:containers:ubi9 | percona-pgbouncer | (none) | `<VERSION>-<RELEASE>` | (none) |

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

