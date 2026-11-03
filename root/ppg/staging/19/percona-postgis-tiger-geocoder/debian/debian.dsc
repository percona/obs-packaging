Format: 3.0 (quilt)
Source: percona-postgis-tiger-geocoder
Binary: percona-postgresql-%!{PG_MAJOR_VERSION}-postgis-tiger-geocoder
Architecture: all
Version: %!{POSTGIS_TIGER_GEOCODER_VERSION}-%!{PKG_REVISION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper,
 mawk,
 perl,
 percona-postgresql-server-dev-all (>= 153~),
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
