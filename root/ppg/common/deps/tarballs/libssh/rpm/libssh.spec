# PERCONA REBUILD of the Rocky Linux 8 libssh source package, for
# ppg:common:deps (RockyLinux_8 repository only).
#
# Why: the EL8-built Percona PostgreSQL binary tarball (ssl1.1 variant)
# bundles libssh.so.4 (a libcurl dependency for scp/sftp). Red Hat
# builds libssh against Red Hat's OpenSSL 1.1.1 fork, so the library
# needs symbol version nodes (EVP_KDF_ctrl@OPENSSL_1_1_1b) that exist
# ONLY in RHEL-family libcrypto.so.1.1 — it fails to load on stock
# OpenSSL 1.1 hosts (proven on Debian 11).
#
# Delta vs. the distro spec (kept minimal, marked "PERCONA"):
#   - -DWITH_GCRYPT=ON: libgcrypt crypto backend, no OpenSSL linkage.
#   - BuildRequires libgcrypt-devel instead of openssl-devel.
#   - Release carries a .percona suffix so this EVR wins over the
#     distro package inside the OBS build chroots.
# Binary package names, sonames and the public ABI are unchanged.

Name:           libssh
Version:        0.9.6
# PERCONA: ".percona.N" appended to the distro Release (16) so that this
# rebuild's EVR beats 0.9.6-16.el8_10 during dependency resolution while
# still yielding to a future distro 0.9.6-17 security rebase.
Release:        16.percona.1%{?dist}
Summary:        A library implementing the SSH protocol
License:        LGPLv2+
URL:            http://www.libssh.org

Source0:        https://www.libssh.org/files/0.9/%{name}-%{version}.tar.xz
Source1:        https://www.libssh.org/files/0.9/%{name}-%{version}.tar.xz.asc
Source2:        https://cryptomilk.org/gpgkey-8DFF53E18F2ABC8D8F3C92237EE0FC4DCC014E3D.gpg#/%{name}.keyring
Source3:        libssh_client.config
Source4:        libssh_server.config

Patch0:         loglevel.patch
Patch1:         s390x_fix.patch
Patch2:         null_dereference_rekey.patch
Patch3:         auth_bypass.patch
Patch4:         fix_tests.patch
Patch5:         covscan23.patch
Patch6:         CVE-2023-48795.patch
Patch7:         CVE-2023-6004.patch
Patch8:         CVE-2023-6918.patch
Patch9:         CVE-2025-5318.patch
Patch10:        CVE-2025-5372.patch

BuildRequires:  cmake
BuildRequires:  doxygen
BuildRequires:  gcc-c++
BuildRequires:  gnupg2
# PERCONA: libgcrypt backend instead of OpenSSL (was: openssl-devel).
BuildRequires:  libgcrypt-devel
BuildRequires:  pkgconfig
BuildRequires:  zlib-devel
BuildRequires:  krb5-devel
BuildRequires:  libcmocka-devel
BuildRequires:  openssh-clients
BuildRequires:  openssh-server
BuildRequires:  pam_wrapper
BuildRequires:  socket_wrapper
BuildRequires:  nss_wrapper
BuildRequires:  uid_wrapper
BuildRequires:  nmap-ncat

Requires:       crypto-policies
Requires:       %{name}-config = %{version}-%{release}

%ifarch aarch64 ppc64 ppc64le s390x x86_64
Provides: libssh_threads.so()(64bit)
Provides: libssh_threads.so.4()(64bit)
%else
Provides: libssh_threads.so
Provides: libssh_threads.so.4
%endif

%description
The ssh library was designed to be used by programmers needing a working SSH
implementation by the mean of a library. The complete control of the client is
made by the programmer. With libssh, you can remotely execute programs, transfer
files, use a secure and transparent tunnel for your remote programs. With its
Secure FTP implementation, you can play with remote files easily, without
third-party programs others than libcrypto (from openssl).

%package devel
Summary:        Development files for %{name}
Requires:       %{name}%{?_isa} = %{version}-%{release}

%description devel
The %{name}-devel package contains libraries and header files for developing
applications that use %{name}.

%package config
Summary:        Configuration files for %{name}
BuildArch:      noarch
Obsoletes:      %{name} < 0.9.0-1

%description config
The %{name}-config package provides the default configuration files for %{name}.

%prep
gpgv2 --quiet --keyring %{SOURCE2} %{SOURCE1} %{SOURCE0}
%autosetup -p1

%build
if test ! -e "obj"; then
  mkdir obj
fi
pushd obj

%cmake .. \
    -DWITH_GCRYPT=ON \
    -DUNIT_TESTING=ON \
    -DCLIENT_TESTING=ON \
    -DSERVER_TESTING=ON \
    -DGLOBAL_CLIENT_CONFIG="%{_sysconfdir}/libssh/libssh_client.config" \
    -DGLOBAL_BIND_CONFIG="%{_sysconfdir}/libssh/libssh_server.config"


%make_build VERBOSE=1
make docs

popd

%install
make DESTDIR=%{buildroot} install/fast -C obj
install -d -m755 %{buildroot}%{_sysconfdir}/libssh
install -m644 %{SOURCE3} %{buildroot}%{_sysconfdir}/libssh/libssh_client.config
install -m644 %{SOURCE4} %{buildroot}%{_sysconfdir}/libssh/libssh_server.config

#
# Workaround for the removal of libssh_threads.so
#
# This will allow libraries which link against libssh_threads.so or packages
# requiring it to continue working.
#
pushd %{buildroot}%{_libdir}
for i in libssh.so.4*;
do
    _target="${i}"
    _link_name="${i%libssh*}libssh_threads${i##*libssh}"
    if [ -L "${i}" ]; then
        _target="$(readlink ${i})"
    fi
    ln -s "${_target}" "${_link_name}"
done;
popd

%ldconfig_scriptlets

%check
pushd obj
ctest --output-on-failure
popd

%files
%doc AUTHORS BSD ChangeLog README
%license COPYING
%{_libdir}/libssh.so.4*
%{_libdir}/libssh_threads.so.4*

%files devel
%doc obj/doc/html
%{_includedir}/libssh/
# own this to avoid dep on cmake -- rex
%dir  %{_libdir}/cmake/
%{_libdir}/cmake/libssh/
%{_libdir}/pkgconfig/libssh.pc
%{_libdir}/libssh.so

%files config
%attr(0755,root,root) %dir %{_sysconfdir}/libssh
%attr(0644,root,root) %config(noreplace) %{_sysconfdir}/libssh/libssh_client.config
%attr(0644,root,root) %config(noreplace) %{_sysconfdir}/libssh/libssh_server.config

%changelog
* Wed Jul 22 2026 Percona Development Team <info@percona.com> - 0.9.6-16.percona.1
- Rebuild with the libgcrypt crypto backend (-DWITH_GCRYPT=ON) so that
  libssh.so.4 has no OpenSSL linkage. Red Hat's build needs symbol
  version nodes (EVP_KDF_ctrl@OPENSSL_1_1_1b) that only exist in the
  RHEL OpenSSL 1.1.1 fork, which breaks the Percona PostgreSQL binary
  tarball on stock OpenSSL 1.1 hosts.

* Wed Nov 05 2025 Pavol Žáčik <pzacik@redhat.com> - 0.9.6-16
- Fix CVE-2025-5372
  Resolves: RHEL-121232

* Tue Sep 30 2025 Pavol Žáčik <pzacik@redhat.com> - 0.9.6-15
- Fix CVE-2025-5318
  Resolves: RHEL-111724

* Mon Feb 26 2024 Sahana Prasad <sahana@redhat.com> - 0.9.6-14
- Fix CVE-2023-48795 Prefix truncation attack on Binary Packet Protocol (BPP)
- Fix CVE-2023-6918 Missing checks for return values for digests
- Fix CVE-2023-6004 ProxyCommand/ProxyJump features allow injection
  of malicious code through hostname
- Note: version is bumped from 12 to 14 directly, as the z-stream
  version in 8.9 also has 13. So bumping it to 14, will prevent
  upgrade conflicts.
- Resolves:RHEL-19690, RHEL-17244, RHEL-19312

* Mon May 15 2023 Norbert Pocs <npocs@redhat.com> - 0.9.6-12
- Fix loglevel regression
- Related: rhbz#2182251, rhbz#2189742

* Thu May 04 2023 Norbert Pocs <npocs@redhat.com> - 0.9.6-11
- .fmf/version is needed to run the tests
- Related: rhbz#2182251, rhbz#2189742

* Wed May 03 2023 Norbert Pocs <npocs@redhat.com> - 0.9.6-10
- Add missing ci.fmf file
- Related: rhbz#2182251, rhbz#2189742

* Wed May 03 2023 Norbert Pocs <npocs@redhat.com> - 0.9.6-9
- Fix covscan errors found at gating
- Related: rhbz#2182251, rhbz#2189742

* Tue May 02 2023 Norbert Pocs <npocs@redhat.com> - 0.9.6-8
- Backport test fixing commits to make the build pass
- Related: rhbz#2182251, rhbz#2189742

* Thu Apr 27 2023 Norbert Pocs <npocs@redhat.com> - 0.9.6-7
- Fix NULL dereference during rekeying with algorithm guessing
  GHSL-2023-032 / CVE-2023-1667
- Fix possible authentication bypass
  GHSL 2023-085 / CVE-2023-2283
- Resolves: rhbz#2182251, rhbz#2189742

* Fri Jan 06 2023 Norbert Pocs <npocs@redhat.com> - 0.9.6-6
- Enable client and server testing build time
- Fix failing rekey test on arch s390x
- Resolves: rhbz#2126342

* Mon Dec 05 2022 Stanislav Zidek <szidek@redhat.com> - 0.9.6-5
- Fix CI configuration for new TMT
- Resolves: rhbz#2149910

* Mon Nov 28 2022 Norbert Pocs <npocs@redhat.com> - 0.9.6-4
- Make VERBOSE and lower log levels less verbose
- Resolves: rhbz#2091512

* Fri Nov 05 2021 Norbert Pocs <npocs@redhat.com> - 0.9.6-3
- Remove STI tests

* Thu Oct 21 2021 Norbert Pocs <npocs@redhat.com> - 0.9.6-2
- Remove bad patch causing errors
- Adding BuildRequires for openssh (SSHD support)

* Thu Oct 14 2021 Norbert Pocs <npocs@redhat.com> - 0.9.6-1
- Fix CVE-2021-3634: Fix possible heap-buffer overflow when
  rekeying with different key exchange mechanism
- Rebase to version 0.9.6
- Rename SSHD_EXECUTABLE to SSH_EXECUTABLE in tests/torture.c
- Resolves: rhbz#1896651, rhbz#1994600

* Thu Oct 14 2021 Sahana Prasad <sahana@redhat.com> - 0.9.4-4
- Revert previous commit as it is incorrect.

* Thu Oct 14 2021 Norbert Pocs <npocs@redhat.com> - 0.9.6-1
- Fix CVE-2021-3634: Fix possible heap-buffer overflow when
  rekeying with different key exchange mechanism (#1978810)

* Wed Apr 21 2021 Sahana Prasad <sahana@redhat.com> - 0.9.4-3
- Fix CVE-2020-16135 NULL pointer dereference in sftpserver.c if
  ssh_buffer_new returns NULL (#1862646)

* Wed Jun 24 2020 Anderson Sasaki <ansasaki@redhat.com> - 0.9.4-2
- Do not return error when server properly closed the channel (#1849071)
- Add a test for CVE-2019-14889
- Do not parse configuration file in torture_knownhosts test

* Tue May 26 2020 Anderson Sasaki <ansasaki@redhat.com> - 0.9.4-1
- Update to version 0.9.4
  https://www.libssh.org/2020/04/09/libssh-0-9-4-and-libssh-0-8-9-security-release/
- Fixed CVE-2019-14889 (#1781782)
- Fixed CVE-2020-1730 (#1802422)
- Create missing directories in the path provided for known_hosts files (#1733914)
- Removed inclusion of OpenSSH server configuration file from
  libssh_server.config (#1821339)

* Mon Aug 05 2019 Anderson Sasaki <ansasaki@redhat.com> - 0.9.0-4
- Skip 1024 bits RSA key generation test in FIPS mode (#1734485)

* Thu Jul 11 2019 Anderson Sasaki <ansasaki@redhat.com> - 0.9.0-3
- Add Obsoletes in libssh-config to avoid conflict with old libssh which
  installed the configuration files.

* Wed Jul 10 2019 Anderson Sasaki <ansasaki@redhat.com> - 0.9.0-2
- Eliminate circular dependency with libssh-config subpackage

* Wed Jul 10 2019 Anderson Sasaki <ansasaki@redhat.com> - 0.9.0-1
- Update to version 0.9.0
  https://www.libssh.org/2019/06/28/libssh-0-9-0/
- Added explicit Requires for crypto-policies
- Do not ignore known_hosts keys when SSH_OPTIONS_HOSTKEYS is set
- Provide the configuration files in a separate libssh-config subpackage

* Mon Jun 17 2019 Anderson Sasaki <ansasaki@redhat.com> - 0.8.91-0.1
- Update to 0.9.0 pre release version (0.8.91)
- Added default configuration files for client and server
- Removed unused patch files left behind
- Fixed issues found to run upstream test suite with SELinux

* Fri Dec 14 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.5-2
- Fix more regressions introduced by the fixes for CVE-2018-10933

* Thu Nov 29 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.5-1
- Update to version 0.8.5
  * Fixed an issue where global known_hosts file was ignored (#1649321)
  * Fixed ssh_get_fd() to return writable file descriptor (#1649319)
  * Fixed regression introduced in known_hosts parsing (#1649315)
  * Fixed a regression which caused only the first algorithm in known_hosts to
    be considered (#1638790)

* Thu Nov 08 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.3-5
- Fix regressions introduced by the fixes for CVE-2018-10933

* Wed Oct 17 2018 Nikos Mavrogiannopoulos <nmav@redhat.com> - 0.8.3-4
- Fix for authentication bypass issue in server implementation (#1639926)

* Tue Oct 02 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.3-3
- Fixed errors found by static code analysis (#1602594)

* Fri Sep 21 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.3-1
- Update to version 0.8.3
  * Added support for rsa-sha2 (#1610882)
  * Added support to parse private keys in openssh container format (other than
    ed25519) (#1622983)
  * Added support for diffie-hellman-group18-sha512 and
    diffie-hellman-group16-sha512 (#1610885)
  * Added ssh_get_fingerprint_hash()
  * Added ssh_pki_export_privkey_base64()
  * Added support for Match keyword in config file
  * Improved performance and reduced memory footprint for sftp
  * Fixed ecdsa publickey auth
  * Fixed reading a closed channel
  * Added support to announce posix-rename@openssh.com and hardlink@openssh.com
    in the sftp server
  * Use -fstack-protector-strong if possible (#1624135)

* Wed Aug 15 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.1-4
- Fix the creation of symbolic links for libssh_threads.so.4

* Wed Aug 15 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.1-3
- Add missing Provides for libssh_threads.so.4

* Tue Aug 14 2018 Anderson Sasaki <ansasaki@redhat.com> - 0.8.1-2
- Add Provides for libssh_threads.so to unbreak applications
- Fix ABIMap detection to not depend on python to build

* Mon Aug 13 2018 Andreas Schneider <asn@redhat.com> - 0.8.1-1
- Update to version 0.8.1
  https://www.libssh.org/2018/08/13/libssh-0-8-1/

* Fri Aug 10 2018 Andreas Schneider <asn@redhat.com> - 0.8.0-1
- Update to version 0.8.0
  https://www.libssh.org/2018/08/10/libssh-0-8-0/

* Fri Jul 13 2018 Fedora Release Engineering <releng@fedoraproject.org> - 0.7.5-9
- Rebuilt for https://fedoraproject.org/wiki/Fedora_29_Mass_Rebuild

* Wed Mar 07 2018 Rex Dieter <rdieter@fedoraproject.org> - 0.7.5-8
- BR: gcc-c++, use %%make_build

* Wed Feb 07 2018 Fedora Release Engineering <releng@fedoraproject.org> - 0.7.5-7
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild
- Related: bug#1614611

* Thu Feb 01 2018 Andreas Schneider <asn@redhat.com> - 0.7.5-6
- resolves: #1540021 - Build against OpenSSL 1.1

* Wed Jan 31 2018 Igor Gnatenko <ignatenkobrain@fedoraproject.org> - 0.7.5-5
- Switch to %%ldconfig_scriptlets

* Fri Dec 29 2017 Andreas Schneider <asn@redhat.com> - 0.7.5-4
- Fix parsing ssh_config

* Thu Aug 03 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.7.5-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Binutils_Mass_Rebuild

* Wed Jul 26 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.7.5-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Wed Apr 26 2017 Peter Robinson <pbrobinson@fedoraproject.org> 0.7.5-1
- Update to version 0.7.5

* Sat Mar 11 2017 Rex Dieter <rdieter@fedoraproject.org> - 0.7.4-2
- BR: compat-openssl10-devel (f26+, #1423088)
- use %%license
- -devel: drop hardcoded pkgconfig dep (let autodeps handle it)
- %%files: track library sonames, simplify -devel
- %%install: use 'install/fast' target
- .spec cosmetics, drop deprecated %%clean section

* Wed Feb 08 2017 Andreas Schneider <asn@redhat.com> - 0.7.4-1
- Update to version 0.7.4
  * Added id_ed25519 to the default identity list
  * Fixed sftp EOF packet handling
  * Fixed ssh_send_banner() to confirm with RFC 4253
  * Fixed some memory leaks
- resolves: #1419007

* Wed Feb 24 2016 Andreas Schneider <asn@redhat.com> - 0.7.3-1
- resolves: #1311259 - Fix CVE-2016-0739
- resolves: #1311332 - Update to version 0.7.3
  * Fixed CVE-2016-0739
  * Fixed ssh-agent on big endian
  * Fixed some documentation issues
- Enabled GSSAPI support

* Thu Feb 04 2016 Fedora Release Engineering <releng@fedoraproject.org> - 0.7.2-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_24_Mass_Rebuild

* Thu Oct 22 2015 Andreas Schneider <asn@redhat.com> - 0.7.2-2
- resolves: #1271230 - Fix ssh-agent support on big endian

* Wed Sep 30 2015 Andreas Schneider <asn@redhat.com> - 0.7.2-1
- Update to version 0.7.2
  * Fixed OpenSSL detection on Windows
  * Fixed return status for ssh_userauth_agent()
  * Fixed KEX to prefer hmac-sha2-256
  * Fixed sftp packet handling
  * Fixed return values of ssh_key_is_(public|private)
  * Fixed bug in global success reply
- resolves: #1267346

* Tue Jun 30 2015 Andreas Schneider <asn@redhat.com> - 0.7.1-1
- Update to version 0.7.1
  * Fixed SSH_AUTH_PARTIAL auth with auto public key
  * Fixed memory leak in session options
  * Fixed allocation of ed25519 public keys
  * Fixed channel exit-status and exit-signal
  * Reintroduce ssh_forward_listen()

* Wed Jun 17 2015 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.7.0-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_23_Mass_Rebuild

* Thu May 21 2015 Orion Poplawski <orion@cora.nwra.com> - 0.7.0-2
- Add patch to fix undefined symbol: ssh_forward_listen (bug #1221310)

* Mon May 11 2015 Andreas Schneider <asn@redhat.com> - 0.7.0-1
- Update to version 0.7.0
  * Added support for ed25519 keys
  * Added SHA2 algorithms for HMAC
  * Added improved and more secure buffer handling code
  * Added callback for auth_none_function
  * Added support for ECDSA private key signing
  * Added more tests
  * Fixed a lot of bugs
  * Improved API documentation

* Thu Apr 30 2015 Andreas Schneider <asn@redhat.com> - 0.6.5-1
- resolves: #1213775 - Security fix for CVE-2015-3146
- resolves: #1218076 - Security fix for CVE-2015-3146

* Fri Dec 19 2014 - Andreas Schneider <asn@redhat.com> - 0.6.4-1
- Security fix for CVE-2014-8132.

* Sun Aug 17 2014 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.3-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_21_22_Mass_Rebuild

* Sat Jun 07 2014 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.3-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_21_Mass_Rebuild

* Tue Mar 04 2014 - Andreas Schneider <asn@redhat.com> - 0.6.3-1
- Fix CVE-2014-0017.

* Mon Feb 10 2014 - Andreas Schneider <asn@redhat.com> - 0.6.1-1
- Update to version 0.6.1.
- resolves: #1056757 - Fix scp mode.
- resolves: #1053305 - Fix known_hosts heuristic.

* Wed Jan 08 2014 - Andreas Schneider <asn@redhat.com> - 0.6.0-1
- Update to 0.6.0

* Fri Jul 26 2013 - Andreas Schneider <asn@redhat.com> - 0.5.5-1
- Update to 0.5.5.
- Clenup the spec file.

* Thu Jul 18 2013 Simone Caronni <negativo17@gmail.com> - 0.5.4-5
- Add EPEL 5 support.
- Add Debian patches to enable Doxygen documentation.

* Tue Jul 16 2013 Simone Caronni <negativo17@gmail.com> - 0.5.4-4
- Add patch for #982685.

* Mon Jun 10 2013 Simone Caronni <negativo17@gmail.com> - 0.5.4-3
- Clean up SPEC file and fix rpmlint complaints.

* Thu Feb 14 2013 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.5.4-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_19_Mass_Rebuild

* Wed Jan 23 2013 Petr Lautrbach <plautrba@redhat.com> 0.5.4-1
- update to security 0.5.4 release
- CVE-2013-0176 (#894407)

* Tue Nov 20 2012 Petr Lautrbach <plautrba@redhat.com> 0.5.3-1
- update to security 0.5.3 release (#878465)

* Thu Jul 19 2012 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.5.2-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_18_Mass_Rebuild

* Thu Feb 02 2012 Petr Lautrbach <plautrba@redhat.com> 0.5.2-1
- update to 0.5.2 version (#730270)

* Fri Jan 13 2012 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.5.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_17_Mass_Rebuild

* Wed Jun  1 2011 Jan F. Chadima <jchadima@redhat.com> - 0.5.0-1
- bounce versionn to 0.5.0 (#709785)
- the support for protocol v1 is disabled

* Tue Feb 08 2011 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.4.8-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_15_Mass_Rebuild

* Wed Jan 19 2011 Jan F. Chadima <jchadima@redhat.com> - 0.4.8-1
- bounce versionn to 0.4.8 (#670456)

* Mon Sep  6 2010 Jan F. Chadima <jchadima@redhat.com> - 0.4.6-1
- bounce versionn to 0.4.6 (#630602)

* Thu Jun  3 2010 Jan F. Chadima <jchadima@redhat.com> - 0.4.4-1
- bounce versionn to 0.4.4 (#598592)

* Wed May 19 2010 Jan F. Chadima <jchadima@redhat.com> - 0.4.3-1
- bounce versionn to 0.4.3 (#593288)

* Tue Mar 16 2010 Jan F. Chadima <jchadima@redhat.com> - 0.4.2-1
- bounce versionn to 0.4.2 (#573972)

* Tue Feb 16 2010 Jan F. Chadima <jchadima@redhat.com> - 0.4.1-1
- bounce versionn to 0.4.1 (#565870)

* Fri Dec 11 2009 Jan F. Chadima <jchadima@redhat.com> - 0.4.0-1
- bounce versionn to 0.4.0 (#541010)

* Thu Nov 26 2009 Jan F. Chadima <jchadima@redhat.com> - 0.3.92-2
- typo in spec file

* Thu Nov 26 2009 Jan F. Chadima <jchadima@redhat.com> - 0.3.92-1
- bounce versionn to 0.3.92 (0.4 beta2) (#541010)

* Fri Aug 21 2009 Tomas Mraz <tmraz@redhat.com> - 0.2-4
- rebuilt with new openssl

* Sat Jul 25 2009 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.2-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_12_Mass_Rebuild

* Tue Jun 02 2009 Jan F. Chadima <jchadima@redhat.com> - 0.2-2
- Small changes during review

* Mon Jun 01 2009 Jan F. Chadima <jchadima@redhat.com> - 0.2-1
- Initial build

