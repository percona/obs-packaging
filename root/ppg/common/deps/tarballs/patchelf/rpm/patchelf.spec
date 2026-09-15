# PERCONA PACKAGE for ppg:common:deps:tarballs.
#
# Why this exists: build-tarball.sh rewrites every bundled ELF's RUNPATH
# with patchelf. EPEL 8 ships patchelf 0.12, which fails with "unsupported
# overlap of SHT_NOTE and PT_NOTE" on binaries whose note layout comes from
# newer toolchains — proven on PG 16's unstripped pg_verifybackup, which
# then shipped in the ssl1.1 tarball WITHOUT a RUNPATH and could not
# resolve libpq.so.5 on any EL8 QA host. 0.17.2 handles that layout
# (verified against the exact failing binary on a Rocky 8 base) and builds
# with the stock EL8 gcc-c++. The EVR beats EPEL's 0.12, so the ssl
# chroots pick this build; on newer bases whichever of ours/EPEL's is
# newer wins — both are fine there.

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
upstream 0.17.2 release for the Percona PostgreSQL binary-tarball build
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
* Mon Sep 15 2026 Ricardo Dias <ricardo.dias@percona.com> - 0.17.2-1
- patchelf 0.17.2 for the tarball build chroots: EPEL 8's 0.12 fails on
  newer SHT_NOTE/PT_NOTE layouts (PG 16 pg_verifybackup).
