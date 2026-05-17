%global debug_package %{nil}

%ifarch aarch64
%global go_tarball go1.26.3.linux-arm64.tar.gz
%else
%global go_tarball go1.26.3.linux-amd64.tar.gz
%endif

Name:     golang-1.26
Version:  1.26.3
Release:  1%{?dist}
Summary:  Go programming language toolchain version 1.26
License:  BSD-3-Clause
URL:      https://go.dev
Source0:  go1.26.3.linux-amd64.tar.gz
Source1:  go1.26.3.linux-arm64.tar.gz

ExclusiveArch: x86_64 aarch64
AutoReq: no

Provides: golang-go
Provides: golang

%description
The Go programming language toolchain, version 1.26.3,
installed from the official binary distribution.

%prep
# binary distribution — nothing to prepare

%build
# binary distribution — nothing to build

%install
mkdir -p %{buildroot}/usr/local
tar xzf %{_sourcedir}/%{go_tarball} -C %{buildroot}/usr/local
mkdir -p %{buildroot}%{_bindir}
ln -sf /usr/local/go/bin/go %{buildroot}%{_bindir}/go
ln -sf /usr/local/go/bin/gofmt %{buildroot}%{_bindir}/gofmt

%files
/usr/local/go
%{_bindir}/go
%{_bindir}/gofmt

%changelog
* Sat May 17 2026 Percona Development Team <info@percona.com> - 1.26.3-1
- Package Go 1.26.3 binary distribution for RockyLinux 9
