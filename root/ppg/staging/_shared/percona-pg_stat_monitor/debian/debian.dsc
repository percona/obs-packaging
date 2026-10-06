Format: 3.0 (quilt)
Source: percona-pg-stat-monitor
Binary: percona-pg-stat-monitor%!{PG_MAJOR_VERSION}
Architecture: any
Version: 1:%!{PG_STAT_MONITOR_VERSION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 9),
 mawk,
 libkrb5-dev,
 libssl-dev,
 percona-postgresql-server-dev-all (>= 153~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
