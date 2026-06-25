## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:15 | 3.5.30-1+5.1 |
| percona-haproxy | ppg:15 | 2.8.23-1+1.1 |
| percona-patroni | ppg:15 | 4.1.3-1+1.1 |
| percona-pg-telemetry | ppg:15 | 1.2.0-1+1.1 |
| percona-pg_cron | ppg:15 | 1.6.7-1+1.1 |
| percona-pg_gather | ppg:15 | 33-1+1.1 |
| percona-pg_repack | ppg:15 | 1.5.3-1+1.1 |
| percona-pg_stat_monitor | ppg:15 | 2.3.2-1+1.1 |
| percona-pgaudit | ppg:15 | 1.6.3-1+1.1 |
| percona-pgaudit_set_user | ppg:15 | 4.2.0-1+1.1 |
| percona-pgbackrest | ppg:15 | 2.58.0-1+1.1 |
| percona-pgbadger | ppg:15 | 13.2-1+1.1 |
| percona-pgbouncer | ppg:15 | 1.25.2-1+1.1 |
| percona-pgpool-II | ppg:15 | 4.7.1-1+1.1 |
| percona-pgvector | ppg:15 | 0.8.3-1+1.1 |
| percona-postgis | ppg:15 | 3.5.7-1+1.1 |
| percona-postgresql | ppg:15 | 15.18-1+1.1 |
| percona-postgresql-common | ppg:15 | 290-1+1.1 |
| percona-ppg-server | ppg:15 | 15.18-1 |
| percona-ppg-server-ha | ppg:15 | 15.18-1 |
| percona-telemetry-agent | ppg:15 | 1.0.14-1+9.1 |
| percona-wal2json | ppg:15 | 2.6-1+1.1 |
| python3-attrs | ppg:15 | 22.1.0-2.2 |
| python3-blessed | ppg:15 | 1.22.0-2.2 |
| python3-boto3 | ppg:15 | 1.38.19-2.2 |
| python3-botocore | ppg:15 | 1.38.19-2.2 |
| python3-click | ppg:15 | 8.1.7-2.2 |
| python3-dateutil | ppg:15 | 2.9.0.post0-3.2 |
| python3-dns | ppg:15 | 1.15.0-2.2 |
| python3-etcd | ppg:15 | 0.4.5-2.2 |
| python3-kazoo | ppg:15 | 2.8.0-2.2 |
| python3-lz4 | ppg:15 | 4.3.3-3.2 |
| python3-prettytable | ppg:15 | 3.4.0-2.2 |
| python3-psutil | ppg:15 | 6.1.1-2.2 |
| python3-psycopg2 | ppg:15 | 2.9.10-1.2 |
| python3-py-consul | ppg:15 | 1.6.0-2.2 |
| python3-pysyncobj | ppg:15 | 0.3.10-1+3.1 |
| python3-six | ppg:15 | 1.17.0-2.2 |
| python3-wcwidth | ppg:15 | 0.2.13-2.2 |
| python3-zstandard | ppg:15 | 0.23.0-2.2 |
| sfcgal | ppg:15 | 2.2.0-4.2 |
| ydiff | ppg:15 | 1.4.2-1+2.1 |

# Repository Installation Instructions


### Debian_13

**`isv:percona:ppg:15`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:15.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_15.gpg > /dev/null
apt update
```


### RockyLinux_10

**`isv:percona:ppg:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/RockyLinux_10/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_15.repo << 'EOF'
[isv:percona:ppg:15]
name=isv:percona:ppg:15 - RockyLinux_10
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/RockyLinux_10/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_9

**`isv:percona:ppg:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/RockyLinux_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_15.repo << 'EOF'
[isv:percona:ppg:15]
name=isv:percona:ppg:15 - RockyLinux_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/RockyLinux_9/
enabled=1
gpgcheck=0
EOF
```


### UBI_8

**`isv:percona:ppg:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/UBI_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_15.repo << 'EOF'
[isv:percona:ppg:15]
name=isv:percona:ppg:15 - UBI_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/UBI_8/
enabled=1
gpgcheck=0
EOF
```


### UBI_9

**`isv:percona:ppg:15`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/UBI_9/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_15.repo << 'EOF'
[isv:percona:ppg:15]
name=isv:percona:ppg:15 - UBI_9
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/UBI_9/
enabled=1
gpgcheck=0
EOF
```


### Ubuntu_24.04

**`isv:percona:ppg:15`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/Ubuntu_24.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:15.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/Ubuntu_24.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_15.gpg > /dev/null
apt update
```


### Ubuntu_26.04

**`isv:percona:ppg:15`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/Ubuntu_26.04/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:15.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/Ubuntu_26.04/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_15.gpg > /dev/null
apt update
```


### openSUSE_Leap_16

**`isv:percona:ppg:15`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/openSUSE_Leap_16/ \
  isv:percona:ppg:15
zypper --gpg-auto-import-keys refresh
```


### openSUSE_Tumbleweed

**`isv:percona:ppg:15`**

```bash
zypper addrepo \
  https://download.opensuse.org/repositories/isv:/percona:/ppg:/15/openSUSE_Tumbleweed/ \
  isv:percona:ppg:15
zypper --gpg-auto-import-keys refresh
```

