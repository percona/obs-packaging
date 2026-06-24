## Packages

| Package | Project | Version |
| ------- | ------- | ------- |
| percona-pg-telemetry | ppg:15 | 1.2.0-1+1.1 |
| percona-postgresql | ppg:15 | 15.18-1+1.1 |
| percona-postgresql-common | ppg:15 | 290-1+1.1 |
| percona-telemetry-agent | ppg:15 | 1.0.14-1+9.1 |

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

