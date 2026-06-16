## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| percona-patroni | ppg:16 | 4.1.3-1+1.2 |
| percona-pg-telemetry | ppg:16 | 1.2.0-1+1.2 |
| percona-pg_cron | ppg:16 | 1.6.7-1+1.2 |
| percona-postgresql | ppg:16 | 16.14-1+4.1 |
| percona-postgresql-common | ppg:16 | 290-1+1.1 |
| percona-telemetry-agent | ppg:16 | 1.0.14-1+6.1 |

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

