%if 0%{?rhel} && 0%{?rhel} >= 8
%global __ospython        %{_bindir}/python3.12
%global python3_pkgprefix python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%else
%global __ospython        %{_bindir}/python3
%global python3_pkgprefix python3
%global python3_buildversion 3
%endif
%{expand: %%global py3ver %(echo `%{__ospython} -P -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitearch %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('platlib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-psycopg-c
Version:        3.3.4
Release:        1%{?dist}
Summary:        PostgreSQL database adapter for Python -- C optimisation distribution
License:        LGPL-3.0-only
URL:            https://psycopg.org/
Source0:        https://files.pythonhosted.org/packages/source/p/psycopg-c/psycopg_c-3.3.4.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  libpq-devel
BuildRequires:  gcc
# for the %check import
BuildRequires:  %{python3_pkgprefix}-psycopg

%description
PostgreSQL database adapter for Python -- C optimisation distribution.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n psycopg_c-3.3.4
# setuptools 68 (RHEL 9) cannot parse PEP 639 licence metadata: use the table form, drop license-files
sed -i -e 's/^license = "\(.*\)"$/license = {text = "\1"}/' -e '/^license-files = \[$/,/^\]$/d' -e '/^license-files = \[.*\]$/d' pyproject.toml
# setuptools 68 also predates [[tool.setuptools.ext-modules]] (added in 74.1):
# move the extension declarations into a setup.py shim (the 3.2.x layout).
# The single range spans both ext-modules tables (the end pattern only occurs
# in the second one); cmdclass moves into setup.py with them.
sed -i -e '/^\[\[tool\.setuptools\.ext-modules\]\]$/,/^sources = \["psycopg_c\/pq\.c"\]$/d' \
       -e '/^\[tool\.setuptools\.cmdclass\]$/,/^build_ext = /d' pyproject.toml
cat > setup.py <<'PYEOF'
import sys

sys.path.insert(0, "build_backend")

from setuptools import Extension, setup

from psycopg_build_ext import psycopg_build_ext

setup(
    ext_modules=[
        Extension(
            "psycopg_c._psycopg",
            ["psycopg_c/_psycopg.c", "psycopg_c/types/numutils.c"],
        ),
        Extension("psycopg_c.pq", ["psycopg_c/pq.c"]),
    ],
    cmdclass={"build_ext": psycopg_build_ext},
)
PYEOF

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -P -c "import psycopg; import psycopg_c"

%files
%{python3_sitearch}/*

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 3.3.4-1
- Package psycopg-c 3.3.4 for Python 3.12 (pgAdmin 4 dependency stack)
