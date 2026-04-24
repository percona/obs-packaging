Name:           umoci
Version:        0.6.0
Release:        1
Summary:        OCI image manipulation tool
License:        Apache-2.0
URL:            https://github.com/opencontainers/umoci
Source0:        umoci.linux.amd64
Source1:        umoci.linux.arm64

%description
umoci is a tool for creating and manipulating OCI images. It is used
by KIWI to build OCI/Docker container images.

%install
%ifarch x86_64
install -D -m 0755 %{SOURCE0} %{buildroot}%{_bindir}/umoci
%endif
%ifarch aarch64
install -D -m 0755 %{SOURCE1} %{buildroot}%{_bindir}/umoci
%endif

%files
%{_bindir}/umoci
