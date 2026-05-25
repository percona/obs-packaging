Name:           file-devel
Version:        5.33
Release:        27.el8_10
Summary:        Libraries and header files for file development
License:        BSD
URL:            https://www.darwinsys.com/file/
# Pre-extracted from AlmaLinux 8.10 PowerTools file-devel RPM (ABI-compatible with UBI-8)
Source0:        file-devel-%{version}-%{_arch}.tar.gz
ExclusiveArch:  x86_64 aarch64
Requires:       file-libs%{?_isa} = %{version}
%define _enable_debug_packages 0
%define debug_package %{nil}

%description
Libraries and header files for developing applications that use libmagic,
the file-type detection library.

%prep
%setup -q -c -n file-devel-%{version}

%build

%install
cp -a usr %{buildroot}/

%files
%{_includedir}/magic.h
%{_libdir}/libmagic.so
%{_mandir}/man3/libmagic.3.gz
