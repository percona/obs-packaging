%global python3_sitelib %(%{__python3} -c "import sysconfig; print(sysconfig.get_path('purelib'))")

Name:           python3-poetry-core
Version:        1.9.1
Release:        1
Summary:        Poetry's core utilities — build backend for Python packages
License:        MIT
URL:            https://github.com/python-poetry/poetry-core
# Pre-built universal wheel to avoid self-referential bootstrap problem
Source0:        poetry_core-%{version}-py3-none-any.whl
BuildArch:      noarch
BuildRequires:  python3-pip
# tomli is required by poetry-core on Python < 3.11 (Rocky 9 uses Python 3.9)
Requires:       python3-tomli

%description
Poetry Core provides the core utilities for the Poetry packaging tool,
including a PEP 517 build backend used to build Python packages that
use pyproject.toml with the poetry build system.

%install
python3 -m pip install --no-deps \
    --prefix=/usr --root=%{buildroot} %{SOURCE0}

%files
%{python3_sitelib}/poetry*
