Name:           bison
Version:        3.8.2
Release:        1%{?dist}
Summary:        A GNU general-purpose parser generator
License:        GPL-3.0-or-later
URL:            https://www.gnu.org/software/bison/
Source0:        bison-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  m4
BuildRequires:  perl
BuildRequires:  flex
BuildRequires:  gettext-devel

Requires:       m4

%description
Bison is a general purpose parser generator that converts a grammar
description for an LALR(1) context-free grammar into a C program to
parse that grammar.  Once proficient with Bison, you can use it to
develop a wide range of language parsers, from those used in simple
desk calculators to complex programming languages.

%prep
%autosetup

%build
%configure
%make_build

%install
%make_install
rm -f %{buildroot}%{_infodir}/dir
rm -rf %{buildroot}%{_docdir}/bison/

%files
%license COPYING
%doc AUTHORS ChangeLog NEWS README THANKS
%{_bindir}/bison
%{_bindir}/yacc
%{_datadir}/bison/
%{_datadir}/aclocal/bison-i18n.m4
%{_datadir}/locale/*/LC_MESSAGES/*.mo
%{_libdir}/liby.a
%{_mandir}/man1/bison.1*
%{_mandir}/man1/yacc.1*
%{_infodir}/bison.info*

%changelog
* Tue May 26 2026 Percona Build/Release Team <eng-build@percona.com> - 3.8.2-1
- Initial build of bison 3.8.2 for UBI-8
