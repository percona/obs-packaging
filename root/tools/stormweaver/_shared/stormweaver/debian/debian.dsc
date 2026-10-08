Format: 3.0 (quilt)
Source: stormweaver
Binary: stormweaver
Architecture: any
Version: 1.0.0
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper (>= 10), cmake (>= 3.22), ninja-build, g++, pkg-config, libpq-dev (>= %!{STORMWEAVER_PG_MAJOR}~), libmariadb-dev, libcrypto++-dev, libssl-dev, zlib1g-dev, percona-python%!{PYFT_MINOR}t, percona-python%!{PYFT_MINOR}t-pytest
