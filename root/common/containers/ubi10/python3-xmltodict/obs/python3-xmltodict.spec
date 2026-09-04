%global python3_sitelib %(%{__python3} -c "import sysconfig; print(sysconfig.get_path('purelib'))")

Name:           python3-xmltodict
Version:        0.14.2
Release:        1
Summary:        Makes working with XML feel like you are working with JSON
License:        MIT
URL:            https://github.com/martinblech/xmltodict
Source0:        xmltodict-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-setuptools

%description
xmltodict is a Python module that makes working with XML feel like
working with JSON. It is used by KIWI for XML processing.

%prep
%setup -q -n xmltodict-%{version}

%install
python3 setup.py install --root=%{buildroot} --prefix=/usr

%files
%license LICENSE
%{python3_sitelib}/xmltodict*
%{python3_sitelib}/__pycache__/xmltodict*
