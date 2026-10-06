Format: 3.0 (quilt)
Source: percona-pgvector
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-pgvector
Architecture: any
Version: 1:%!{PGVECTOR_VERSION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper-compat (= 13),
 percona-postgresql-server-dev-all (>= 153~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
