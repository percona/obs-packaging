Format: 3.0 (quilt)
Source: percona-pgbackrest
Binary: percona-pgbackrest, percona-pgbackrest-doc
Architecture: any all
Version: 1:%!{PGBACKREST_VERSION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper-compat (= 13),
               libbz2-dev,
               liblz4-dev,
               libpq-dev,
               libssh2-1-dev,
               libssl-dev,
               libsystemd-dev,
               libxml2-dev,
               libyaml-dev,
               libzstd-dev,
               libcurl4-openssl-dev (>= 8.23.0),
               meson,
               pkgconf,
               python3 (>= 3.10) | python3-distutils,
               txt2man,
               zlib1g-dev
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
