Format: 3.0 (quilt)
Source: percona-pg-oidc-validator%!{PG_MAJOR_VERSION}
Binary: percona-pg-oidc-validator%!{PG_MAJOR_VERSION}
Architecture: any
Version: 1.0-1
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 9),
 libcurl4-openssl-dev,
 libkrb5-dev,
 libreadline-dev,
 libssl-dev (>= 1.1.1),
 libxml2-dev,
 libxslt1-dev,
 mawk,
 percona-postgresql-server-dev-all (>= 153~),
 zlib1g-dev,
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
