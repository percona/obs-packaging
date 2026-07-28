# PERCONA PACKAGE for ppg:common:deps (RockyLinux_8 and RockyLinux_9 only).
#
# /opt-prefixed Tcl runtime consumed by the Percona PostgreSQL binary
# tarball (QA item 4 of the 2026-07 tarball QA round).
#
# Why this exists: the tarball bundles the RPM-built pltcl.so, which links
# libtcl8.6.so; the distro libtcl's compiled-in TCL_LIBRARY default is
# /usr/share/tcl8.6, which does not exist on the tarball's target hosts,
# so pltcl only worked when the server was started through an
# env-exporting wrapper (TCL_LIBRARY) and QA proved any wrapper bypass
# breaks it ("could not initialize Tcl interpreter"). This package builds
# Tcl from source with --prefix=/opt/percona-tcl so the compiled-in
# TCL_LIBRARY default is /opt/percona-tcl/lib/tcl8.6 and pltcl works with
# ZERO environment variables — the official tarball's mechanism.
#
# Version: one 8.6.x for both bases. pltcl.so links the unversioned
# SONAME libtcl8.6.so and Tcl is ABI-stable within the 8.6 series; 8.6.10
# is the newer of the two distro-shipped minors (EL8 ships 8.6.8, EL9
# ships 8.6.10), verified to serve pltcl on BOTH bases.
#
# The name is deliberately distinct from the distro tcl and everything
# installs under /opt/percona-tcl: nothing shadows system packages.
# ppg:common:deps is publish=false project-wide.

%global tcl_prefix /opt/percona-tcl
%global tcl_major 8.6

# PERCONA: self-contained /opt runtime — do not leak provides from the
# /opt tree, and libtcl8.6.so is our own file (do not require it).
%global __provides_exclude_from ^%{tcl_prefix}/.*$
%global __requires_exclude ^libtcl8\\.6\\.so
# PERCONA: keep /opt shebangs untouched.
%undefine __brp_mangle_shebangs

Name:           percona-tarball-tcl
Version:        8.6.10
Release:        1%{?dist}
Summary:        Tcl runtime under /opt/percona-tcl for the Percona PostgreSQL binary tarball
License:        TCL
URL:            https://www.tcl.tk/
Source0:        tcl%{version}-src.tar.gz

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  zlib-devel

%description
Tcl %{version} built from the upstream source with
--prefix=/opt/percona-tcl, so libtcl8.6.so's compiled-in TCL_LIBRARY
default is /opt/percona-tcl/lib/tcl8.6 and the RPM-built pltcl.so
initializes its interpreter without any environment variables. Consumed
by the Percona PostgreSQL binary tarball build; not intended for
standalone installation.

%prep
%setup -q -n tcl%{version}

%build
cd unix
# PERCONA: LIBS=-lm — tcl's configure probes sin() with a program gcc
# resolves via its builtin, so MATH_LIBS comes out empty and libtcl8.6.so
# underlinks libm (undefined sinh/atan2/... at the tclsh link on EL9).
./configure \
    --prefix=%{tcl_prefix} \
    --enable-shared \
    --enable-threads \
    --enable-64bit \
    CFLAGS="%{optflags}" \
    LIBS="-lm"
make %{?_smp_mflags}

%install
make -C unix install INSTALL_ROOT=%{buildroot}

# PERCONA: unversioned tclsh convenience link, like the distro ships.
ln -sf tclsh%{tcl_major} %{buildroot}%{tcl_prefix}/bin/tclsh

%files
%license license.terms
%{tcl_prefix}

%changelog
* Tue Jul 28 2026 Percona Build/Release Team <eng-build@percona.com> - 8.6.10-1
- Initial /opt/percona-tcl runtime for the Percona PostgreSQL binary
  tarball: Tcl 8.6.10 built from upstream source with the TCL_LIBRARY
  default compiled to /opt/percona-tcl/lib/tcl8.6, so the RPM-built
  pltcl.so works with zero environment variables (tarball QA item 4).
