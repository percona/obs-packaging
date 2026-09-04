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

Name:           %{python3_pkgprefix}-setuptools
Version:        80.10.2
Release:        1%{?dist}
Summary:        Easily download, build, install, upgrade, and uninstall Python packages
License:        MIT
URL:            https://github.com/pypa/setuptools
Source0:        https://files.pythonhosted.org/packages/source/s/setuptools/setuptools-80.10.2.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
# Epoch 1 so this outranks RHEL 9's python3.12-setuptools 68.2.2 for every
# setuptools-backed package in this project. Chosen over the newest 84.x line,
# which removes pkg_resources (still imported by older packages) and raises the
# Python floor to 3.10; 80.10.2 still ships pkg_resources and is >=3.9.
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel

# setuptools provides pkg_resources; keep an explicit Provides so consumers can
# depend on it by name if needed (auto python3.12dist provides are excluded).
Provides:       %{python3_pkgprefix}-pkg_resources = %{epoch}:%{version}-%{release}

%description
setuptools is a fully-featured, actively-maintained, and stable library for
packaging Python projects. Built for Python 3.12 from the PyPI sdist; the
stack-wide build backend for the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n setuptools-%{version}

%build
# setuptools self-bootstraps: its pyproject build-system.requires is empty, so
# the buildroot's RHEL setuptools 68 builds the 80.10.2 wheel.
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import setuptools, pkg_resources; print(setuptools.__version__)"

%files
%{python3_sitelib}/*

%changelog
* Fri Sep 04 2026 Percona Development Team <info@percona.com> - 1:80.10.2-1
- Package setuptools 80.10.2 for Python 3.12 — stack-wide build backend so the
  pgAdmin dependency stack can build setuptools>=77 packages (pillow 12,
  jaraco.context 6.1) and use native PEP 639 metadata
