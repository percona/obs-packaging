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

Name:           %{python3_pkgprefix}-pyasn1
Version:        0.6.4
Release:        1%{?dist}
Summary:        Pure-Python implementation of ASN.1 types and DER/BER/CER codecs (X.208)
License:        BSD-2-Clause
URL:            https://github.com/pyasn1/pyasn1
Source0:        https://files.pythonhosted.org/packages/source/p/pyasn1/pyasn1-0.6.4.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel

%description
Pure-Python implementation of ASN.1 types and DER/BER/CER codecs (X.208).

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n pyasn1-0.6.4

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import pyasn1"

%files
%{python3_sitelib}/*

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 0.6.4-1
- Package pyasn1 0.6.4 for Python 3.12 (pgAdmin 4 dependency stack)
