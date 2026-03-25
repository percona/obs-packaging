Format: 3.0 (quilt)
Source: percona-pgbackrest
Binary: percona-pgbackrest, percona-pgbackrest-doc
Architecture: any all
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper-compat (= 10),
               libbz2-dev,
               liblz4-dev,
               libpq-dev,
               libssh2-1-dev,
               libssl-dev,
               libxml-checker-perl,
               libxml2-dev,
               libyaml-dev,
               libyaml-libyaml-perl (>= 0.67),
               libzstd-dev,
               meson,
               perl,
               pkgconf,
               python3 (>= 3.10) | python3-distutils,
               txt2man,
               zlib1g-dev
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz rpm.tar.gz
