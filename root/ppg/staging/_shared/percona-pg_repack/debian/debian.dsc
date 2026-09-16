Format: 3.0 (quilt)
Source: percona-pg-repack
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-repack
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 13),
 liblz4-dev,
 libnuma-dev,
 libreadline-dev,
 libssl-dev,
 libzstd-dev,
 mawk,
 percona-postgresql-server-dev-all (>= 153~),
 zlib1g-dev,
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
