Format: 3.0 (quilt)
Source: percona-credcheck
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-credcheck
Architecture: any
Version: %!{CREDCHECK_VERSION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper-compat (= 13),
 libkrb5-dev,
 percona-postgresql-server-dev-all (>= 153~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
