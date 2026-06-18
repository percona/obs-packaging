## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:14 | 3.5.30-1+5.1 |
| percona-haproxy | ppg:14 | 2.8.23-1+1.1 |
| percona-patroni | ppg:14 | 4.1.3-1+2.1 |
| percona-pg-telemetry | ppg:14 | 1.2.0-1+1.2 |
| percona-pg_cron | ppg:14 | 1.6.7-1+1.2 |
| percona-pg_gather | ppg:14 | 33-1+1.1 |
| percona-pg_repack | ppg:14 | 1.5.3-1+1.2 |
| percona-pg_stat_monitor | ppg:14 | 2.3.2-1+1.2 |
| percona-pgaudit | ppg:14 | 1.6.3-1+1.2 |
| percona-pgaudit_set_user | ppg:14 | 4.2.0-1+1.2 |
| percona-pgbackrest | ppg:14 | 2.58.0-1+1.2 |
| percona-pgbadger | ppg:14 | 13.2-1+1.1 |
| percona-pgbouncer | ppg:14 | 1.25.2-1+1.2 |
| percona-pgpool-II | ppg:14 | 4.7.1-1+1.2 |
| percona-pgvector | ppg:14 | 0.8.2-1+1.2 |
| percona-postgis | ppg:14 | 3.5.6-1+1.2 |
| percona-postgresql | ppg:14 | 14.23-1+2.1 |
| percona-postgresql-common | ppg:14 | 290-1+1.1 |
| percona-ppg-server | ppg:14 | 14.23-1 |
| percona-ppg-server-ha | ppg:14 | 14.23-1 |
| percona-telemetry-agent | ppg:14 | 1.0.14-1+7.1 |
| percona-wal2json | ppg:14 | 2.6-1+1.2 |
| python3-attrs | ppg:14 | 22.1.0-2.2 |
| python3-blessed | ppg:14 | 1.22.0-2.2 |
| python3-boto3 | ppg:14 | 1.38.19-2.2 |
| python3-botocore | ppg:14 | 1.38.19-2.2 |
| python3-click | ppg:14 | 8.1.7-2.2 |
| python3-dateutil | ppg:14 | 2.9.0.post0-2.2 |
| python3-dns | ppg:14 | 1.15.0-2.2 |
| python3-etcd | ppg:14 | 0.4.5-2.2 |
| python3-kazoo | ppg:14 | 2.8.0-2.2 |
| python3-lz4 | ppg:14 | 4.3.3-2.2 |
| python3-prettytable | ppg:14 | 3.4.0-2.2 |
| python3-psutil | ppg:14 | 6.1.1-2.2 |
| python3-psycopg2 | ppg:14 | 2.9.10-1.2 |
| python3-py-consul | ppg:14 | 1.6.0-2.2 |
| python3-pysyncobj | ppg:14 | 0.3.10-1+3.1 |
| python3-six | ppg:14 | 1.17.0-2.2 |
| python3-wcwidth | ppg:14 | 0.2.13-2.2 |
| python3-zstandard | ppg:14 | 0.23.0-2.2 |
| sfcgal | ppg:14 | 2.2.0-3.2 |
| ydiff | ppg:14 | 1.4.2-1+2.1 |

# Repository Installation Instructions


### Debian_13

**`isv:percona:ppg:14`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:14.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_14.gpg > /dev/null
apt update
```


### RockyLinux_9

**`isv:percona:ppg:14`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_14.repo << 'EOF'
[isv:percona:ppg:14]
name=isv:percona:ppg:14 - RockyLinux_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/RockyLinux_9/
enabled=1
gpgcheck=0
EOF
```


### UBI_8

**`isv:percona:ppg:14`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/UBI_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_14.repo << 'EOF'
[isv:percona:ppg:14]
name=isv:percona:ppg:14 - UBI_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/UBI_8/
enabled=1
gpgcheck=0
EOF
```


### UBI_9

**`isv:percona:ppg:14`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/UBI_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_14.repo << 'EOF'
[isv:percona:ppg:14]
name=isv:percona:ppg:14 - UBI_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/UBI_9/
enabled=1
gpgcheck=0
EOF
```


### Ubuntu_24.04

**`isv:percona:ppg:14`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Ubuntu_24.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:14.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Ubuntu_24.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_14.gpg > /dev/null
apt update
```


### Ubuntu_26.04

**`isv:percona:ppg:14`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Ubuntu_26.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:14.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Ubuntu_26.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_14.gpg > /dev/null
apt update
```


### openSUSE_Leap_16

**`isv:percona:ppg:14`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/openSUSE_Leap_16/ \
  isv:percona:ppg:14
zypper --gpg-auto-import-keys refresh
```


### openSUSE_Tumbleweed

**`isv:percona:ppg:14`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/openSUSE_Tumbleweed/ \
  isv:percona:ppg:14
zypper --gpg-auto-import-keys refresh
```

