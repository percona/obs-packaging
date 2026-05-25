Name:           flex
Version:        2.6.4
Release:        1%{?dist}
Summary:        A tool for creating scanners (tokenizers)
License:        BSD
URL:            https://github.com/westes/flex
Source0:        flex-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  m4
BuildRequires:  gettext-devel

%description
The flex package contains a tool for generating scanners (programs
which recognize patterns in text). Flex takes pairs of regular
expressions and C code as input and generates a C source file as
output. The output file is compiled and linked with a library to
produce an executable. The executable searches through its input for
occurrences of the regular expressions and executes the associated C
code when a match is found. Flex was designed to work with both Yacc
and Bison parser-generation tools.

%package        devel
Summary:        Libraries for flex scanner development
Requires:       %{name} = %{version}-%{release}

%description    devel
This package contains static library and header file needed to develop
applications that use flex-generated scanners.

%prep
%autosetup

%build
export CFLAGS="$RPM_OPT_FLAGS -D_GNU_SOURCE"
export CXXFLAGS="$RPM_OPT_FLAGS -D_GNU_SOURCE"
%configure
%make_build

%install
%make_install
rm -f %{buildroot}%{_infodir}/dir
find %{buildroot}%{_libdir} -name '*.la' -delete
rm -rf %{buildroot}%{_docdir}/flex/

%files
%license COPYING
%doc AUTHORS ChangeLog NEWS README.md
%{_bindir}/flex
%{_bindir}/flex++
%{_libdir}/libfl.so.2*
%{_datadir}/locale/*/LC_MESSAGES/flex.mo
%{_mandir}/man1/flex.1*
%{_infodir}/flex.info*

%files devel
%{_includedir}/FlexLexer.h
%{_libdir}/libfl.so
%{_libdir}/libfl.a

%changelog
* Tue May 26 2026 Percona Build/Release Team <eng-build@percona.com> - 2.6.4-1
- Initial build of flex 2.6.4 for UBI-8
