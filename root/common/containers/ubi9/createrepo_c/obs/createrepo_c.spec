Name:           createrepo_c
Version:        0.20.1
Release:        1%{?dist}
Summary:        Creates a common metadata repository
License:        GPLv2+
URL:            https://github.com/rpm-software-management/createrepo_c

Source0:        https://github.com/rpm-software-management/createrepo_c/archive/%{version}/%{name}-%{version}.tar.gz

BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  bzip2-devel
BuildRequires:  glib2-devel
BuildRequires:  libcurl-devel
BuildRequires:  libxml2-devel
BuildRequires:  openssl-devel
BuildRequires:  sqlite-devel
BuildRequires:  xz-devel
BuildRequires:  zlib-devel
BuildRequires:  libzstd-devel
BuildRequires:  bash-completion
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  rpm-devel
BuildRequires:  libmodulemd-devel
BuildRequires:  file-devel

# drpm and zchunk disabled (not available in UBI/AlmaLinux 9)
# rpm-devel and libmodulemd-devel come from AlmaLinux 9 buildtools

Provides:       createrepo = %{version}-%{release}

%global debug_package %{nil}
%global __debug_install_post :

%description
C implementation of createrepo. The goal is to generate a common
metadata repository from a directory of rpm packages.

%package libs
Summary:        Library for repodata manipulation

%description libs
Libraries for manipulating repodata.

%package devel
Summary:        Library for repodata manipulation
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
Requires:       pkgconfig(glib-2.0)

%description devel
This package contains the createrepo_c C library and its header files.

%package -n python3-%{name}
Summary:        Python 3 bindings for the createrepo_c library
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
%{?python_provide:%python_provide python3-%{name}}

%description -n python3-%{name}
Python 3 bindings for the createrepo_c library.

%prep
%autosetup -p1 -n %{name}-%{version}

%build
%cmake \
    -DENABLE_DRPM=OFF \
    -DWITH_ZCHUNK=OFF \
    -DPYTHON_DESIRED=3
%cmake_build

%install
%cmake_install

# Compat symlinks for scripts that call createrepo
ln -sr %{buildroot}%{_bindir}/createrepo_c %{buildroot}%{_bindir}/createrepo
ln -sr %{buildroot}%{_bindir}/mergerepo_c %{buildroot}%{_bindir}/mergerepo

%files
%license COPYING
%doc README.md
%{_bindir}/createrepo_c
%{_bindir}/createrepo
%{_bindir}/mergerepo_c
%{_bindir}/mergerepo
%{_bindir}/modifyrepo_c
%{_bindir}/sqliterepo_c
%{_mandir}/man8/createrepo_c.8*
%{_mandir}/man8/mergerepo_c.8*
%{_mandir}/man8/modifyrepo_c.8*
%{_mandir}/man8/sqliterepo_c.8*
%dir %{_datadir}/bash-completion
%dir %{_datadir}/bash-completion/completions
%{_datadir}/bash-completion/completions/createrepo_c
%{_datadir}/bash-completion/completions/mergerepo_c
%{_datadir}/bash-completion/completions/modifyrepo_c
%{_datadir}/bash-completion/completions/sqliterepo_c

%files libs
%license COPYING
%{_libdir}/libcreaterepo_c.so.*

%files devel
%{_libdir}/libcreaterepo_c.so
%{_libdir}/pkgconfig/createrepo_c.pc
%{_includedir}/createrepo_c/

%files -n python3-%{name}
%{python3_sitearch}/createrepo_c/
%{python3_sitearch}/createrepo_c-*.egg-info

%changelog
* Wed Mar 18 2026 Admin <admin@obs.local> - 0.20.1-1
- Build for UBI 9, disabling drpm, zchunk, modulemd, legacy weakdeps
