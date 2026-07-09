## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| etcd | ppg:14 | 3.5.30-1+5.1 |
| percona-haproxy | ppg:14 | 2.8.23-1+1.1 |
| percona-patroni | ppg:14 | 4.1.3-1+2.4 |
| percona-pg-telemetry | ppg:14 | 1.2.0-1+1.3 |
| percona-pg_cron | ppg:14 | 1.6.7-1+1.3 |
| percona-pg_gather | ppg:14 | 33-1+1.1 |
| percona-pg_repack | ppg:14 | 1.5.3-1+1.3 |
| percona-pg_stat_monitor | ppg:14 | 2.3.2-1+1.3 |
| percona-pgaudit | ppg:14 | 1.6.3-1+1.3 |
| percona-pgaudit_set_user | ppg:14 | 4.2.0-1+1.3 |
| percona-pgbackrest | ppg:14 | 2.58.0-1+2.4 |
| percona-pgbadger | ppg:14 | 13.2-1+1.1 |
| percona-pgbouncer | ppg:14 | 1.25.2-1+1.4 |
| percona-pgpool-II | ppg:14 | 4.7.1-1+1.3 |
| percona-pgvector | ppg:14 | 0.8.3-1+1.3 |
| percona-postgis | ppg:14 | 3.5.7-1+2.3 |
| percona-postgresql | ppg:14 | 14.23-1+5.1 |
| percona-postgresql-common | ppg:14 | 290-1+1.1 |
| percona-ppg-server | ppg:14 | 14.23-1 |
| percona-ppg-server-ha | ppg:14 | 14.23-1 |
| percona-telemetry-agent | ppg:14 | 1.0.14-1+9.1 |
| percona-wal2json | ppg:14 | 2.6-1+1.3 |
| python3-attrs | ppg:14 | 22.1.0-2.3 |
| python3-blessed | ppg:14 | 1.22.0-2.3 |
| python3-boto3 | ppg:14 | 1.38.19-2.3 |
| python3-botocore | ppg:14 | 1.38.19-2.3 |
| python3-click | ppg:14 | 8.1.7-2.3 |
| python3-dateutil | ppg:14 | 2.9.0.post0-3.3 |
| python3-dns | ppg:14 | 1.15.0-2.3 |
| python3-etcd | ppg:14 | 0.4.5-2.3 |
| python3-kazoo | ppg:14 | 2.8.0-2.3 |
| python3-lz4 | ppg:14 | 4.3.3-3.3 |
| python3-prettytable | ppg:14 | 3.4.0-2.3 |
| python3-psutil | ppg:14 | 6.1.1-2.3 |
| python3-psycopg2 | ppg:14 | 2.9.10-1.7 |
| python3-py-consul | ppg:14 | 1.6.0-2.3 |
| python3-pysyncobj | ppg:14 | 0.3.10-1+3.1 |
| python3-six | ppg:14 | 1.17.0-2.3 |
| python3-wcwidth | ppg:14 | 0.2.13-2.3 |
| python3-zstandard | ppg:14 | 0.23.0-2.3 |
| sfcgal | ppg:14 | 2.2.0-4.4 |
| ydiff | ppg:14 | 1.4.2-1+2.1 |

## Container Images

| Package | Project | Image | Version | Tags | Installed packages |
| ------- | ------- | ----- | ------- | ---- | ------------------ |
| percona-distribution-postgresql | ppg:14:containers:ubi8 | percona-distribution-postgresql | 14.23-1 | `14.23-1-1.15` `14.23-1` `14.23` `14` | gosu 1.19-6.8, percona-patroni 4.1.3-2.5, percona-patroni-etcd 4.1.3-2.5, percona-pg-telemetry14 1.2.0-1.10, percona-pg_cron_14 1.6.7-1.10, percona-pg_repack14 1.5.3-1.10, percona-pg_stat_monitor14 2.3.2-1.10, percona-pgaudit14 1.6.3-1.12, percona-pgaudit14_set_user 4.2.0-1.10, percona-pgbackrest 2.58.0-2.5, percona-pgvector_14 0.8.3-1.7, percona-pgvector_14-llvmjit 0.8.3-1.7, percona-postgresql-client-common 290-1.5, percona-postgresql-common 290-1.5, percona-postgresql14 14.23-5.3, percona-postgresql14-contrib 14.23-5.3, percona-postgresql14-libs 14.23-5.3, percona-postgresql14-llvmjit 14.23-5.3, percona-postgresql14-server 14.23-5.3, percona-telemetry-agent 1.0.14-9.4, percona-wal2json14 2.6-1.10, perl-JSON 4.03-2.6, python3-etcd 0.4.5-2.7, python3-ydiff 1.4.2-2.7, python3.12-click 8.1.7-2.7, python3.12-dateutil 2.9.0.post0-3.4, python3.12-dns 1.15.0-2.7, python3.12-etcd 0.4.5-2.7, python3.12-prettytable 3.4.0-2.7, python3.12-psutil 6.1.1-2.7, python3.12-psycopg2 2.9.10-1.10, python3.12-six 1.17.0-2.7, python3.12-wcwidth 0.2.13-2.7 |
| percona-distribution-postgresql-with-postgis | ppg:14:containers:ubi8 | percona-distribution-postgresql-with-postgis | 14.23-1 | `14.23-1-1.30` `14.23-1` `14.23` `14` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.7, geos 3.13.1-1.7, gosu 1.19-6.8, lapack 3.9.0-1.7, percona-patroni 4.1.3-2.5, percona-patroni-etcd 4.1.3-2.5, percona-pg-telemetry14 1.2.0-1.10, percona-pg_cron_14 1.6.7-1.10, percona-pg_repack14 1.5.3-1.10, percona-pg_stat_monitor14 2.3.2-1.10, percona-pgaudit14 1.6.3-1.12, percona-pgaudit14_set_user 4.2.0-1.10, percona-pgbackrest 2.58.0-2.5, percona-pgvector_14 0.8.3-1.7, percona-pgvector_14-llvmjit 0.8.3-1.7, percona-postgis35_14 3.5.7-2.7, percona-postgis35_14-client 3.5.7-2.7, percona-postgis35_14-gui 3.5.7-2.7, percona-postgis35_14-llvmjit 3.5.7-2.7, percona-postgis35_14-utils 3.5.7-2.7, percona-postgresql-client-common 290-1.5, percona-postgresql-common 290-1.5, percona-postgresql14 14.23-5.3, percona-postgresql14-contrib 14.23-5.3, percona-postgresql14-libs 14.23-5.3, percona-postgresql14-llvmjit 14.23-5.3, percona-postgresql14-server 14.23-5.3, percona-telemetry-agent 1.0.14-9.4, percona-wal2json14 2.6-1.10, perl-JSON 4.03-2.6, python3-etcd 0.4.5-2.7, python3-ydiff 1.4.2-2.7, python3.12-click 8.1.7-2.7, python3.12-dateutil 2.9.0.post0-3.4, python3.12-dns 1.15.0-2.7, python3.12-etcd 0.4.5-2.7, python3.12-prettytable 3.4.0-2.7, python3.12-psutil 6.1.1-2.7, python3.12-psycopg2 2.9.10-1.10, python3.12-six 1.17.0-2.7, python3.12-wcwidth 0.2.13-2.7 |
| percona-pgbackrest | ppg:14:containers:ubi8 | percona-pgbackrest | 2.58.0 | `2.58.0-2.5` `2.58.0` `latest` | percona-pgbackrest 2.58.0-2.5 |
| percona-pgbouncer | ppg:14:containers:ubi8 | percona-pgbouncer | 1.25.2 | `1.25.2-2.5` `1.25.2` `latest` | c-ares 1.19.1-1.1, percona-pgbouncer 1.25.2-1.5, python3.12-psycopg2 2.9.10-1.10 |
| percona-distribution-postgresql | ppg:14:containers:ubi9 | percona-distribution-postgresql | 14.23-1 | `14.23-1-1.24` `14.23-1` `14.23` `14` | gosu 1.19-6.6, percona-patroni 4.1.3-2.3, percona-patroni-etcd 4.1.3-2.3, percona-pg-telemetry14 1.2.0-1.8, percona-pg_cron_14 1.6.7-1.8, percona-pg_repack14 1.5.3-1.8, percona-pg_stat_monitor14 2.3.2-1.8, percona-pgaudit14 1.6.3-1.12, percona-pgaudit14_set_user 4.2.0-1.8, percona-pgbackrest 2.58.0-2.5, percona-pgvector_14 0.8.3-1.6, percona-pgvector_14-llvmjit 0.8.3-1.6, percona-postgresql-client-common 290-1.3, percona-postgresql-common 290-1.3, percona-postgresql14 14.23-5.2, percona-postgresql14-contrib 14.23-5.2, percona-postgresql14-libs 14.23-5.2, percona-postgresql14-llvmjit 14.23-5.2, percona-postgresql14-server 14.23-5.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json14 2.6-1.8, perl-JSON 4.03-2.4, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-1.8, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-distribution-postgresql-with-postgis | ppg:14:containers:ubi9 | percona-distribution-postgresql-with-postgis | 14.23-1 | `14.23-1-1.38` `14.23-1` `14.23` `14` | SFCGAL 2.2.0-4.4, blas 3.9.0-1.8, flexiblas 3.0.4-2.5, flexiblas-netlib 3.0.4-2.5, flexiblas-netlib64 3.0.4-2.5, flexiblas-openblas-threads 3.0.4-2.5, geos 3.13.1-1.9, gosu 1.19-6.6, lapack 3.9.0-1.8, percona-patroni 4.1.3-2.3, percona-patroni-etcd 4.1.3-2.3, percona-pg-telemetry14 1.2.0-1.8, percona-pg_cron_14 1.6.7-1.8, percona-pg_repack14 1.5.3-1.8, percona-pg_stat_monitor14 2.3.2-1.8, percona-pgaudit14 1.6.3-1.12, percona-pgaudit14_set_user 4.2.0-1.8, percona-pgbackrest 2.58.0-2.5, percona-pgvector_14 0.8.3-1.6, percona-pgvector_14-llvmjit 0.8.3-1.6, percona-postgis35_14 3.5.7-2.9, percona-postgis35_14-client 3.5.7-2.9, percona-postgis35_14-gui 3.5.7-2.9, percona-postgis35_14-llvmjit 3.5.7-2.9, percona-postgis35_14-utils 3.5.7-2.9, percona-postgresql-client-common 290-1.3, percona-postgresql-common 290-1.3, percona-postgresql14 14.23-5.2, percona-postgresql14-contrib 14.23-5.2, percona-postgresql14-libs 14.23-5.2, percona-postgresql14-llvmjit 14.23-5.2, percona-postgresql14-server 14.23-5.2, percona-telemetry-agent 1.0.14-9.5, percona-wal2json14 2.6-1.8, perl-JSON 4.03-2.4, proj 9.6.0-2.5, proj-data 9.6.0-2.5, python3-etcd 0.4.5-2.4, python3-ydiff 1.4.2-2.4, python3.12-click 8.1.7-2.4, python3.12-dateutil 2.9.0.post0-3.3, python3.12-dns 1.15.0-2.4, python3.12-etcd 0.4.5-2.4, python3.12-prettytable 3.4.0-2.4, python3.12-psutil 6.1.1-2.4, python3.12-psycopg2 2.9.10-1.8, python3.12-six 1.17.0-2.4, python3.12-wcwidth 0.2.13-2.4 |
| percona-pgbackrest | ppg:14:containers:ubi9 | percona-pgbackrest | 2.58.0 | `2.58.0-2.4` `2.58.0` `latest` | percona-pgbackrest 2.58.0-2.5, percona-postgresql14-libs 14.23-5.2 |
| percona-pgbouncer | ppg:14:containers:ubi9 | percona-pgbouncer | 1.25.2 | `1.25.2-2.4` `1.25.2` `latest` | c-ares 1.19.1-1.9, percona-pgbouncer 1.25.2-1.6, percona-postgresql14-libs 14.23-5.2, python3.12-psycopg2 2.9.10-1.8 |

# Repository Installation Instructions


### Debian_11

**`isv:percona:ppg:14`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Debian_11/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:14.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Debian_11/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_14.gpg > /dev/null
apt update
```


### Debian_13

**`isv:percona:ppg:14`**

```bash
echo 'deb https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Debian_13/ /' \
  | tee /etc/apt/sources.list.d/isv:percona:ppg:14.list
curl -fsSL https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/Debian_13/Release.key \
  | gpg --dearmor | tee /etc/apt/trusted.gpg.d/isv_percona_ppg_14.gpg > /dev/null
apt update
```


### RockyLinux_10

**`isv:percona:ppg:14`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/RockyLinux_10/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_14.repo << 'EOF'
[isv:percona:ppg:14]
name=isv:percona:ppg:14 - RockyLinux_10
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/RockyLinux_10/
enabled=1
gpgcheck=0
EOF
```


### RockyLinux_8

**`isv:percona:ppg:14`**

```bash
rpm --import https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/RockyLinux_8/repodata/repomd.xml.key
tee /etc/yum.repos.d/isv_percona_ppg_14.repo << 'EOF'
[isv:percona:ppg:14]
name=isv:percona:ppg:14 - RockyLinux_8
baseurl=https://download.opensuse.org/repositories/isv:/percona:/ppg:/14/RockyLinux_8/
enabled=1
gpgcheck=0
EOF
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


### Container Images

**`isv:percona:ppg:14:containers:ubi8`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi8/images/percona-distribution-postgresql:14.23
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi8/images/percona-distribution-postgresql:14
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi8/images/percona-distribution-postgresql-with-postgis:14.23
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi8/images/percona-distribution-postgresql-with-postgis:14
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi8/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi8/images/percona-pgbouncer:latest
```

**`isv:percona:ppg:14:containers:ubi9`**

**`percona-distribution-postgresql`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi9/images/percona-distribution-postgresql:14.23
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi9/images/percona-distribution-postgresql:14
```

**`percona-distribution-postgresql-with-postgis`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi9/images/percona-distribution-postgresql-with-postgis:14.23
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi9/images/percona-distribution-postgresql-with-postgis:14
```

**`percona-pgbackrest`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi9/images/percona-pgbackrest:latest
```

**`percona-pgbouncer`**

```bash
docker pull registry.opensuse.org/isv/percona/ppg/14/containers/ubi9/images/percona-pgbouncer:latest
```

