# PERCONA PACKAGE for ppg:common:deps:tarballs.
#
# Why this exists: build-tarball.sh rewrites every bundled ELF's RUNPATH
# with patchelf. EPEL 8 ships patchelf 0.12, which fails with "unsupported
# overlap of SHT_NOTE and PT_NOTE" on binaries whose note layout comes from
# newer toolchains — proven on PG 16's unstripped pg_verifybackup, which
# then shipped in the ssl1.1 tarball WITHOUT a RUNPATH and could not
# resolve libpq.so.5 on any EL8 QA host.
#
# Why 0.19.1 and nothing older: every earlier release we tried broke a
# different subset of the artifact, always exiting 0 and never saying so:
#
#   * 0.12 (EPEL 8) REFUSES binaries with the newer SHT_NOTE/PT_NOTE
#     layout ("unsupported overlap") — pg_verifybackup shipped with no
#     RUNPATH and could not resolve libpq on EL8 hosts.
#   * 0.17.2 writes EXECUTABLES whose program headers make glibc's rtld
#     segfault in dl_main() before any program code runs — pg_ctl,
#     pg_basebackup, pg_checksums, pg_resetwal on EL8; createdb,
#     createuser on EL9; bin/postgres on the EL9 PG 14 build. That reached
#     the released 18.6 tarball.
#   * 0.18.0 fixes those but writes SHARED LIBRARIES with misaligned
#     PT_LOAD segments — the loader rejects them ("ELF load command
#     address/offset not properly aligned"): every EL8 ICU library and
#     libgssapi_krb5, so every ssl1.1 build of PG 15-18 died at
#     initdb --version.
#
# Measured on Rocky 8 (PG 16 binaries + distro ICU 60) and Rocky 9.6 (PG
# 18 binaries + ICU 67), each version patching the pristine files:
#
#     object                          0.12      0.17.2    0.18.0    0.19.1
#     pg_verifybackup (EL8)           REFUSED   ok        ok        ok
#     pg_ctl/pg_basebackup/... (EL8)  ok        CRASHES   ok        ok
#     createdb/createuser (EL9)       ok        CRASHES   ok        ok
#     libicu{i18n,uc,data} (EL8)      ok        ok        REJECTED  ok
#     libicu{i18n,uc,data} (EL9)      ok        ok        ok        ok
#
# 0.19.1 is the tagged upstream release carrying the alignment fixes
# ("Fix alignment problem when rewriting sections", "rewriteSectionsLibrary:
# cap honoured PT_LOAD alignment") and builds with the stock EL8 gcc-c++.
# build-tarball.sh's loader gate now fails the build on ANY loader
# rejection (not just crashes) and probes shared objects directly, so the
# next regression of this kind fails the build instead of shipping.

%undefine _package_note_file

Summary:        Utility to modify the dynamic linker and RPATH of ELF executables
Name:           patchelf
# Placeholder: rewritten by the OBS set_version source service (see obs/_service).
Version:        1.0.0
Release:        1.percona%{?dist}
License:        GPL-3.0-or-later
Group:          Development/Tools
Url:            https://github.com/NixOS/patchelf
Vendor:         Percona, LLC

Source0:        patchelf-%{version}.tar.gz

BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  autoconf
BuildRequires:  automake

%description
patchelf modifies the dynamic loader path, RUNPATH/RPATH and DT_NEEDED
entries of existing ELF executables and libraries. Rebuilt from the
upstream 0.19.1 release for the Percona PostgreSQL binary-tarball build
chroots, where EPEL 8's 0.12 cannot parse newer note-section layouts.

%prep
%setup -q -n patchelf-%{version}

%build
./bootstrap.sh
%configure
%make_build

%install
%make_install
# No need to ship upstream's docs/completions in a chroot-only tool.
rm -rf %{buildroot}%{_docdir} %{buildroot}%{_datadir}/zsh

%check
# The one job this package has is to rewrite RUNPATHs WITHOUT breaking the
# object. Self-patch, then make the loader accept both the patched
# executable (trace it) and the patched shared library (ld.so --list) —
# exactly the two classes 0.17.2 and 0.18.0 respectively corrupted while
# exiting 0. A mere --print-rpath round-trip would have passed both.
cp src/patchelf /tmp/pe-selftest
./src/patchelf --set-rpath '$ORIGIN/../lib' /tmp/pe-selftest
./src/patchelf --print-rpath /tmp/pe-selftest | grep -q ORIGIN
LD_TRACE_LOADED_OBJECTS=1 /tmp/pe-selftest >/dev/null
cp %{_libdir}/libz.so.1* /tmp/ 2>/dev/null || cp /lib64/libz.so.1* /tmp/
LIB=$(ls /tmp/libz.so.1.* | head -1)
./src/patchelf --set-rpath '$ORIGIN' "$LIB"
LDSO=$(readelf -lW /tmp/pe-selftest | sed -n 's/.*interpreter: \([^]]*\)\].*/\1/p')
"$LDSO" --list "$LIB" >/dev/null

%files
%license COPYING
%{_bindir}/patchelf
%{_mandir}/man1/patchelf.1*

%changelog
* Mon Sep 21 2026 Ricardo Dias <ricardo.dias@percona.com> - 0.19.1-1
- Bump to 0.19.1: 0.18.0 misaligned PT_LOAD in shared libraries on EL8
  (loader rejects libicu*/libgssapi_krb5 — every ssl1.1 build failed).
  %check now makes the loader accept a patched executable AND library.
* Fri Sep 18 2026 Ricardo Dias <ricardo.dias@percona.com> - 0.18.0-1
- Bump to 0.18.0: 0.17.2 silently corrupted some binaries (rtld segfaults
  in dl_main) — pg_ctl/pg_basebackup on EL8, createdb/createuser on EL9.
* Mon Sep 15 2026 Ricardo Dias <ricardo.dias@percona.com> - 0.17.2-1
- patchelf 0.17.2 for the tarball build chroots: EPEL 8's 0.12 fails on
  newer SHT_NOTE/PT_NOTE layouts (PG 16 pg_verifybackup).
