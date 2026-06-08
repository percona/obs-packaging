%global debug_package %{nil}

Name:     gosu
Version:  1.0.0
Release:  1%{?dist}
Summary:  Lightweight Go-based su replacement for containers
License:  GPL-3.0-only
URL:      https://github.com/tianon/gosu
Source0:  gosu-%{version}.tar.gz
Source2:  vendor.tar.gz

BuildRequires: golang >= 1.26.4

%description
gosu is a simple tool that drops privileges to a given user and executes
the given process. It is designed to be used in Docker ENTRYPOINT scripts
where su and sudo have TTY and signal-forwarding issues.

%prep
%setup -q -n gosu-%{version}
tar -xzf %{SOURCE2}

%build
export CGO_ENABLED=0
go build -mod=vendor -trimpath -ldflags='-d -w' -o gosu .

%install
install -Dm755 gosu %{buildroot}%{_sbindir}/gosu

%files
%license LICENSE
%doc README.md INSTALL.md
%attr(755, root, root) %{_sbindir}/gosu

%changelog
* Tue Mar 24 2026 Ricardo Dias <ricardo.dias@percona.com> - 1.19-1
- Initial packaging of gosu 1.19
