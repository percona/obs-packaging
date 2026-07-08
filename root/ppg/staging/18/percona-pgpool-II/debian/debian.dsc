Format: 3.0 (quilt)
Source: percona-pgpool2
Binary: percona-pgpool2, libpgpool2, libpgpool-dev, postgresql-%!{PG_MAJOR_VERSION}-pgpool2
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 10),
 bison,
 chrpath,
 docbook,
 docbook-dsssl,
 docbook-xml,
 docbook-xsl,
 flex,
 libcrypt-dev,
 libldap-dev,
 libmemcached-dev,
 libpam0g-dev,
 libpq-dev,
 libssl-dev,
 libxml2-utils,
 openjade,
 opensp,
 percona-postgresql-server-dev-%!{PG_MAJOR_VERSION},
 percona-postgresql-server-dev-all,
 percona-postgresql-common,
 xsltproc
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
