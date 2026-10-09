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

Name:           %{python3_pkgprefix}-pillow
Version:        12.3.0
Release:        1%{?dist}
Summary:        Python Imaging Library (Fork)
License:        MIT-CMU
URL:            https://python-pillow.github.io
Source0:        https://files.pythonhosted.org/packages/source/p/pillow/pillow-12.3.0.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  libjpeg-turbo-devel
BuildRequires:  zlib-devel
BuildRequires:  gcc
BuildRequires:  %{python3_pkgprefix}-pybind11

%description
Python Imaging Library (Fork).

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n pillow-12.3.0

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index -C platform-guessing=disable -C zlib=enable -C jpeg=enable -C tiff=disable -C freetype=disable -C raqm=disable -C lcms=disable -C webp=disable -C xcb=disable -C jpeg2000=disable -C imagequant=disable -C avif=disable --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -P -c "import PIL"

%files
%{python3_sitearch}/*

%changelog
* Fri Sep 04 2026 Percona Development Team <info@percona.com> - 1:12.3.0-1
- Update to pillow 12.3.0 (12 HIGH CVEs: CVE-2026-25990, -40192, -42311,
  -54058/9/60, -55379/80, -59197/9/200/204/205); needs setuptools>=77 + pybind11

* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 11.1.0-1
- Package pillow 11.1.0 for Python 3.12 (pgAdmin 4 dependency stack)
