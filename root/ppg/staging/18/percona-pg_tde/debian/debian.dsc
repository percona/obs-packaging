Format: 3.0 (quilt)
Source: percona-pg-tde%!{PG_MAJOR_VERSION}
Binary: percona-pg-tde%!{PG_MAJOR_VERSION}, percona-pg-tde%!{PG_MAJOR_VERSION}-client
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 9),
 libcurl4-openssl-dev,
 libkrb5-dev,
 libnuma-dev,
 liblz4-dev,
 libpam0g-dev,
 libreadline-dev,
 libselinux1-dev,
 libssl-dev (>= 1.1.1),
 libxml2-dev,
 libxslt1-dev,
 libzstd-dev,
 mawk,
 percona-postgresql-server-dev-all (>= 153~),
 zlib1g-dev,
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
