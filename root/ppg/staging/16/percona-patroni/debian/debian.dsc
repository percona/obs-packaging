Format: 3.0 (quilt)
Source: percona-patroni
Binary: percona-patroni, percona-patroni-doc
Architecture: all
Version: %!{PATRONI_VERSION}
Maintainer: Percona Development Team <info@percona.com>
Build-Depends:
 debhelper (>= 10),
 dh-python,
 libjs-jquery,
 libjs-mathjax,
 libjs-underscore,
 pyflakes3,
 python3,
 python3-boto | python3-boto3,
 python3-click (>= 4.1),
 python3-consul,
 python3-dateutil,
 python3-dnspython,
 python3-doc,
 python3-etcd,
 python3-flake8,
 python3-kazoo,
 python3-mccabe,
 python3-kubernetes,
 python3-mock,
 python3-prettytable (>= 0.7),
 python3-psutil,
 python3-psycopg2 (>= 2.6.1),
 python3-pycodestyle,
 python3-pysyncobj,
 python3-pytest,
 python3-pytest-cov,
 python3-setuptools,
 python3-sphinx,
 python3-sphinx-rtd-theme,
 python3-sphinxcontrib.apidoc,
 python3-tzlocal,
 python3-yaml,
 python3-ydiff,
 sphinx-common,
 python3-systemd
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz