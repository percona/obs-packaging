Format: 3.0 (quilt)
Source: percona-pgaudit%!{PG_MAJOR_VERSION}-set-user
Binary: percona-pgaudit%!{PG_MAJOR_VERSION}-set-user
Architecture: any
Version: 1:%!{PGAUDIT_SET_USER_VERSION}-%!{PKG_REVISION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper-compat (= 13),
 libkrb5-dev,
 libssl-dev,
 mawk,
 percona-postgresql-server-dev-all (>= 163~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
