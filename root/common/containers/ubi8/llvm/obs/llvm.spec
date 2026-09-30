%global __strip /bin/true
%global __brp_strip %{nil}
%global __brp_mangle_shebangs %{nil}
%global __brp_check_rpaths %{nil}
%define debug_package %{nil}
%define _enable_debug_packages 0

Name:           llvm
Version:        21.1.8
Release:        1%{?dist}
Summary:        The Low Level Virtual Machine
License:        Apache-2.0 WITH LLVM-exception OR NCSA
URL:            http://llvm.org
ExclusiveArch:  x86_64 aarch64

# Non-modular repackaging of the Rocky Linux 8 AppStream llvm-toolset:rhel8
# 21.1.8 RPMs (llvm, llvm-libs, llvm-filesystem) for the UBI 8 container
# images. Every -llvmjit subpackage built on UBI_8 requires llvm >= 19 and
# links against the llvm-toolset:rhel8 module's llvm 21.1.8, but the real
# ubi8/ubi-minimal image's microdnf refuses module-stream packages
# (modularity label, no module metadata in OBS's in-build repository), so
# the binary content of the AppStream RPMs is repackaged here as plain,
# non-modular packages with the same names, version and content.
Source0:        llvm-%{version}-%{_arch}.rpm
Source1:        llvm-libs-%{version}-%{_arch}.rpm
Source2:        llvm-filesystem-%{version}-%{_arch}.rpm

BuildRequires:  rpm
BuildRequires:  cpio

# Mirrors the original llvm.rpm's explicit cross-subpackage version pin
# (rpm -qRp llvm-21.1.8-*.rpm); all other Requires are ELF/interpreter
# dependencies that rpm's automatic dependency generator re-derives from
# the packaged binaries.
Requires:       llvm-libs%{?_isa} = %{version}-%{release}

%description
LLVM is a compiler infrastructure designed for compile-time, link-time,
runtime, and idle-time optimization of programs from arbitrary programming
languages. The compiler infrastructure includes mirror sets of programming
tools as well as libraries with equivalent functionality.

%package libs
Summary:        LLVM shared libraries
# Mirrors the original llvm-libs.rpm's explicit cross-subpackage version
# pin (rpm -qRp llvm-libs-21.1.8-*.rpm); all other Requires/Provides
# (libLLVM.so, libLTO.so, libRemarks.so, ...) are auto-generated ELF
# soname deps that rpm re-derives from the packaged binaries.
Requires:       llvm-filesystem%{?_isa} = %{version}-%{release}

%description libs
Shared libraries for the LLVM compiler infrastructure.

%package filesystem
Summary:        Filesystem package that owns the versioned llvm prefix

%description filesystem
This package owns the versioned llvm prefix directory: $libdir/llvm$version

%prep
%setup -q -c -T
mkdir -p llvm && cd llvm && rpm2cpio %{SOURCE0} | cpio -idm --quiet && cd ..
mkdir -p llvm-libs && cd llvm-libs && rpm2cpio %{SOURCE1} | cpio -idm --quiet && cd ..
mkdir -p llvm-filesystem && cd llvm-filesystem && rpm2cpio %{SOURCE2} | cpio -idm --quiet && cd ..

%install
cp -a llvm-filesystem/. llvm-libs/. llvm/. %{buildroot}/

rpm -qlp %{SOURCE0} | sed 's/^/\//' | grep -v '^//$' > llvm.files.raw
rpm -qlp %{SOURCE1} | sed 's/^/\//' | grep -v '^//$' > llvm-libs.files.raw
rpm -qlp %{SOURCE2} | sed 's/^/\//' | grep -v '^//$' > llvm-filesystem.files.raw

for base in llvm llvm-libs llvm-filesystem; do
  > ${base}.files
  while read -r p; do
    if [ -d "%{buildroot}$p" ] && [ ! -L "%{buildroot}$p" ]; then
      echo "%dir $p" >> ${base}.files
    else
      echo "$p" >> ${base}.files
    fi
  done < ${base}.files.raw
done

%files -f llvm.files
%files libs -f llvm-libs.files
%files filesystem -f llvm-filesystem.files

%changelog
* Wed Sep 30 2026 Percona Development <info@percona.com> - 21.1.8-1
- Non-modular repackaging of the Rocky Linux 8 AppStream llvm 21.1.8 RPMs for the UBI 8 container images
