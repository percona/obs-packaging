Format: 3.0 (quilt)
Source: percona-haproxy
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper (>= 9.0.0),
               libpcre2-dev,
               libssl-dev,
               liblua5.3-dev,
               libsystemd-dev [linux-any],
               python3-sphinx,
               zlib1g-dev,
               libcrypt-dev
Build-Depends-Indep: python3, python3-mako
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
