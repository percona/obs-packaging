# PERCONA build of curl 8.23.0 (CVE fixes) for every PPG RPM repository
# (ppg:common:deps: RockyLinux 8/9/9.6/10, UBI 8/9/10, openSUSE Leap 16).
# Every PPG staging repository, the binary tarballs and the container
# images resolve ppg:common:deps first, so all PPG packages build against
# this libcurl, and the staging repositories ship it (_aggregate).
#
#   - curl >= 8.22.0 requires OpenSSL >= 3.0. EL8 only has OpenSSL 1.1.1,
#     so there a static OpenSSL 3 is built in a private prefix and linked
#     into libcurl alone, with its symbols hidden: no OpenSSL 3 shared
#     library is shipped and nothing else can bind to it (as in
#     pg_tarballs_builder.sh in percona/postgres-packaging).
#   - OpenSSL's default CA locations are pointed at the system trust
#     stores (RHEL-family bundle file, Debian/Ubuntu/SUSE hashed directory)
#     and libcurl uses them (--with-ca-fallback), so the tarball's libcurl
#     finds CA certificates on any distro.
#   - Feature set matches the distro's full libcurl (this build replaces
#     it on customer hosts): HTTP/2, IDN, PSL, brotli, GSS-API/Kerberos,
#     SCP/SFTP (libssh), LDAP/LDAPS, NTLM (opt-in upstream since 8.20.0;
#     SMB was removed upstream in 8.23.0), plus zstd on SUSE.
#   - Versioned symbols (CURL_OPENSSL_4). The EL and SUSE libcurl are
#     unversioned, so every package built against this one automatically
#     requires libcurl.so.4(CURL_OPENSSL_4)(64bit), which only this build
#     provides: installing a PPG package pulls it in. Programs built
#     against the distro libcurl keep working with it.
#
# Binary package names, the libcurl.so.4 soname and the public ABI match
# the distro's (libcurl on EL, libcurl4 on SUSE). The Debian/Ubuntu build
# of the same sources is in ../debian.

%global openssl_version 3.5.4
%global openssl_prefix %{_builddir}/openssl3-static
%if 0%{?rhel} == 8
%global curl_openssl %{openssl_prefix}
%else
%global curl_openssl %{_prefix}
%endif
%if 0%{?suse_version}
%global libname libcurl4
%global zstd_opt --with-zstd
%else
%global libname libcurl
%global zstd_opt --without-zstd
%endif

Name:           curl
Version:        8.23.0
Release:        1.percona%{?dist}
Summary:        A utility for getting files from remote servers (FTP, HTTP, and others)
License:        curl
URL:            https://curl.se/

Source0:        https://curl.se/download/%{name}-%{version}.tar.xz
Source1:        https://github.com/openssl/openssl/releases/download/openssl-%{openssl_version}/openssl-%{openssl_version}.tar.gz

# PERCONA: use the OpenSSL 3.0 API for the negotiated group name so that
# libcurl built on an OpenSSL >= 3.2 base (RockyLinux_9.6) only needs
# OPENSSL_3.0.* symbol versions (ssl3 tarball promise).
Patch0:         curl-openssl-3.0-abi.patch

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  binutils
BuildRequires:  pkgconfig
BuildRequires:  zlib-devel
BuildRequires:  krb5-devel
BuildRequires:  pkgconfig(libbrotlidec)
BuildRequires:  pkgconfig(libidn2)
BuildRequires:  pkgconfig(libnghttp2)
BuildRequires:  pkgconfig(libpsl)
BuildRequires:  pkgconfig(libssh)
%if 0%{?suse_version}
BuildRequires:  openldap2-devel
BuildRequires:  pkgconfig(libzstd)
# man pages and the built-in manual are generated from markdown by perl.
BuildRequires:  perl
%else
BuildRequires:  openldap-devel
BuildRequires:  perl-interpreter
%endif
%if 0%{?rhel} == 8
# OpenSSL 3's Configure and build scripts need non-core-split perl modules.
BuildRequires:  perl
BuildRequires:  perl-IPC-Cmd
%else
%if 0%{?suse_version}
# By name: libressl-devel also provides pkgconfig(openssl) on SUSE.
BuildRequires:  libopenssl-devel >= 3.0
%else
BuildRequires:  openssl-devel >= 3.0
%endif
%endif

Requires:       %{libname}%{?_isa} = %{version}-%{release}
Provides:       curl-full = %{version}-%{release}
Provides:       webclient
# Replace the distro's minimal curl (ubi-minimal ships it).
Provides:       curl-minimal = %{version}-%{release}
Obsoletes:      curl-minimal < %{version}-%{release}
Obsoletes:      curl-mini < %{version}-%{release}

%description
curl is a command line tool for transferring data with URL syntax,
supporting HTTP, HTTPS, FTP, FTPS, SCP, SFTP, LDAP and other protocols.

This Percona build is linked against OpenSSL 3 (a private static copy on
EL8) and uses the system CA trust store.

%package -n %{libname}
Summary:        A library for getting files from web servers
Provides:       libcurl-full = %{version}-%{release}
Provides:       libcurl-full%{?_isa} = %{version}-%{release}
# Replace the distro's minimal libcurl (ubi-minimal and the openSUSE
# images ship it).
Provides:       libcurl-minimal = %{version}-%{release}
Provides:       libcurl-minimal%{?_isa} = %{version}-%{release}
Obsoletes:      libcurl-minimal < %{version}-%{release}
%if 0%{?suse_version}
Provides:       libcurl-mini4 = %{version}-%{release}
Obsoletes:      libcurl-mini4 < %{version}-%{release}
%endif

%description -n %{libname}
libcurl is a free and easy-to-use client-side URL transfer library,
supporting HTTP, HTTPS, FTP, FTPS, SCP, SFTP, LDAP and other protocols.

%package -n libcurl-devel
Summary:        Files needed for building applications with libcurl
Requires:       %{libname}%{?_isa} = %{version}-%{release}
Provides:       curl-devel = %{version}-%{release}
Provides:       curl-devel%{?_isa} = %{version}-%{release}
Obsoletes:      curl-devel < %{version}-%{release}
%if 0%{?suse_version}
Obsoletes:      libcurl-mini-devel < %{version}-%{release}
%endif

%description -n libcurl-devel
The libcurl-devel package includes header files and libraries necessary
for developing programs which use the libcurl library.

%prep
%setup -q
%patch -P 0 -p1
%if 0%{?rhel} == 8
%setup -q -T -D -a 1
%endif

%build
%if 0%{?rhel} == 8
# Static OpenSSL 3 in a private prefix, linked only into libcurl.
pushd openssl-%{openssl_version}
# Point OpenSSL's default CA locations at the system trust stores instead
# of OPENSSLDIR: RHEL family bundle file, Debian/Ubuntu/SUSE hashed
# certificate directory. libcurl uses these defaults (--with-ca-fallback).
hdr=$(grep -lE '^#  define X509_CERT_DIR +OPENSSLDIR' include/internal/*.h)
sed -i -e 's|^\(#  define X509_CERT_DIR \).*OPENSSLDIR.*|\1"/etc/ssl/certs:/etc/pki/tls/certs"|' \
       -e 's|^\(#  define X509_CERT_FILE \).*OPENSSLDIR.*|\1"/etc/pki/tls/cert.pem"|' ${hdr}
grep -q '"/etc/ssl/certs:/etc/pki/tls/certs"' ${hdr} && grep -q '"/etc/pki/tls/cert.pem"' ${hdr} \
    || { echo "Error: failed to set OpenSSL default CA locations"; exit 1; }
# OPENSSLDIR is a path nothing creates, so the host's (OpenSSL 1.1)
# openssl.cnf is never parsed by this OpenSSL 3.
./Configure --prefix=%{openssl_prefix} --openssldir=%{_libdir}/libcurl-openssl3 \
    --libdir=lib no-shared no-tests -fPIC
%make_build
make install_sw
popd
export PKG_CONFIG_PATH=%{openssl_prefix}/lib/pkgconfig
export LIBS="-ldl -lpthread"
export LDFLAGS="%{build_ldflags} -Wl,--exclude-libs,libssl.a:libcrypto.a"
%endif

%configure \
    --disable-static \
    --enable-symbol-hiding \
    --enable-versioned-symbols \
    --enable-threaded-resolver \
    --with-openssl=%{curl_openssl} \
    --with-zlib \
    --without-ca-bundle \
    --without-ca-path \
    --with-ca-fallback \
    --with-brotli \
    %{zstd_opt} \
    --with-libidn2 \
    --with-libpsl \
    --with-nghttp2 \
    --without-ngtcp2 \
    --without-nghttp3 \
    --with-libssh \
    --without-libssh2 \
    --with-gssapi \
    --enable-ldap \
    --enable-ldaps \
    --without-libgsasl \
    --enable-ntlm \
    --without-zsh-functions-dir \
    --without-fish-functions-dir

# Use the system libtool's RPATH handling: no RPATH in libcurl or curl.
sed -i -e 's|^hardcode_libdir_flag_spec=.*|hardcode_libdir_flag_spec=""|' \
       -e 's|^runpath_var=LD_RUN_PATH|runpath_var=DIE_RPATH_DIE|' libtool

%make_build

%install
%make_install
rm -f %{buildroot}%{_libdir}/libcurl.la
%if 0%{?rhel} == 8
# OpenSSL 3 lives inside libcurl.so.4 itself and no static libcurl is
# shipped, so consumers must not be pointed at OpenSSL: libcurl.pc's
# "Requires.private: openssl" would make libcurl-devel require EL8's
# OpenSSL 1.1 pkgconfig(openssl), and the private static prefix is a
# build-time path. Drop both from libcurl.pc and curl-config.
sed -i -e '/^Requires.private:/{s/\bopenssl\b//g;s/,,*/,/g;s/: *,/: /;s/,* *$//}' \
       -e '/^Libs.private:/{s|-L%{openssl_prefix}/lib||g;s/ *-lssl//g;s/ *-lcrypto//g}' \
       %{buildroot}%{_libdir}/pkgconfig/libcurl.pc
sed -i -e 's|-L%{openssl_prefix}/lib ||g;s/ *-lssl//g;s/ *-lcrypto//g' \
       -e 's|--with-openssl=%{openssl_prefix}|--with-openssl=openssl-%{openssl_version}-static|g' \
       %{buildroot}%{_bindir}/curl-config
if grep -nE 'openssl3-static|^Requires.private:.*openssl|lssl|lcrypto' \
        %{buildroot}%{_libdir}/pkgconfig/libcurl.pc %{buildroot}%{_bindir}/curl-config; then
    echo "Error: libcurl-devel still references the private OpenSSL"
    exit 1
fi
%endif

%check
# The upstream test suite is long and partly network-bound; these gates
# check what this build exists for.
lib=$(readlink -f lib/.libs/libcurl.so)
LD_LIBRARY_PATH=$(dirname ${lib}) src/curl -V | tee curl-V.txt
grep -q '^curl %{version} ' curl-V.txt
grep -q 'OpenSSL/3\.' curl-V.txt
# Distro feature parity. AsynchDNS: libpq-oauth needs a non-blocking resolver.
for p in https scp sftp ldap ldaps; do
    grep -qE "^Protocols:.* ${p}( |$)" curl-V.txt || { echo "Error: protocol ${p} missing"; exit 1; }
done
for f in AsynchDNS brotli GSS-API HTTP2 IDN Kerberos NTLM PSL SPNEGO%{?suse_version: zstd}; do
    grep -qE "^Features:.* ${f}( |$)" curl-V.txt || { echo "Error: feature ${f} missing"; exit 1; }
done
# Exported API carries the CURL_OPENSSL_4 symbol version (dependency
# enforcement, see the header).
objdump -T ${lib} | grep -q ' CURL_OPENSSL_4 *curl_easy_init$' \
    || { echo "Error: libcurl symbols are not versioned CURL_OPENSSL_4"; exit 1; }
%if 0%{?rhel} == 8
# libcurl must neither depend on nor export OpenSSL 3 symbols.
if readelf -d ${lib} | grep -E 'NEEDED.*lib(ssl|crypto)\.so'; then
    echo "Error: libcurl links to a shared OpenSSL library"
    exit 1
fi
if nm -D --defined-only ${lib} | grep -E ' (SSL_|EVP_|OPENSSL_|CRYPTO_|X509_)'; then
    echo "Error: libcurl exports OpenSSL symbols"
    exit 1
fi
%else
# libcurl must load on any OpenSSL 3.0 host: only OPENSSL_3.0.* symbol
# versions may be needed (the ssl3 tarball promise).
# (-w: CURL_OPENSSL_4, libcurl's own symbol version, is not an OpenSSL one.)
if objdump -T ${lib} | grep -owE 'OPENSSL_[0-9]+\.[0-9]+\.[0-9]+' | sort -u | grep -vE '^OPENSSL_3\.0\.[0-9]+$'; then
    echo "Error: libcurl needs OpenSSL symbol versions newer than 3.0"
    exit 1
fi
%endif

%post -n %{libname} -p /sbin/ldconfig
%postun -n %{libname} -p /sbin/ldconfig

%files
%license COPYING
%doc CHANGES.md README RELEASE-NOTES
%{_bindir}/curl
%{_bindir}/wcurl
%{_mandir}/man1/curl.1*
%{_mandir}/man1/wcurl.1*

%files -n %{libname}
%license COPYING
%{_libdir}/libcurl.so.4
%{_libdir}/libcurl.so.4.*

%files -n libcurl-devel
%doc docs/examples/*.c
%{_bindir}/curl-config
%{_includedir}/curl
%{_libdir}/libcurl.so
%{_libdir}/pkgconfig/libcurl.pc
%{_mandir}/man1/curl-config.1*
%{_mandir}/man3/*
%{_datadir}/aclocal/libcurl.m4

%changelog
* Thu Oct 22 2026 Percona Development Team <info@percona.com> - 8.23.0-1.percona
- curl 8.23.0 for every PPG RPM repository (CVE fixes), replacing the
  distro curl with the distro's feature set (HTTP/2, IDN, PSL, brotli,
  GSS-API, SCP/SFTP, LDAP; zstd on SUSE).
- curl >= 8.22.0 requires OpenSSL 3: on EL8 a static OpenSSL 3.5.4 is
  linked privately into libcurl with its symbols hidden; EL9/EL10/SUSE
  use the system OpenSSL 3, limited to OPENSSL_3.0.* symbol versions.
- Versioned symbols (CURL_OPENSSL_4), so packages built against this
  libcurl require it.
- OpenSSL default CA locations point at the system trust stores and
  libcurl uses them (--with-ca-fallback), as in pg_tarballs_builder.sh.
