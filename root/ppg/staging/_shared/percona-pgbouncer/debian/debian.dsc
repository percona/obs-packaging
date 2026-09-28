Format: 3.0 (quilt)
Source: percona-pgbouncer
Binary: percona-pgbouncer
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 ca-certificates,
 debhelper,
 ldap-utils <!nocheck>,
 libevent-dev (>= 1.3b),
 libldap-dev,
 libpam0g-dev | libpam-dev,
 libssl-dev,
 libc-ares-dev (>> 1.12),
 libpq-dev,
 libsystemd-dev [linux-any],
 pkgconf,
 pandoc,
 python3,
 python3-pytest <!nocheck>,
 python3-pytest <!nocheck>,
 python3-pytest-asyncio <!nocheck>,
 python3-pytest-timeout <!nocheck>,
 python3-pytest-xdist <!nocheck>,
 python3-psycopg2 <!nocheck>,
 python3-filelock <!nocheck>,
 slapd <!nocheck>,
 socat <!nocheck>,
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
