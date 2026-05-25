Name:           rpm-devel
Version:        4.14.3
Release:        32.el8_10
Summary:        Development files for manipulating RPM packages
License:        GPLv2+
URL:            https://rpm.org
# Pre-extracted from AlmaLinux 8.10 BaseOS rpm-devel RPM (ABI-compatible with UBI-8)
Source0:        rpm-devel-%{version}-%{_arch}.tar.gz
ExclusiveArch:  x86_64 aarch64
Requires:       rpm-libs%{?_isa}
Requires:       rpm-build-libs%{?_isa}
Requires:       popt-devel%{?_isa}
%define _enable_debug_packages 0
%define debug_package %{nil}

%description
Header files and libraries for developing applications that manipulate
RPM packages using the RPM library (librpm).

%prep
%setup -q -c -n rpm-devel-%{version}

%build

%install
cp -a usr %{buildroot}/
# Remove .build-id entries — handled by the build system
rm -rf %{buildroot}/usr/lib/.build-id %{buildroot}/usr/lib

%files
%{_bindir}/rpmgraph
%{_includedir}/rpm/
%{_libdir}/librpm.so
%{_libdir}/librpmbuild.so
%{_libdir}/librpmio.so
%{_libdir}/librpmsign.so
%{_libdir}/pkgconfig/rpm.pc
%{_mandir}/man8/rpmgraph.8.gz
