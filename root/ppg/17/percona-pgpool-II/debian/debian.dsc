Format: 3.0 (quilt)
Source: percona-pgpool2
Binary: percona-pgpool2, percona-pgpool2-dev, percona-pgpool2-recovery
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper-compat (= 13),
 bison,
 flex,
 libpq-dev,
 postgresql-server-dev-17 | percona-postgresql-server-dev-17,
 libmemcached-dev,
 libssl-dev,
 libpam0g-dev,
 libldap-dev,
 pkg-config,
 libtool,
 autoconf,
 automake
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz rpm.tar.gz
