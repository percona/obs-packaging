Format: 3.0 (quilt)
Source: percona-wal2json
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-wal2json
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 10),
 mawk,
 percona-postgresql-server-dev-all (>= 153~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
