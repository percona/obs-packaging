%global         debug_package %{nil}

%global __ospython %{_bindir}/python3.12

Name:           python3.12-systemd
Version:        235
Release:        1%{?dist}
Summary:        Python interface for libsystemd
License:        LGPL-2.1-or-later
URL:            https://github.com/systemd/python-systemd
Source0:        python3-systemd-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  pkgconfig
BuildRequires:  systemd-devel
BuildRequires:  python3.12-devel
BuildRequires:  python3.12-setuptools

Provides:       python3-systemd = %{version}-%{release}

%description
Python module for native access to libsystemd facilities: sending
structured messages to the journal, reading journal files, and querying
machine/boot identifiers. Needed by percona-patroni for systemd notify
support under the python3.12 interpreter stream.

%prep
%setup -q -n python3-systemd-%{version}

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=%{buildroot} --record=INSTALLED_FILES

%files -f INSTALLED_FILES
%license LICENSE.txt

%changelog
* Tue Sep 01 2026 Percona Development Team <info@percona.com> - 235-1
- Initial build of python-systemd 235 for python3.12 (needed by percona-patroni)
