Format: 3.0 (quilt)
Source: percona-pg-tde%!{PG_MAJOR_VERSION}
Binary: percona-pg-tde%!{PG_MAJOR_VERSION}, percona-pg-tde%!{PG_MAJOR_VERSION}-client
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 9),
 meson,
 ninja-build,
 chrpath,
 pkg-config,
 percona-postgresql-server-dev-all (>= 153~),
 clang,
 libcurl4-openssl-dev,
 libssl-dev (>= 1.1.1),
 zlib1g-dev,
 libzstd-dev,
 liblz4-dev,
 libxml2-dev,
 libxslt1-dev,
 libselinux1-dev,
 libpam0g-dev,
 libkrb5-dev,
 libreadline-dev,
 shtool
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
