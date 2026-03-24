%global debug_package %{nil}

Name:     gosu
Version:  1.0.0
Release:  1%{?dist}
Summary:  Lightweight Go-based su replacement for containers
License:  GPL-3.0-only
URL:      https://github.com/tianon/gosu
Source0:  gosu-%{version}.tar.gz
Source1:  go.mod
Source2:  vendor.tar.gz

BuildRequires: golang

%description
gosu is a simple tool that drops privileges to a given user and executes
the given process. It is designed to be used in Docker ENTRYPOINT scripts
where su and sudo have TTY and signal-forwarding issues.

%prep
%setup -q -n gosu-%{version}
cp %{SOURCE1} go.mod
tar -xzf %{SOURCE2}

%build
export CGO_ENABLED=0
go build -mod=vendor -ldflags='-d -s -w' -o gosu .

%install
install -Dm755 gosu %{buildroot}%{_sbindir}/gosu

%files
%license LICENSE
%doc README.md INSTALL.md
%attr(755, root, root) %{_sbindir}/gosu

%changelog
* Tue Mar 24 2026 Radoslav Dias <rdias@percona.com> - 1.11-1
- Initial packaging of gosu 1.11
