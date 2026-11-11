Name:           libzstd-devel
Version:        1.4.4
Release:        1.el8
Summary:        Header files for Zstd library
License:        BSD and GPLv2
URL:            https://github.com/facebook/zstd
# Pre-extracted from AlmaLinux 8.10 BaseOS libzstd-devel RPM (ABI-compatible with UBI-8).
# UBI 8 BaseOS ships libzstd-devel for aarch64 but not for x86_64, where
# createrepo_c (BuildRequires) and rpm-devel (rpm.pc: Requires.private libzstd)
# need it, so this repackage is x86_64-only.
Source0:        libzstd-devel-%{version}-%{_arch}.tar.gz
ExclusiveArch:  x86_64
Requires:       libzstd%{?_isa} = %{version}
%define _enable_debug_packages 0
%define debug_package %{nil}

%description
Header files for Zstd library.

%prep
%setup -q -c -n libzstd-devel-%{version}

%build

%install
cp -a usr %{buildroot}/

%files
%{_includedir}/zbuff.h
%{_includedir}/zdict.h
%{_includedir}/zstd.h
%{_includedir}/zstd_errors.h
%{_libdir}/libzstd.so
%{_libdir}/pkgconfig/libzstd.pc
