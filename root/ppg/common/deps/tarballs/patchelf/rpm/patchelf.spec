# PERCONA PACKAGE for ppg:common:deps:tarballs.
#
# Why this exists: build-tarball.sh rewrites every bundled ELF's RUNPATH
# with patchelf. EPEL 8 ships patchelf 0.12, which fails with "unsupported
# overlap of SHT_NOTE and PT_NOTE" on binaries whose note layout comes from
# newer toolchains — proven on PG 16's unstripped pg_verifybackup, which
# then shipped in the ssl1.1 tarball WITHOUT a RUNPATH and could not
# resolve libpq.so.5 on any EL8 QA host.
#
# Why 0.18.0 and not 0.17.x: 0.17.2 SILENTLY CORRUPTS some binaries — it
# exits 0, writes a plausible-looking ELF, and glibc's rtld then segfaults
# in dl_main() before any program code runs. Measured on a Rocky 8 base
# with PG 16's own binaries:
#
#     binary            0.12          0.17.2      0.18.0
#     pg_verifybackup   REFUSED       ok          ok
#     pg_ctl            ok            CRASHES     ok
#     pg_basebackup     ok            CRASHES     ok
#
# and on EL9 with PG 18's, 0.17.2 corrupts createdb/createuser instead.
# That shipped: the released 18.6 ssl3 tarball carries a segfaulting
# createdb/createuser, PG 16's ssl1.1 a segfaulting pg_ctl (QA job
# tarball-parallel-ssl1 #427), and PG 14's EL9 build died on its own
# smoke probe. 0.18.0 fixes every case while keeping the 0.12 gap closed,
# and builds with the stock EL8 gcc-c++. build-tarball.sh additionally
# gates every patched ELF through the loader now, so a corrupt binary can
# never reach an artifact again regardless of patchelf version.

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
upstream 0.18.0 release for the Percona PostgreSQL binary-tarball build
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
# The one job this package has: cope with SHT_NOTE/PT_NOTE layouts 0.12
# rejects. Exercise a self-patch as a smoke test.
cp src/patchelf /tmp/pe-selftest
./src/patchelf --set-rpath '$ORIGIN/../lib' /tmp/pe-selftest
./src/patchelf --print-rpath /tmp/pe-selftest | grep -q ORIGIN

%files
%license COPYING
%{_bindir}/patchelf
%{_mandir}/man1/patchelf.1*

%changelog
* Fri Sep 18 2026 Ricardo Dias <ricardo.dias@percona.com> - 0.18.0-1
- Bump to 0.18.0: 0.17.2 silently corrupted some binaries (rtld segfaults
  in dl_main) — pg_ctl/pg_basebackup on EL8, createdb/createuser on EL9.
* Mon Sep 15 2026 Ricardo Dias <ricardo.dias@percona.com> - 0.17.2-1
- patchelf 0.17.2 for the tarball build chroots: EPEL 8's 0.12 fails on
  newer SHT_NOTE/PT_NOTE layouts (PG 16 pg_verifybackup).
