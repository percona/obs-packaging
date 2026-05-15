Format: 3.0 (quilt)
Source: percona-pgaudit
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-pgaudit
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 10), percona-postgresql-server-dev-%!{PG_MAJOR_VERSION}, libssl-dev, libkrb5-dev
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
