%global debug_package %{nil}
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
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-alembic
Version:        1.19.1
Release:        1%{?dist}
Summary:        A database migration tool for SQLAlchemy
License:        MIT
URL:            https://alembic.sqlalchemy.org
Source0:        https://files.pythonhosted.org/packages/source/a/alembic/alembic-1.19.1.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# runtime dependencies, also needed by the %check import test
BuildRequires:  %{python3_pkgprefix}-sqlalchemy >= 1.4.23
BuildRequires:  %{python3_pkgprefix}-mako
BuildRequires:  %{python3_pkgprefix}-typing-extensions >= 4.12

Requires:       %{python3_pkgprefix}-sqlalchemy >= 1.4.23
Requires:       %{python3_pkgprefix}-mako
Requires:       %{python3_pkgprefix}-typing-extensions >= 4.12

%description
A database migration tool for SQLAlchemy.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n alembic-1.19.1
# setuptools 68 (RHEL 9) cannot parse PEP 639 licence metadata: use the table form, drop license-files
sed -i -e 's/^license = "\(.*\)"$/license = {text = "\1"}/' -e '/^license-files = \[$/,/^\]$/d' -e '/^license-files = \[.*\]$/d' pyproject.toml

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import alembic"

%files
%{python3_sitelib}/*
%{_bindir}/alembic

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 1.19.1-1
- Package alembic 1.19.1 for Python 3.12 (pgAdmin 4 dependency stack)
