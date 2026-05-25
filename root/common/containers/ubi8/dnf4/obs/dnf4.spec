Name:           dnf4
Version:        4.14.0
Release:        1
Summary:        Compatibility stub providing dnf4 on UBI-8
License:        GPLv2+
URL:            https://rpm.org
BuildArch:      noarch
Requires:       dnf
%define debug_package %{nil}

%description
Compatibility package providing the dnf4 virtual provide for UBI-8,
where DNF 4.x ships as 'dnf'.

%prep

%build

%install

%files
