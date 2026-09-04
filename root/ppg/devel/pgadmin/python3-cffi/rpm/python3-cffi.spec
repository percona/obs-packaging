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

Name:           %{python3_pkgprefix}-cffi
Version:        2.1.1
Release:        1%{?dist}
Summary:        C Foreign Function Interface for Python
License:        MIT-0
URL:            https://cffi.readthedocs.io/
Source0:        https://files.pythonhosted.org/packages/source/c/cffi/cffi-2.1.1.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
# Epoch 1 so this outranks the RHEL 9 python3.12-cffi 1.x (cryptography >= 49
# requires cffi >= 2.0)
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  libffi-devel
BuildRequires:  gcc

# cffi.FFI() imports pycparser (RHEL 9 package; auto-generated dist()
# requires are excluded, so the dependency must be explicit)
Requires:       %{python3_pkgprefix}-pycparser

%description
CFFI provides a convenient and reliable way to call compiled C code from
Python using interface declarations written in C.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4
(percona-pgadmin4) dependency stack (cryptography >= 49 needs cffi >= 2.0).

%prep
%autosetup -p1 -n cffi-%{version}

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -P -c "import cffi; import _cffi_backend; print(cffi.__version__)"

%files
# console script new in cffi 2.x
%{_bindir}/cffi-gen-src
%{python3_sitearch}/*

%changelog
* Tue Sep 01 2026 Percona Development Team <info@percona.com> - 1:2.1.1-1
- Package cffi 2.1.1 for Python 3.12 (cryptography 49 requires cffi >= 2.0;
  pgAdmin 4 dependency stack)
