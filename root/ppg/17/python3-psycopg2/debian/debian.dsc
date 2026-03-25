Format: 3.0 (quilt)
Source: psycopg2
Binary: python3-psycopg2, python3-psycopg2-dbg
Architecture: any
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 9),
 python-all-dev | python3-all-dev,
 python-all-dbg | python3-all-dbg,
 dh-python,
 libpq-dev,
 python3-sphinx (>= 1.0.7+dfsg-1~),
 python3-setuptools
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz rpm.tar.gz
