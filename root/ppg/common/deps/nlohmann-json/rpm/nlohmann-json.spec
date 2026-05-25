Name:           nlohmann-json
Version:        3.11.3
Release:        1%{?dist}
Summary:        JSON for Modern C++ -- a header-only JSON library
License:        MIT
URL:            https://github.com/nlohmann/json
Source0:        nlohmann-json-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  cmake
BuildRequires:  make

%description
A C++11 header-only JSON library with an intuitive syntax.

%package devel
Summary:        Development files for nlohmann-json
BuildArch:      noarch

%description devel
Headers and cmake modules for building applications that use nlohmann/json.

%prep
%autosetup -n json-%{version}

%build
%cmake \
    -DJSON_BuildTests=OFF

%cmake_install

%files devel
%license LICENSE.MIT
%{_includedir}/nlohmann/
%{_datadir}/cmake/nlohmann_json/
%{_datadir}/pkgconfig/nlohmann_json.pc

%changelog
* Tue May 26 2026 Percona Build/Release Team <eng-build@percona.com> - 3.11.3-1
- Initial build of nlohmann-json 3.11.3 for UBI-8
