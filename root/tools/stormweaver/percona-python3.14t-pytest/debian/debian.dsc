Format: 3.0 (quilt)
Source: percona-python3.14t-pytest
Binary: percona-python3.14t-pytest
Architecture: all
Version: %!{PYTEST_VERSION}
Debtransform-Release: %!{BUNDLE_RELEASE}
Debtransform-Tar: pytest-%!{PYTEST_VERSION}.tar.gz
Debtransform-Files-Tar: debian.tar.gz
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper (>= 10), percona-python%!{PYFT_MINOR}t
