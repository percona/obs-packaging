Format: 3.0 (quilt)
Source: percona-address-standardizer
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-address-standardizer
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper,
 mawk,
 libpcre2-dev,
 percona-postgresql-server-dev-all (>= 153~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
