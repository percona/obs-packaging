## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| gosu | ppg:18:containers:ubi9 | 1.19-2.5 |
| etcd | ppg:18 | 3.5.29-1+5.1 |
| percona-haproxy | ppg:18 | 2.8.18-1+1.1 |
| percona-patroni | ppg:18 | 4.1.1-1+5.1 |
| percona-pg_cron | ppg:18 | 1.6.7-0+2.1 |
| percona-pg_gather | ppg:18 | 32-0+1.1 |
| percona-pg_oidc_validator | ppg:18 | 1.0-0+2.1 |
| percona-pg_repack | ppg:18 | 1.5.3-0+3.1 |
| percona-pg_stat_monitor | ppg:18 | 2.3.2-0+3.1 |
| percona-pg_tde | ppg:18 | 2.1.2-0+3.1 |
| percona-pgaudit | ppg:18 | 18.0-1+3.1 |
| percona-pgaudit_set_user | ppg:18 | 4.2.0-0+3.1 |
| percona-pgbackrest | ppg:18 | 2.58.0-0+2.3 |
| percona-pgbadger | ppg:18 | 13.2-1+1.1 |
| percona-pgbouncer | ppg:18 | 1.25.1-1+2.3 |
| percona-pgpool-II | ppg:18 | 4.7.0-1+2.1 |
| percona-pgvector | ppg:18 | 0.8.2-0+2.1 |
| percona-postgis | ppg:18 | 3.5.5-1+2.1 |
| percona-postgresql-common | ppg:18 | 289-1+1.1 |
| percona-postgresql18 | ppg:18 | 18.3-1+4.1 |
| percona-ppg-server-18 | ppg:18 | 18.3-1 |
| percona-ppg-server-ha-18 | ppg:18 | 18.3-1 |
| percona-wal2json | ppg:18 | 2.6-0+3.1 |
| python3-attrs | ppg:18 | 22.1.0-1.6 |
| python3-blessed | ppg:18 | 1.22.0-1.6 |
| python3-boto3 | ppg:18 | 1.38.19-1.6 |
| python3-botocore | ppg:18 | 1.38.19-1.6 |
| python3-click | ppg:18 | 8.1.7-1.6 |
| python3-dateutil | ppg:18 | 2.9.0.post0-1.6 |
| python3-dns | ppg:18 | 1.15.0-1.6 |
| python3-etcd | ppg:18 | 0.4.5-1.6 |
| python3-kazoo | ppg:18 | 2.8.0-1.6 |
| python3-lz4 | ppg:18 | 4.3.3-1.6 |
| python3-prettytable | ppg:18 | 3.4.0-1.6 |
| python3-psutil | ppg:18 | 6.1.1-1.6 |
| python3-psycopg2 | ppg:18 | 2.9.10-1.9 |
| python3-py-consul | ppg:18 | 1.6.0-1.5 |
| python3-pysyncobj | ppg:18 | 0.3.10-1+1.1 |
| python3-six | ppg:18 | 1.17.0-1.6 |
| python3-wcwidth | ppg:18 | 0.2.13-1.6 |
| python3-zstandard | ppg:18 | 0.23.0-1.6 |
| sfcgal | ppg:18 | 2.2.0-2.3 |
| ydiff | ppg:18 | 1.4.2-1+1.1 |

## Container Images

| Package | Project | Image | Version | Tags |
| ------- | ------- | ----- | ------- | ---- |
| percona-distribution-postgresql | ppg:18:containers:ubi9 | percona-distribution-postgresql | 18.3 | `18.3-2.1` `18.3` `18` |
| percona-distribution-postgresql-with-postgis | ppg:18:containers:ubi9 | percona-distribution-postgresql-with-postgis | 18.3 | `18.3-2.1` `18.3` `18` |

# Repository Installation Instructions


### Debian_13

**`isv:percona:ppg:18`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:18.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_18.gpg > /dev/null
apt update
```


### RockyLinux_9

**`isv:percona:ppg:18`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_18.repo << 'EOF'
[isv:percona:ppg:18]
name=isv:percona:ppg:18 - RockyLinux_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/RockyLinux_9/
enabled=1
gpgcheck=0
EOF
```


### Ubuntu_24.04

**`isv:percona:ppg:18`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/Ubuntu_24.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:18.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/Ubuntu_24.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_18.gpg > /dev/null
apt update
```


### Ubuntu_26.04

**`isv:percona:ppg:18`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/Ubuntu_26.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:18.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/Ubuntu_26.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_18.gpg > /dev/null
apt update
```


### openSUSE_Leap_16

**`isv:percona:ppg:18`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/openSUSE_Leap_16/ \
  isv:percona:ppg:18
zypper --gpg-auto-import-keys refresh
```


### openSUSE_Tumbleweed

**`isv:percona:ppg:18`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/18/openSUSE_Tumbleweed/ \
  isv:percona:ppg:18
zypper --gpg-auto-import-keys refresh
```


### Container Images

**`isv:percona:ppg:18:containers:ubi9`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/18/containers/ubi9/images/percona-distribution-postgresql:18
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/18/containers/ubi9/images/percona-distribution-postgresql-with-postgis:18
```

