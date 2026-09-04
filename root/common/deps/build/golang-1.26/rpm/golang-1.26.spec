%global debug_package %{nil}

# Official Go binary distribution ships as-is: it contains foreign-arch
# .syso objects and ELF testdata that strip cannot parse (fatal with the
# older brp-strip of RHEL 9.6's redhat-rpm-config 209), and stripping the
# upstream toolchain is unwanted anyway.
%global __brp_strip %{nil}
%global __brp_strip_static_archive %{nil}
%global __brp_strip_lto %{nil}
%global __brp_strip_comment_note %{nil}

%ifarch aarch64
%global go_tarball go%!{GOLANG_VERSION}.linux-arm64.tar.gz
%else
%global go_tarball go%!{GOLANG_VERSION}.linux-amd64.tar.gz
%endif

Name:     golang-1.26
Version:  %!{GOLANG_VERSION}
Release:  1%{?dist}
Summary:  Go programming language toolchain version 1.26
License:  BSD-3-Clause
URL:      https://go.dev
Source0:  go%!{GOLANG_VERSION}.linux-amd64.tar.gz
Source1:  go%!{GOLANG_VERSION}.linux-arm64.tar.gz

ExclusiveArch: x86_64 aarch64
AutoReq: no

Provides: golang-go = %{version}
Provides: golang = %{version}

%description
The Go programming language toolchain, version %!{GOLANG_VERSION},
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
* Mon Aug 24 2026 Percona Development Team <info@percona.com> - %!{GOLANG_VERSION}-1
- Package Go %!{GOLANG_VERSION} binary distribution for RHEL based distributions (CVE fixes)

* Mon Jul 13 2026 Percona Development Team <info@percona.com> - 1.26.5-1
- Package Go 1.26.5 binary distribution for RHEL based distributions

* Mon Jun 08 2026 Percona Development Team <info@percona.com> - 1.26.4-1
- Package Go 1.26.4 binary distribution for RHEL based distributions

* Sun May 17 2026 Percona Development Team <info@percona.com> - 1.26.3-1
- Package Go 1.26.3 binary distribution for RockyLinux 9
