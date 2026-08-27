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
%{expand: %%global py3ver %(echo `%{__ospython} -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitearch %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('platlib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-backports-zstd
Version:        1.7.0
Release:        1%{?dist}
Summary:        Backport of compression.zstd
License:        PSF-2.0
URL:            https://github.com/rogdham/backports.zstd
Source0:        https://files.pythonhosted.org/packages/source/b/backports.zstd/backports_zstd-1.7.0.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  libzstd-devel
BuildRequires:  gcc

%description
Backport of compression.zstd.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n backports_zstd-1.7.0

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -c "import backports.zstd"

%files
%{python3_sitearch}/*

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 1.7.0-1
- Package backports.zstd 1.7.0 for Python 3.12 (pgAdmin 4 dependency stack)
