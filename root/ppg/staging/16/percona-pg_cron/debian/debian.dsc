Format: 3.0 (quilt)
Source: percona-pg-cron
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-cron
Architecture: any
Version: %!{PG_CRON_VERSION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper,
 mawk,
 percona-postgresql-server-dev-all (>= 153~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
