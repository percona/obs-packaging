Format: 3.0 (quilt)
Source: percona-pgaudit%!{PG_MAJOR_VERSION}-set-user
Binary: percona-pgaudit%!{PG_MAJOR_VERSION}-set-user
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 9),
 libkrb5-dev,
 libssl-dev,
 mawk,
 percona-postgresql-server-dev-all (>= 163~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
