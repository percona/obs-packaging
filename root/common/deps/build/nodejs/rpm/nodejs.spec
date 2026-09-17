# Node.js 22 for UBI 9, ported from the CentOS Stream 9 nodejs:22 module
# dist-git (rpms/nodejs, branch stream-nodejs-22-rhel-9.9.0) — the spec RHEL
# builds the EL9 nodejs:22 module from. EL9 module streams are not exposed in
# OBS download-on-demand repos (only the default nodejs 16 stream is), and
# pgAdmin 4's webpack toolchain needs Node >= 20, so we build it ourselves.
#
# Deviations from the CS9 spec (EL9-only trims aside):
#  - two-argument "%%bcond name N" syntax replaced with classic
#    %%bcond_with/%%bcond_without (EL9 rpm 4.16 predates it)
#  - ExclusiveArch hardcoded (%%nodejs_arches is defined by macro packages we
#    do not carry in the buildroot at SRPM parse time)
#  - OBS owns the Release tag (rewrites every Release: line with its build
#    counter), so nodejs_envr is release-free (epoch:version) and the npm
#    subpackage inherits the main EVR instead of carrying npm's own
#    epoch/version/release — npm's real version is still exposed through
#    Provides: npm(npm)
#  - the v8-X.Y-devel subpackage is dropped (nothing here consumes it and its
#    constructed EVR fights the OBS release counter); the v8 compat symlinks
#    that belonged to it are not created
#  - nodejs-tarball.sh (Source200 upstream) is not carried: Source0 is the
#    already-stripped tarball fetched from the public CS9 lookaside

%global nodejs_pkg_major 22

%global nodejs_default %{nodejs_pkg_major}

%global nodejs_default_sitelib %{_prefix}/lib/node_modules
%global nodejs_private_sitelib %{nodejs_default_sitelib}

# EL9 (rhel < 10, nodejs 22): bundle cjs-module-lexer, undici, libuv and
# sqlite; link against the system zlib, brotli and openssl.
%bcond_without bundled_cjs_module_lexer
%bcond_without bundled_undici
%bcond_without bundled_libuv
%bcond_with bundled_zlib
%bcond_without bundled_sqlite

# LTO is currently broken on Node.js builds
%define _lto_cflags %{nil}

# Heavy-handed approach to avoiding issues with python
# bytecompiling files in the node_modules/ directory
%global __python %{python3}

%global baserelease 2

%{?!_pkgdocdir:%global _pkgdocdir %{_docdir}/%{name}-%{version}}

# == Node.js Version ==
%global nodejs_epoch 1
%global nodejs_major 22
%global nodejs_minor 23
%global nodejs_patch 1
# nodejs_soversion - from NODE_MODULE_VERSION in src/node_version.h
%global nodejs_soversion 127
%global nodejs_abi %{nodejs_soversion}
%global nodejs_version %{nodejs_major}.%{nodejs_minor}.%{nodejs_patch}
# Release-free EVR for inter-subpackage deps: OBS rewrites the Release tag
# with its own build counter, so a release-locked envr would never match.
%global nodejs_envr %{nodejs_epoch}:%{nodejs_version}

%global nodejs_datadir %{_datarootdir}/node-%{nodejs_pkg_major}

# == Bundled Dependency Versions ==
# v8 - from deps/v8/include/v8-version.h
%global v8_epoch 3
%global v8_major 12
%global v8_minor 4
%global v8_build 254
%global v8_patch 21
%global v8_version %{v8_major}.%{v8_minor}.%{v8_build}.%{v8_patch}

# zlib - from deps/zlib/zlib.h
%global zlib_version 1.3.1

# c-ares - from deps/cares/include/ares_version.h
%global c_ares_version 1.34.6

# llhttp - from deps/llhttp/include/llhttp.h
%global llhttp_version 9.4.2

# libuv - from deps/uv/include/uv/version.h
%global libuv_version 1.51.0

# nghttp2 - from deps/nghttp2/lib/includes/nghttp2/nghttp2ver.h
%global nghttp2_version 1.69.0

# nghttp3 - from deps/ngtcp2/nghttp3/lib/includes/nghttp3/version.h
%global nghttp3_version 1.6.0

# ngtcp2 from deps/ngtcp2/ngtcp2/lib/includes/ngtcp2/version.h
%global ngtcp2_version 1.11.0

# ICU - from tools/icu/current_ver.dep
%global icu_major 78
%global icu_minor 2
%global icu_version %{icu_major}.%{icu_minor}

%global icudatadir %{nodejs_datadir}/icudata
%{!?little_endian: %global little_endian %(%{python3} -c "import sys;print (0 if sys.byteorder=='big' else 1)")}
# " this line just fixes syntax highlighting for vim that is confused by the above and continues literal

# simdutf from deps/simdutf/simdutf.h
%global simdutf_version 6.4.2

# OpenSSL minimum version
%global openssl30_minimum 1:3.0.2

# punycode - from lib/punycode.js
%global punycode_version 2.1.0

# npm - from deps/npm/package.json
%global npm_version 10.9.8

# uvwasi - from deps/uvwasi/include/uvwasi.h
%global uvwasi_version 0.0.23

# histogram_c - assumed from timestamps
%global histogram_version 0.11.9

# sqlite - from deps/sqlite/sqlite3.h
%global sqlite_version 3.51.3


Name: nodejs
Epoch: %{nodejs_epoch}
Version: %{nodejs_version}
Release: %{baserelease}%{?dist}
Summary: JavaScript runtime
License: Apache-2.0 AND Artistic-2.0 AND BSD-2-Clause AND BSD-3-Clause AND BlueOak-1.0.0 AND CC-BY-3.0 AND CC0-1.0 AND ISC AND MIT
Group: Development/Languages
URL: http://nodejs.org/
Vendor: Percona, LLC
Packager: Percona Development Team <https://jira.percona.com>

ExclusiveArch: x86_64 aarch64

# nodejs bundles openssl, but RHEL uses the system version, so openssl is
# removed completely from this tarball (CS9 lookaside, sha512-addressed).
Source0: node-v%{nodejs_version}-stripped.tar.gz
Source1: npmrc
Source2: btest402.js
# The binary data that icu-small can use to get icu-full capability
Source3: https://github.com/unicode-org/icu/releases/download/release-%{icu_major}.%{icu_minor}/icu4c-%{icu_major}.%{icu_minor}-data-bin-b.zip
Source4: https://github.com/unicode-org/icu/releases/download/release-%{icu_major}.%{icu_minor}/icu4c-%{icu_major}.%{icu_minor}-data-bin-l.zip
Source201: npmrc.builtin.in
Source202: nodejs.pc.in
Source300: test-runner.sh
Source301: test-should-pass.txt

Patch: 0001-Remove-unused-OpenSSL-config.patch
Patch: 0003-fips-disable-options.patch
Patch: 0001-CVE-2026-25547-braces-expansion.patch
# npm deps patches
Patch: 0002-CVE-2026-42338-npm-ip-address-security-fix.patch
Patch: 0003-CVE-2026-13149-brace-expansion-unbound-recursion.patch
Patch: 0003-CVE-2026-59873-CVE-2026-59874-tar-rebase-to-7.5.19.patch

%global pkgname nodejs

BuildRequires: make
BuildRequires: python3-devel
BuildRequires: python3-setuptools
BuildRequires: python3-jinja2
%if %{with bundled_zlib}
Provides: bundled(zlib) = %{zlib_version}
%else
BuildRequires: zlib-devel
%endif
BuildRequires: brotli-devel
BuildRequires: gcc >= 8.3.0
BuildRequires: gcc-c++ >= 8.3.0

BuildRequires: pkgconf
BuildRequires: jq

# needed to generate bundled provides for npm dependencies
BuildRequires: nodejs-packaging

BuildRequires: chrpath
BuildRequires: libatomic
BuildRequires: ninja-build
BuildRequires: unzip

Provides: nodejs = %{nodejs_envr}

%if %{with bundled_libuv}
Provides:      bundled(libuv) = %{libuv_version}
%else
BuildRequires: libuv-devel >= 1:%{libuv_version}
Requires:      libuv >= 1:%{libuv_version}
%endif

# Node.js frequently bumps these faster than the distro can follow.
Provides: bundled(nghttp2) = %{nghttp2_version}
Provides: bundled(nghttp3) = %{nghttp3_version}
Provides: bundled(ngtcp2) = %{ngtcp2_version}
Provides: bundled(llhttp) = %{llhttp_version}

Requires: openssl >= %{openssl30_minimum}
BuildRequires: openssl-devel >= %{openssl30_minimum}
%global ssl_configure --shared-openssl --openssl-conf-name=openssl_conf

# we need the system certificate store
Requires: ca-certificates

Requires: %{pkgname}-libs%{?_isa} = %{nodejs_envr}

Recommends: %{pkgname}-full-i18n%{?_isa} = %{nodejs_envr}
Recommends: npm = %{nodejs_envr}

# ABI virtual provides
Provides: nodejs(abi) = %{nodejs_abi}
Provides: nodejs(abi%{nodejs_major}) = %{nodejs_abi}

# this corresponds to the "engine" requirement in package.json
Provides: nodejs(engine) = %{nodejs_version}

Conflicts: node <= 0.3.2-12

# punycode was absorbed into the standard library in v0.6
Provides: nodejs-punycode = %{punycode_version}
Provides: npm(punycode) = %{punycode_version}

# Node.js forked c-ares in an incompatible way; bundled.
Provides: bundled(c-ares) = %{c_ares_version}

# v8 cannot be built shared any more; bundled.
Provides: bundled(v8) = %{v8_version}

# Node.js pins its own ICU; bundled.
Provides: bundled(icu) = %{icu_version}

Provides: bundled(uvwasi) = %{uvwasi_version}
Provides: bundled(histogram) = %{histogram_version}
Provides: bundled(simdutf) = %{simdutf_version}
Provides: bundled(ada) = 2.9.2

%if %{with bundled_cjs_module_lexer}
Provides: bundled(nodejs-cjs-module-lexer) = 2.2.0
%else
BuildRequires: nodejs-cjs-module-lexer
Requires: nodejs-cjs-module-lexer
%endif

%if %{with bundled_undici}
Provides: bundled(nodejs-undici) = 6.27.0
%else
BuildRequires: nodejs-undici
Requires: nodejs-undici
%endif

%if %{with bundled_sqlite}
Provides: bundled(sqlite) = %{sqlite_version}
%else
BuildRequires: pkgconfig(sqlite3) >= 3.45
%endif


%description
Node.js is a platform built on Chrome's JavaScript runtime
for easily building fast, scalable network applications.
Node.js uses an event-driven, non-blocking I/O model that
makes it lightweight and efficient, perfect for data-intensive
real-time applications that run across distributed devices.

%package -n %{pkgname}-devel
Summary: JavaScript runtime - development headers
Group: Development/Languages
Requires: %{pkgname}%{?_isa} = %{nodejs_envr}
Requires: %{pkgname}-libs%{?_isa} = %{nodejs_envr}
Requires: openssl-devel%{?_isa}
%if !%{with bundled_zlib}
Requires: zlib-devel%{?_isa}
%endif
Requires: brotli-devel%{?_isa}
Requires: nodejs-packaging

%if %{without bundled_libuv}
Requires: libuv-devel%{?_isa}
%endif

Provides: nodejs-devel = %{nodejs_envr}
Provides: nodejs-devel-pkg = %{nodejs_envr}
Conflicts: nodejs-devel-pkg


%description -n %{pkgname}-devel
Development headers for the Node.js JavaScript runtime.


%package -n %{pkgname}-libs
Summary: Node.js and v8 libraries

# Compatibility for obsolete v8 package
%if 0%{?__isa_bits} == 64
Provides: libv8.so.%{v8_major}()(64bit) = %{v8_epoch}:%{v8_version}
Provides: libv8_libbase.so.%{v8_major}()(64bit) = %{v8_epoch}:%{v8_version}
Provides: libv8_libplatform.so.%{v8_major}()(64bit) = %{v8_epoch}:%{v8_version}
%else
Provides: libv8.so.%{v8_major} = %{v8_epoch}:%{v8_version}
Provides: libv8_libbase.so.%{v8_major} = %{v8_epoch}:%{v8_version}
Provides: libv8_libplatform.so.%{v8_major} = %{v8_epoch}:%{v8_version}
%endif

Provides: v8 = %{v8_epoch}:%{v8_version}
Provides: v8%{?_isa} = %{v8_epoch}:%{v8_version}
Obsoletes: v8 < 1:6.7.17-10

Provides: nodejs-libs = %{nodejs_envr}

%description -n %{pkgname}-libs
Libraries to support Node.js and provide stable v8 interfaces.


%package -n %{pkgname}-full-i18n
Summary: Non-English locale data for Node.js
Requires: %{pkgname}%{?_isa} = %{nodejs_envr}

%description -n %{pkgname}-full-i18n
Optional data files to provide full-icu support for Node.js. Remove this
package to save space if non-English locales are not needed.


%package -n npm
Summary: Node.js Package Manager

# npm inherits the nodejs EVR (see the header comment); the real npm version
# is exposed via the virtual provide below and asserted in %%check.
Requires: %{pkgname} = %{nodejs_envr}

# Do not add epoch to the virtual NPM provides or it will break
# the automatic dependency-generation script.
Provides: npm(npm) = %{npm_version}

# Obsolete the distro npm (EL9 ships 1:8.x with nodejs 16)
Obsoletes: npm < 1:9


%description -n npm
npm is a package manager for node.js. You can use it to install and publish
your node programs. It manages dependencies and does other cool stuff.


%package -n %{pkgname}-docs
Summary: Node.js API documentation
Group: Documentation
BuildArch: noarch
Requires(meta): %{pkgname} = %{nodejs_envr}

Provides: nodejs-docs = %{nodejs_envr}


%description -n %{pkgname}-docs
The API documentation for the Node.js JavaScript runtime.


%prep
%autosetup -p1 -n node-v%{nodejs_version}

# remove bundled dependencies that we aren't building
%if !%{with bundled_zlib}
rm -rf deps/zlib
%endif

rm -rf deps/brotli
rm -rf deps/v8/third_party/jinja2
rm -rf tools/inspector_protocol/jinja2

%if %{without bundled_cjs_module_lexer}
rm -rf deps/cjs-module-lexer
%endif

%if %{without bundled_undici}
rm -rf deps/undici
%endif

%if %{without bundled_sqlite}
rm -rf deps/sqlite
%endif

# Replace any instances of unversioned python with python3
pfiles=( $(grep -rl python) )
%py3_shebang_fix ${pfiles[@]}


%build

# Decrease debuginfo verbosity to reduce memory consumption during final
# library linking
%global optflags %(echo %{optflags} | sed 's/-g /-g1 /')

export CC='%{__cc}'
export CXX='%{__cxx}'
export NODE_GYP_FORCE_PYTHON=%{python3}

# 2022-07-14: There's a bug in either torque or gcc that causes a
# segmentation fault on ppc64le and s390x if compiled with -O2. Things
# run fine on -O1 and -O3, so we'll just go with -O3 (like upstream)
# while this gets sorted out.
extra_cflags=(
    -D_LARGEFILE_SOURCE
    -D_FILE_OFFSET_BITS=64
    -DOPENSSL_NO_ENGINE  # https://issues.redhat.com/browse/RHEL-33743
    -DZLIB_CONST
    -O3
    -fno-ipa-icf
)
export CFLAGS="%{optflags} ${extra_cflags[*]}" CXXFLAGS="%{optflags} ${extra_cflags[*]}"
export LDFLAGS="%{build_ldflags}"

# Fake up the unversioned python executable because gyp calls it from the PATH
mkdir .bin
cwd=$(pwd)
ln -srf /usr/bin/python3 ./.bin/python
export PATH="${cwd}/.bin:$PATH"

%{python3} configure.py \
           --verbose \
           --ninja \
           --enable-lto \
           --prefix=%{_prefix} \
           --shared \
           --libdir=%{_lib} \
           %{ssl_configure} \
           %{!?with_bundled_zlib:--shared-zlib} \
           %{!?with_bundled_cjs_module_lexer:--shared-builtin-cjs_module_lexer/lexer-path %{nodejs_private_sitelib}/cjs-module-lexer/lexer.js} \
           %{!?with_bundled_cjs_module_lexer:--shared-builtin-cjs_module_lexer/dist/lexer-path %{nodejs_private_sitelib}/cjs-module-lexer/dist/lexer.js} \
           %{!?with_bundled_undici:--shared-builtin-undici/undici-path %{nodejs_private_sitelib}/undici/loader.js} \
           --shared-brotli \
           %{!?with_bundled_libuv:--shared-libuv} \
           %{!?with_bundled_sqlite:--shared-sqlite} \
           --with-intl=small-icu \
           --with-icu-default-data-dir=%{icudatadir} \
           --without-corepack \
           --openssl-use-def-ca-store \
           --use-prefix-to-find-headers

%ninja_build -C out/Release


%install

# The ninja build does not put the shared library in the expected location, so
# we will move it.
mv out/Release/lib/libnode.so.%{nodejs_soversion} out/Release/

./tools/install.py install --dest-dir %{buildroot} --prefix %{_prefix}

# Set the binary permissions properly
chmod 0755 %{buildroot}/%{_bindir}/node
chrpath --delete %{buildroot}%{_bindir}/node

# Rename the node binary
mv %{buildroot}%{_bindir}/node %{buildroot}%{_bindir}/node-%{nodejs_pkg_major}

# Move the npm binary to npm-NODEJS_MAJOR
rm -f %{buildroot}%{_bindir}/npm

# Set the hashbang to use the matching Node.js interpreter
sed --in-place --regexp-extended \
    's;^#!/usr/bin/env node($|\ |\t)+;#!/usr/bin/node-%{nodejs_pkg_major};g' \
    %{buildroot}%{nodejs_private_sitelib}/npm/bin/npm-cli.js

ln -srf %{buildroot}%{nodejs_private_sitelib}/npm/bin/npm-cli.js \
        %{buildroot}%{_bindir}/npm-%{nodejs_pkg_major}

# Move the npx binary to npx-NODEJS_MAJOR
rm -f %{buildroot}%{_bindir}/npx

# Set the hashbang to use the matching Node.js interpreter
sed --in-place --regexp-extended \
    's;^#!/usr/bin/env node($|\ |\t)+;#!/usr/bin/node-%{nodejs_pkg_major};g' \
    %{buildroot}%{nodejs_private_sitelib}/npm/bin/npx-cli.js

ln -srf %{buildroot}%{nodejs_private_sitelib}/npm/bin/npx-cli.js \
        %{buildroot}%{_bindir}/npx-%{nodejs_pkg_major}

# Add the symlinks back for the default version
ln -srf %{buildroot}%{_bindir}/node-%{nodejs_pkg_major} \
        %{buildroot}%{_bindir}/node

ln -srf %{buildroot}%{_bindir}/npm-%{nodejs_pkg_major} \
        %{buildroot}%{_bindir}/npm

ln -srf %{buildroot}%{_bindir}/npx-%{nodejs_pkg_major} \
        %{buildroot}%{_bindir}/npx

# Install library symlink
ln -srf %{buildroot}%{_libdir}/libnode.so.%{nodejs_soversion} \
        %{buildroot}%{_libdir}/libnode.so

# Install v8 compatibility symlinks (versioned only; the unversioned .so
# symlinks and header symlinks belonged to the dropped v8-devel subpackage)
for soname in libv8 libv8_libbase libv8_libplatform; do
  ln -srf %{buildroot}%{_libdir}/libnode.so.%{nodejs_soversion} %{buildroot}%{_libdir}/${soname}.so.%{v8_major}.%{v8_minor}
  ln -srf %{buildroot}%{_libdir}/libnode.so.%{nodejs_soversion} %{buildroot}%{_libdir}/${soname}.so.%{v8_major}
done

# install documentation
mkdir -p %{buildroot}%{_pkgdocdir}/html
cp -pr doc/* %{buildroot}%{_pkgdocdir}/html
rm -f %{buildroot}%{_pkgdocdir}/html/nodejs.1

# node-gyp needs common.gypi too
mkdir -p %{buildroot}%{nodejs_datadir}
cp -p common.gypi %{buildroot}%{nodejs_datadir}

# The config.gypi file is platform-dependent, so rename it to not conflict
mv %{buildroot}%{_includedir}/node/config.gypi \
   %{buildroot}%{_includedir}/node/config-%{_arch}.gypi

# Install the GDB init tool into the documentation directory
mv %{buildroot}/%{_datadir}/doc/node/gdbinit %{buildroot}/%{_pkgdocdir}/gdbinit

mkdir -p %{buildroot}%{_mandir}/nodejs-%{nodejs_pkg_major}/man1 \
         %{buildroot}%{_mandir}/nodejs-%{nodejs_pkg_major}/man5 \
         %{buildroot}%{_mandir}/nodejs-%{nodejs_pkg_major}/man7 \
         %{buildroot}%{nodejs_private_sitelib}/npm/man \
         %{buildroot}%{_pkgdocdir}/npm

# install manpage docs to mandir
cp -pr deps/npm/man/* \
       %{buildroot}%{_mandir}/nodejs-%{nodejs_pkg_major}/
rm -rf %{buildroot}%{nodejs_private_sitelib}/npm/man
ln -srf %{buildroot}%{_mandir}/nodejs-%{nodejs_pkg_major} \
        %{buildroot}%{nodejs_private_sitelib}/npm/man

for i in 1 5 7; do
  mkdir -p %{buildroot}%{_mandir}/man${i}
  for manpage in %{buildroot}%{nodejs_private_sitelib}/npm/man/man$i/*; do
    basename=$(basename ${manpage})
    ln -srf %{buildroot}%{nodejs_private_sitelib}/npm/man/man${i}/${basename} \
            %{buildroot}%{_mandir}/man${i}/${basename}
  done
done

# Install the node interpreter manpage
mv %{buildroot}%{_mandir}/man1/node.1 \
   %{buildroot}%{_mandir}/nodejs-%{nodejs_pkg_major}/man1/

ln -srf %{buildroot}%{_mandir}/nodejs-%{nodejs_pkg_major}/man1/node.1 \
        %{buildroot}%{_mandir}/man1/

# Install Gatsby HTML documentation to %%{_pkgdocdir}
cp -pr deps/npm/docs %{buildroot}%{_pkgdocdir}/npm/
rm -rf %{buildroot}%{nodejs_private_sitelib}/npm/docs
ln -srf %{buildroot}%{_pkgdocdir}/npm %{buildroot}%{nodejs_private_sitelib}/npm/docs

# Node tries to install some python files into a documentation directory
# (and not the proper one). Remove them for now until we figure out what to
# do with them.
rm -f %{buildroot}/%{_defaultdocdir}/node/lldb_commands.py \
      %{buildroot}/%{_defaultdocdir}/node/lldbinit

# Some NPM bundled deps are executable but should not be. This causes
# unnecessary automatic dependencies to be added. Make them not executable.
# Skip the npm bin directory or the npm binary will not work.
find %{buildroot}%{nodejs_private_sitelib}/npm \
    -not -path "%{buildroot}%{nodejs_private_sitelib}/npm/bin/*" \
    -executable -type f \
    -exec chmod -x {} \;

# The above command is a little overzealous. Add a few permissions back.
chmod 0755 %{buildroot}%{nodejs_private_sitelib}/npm/node_modules/@npmcli/run-script/lib/node-gyp-bin/node-gyp
chmod 0755 %{buildroot}%{nodejs_private_sitelib}/npm/node_modules/node-gyp/bin/node-gyp.js

# Set the hashbang to use the matching Node.js interpreter
sed --in-place --regexp-extended \
    's;^#!/usr/bin/env node($|\ |\t)+;#!/usr/bin/node-%{nodejs_pkg_major};g' \
    %{buildroot}%{nodejs_private_sitelib}/npm/node_modules/node-gyp/bin/node-gyp.js

# Drop the NPM builtin configuration in place
sed -e 's#@SYSCONFDIR@#%{_sysconfdir}#g' \
    %{SOURCE201} > %{buildroot}%{nodejs_private_sitelib}/npm/npmrc

# Drop the NPM default configuration in place
mkdir -p %{buildroot}%{_sysconfdir}
cp %{SOURCE1} %{buildroot}%{_sysconfdir}/npmrc

# Install the full-icu data files
mkdir -p %{buildroot}%{icudatadir}
%if 0%{?little_endian}
unzip -d %{buildroot}%{icudatadir} %{SOURCE4} icudt%{icu_major}l.dat
%else
unzip -d %{buildroot}%{icudatadir} %{SOURCE3} icudt%{icu_major}b.dat
%endif

# Add pkg-config files
mkdir -p %{buildroot}%{_libdir}/pkgconfig
sed -e 's#@PREFIX@#%{_prefix}#g' \
    -e 's#@INCLUDEDIR@#%{_includedir}#g' \
    -e 's#@LIBDIR@#%{_libdir}#g' \
    -e 's#@PKGCONFNAME@#nodejs-%{nodejs_pkg_major}#g' \
    -e 's#@NODEJS_VERSION@#%{nodejs_version}#g' \
    %{SOURCE202} > %{buildroot}%{_libdir}/pkgconfig/nodejs-%{nodejs_pkg_major}.pc


%check
#run unit test that should pass from list
LD_LIBRARY_PATH=%{buildroot}%{_libdir} \
  bash %{SOURCE300} \
       %{buildroot}/%{_bindir}/node-%{nodejs_pkg_major} \
       %{_builddir}/node-v%{nodejs_version}/test/ \
       %{SOURCE301}

# Fail the build if the versions don't match
LD_LIBRARY_PATH=%{buildroot}%{_libdir} %{buildroot}/%{_bindir}/node-%{nodejs_pkg_major} -e "require('assert').equal(process.versions.node, '%{nodejs_version}')"
LD_LIBRARY_PATH=%{buildroot}%{_libdir} %{buildroot}/%{_bindir}/node-%{nodejs_pkg_major} -e "require('assert').equal(process.versions.v8.replace(/-node\.\d+$/, ''), '%{v8_version}')"
LD_LIBRARY_PATH=%{buildroot}%{_libdir} %{buildroot}/%{_bindir}/node-%{nodejs_pkg_major} -e "require('assert').equal(process.versions.ares.replace(/-DEV$/, ''), '%{c_ares_version}')"

# Ensure we have punycode and that the version matches
LD_LIBRARY_PATH=%{buildroot}%{_libdir} %{buildroot}/%{_bindir}/node-%{nodejs_pkg_major} -e "require(\"assert\").equal(require(\"punycode\").version, '%{punycode_version}')"

# Ensure we have npm and that the version matches
LD_LIBRARY_PATH=%{buildroot}%{_libdir} %{buildroot}%{_bindir}/node-%{nodejs_pkg_major} %{buildroot}%{_bindir}/npm-%{nodejs_pkg_major} version --json |jq -e '.npm == "%{npm_version}"'

# Make sure i18n support is working
NODE_PATH=%{buildroot}%{_prefix}/lib/node_modules:%{buildroot}%{nodejs_private_sitelib}/npm/node_modules LD_LIBRARY_PATH=%{buildroot}%{_libdir} %{buildroot}/%{_bindir}/node-%{nodejs_pkg_major} --icu-data-dir=%{buildroot}%{icudatadir} %{SOURCE2}

# Ensure npm's update notifier has been disabled
LD_LIBRARY_PATH=%{buildroot}%{_libdir} \
%{buildroot}%{_bindir}/node \
%{buildroot}%{_bindir}/npm \
--globalconfig=%{buildroot}$(LD_LIBRARY_PATH=%{buildroot}%{_libdir} %{buildroot}%{_bindir}/node %{buildroot}%{_bindir}/npm config get globalconfig) config ls -l --json | jq -e '.["update-notifier"] == false'


%files -n %{pkgname}
%doc CHANGELOG.md onboarding.md GOVERNANCE.md README.md
%{_bindir}/node
%{_bindir}/node-%{nodejs_major}
%doc %{_mandir}/man1/node.1*
# Directory only: with default == private sitelib (/usr/lib/node_modules) the
# CS9 glob would double-package the npm tree that %%files -n npm owns.
%dir %{nodejs_default_sitelib}
%doc %{_mandir}/nodejs-%{nodejs_pkg_major}/man1/node.1*


%files -n %{pkgname}-devel
%{_includedir}/node
%{_libdir}/libnode.so
%{nodejs_datadir}/common.gypi
%{_pkgdocdir}/gdbinit
%{_libdir}/pkgconfig/nodejs-%{nodejs_pkg_major}.pc


%files -n %{pkgname}-full-i18n
%dir %{icudatadir}
%{icudatadir}/icudt%{icu_major}*.dat


%files -n %{pkgname}-libs
%license LICENSE
%{_libdir}/libnode.so.%{nodejs_soversion}
%{_libdir}/libv8.so.%{v8_major}.%{v8_minor}
%{_libdir}/libv8_libbase.so.%{v8_major}.%{v8_minor}
%{_libdir}/libv8_libplatform.so.%{v8_major}.%{v8_minor}
%dir %{nodejs_datadir}/
%{_libdir}/libv8.so.%{v8_major}
%{_libdir}/libv8_libbase.so.%{v8_major}
%{_libdir}/libv8_libplatform.so.%{v8_major}


%files -n npm
%{_bindir}/npm
%{_bindir}/npx
%config(noreplace) %{_sysconfdir}/npmrc
%ghost %{_sysconfdir}/npmignore
%doc %{_mandir}/man*/
%exclude %doc %{_mandir}/man1/node.1*
%{_bindir}/npm-%{nodejs_pkg_major}
%{_bindir}/npx-%{nodejs_pkg_major}
%{nodejs_private_sitelib}/npm
%doc %{_mandir}/nodejs-%{nodejs_pkg_major}/
%exclude %doc %{_mandir}/nodejs-%{nodejs_pkg_major}/man1/node.1*


%files -n %{pkgname}-docs
%doc doc
%dir %{_pkgdocdir}
%{_pkgdocdir}/html
%{_pkgdocdir}/npm/docs


%changelog
* Mon Aug 31 2026 Percona Development Team <info@percona.com> - 1:22.23.1-2
- Port nodejs 22.23.1 from the CentOS Stream 9 nodejs:22 module dist-git
  (stream-nodejs-22-rhel-9.9.0) for the pgAdmin 4 (percona-pgadmin4)
  frontend build on UBI 9, where only the nodejs 16 default stream is
  available in the OBS repositories
