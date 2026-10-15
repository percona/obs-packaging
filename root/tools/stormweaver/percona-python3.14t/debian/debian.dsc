Format: 3.0 (quilt)
Source: percona-python3.14t
Binary: percona-python3.14t
Architecture: any
Version: %!{PYFT_VERSION}
Debtransform-Release: 1
Debtransform-Tar: Python-%!{PYFT_VERSION}.tar.xz
Debtransform-Files-Tar: debian.tar.gz
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper (>= 10), libssl-dev, libffi-dev, zlib1g-dev, libbz2-dev, liblzma-dev, libsqlite3-dev, libreadline-dev, libncurses-dev, libexpat1-dev, uuid-dev, libgdbm-dev, libgdbm-compat-dev
