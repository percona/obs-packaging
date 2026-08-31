%global debug_package %{nil}

Name:     local-npm-registry
Version:  %!{LOCAL_NPM_REGISTRY_VERSION}
Release:  1%{?dist}
Summary:  Localhost-only npm registry for offline builds
License:  GPL-3.0-or-later
URL:      https://github.com/openSUSE/npm-localhost-proxy
Source0:  local_npm_registry-v%!{LOCAL_NPM_REGISTRY_VERSION}.tar.gz

BuildArch: noarch

# The launcher runs on /usr/bin/node; both come from this repository's own
# nodejs package (the CS9 nodejs:22 module port — module streams are not
# exposed in OBS DoD repos). The epoch is mandatory: EL9's nodejs carries
# Epoch 1, so a bare ">= 20" is satisfied by 1:16.20.2.
Requires: nodejs >= 1:22
Requires: npm

%description
local-npm-registry serves npm packages on a localhost address so that
`npm install` can run in a non-networked environment such as an OBS build
root. The package tarballs are taken from the node_modules.obscpio archive
that the OBS `node_modules` source service produces for the consuming
package (e.g. percona-pgadmin4).

Ported from openSUSE devel:languages:javascript/local-npm-registry.

%prep
%autosetup -n local_npm_registry-v%{version}

%build
# dist/ and node_modules/ are pre-bundled in the release tarball — nothing to
# build (building would require the very registry this package provides).

%install
mkdir -p %{buildroot}%{_datadir}/%{name}
mkdir -p %{buildroot}%{_bindir}
cp -r dist node_modules %{buildroot}%{_datadir}/%{name}
cat > %{buildroot}%{_bindir}/local-npm-registry << EOF
#!/usr/bin/node
(async () => {
  const registry = await import("%{_datadir}/%{name}/dist/index.js");
  registry.mainEntryFunction();
})();
EOF

%files
%license COPYING
%doc README.md
%attr(755,root,root) %{_bindir}/local-npm-registry
%{_datadir}/%{name}

%changelog
* Wed Aug 26 2026 Percona Development Team <info@percona.com> - %!{LOCAL_NPM_REGISTRY_VERSION}-1
- Package local-npm-registry %!{LOCAL_NPM_REGISTRY_VERSION} (openSUSE npm-localhost-proxy) for UBI 9,
  the offline npm registry used by the percona-pgadmin4 build
