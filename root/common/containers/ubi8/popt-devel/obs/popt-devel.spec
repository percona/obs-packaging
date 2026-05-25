Name:           popt-devel
Version:        1.18
Release:        1.el8
Summary:        Development files for the popt library
License:        MIT
URL:            http://rpm5.org/files/popt/
# Pre-extracted from AlmaLinux 8.10 BaseOS popt-devel RPM (ABI-compatible with UBI-8)
Source0:        popt-devel-%{version}-%{_arch}.tar.gz
ExclusiveArch:  x86_64 aarch64
Requires:       popt%{?_isa}
%define _enable_debug_packages 0
%define debug_package %{nil}

%description
Header files and libraries for developing applications that use the
popt command-line argument parsing library.

%prep
%setup -q -c -n popt-devel-%{version}

%build

%install
cp -a usr %{buildroot}/

%files
%{_includedir}/popt.h
%{_libdir}/libpopt.so
%{_libdir}/pkgconfig/popt.pc
%doc %{_docdir}/popt-devel/
%{_mandir}/man3/popt.3.gz
