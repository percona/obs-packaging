Name:           umoci
Version:        0.4.7
Release:        1
Summary:        OCI image manipulation tool
License:        Apache-2.0
URL:            https://github.com/opencontainers/umoci
Source0:        umoci.amd64
BuildArch:      x86_64
ExclusiveArch:  x86_64

%description
umoci is a tool for creating and manipulating OCI images. It is used
by KIWI to build OCI/Docker container images.

%install
install -D -m 0755 %{SOURCE0} %{buildroot}%{_bindir}/umoci

%files
%{_bindir}/umoci
