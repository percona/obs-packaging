# pgAdmin 4 on UBI-9 — sub-project 3: the Python 3.12 dependency stack design

**Date:** 2026-08-26
**Status:** approved in brainstorming, awaiting spec review
**Parent:** `2026-08-26-pgadmin4-tooling-design.md` (decomposition §4; decisions §3)
**Scope of this document:** every `python3.12-*` RPM that `percona-pgadmin4` (SP4) needs
on UBI-9 and that neither RHEL 9 nor `ppg:common:deps` already provides; the changes to
`ppg:common:deps` this requires; the spec template these packages share.

## 1. Goal

Provide, as ordinary OBS packages in this repository, the complete Python 3.12 runtime
closure of pgAdmin 4 `REL-9_9` (cloud extras excluded, as openSUSE does), built for
`/usr/bin/python3.12` on UBI 9, so that SP4's `percona-pgadmin4.spec` can simply
`BuildRequires`/`Requires` them by RPM name. No `percona_obs` code changes.

## 2. Findings that shaped the design

### 2.1 The closure

`pgadmin4/REL-9_9/requirements.txt`, minus `azure-*`, `boto3`, `google-*`, `pywinpty`,
with the `python_version > '3.9'` variants, resolved with
`uv pip compile --python-version 3.12` on 2026-08-26: **80 packages** (file
`pgadmin-closure-3.12.txt`; the `# via` edges are the source of every `Requires:` below).
A PyPI/openSUSE:Factory survey of all 80 produced, per package: canonical name, sdist,
build backend (from the sdist's `pyproject.toml`), native sources, licence and whether a
Factory `python-<Name>` package exists. Backend mix: 35 setuptools, 15 flit-core,
9 setup.py-only, 7 hatchling, 4 pyproject-without-backend (setuptools), 3 poetry-core,
1 pdm-backend, 1 `uv_build` (bidict 0.24), 1 maturin (cryptography 46), psycopg-c's
in-tree `cython_backend`, Pillow's in-tree `backend`.

### 2.2 What UBI-9 / Rocky 9 already ship for Python 3.12

AppStream: `python3.12` 3.12.14, `-devel`, `-libs`, `-pip` 23.2.1, `-setuptools` 68.2.2,
`-wheel` 0.41.2, `-cffi` 1.16.0, `-cryptography` 41.0.7, `-idna` 3.4, `-pycparser` 2.20,
`-urllib3` 1.26.19, `-requests` 2.28.2, `-charset-normalizer`, `-pyyaml`, `-lxml`,
`-psycopg2`, `-mod_wsgi` 4.9.4.
CRB: `-flit-core` 3.9.0, `-packaging` 23.2, `-pluggy` 1.2.0, `-pytest` 7.4.2,
`-iniconfig`, `-setuptools-rust` 1.7.0, `-semantic_version`, `-Cython` 0.29.35,
`-pybind11`. EPEL 9: `python3.12-setuptools_scm` 8.2.1 (+`+toml`).
Rocky 8 AppStream/PowerTools carry the same set (3.12.x); Rocky 10's default `python3`
*is* 3.12 (`python3-devel` provides `python3.12-devel`) and its CRB has `python3-hatchling`
1.27, `-pathspec`, `-trove-classifiers`, `-setuptools_scm`. openSUSE Tumbleweed and Leap
16.0 ship `python31x-hatchling` (Leap: 1.27.0) and `python31x-dnspython` (Leap: 2.7.0).
Native `-devel` libraries needed by the closure are all in UBI-9 AppStream: `libpq-devel`,
`krb5-devel`, `openssl-devel`, `libffi-devel`, `openldap-devel`, `brotli-devel`,
`libzstd-devel`, `libjpeg-turbo-devel`, `zlib-devel`. Rust 1.92 / cargo resolve from
Rocky 9 on UBI_9 (verified in `cargo-pgrx`'s `_buildinfo`).

### 2.3 Existing repo conventions

`ppg:common:deps` already builds `python3-six` 1.17.0, `python3-dateutil` 2.9.0.post0,
`python3-psutil` 6.1.1, `python3-click` 8.1.7 and `python3-dns` (dnspython **1.15.0**)
with a shared EL spec preamble (`__ospython=/usr/bin/python3.12`,
`python3_pkgprefix=python3.12`, `__requires_exclude ^python3\.12dist`; plain `python3` on
SUSE), `setup.py build/install --record`, `Epoch: 1`, sources via `obs_scm` from GitHub
tags. `python3-dns` is consumed by `python3-etcd` and all `percona-patroni` packages
(staging 14–18, devel 19) and builds on RockyLinux 8/9/10, UBI 8/9, Leap 16, Tumbleweed.
Directory names are `python3-<name>`; the RPM name is `%{python3_pkgprefix}-<name>`.

### 2.4 Constraints discovered

- **setuptools ≥ 77** (PEP 639 licence metadata) is required by the current keyring,
  jaraco.context, jaraco.functools, importlib-resources and Pillow releases; RHEL has 68.
- **Cython 3** is required by gssapi 1.10.1 (`Cython == 3.1.3`; 30 `.pyx`, no generated C);
  psycopg-c ships its generated C and SQLAlchemy's Cython speedups are optional.
- **dnspython** ≥ 2.0 is required by `email-validator` (Flask-Security-Too); dnspython
  dropped `setup.py` after 2.1.0 (2.2–2.4 poetry-core, 2.5+ hatchling).
- `bidict` 0.24 needs the Rust `uv_build` backend; `pyotp` 2.10 needs `hatch-vcs`;
  `ua-parser` 1.0 needs `ua-parser-builtins` (wheel-only, no Factory package).
- `trove-classifiers` uses `calver` at build time (`use_calver=` in `setup.py`).
- **RHEL's build backends are too old for current PEP 639 metadata** (`license = "…"`
  string + `license-files`, used by Flask, Werkzeug, Pygments and most 2025 releases):
  flit-core 3.9.0 aborts with `license field should be dict`; hatchling < 1.27 likewise.
  Current backends need `packaging >= 24.2` (RHEL: 23.2). Verified locally (2026-08-26):
  **pip 23.2.1 (RHEL's) + flit-core 3.12.0 / hatchling 1.28.0 / packaging 25.0** builds
  Flask 3.1.3 and Pygments 2.21.0 sdists into Metadata-Version 2.4 wheels and installs them
  with `pip install --root` — so the shared stack must carry current flit-core, hatchling
  and packaging, and pip itself is fine.

## 3. Decisions taken during brainstorming

| Topic | Decision |
|---|---|
| Version policy | **Reuse existing packages where the libraries' real minimums are met**, even where pgAdmin's `requirements.txt` pins newer: RHEL's cryptography 41.0.7, urllib3 1.26.19, setuptools 68.2.2, cffi, idna, pycparser; common:deps' psutil 6.1.1, click 8.1.7, six, dateutil. openSUSE and Debian ship pgAdmin against distro versions the same way. SP4 relaxes the pins. Consequence: no maturin/Rust for cryptography; no replacement of RHEL packages. |
| dnspython | **Bump `python3-dns` in `ppg:common:deps` to 2.8.0 for everyone**, keeping the package/RPM name, and add a **shared build-backend stack** to `ppg:common:deps` for EL8/EL9/UBI: flit-core 3.12.0, packaging 25.0, pathspec 0.12.1, trove-classifiers, hatchling 1.28.0 (§2.4: RHEL's flit-core 3.9 / packaging 23.2 cannot build PEP 639 metadata). EL10 and openSUSE use their distro `python3-hatchling`/`python3-flit-core`. `python3-etcd` and `percona-patroni` need no source change (dnspython 2 keeps `dns.resolver.query()`); they are dep-cascade rebuilt. |
| setuptools ≥ 77 packages | Pin down to the last releases that build with setuptools 68: keyring 25.2.1, jaraco.context 6.0.1, jaraco.functools 4.1.0, importlib-resources 6.5.2, Pillow 11.1.0 (all still satisfy pgAdmin's and their consumers' ranges). |
| Other backend avoidance | bidict 0.23.1 (setuptools), pyotp 2.9.0 (setuptools), ua-parser 0.18.0 (self-contained; `user-agents` needs ≥ 0.10) — `ua-parser-builtins` dropped. |
| Build tools packaged | `python3-cython` 3.1.3, `python3-poetry-core` 2.2.1, `python3-pdm-backend` 2.4.5 in `ppg:devel:pgadmin`; hatchling stack in `ppg:common:deps`. `setuptools_scm` from EPEL 9. |
| How the ~75 directories are produced | **Plain package directories, no generator or manifest committed.** A throwaway rendering script (scratchpad only) writes them consistently once; from then on they are maintained by hand like every other package. The shared template is documented in `PACKAGING_HOWTO.md`. |
| Sources | PyPI sdists via `download_url` (`https://files.pythonhosted.org/packages/source/<x>/<name>/<file>`, as openSUSE), literal versions in `_service` and spec. bcrypt adds `cargo_vendor` (`cargotoml=src/_bcrypt/Cargo.toml`). |
| `%check` | Import smoke test only (`%{__ospython} -c "import <module>"`); no pytest, to keep the closure closed. pgAdmin (SP4) is the integration test. |
| Naming | Directory/OBS package `python3-<PyPI name lower-cased, `_`/`.` → `-`>`; RPM `%{python3_pkgprefix}-<same>` (Fedora-style, e.g. `python3.12-flask-security-too`, `python3.12-jaraco-classes`). Exception kept: `python3-dns`. |

## 4. Inventory

### 4.1 New packages in `ppg:devel:pgadmin` (`root/ppg/devel/pgadmin/`, UBI_9 only)

68 runtime libraries + 3 build tools. "Required by" lists the closure consumers that get a
`Requires:` on this package (direct pgAdmin requirements have none listed; SP4 adds them).

| Directory | PyPI | Version | Build family | Arch | Required by (closure) | Notes |
|---|---|---|---|---|---|---|
| `python3-alembic` | alembic | 1.19.1 | setuptools | noarch | flask-migrate |  |
| `python3-authlib` | Authlib | 1.6.12 | setuptools | noarch |  |  |
| `python3-babel` | babel | 2.18.0 | setuptools | noarch | flask-babel |  |
| `python3-backports-zstd` | backports.zstd | 1.7.0 | setuptools | arch |  | libzstd-devel |
| `python3-bcrypt` | bcrypt | 5.0.0 | setuptools | arch | paramiko | Rust: setuptools-rust (CRB), cargo/rust; `cargo_vendor` with `cargotoml=src/_bcrypt/Cargo.toml` |
| `python3-bidict` | bidict | 0.23.1 | setuptools | noarch | python-socketio | pinned down from 0.24.1 (uv_build) |
| `python3-blinker` | blinker | 1.9.0 | flit | noarch | flask, flask-mail, flask-principal |  |
| `python3-brotli` | brotli | 1.2.0 | setuptools | arch | flask-compress | gcc-c++ |
| `python3-decorator` | decorator | 5.3.1 | setuptools | noarch | gssapi |  |
| `python3-email-validator` | email-validator | 2.3.0 | setuptools | noarch | flask-security-too | Requires python3.12-dns ≥ 2.0 (common:deps) and RHEL idna |
| `python3-flask` | Flask | 3.1.3 | flit | noarch | flask-babel, flask-compress, flask-login, flask-mail, flask-migrate, flask-paranoid, flask-principal, flask-security-too, flask-socketio, flask-sqlalchemy, flask-wtf | Requires common:deps click |
| `python3-flask-babel` | flask-babel | 4.0.0 | poetry | noarch |  |  |
| `python3-flask-compress` | Flask-Compress | 1.24 | setuptools | noarch |  | build: setuptools_scm (EPEL) |
| `python3-flask-login` | Flask-Login | 0.6.3 | setup.py | noarch | flask-security-too |  |
| `python3-flask-mail` | Flask-Mail | 0.10.0 | flit | noarch |  |  |
| `python3-flask-migrate` | Flask-Migrate | 4.1.0 | setuptools | noarch |  |  |
| `python3-flask-paranoid` | Flask-Paranoid | 0.3.0 | setuptools | noarch |  |  |
| `python3-flask-principal` | Flask-Principal | 0.4.0 | setup.py | noarch | flask-security-too |  |
| `python3-flask-security-too` | Flask-Security-Too | 5.6.2 | flit | noarch |  | Factory name `python-Flask-Security` |
| `python3-flask-socketio` | Flask-SocketIO | 5.5.1 | setuptools | noarch |  |  |
| `python3-flask-sqlalchemy` | Flask-SQLAlchemy | 3.1.1 | flit | noarch | flask-migrate |  |
| `python3-flask-wtf` | Flask-WTF | 1.2.2 | hatchling | noarch | flask-security-too |  |
| `python3-greenlet` | greenlet | 3.5.5 | setuptools | arch | sqlalchemy | gcc-c++ |
| `python3-gssapi` | gssapi | 1.10.1 | setuptools | arch |  | krb5-devel; build: python3.12-cython 3.1.3 (ours) |
| `python3-h11` | h11 | 0.16.0 | setuptools | noarch | wsproto |  |
| `python3-importlib-resources` | importlib-resources | 6.5.2 | setuptools | noarch | flask-security-too | pinned down from 7.1.0; build: setuptools_scm |
| `python3-itsdangerous` | itsdangerous | 2.2.0 | flit | noarch | flask, flask-wtf |  |
| `python3-jaraco-classes` | jaraco.classes | 3.4.0 | setuptools | noarch | keyring | build: setuptools_scm |
| `python3-jaraco-context` | jaraco.context | 6.0.1 | setuptools | noarch | keyring | pinned down from 6.1.2; build: setuptools_scm |
| `python3-jaraco-functools` | jaraco.functools | 4.1.0 | setuptools | noarch | keyring | pinned down from 4.6.0; build: setuptools_scm |
| `python3-jeepney` | jeepney | 0.9.0 | flit | noarch | keyring, secretstorage |  |
| `python3-jinja2` | Jinja2 | 3.1.6 | flit | noarch | flask, flask-babel |  |
| `python3-jsonformatter` | jsonformatter | 0.3.4 | setuptools | noarch |  |  |
| `python3-keyring` | keyring | 25.2.1 | setuptools | noarch |  | pinned down from 25.7.0; build: setuptools_scm |
| `python3-ldap3` | ldap3 | 2.9.1 | setup.py | noarch |  |  |
| `python3-libgravatar` | libgravatar | 1.0.4 | setup.py | noarch |  |  |
| `python3-mako` | Mako | 1.4.1 | setuptools | noarch | alembic |  |
| `python3-markdown-it-py` | markdown-it-py | 4.2.0 | flit | noarch | rich |  |
| `python3-markupsafe` | MarkupSafe | 3.0.3 | setuptools | arch | flask, flask-security-too, jinja2, mako, werkzeug, wtforms | C speedups |
| `python3-mdurl` | mdurl | 0.1.2 | flit | noarch | markdown-it-py |  |
| `python3-more-itertools` | more-itertools | 11.1.0 | flit | noarch | jaraco-classes, jaraco-functools |  |
| `python3-paramiko` | paramiko | 3.5.1 | setup.py | noarch | sshtunnel | Requires RHEL cryptography |
| `python3-passlib` | passlib | 1.7.4 | setup.py | noarch | flask-security-too |  |
| `python3-pillow` | pillow | 11.1.0 | setuptools (in-tree backend) | arch | qrcode | libjpeg-turbo-devel, zlib-devel; other codecs disabled; pinned down from 12.3.0 |
| `python3-psycopg` | psycopg | 3.2.10 | setuptools | noarch |  |  |
| `python3-psycopg-c` | psycopg-c | 3.2.10 | setuptools (in-tree cython_backend, ships C) | arch | psycopg | libpq-devel |
| `python3-pyasn1` | pyasn1 | 0.6.4 | setuptools | noarch | ldap3 |  |
| `python3-pygments` | Pygments | 2.21.0 | hatchling | noarch | rich |  |
| `python3-pynacl` | PyNaCl | 1.6.2 | setuptools | arch | paramiko | bundled libsodium; RHEL cffi |
| `python3-pyotp` | PyOTP | 2.9.0 | setuptools | noarch |  | pinned down from 2.10.0 (hatch-vcs) |
| `python3-python-engineio` | python-engineio | 4.13.5 | setuptools | noarch | python-socketio |  |
| `python3-python-socketio` | python-socketio | 5.16.4 | setuptools | noarch | flask-socketio |  |
| `python3-pytz` | pytz | 2025.2 | setup.py | noarch | flask-babel |  |
| `python3-qrcode` | qrcode | 8.2 | poetry | noarch |  |  |
| `python3-rich` | rich | 15.0.0 | poetry | noarch | typer |  |
| `python3-secretstorage` | SecretStorage | 3.5.0 | setuptools | noarch | keyring | Requires RHEL cryptography |
| `python3-shellingham` | shellingham | 1.5.4 | setuptools | noarch | typer |  |
| `python3-simple-websocket` | simple-websocket | 1.1.0 | setuptools | noarch | python-engineio |  |
| `python3-sqlalchemy` | SQLAlchemy | 2.0.52 | setuptools | arch | alembic, flask-sqlalchemy | C speedups via python3.12-cython (ours) |
| `python3-sqlparse` | sqlparse | 0.6.0 | hatchling | noarch |  |  |
| `python3-sshtunnel` | sshtunnel | 0.4.0 | setuptools | noarch |  |  |
| `python3-typer` | typer | 0.19.2 | pdm | noarch |  | Requires common:deps click |
| `python3-typing-extensions` | typing-extensions | 4.16.0 | flit | noarch | alembic, psycopg, sqlalchemy, typer |  |
| `python3-ua-parser` | ua-parser | 0.18.0 | setup.py | noarch | user-agents | self-contained 0.18 (replaces 1.0 + ua-parser-builtins) |
| `python3-user-agents` | user-agents | 2.2.0 | setup.py | noarch |  |  |
| `python3-werkzeug` | Werkzeug | 3.1.8 | flit | noarch | flask, flask-login |  |
| `python3-wsproto` | wsproto | 1.3.2 | setuptools | noarch | simple-websocket |  |
| `python3-wtforms` | WTForms | 3.2.2 | hatchling | noarch | flask-security-too, flask-wtf |  |
| `python3-cython` | Cython | 3.1.3 | build tool (setup.py) | arch | build-time only (gssapi, sqlalchemy) | overrides CRB's 0.29 by version within the project |
| `python3-poetry-core` | poetry-core | 2.2.1 | build tool (self-hosting) | noarch | build-time only (flask-babel, qrcode, rich) | `PYTHONPATH=src` |
| `python3-pdm-backend` | pdm-backend | 2.4.5 | build tool (self-hosting) | noarch | build-time only (typer) | `PYTHONPATH=src` |

### 4.2 `ppg:common:deps` (`root/ppg/common/deps/`)

| Directory | PyPI | Version | Build family | Builds on | Notes |
|---|---|---|---|---|---|
| `python3-dns` | dnspython | 2.8.0 | hatchling | all RPM repos (as today) | bump 1.15.0 → 2.8.0, name kept; `_service` moves to `download_url`; consumers `python3-etcd`, `percona-patroni` ×6 rebuilt by dep-cascade |
| `python3-flit-core` | flit-core | 3.12.0 | self-hosting (`PYTHONPATH=.`) | RockyLinux_8/9, UBI_8/9 | `build:` disables RockyLinux_10, openSUSE_Leap_16, openSUSE_Tumbleweed (distro backends there); newer than CRB's 3.9.0 by version |
| `python3-packaging` | packaging | 25.0 | flit | RockyLinux_8/9, UBI_8/9 | same build flags; newer than CRB's 23.2 by version |
| `python3-pathspec` | pathspec | 0.12.1 | flit | RockyLinux_8/9, UBI_8/9 | same build flags |
| `python3-trove-classifiers` | trove-classifiers | 2025.9.11.17 | setuptools | RockyLinux_8/9, UBI_8/9 | same build flags; patch: drop `calver`, set version literally |
| `python3-hatchling` | hatchling | 1.28.0 | self-hosting (`PYTHONPATH=src`) | RockyLinux_8/9, UBI_8/9 | same build flags; Requires packaging ≥ 24.2 (ours), pathspec, trove-classifiers, RHEL pluggy |

### 4.3 Reused, not built

| RPM | Provided by | Version | Closure asked for |
|---|---|---|---|
| python3.12-cffi | RHEL 9 AppStream | 1.16.0 | 2.1.1 |
| python3.12-cryptography | RHEL 9 AppStream | 41.0.7 | 46.0.7 |
| python3.12-idna | RHEL 9 AppStream | 3.4 | 3.19 |
| python3.12-pycparser | RHEL 9 AppStream | 2.20 | 3.0 |
| python3.12-setuptools | RHEL 9 AppStream | 68.2.2 | 80.10.2 |
| python3.12-urllib3 | RHEL 9 AppStream | 1.26.19 | 2.5.0 |
| python3.12-click | ppg:common:deps | 8.1.7 | 8.5.0 |
| python3.12-psutil | ppg:common:deps | 6.1.1 | 7.1.3 |
| python3.12-dateutil | ppg:common:deps | 2.9.0.post0 | 2.9.0.post0 |
| python3.12-six | ppg:common:deps | 1.17.0 | 1.17.0 |
| build-only: python3.12-pip, -wheel, -flit-core, -packaging, -pluggy, -setuptools-rust | RHEL 9 | 23.2.1, 0.41.2, 3.9.0, 23.2, 1.2.0, 1.7.0 | — |
| build-only: python3.12-setuptools_scm | EPEL 9 | 8.2.1 | — |
| — (dropped) | — | — | ua-parser-builtins 202606 |

## 5. The spec template

Every package follows one template; the three build families differ only in
`%build`/`%install`.

### 5.1 Header (identical to `python3-click`)

```rpmspec
%global debug_package %{nil}            # noarch packages only

%if 0%{?rhel} && 0%{?rhel} >= 8
%global __ospython        %{_bindir}/python3.12
%global python3_pkgprefix python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%else
%global __ospython        %{_bindir}/python3
%global python3_pkgprefix python3
%global python3_buildversion 3
%endif
%{expand: %%global py3ver %(echo `%{__ospython} -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")
# arch packages: python3_sitearch with 'platlib'

Name:           %{python3_pkgprefix}-flask
Version:        3.1.3
Release:        1%{?dist}
Summary:        ...
License:        BSD-3-Clause
URL:            https://flask.palletsprojects.com
Source0:        flask-%{version}.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  python%{python3_buildversion}-flit-core        # family: flit
Requires:       %{python3_pkgprefix}-werkzeug >= 3.1.0        # from PyPI requires_dist
Requires:       %{python3_pkgprefix}-jinja2 >= 3.1.2
Requires:       %{python3_pkgprefix}-itsdangerous >= 2.2
Requires:       %{python3_pkgprefix}-click >= 8.1.3
Requires:       %{python3_pkgprefix}-blinker >= 1.9
Requires:       %{python3_pkgprefix}-markupsafe
```

Backend BuildRequires per family: `-flit-core` (ours on EL8/9, §4.2); `-hatchling`
behind the conditional below; `-poetry-core` / `-pdm-backend` (ours); `-setuptools_scm`
where the sdist's `[build-system] requires` lists it; `-setuptools-rust` + `cargo` +
`rust` (bcrypt); `-cython` (gssapi, sqlalchemy); `gcc`/`gcc-c++` and `-devel` libraries
for native packages. Runtime `Requires:` are the closure edges with the minimum PyPI
declares; reused distro packages are named verbatim (`python3.12-cryptography`) and
never carry a floor (RHEL's versions are older than several upstream floors but work,
§3). **Every runtime `Requires:` is also emitted as a `BuildRequires:`** so the `%check`
import test can run in the build root (standard Python packaging practice; OBS orders the
builds accordingly).

```rpmspec
%if 0%{?rhel} == 8 || 0%{?rhel} == 9
BuildRequires:  %{python3_pkgprefix}-hatchling       # ours, ppg:common:deps
%else
BuildRequires:  python3-hatchling                     # EL10 CRB / openSUSE
%endif
```

### 5.2 Build families

1. **pyproject** (setuptools, flit, hatchling, poetry, pdm — 66 packages):
   ```rpmspec
   %prep
   %autosetup -p1 -n flask-%{version}
   %build
   %{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .
   %install
   %{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl
   ```
2. **setup.py-only** (9 packages): the existing `setup.py build` /
   `setup.py install --single-version-externally-managed -O1 --root ... --record INSTALLED_FILES`
   recipe from `python3-click`, unchanged.
3. **self-hosting backends** (hatchling, poetry-core, pdm-backend): family 1 with
   `PYTHONPATH=src` exported for the `pip wheel` step.

`%files`: `%{python3_sitelib}/*` (or `%{python3_sitearch}/*`) plus explicit
`%{_bindir}/<script>` entries; `%license` and `%doc` where the sdist ships them. The
buildroot only ever holds this package, so the glob is exact. RHEL's
`python3-rpm-generators` add `python3.12dist(<name>) = <version>` Provides from the
`.dist-info`.

`%check`: `PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import <module>[; import <module2>]"`
(from the installed buildroot — src-layout packages are not importable from the source
directory; `%{python3_sitearch}` for arch packages). The `-P` flag is load-bearing: without
it Python prepends the current working directory (the source tree, not the buildroot) to
`sys.path`, so native-extension packages import the pure-Python source instead of the
installed build (e.g. gssapi's `No module named gssapi.raw.creds`); this was the single
fix applied across all 77 specs in the first build round (`52d93bc`).

`%changelog`: one entry, `* <Day Mon DD YYYY> Percona Development Team <info@percona.com> - <version>-1`.

### 5.3 Patches

Only what a build needs: `trove-classifiers` (two `sed`s in `%prep`: remove `calver` from
`pyproject.toml`'s `requires`, replace `use_calver=...` with `version="%{version}"`);
anything a first build reveals is fixed in that package's spec.

Second standing patch, added during the build loop: for the 7 setuptools-family packages
(alembic, backports-zstd, greenlet, mako, markupsafe, secretstorage, wsproto) RHEL
setuptools 68 rejects PEP 639's `license = "…"` SPDX-expression form plus `license-files`
— a `%prep` `sed` rewrites `license = "…"` to the legacy `license = {text = "…"}` table
and drops the `license-files` key, rather than shipping a newer setuptools (`176d706`).

### 5.4 `package.yaml` and `obs/_service`

```yaml
title: Flask 3.1.3 for Python 3.12
description: |
  ... one paragraph; RPM-only, Python 3.12, consumed by percona-pgadmin4.
```
`ppg:devel:pgadmin` packages carry no `build:` flags (the project is UBI_9-only); the
`ppg:common:deps` hatchling stack disables RockyLinux_10 and both openSUSE repos.

```xml
<services>
  <service name="download_url">
    <param name="url">https://files.pythonhosted.org/packages/source/f/flask/flask-3.1.3.tar.gz</param>
  </service>
</services>
```
bcrypt adds `<service mode="buildtime" name="cargo_vendor">` with `src`, `cargotoml`
`src/_bcrypt/Cargo.toml`, `compression gz`, `update false`; its spec unpacks
`vendor.tar.gz` with `%autosetup -a1` so cargo builds offline.

## 6. How the directories are produced

Plain directories under `root/ppg/devel/pgadmin/` and `root/ppg/common/deps/`, each
`{package.yaml, obs/_service, rpm/python3-<name>.spec}` (+ `rpm/*.patch` if any). A
throwaway script in the implementer's scratchpad renders them once from the survey data
so that 75 files come out consistent; it is **not committed** and leaves no trace beyond
the packages. Afterwards every package is hand-maintained like any other here: bump by
editing `_service` URL + spec `Version:` + changelog.

Documentation committed with the packages:
- `docs/PACKAGING_HOWTO.md`: new section "Python 3.12 packages (pyproject builds)" with
  the header block, the three families, the hatchling conditional, `%check`, and the
  reuse-RHEL policy, so the next Python package follows the same pattern.
- `root/README.md`: `devel/pgadmin/` now holds pgAdmin's Python 3.12 stack;
  `common/deps/` gains the hatchling build stack.
- `.github/copilot-instructions.md`: no change (no tooling or workflow changes in SP3).

## 7. Testing & verification

No `percona_obs` code changes, hence no new unit tests; `black`, `pyright`, `pytest`
still run to show nothing else moved.

**Local, read-only** (before pushing):
- `rpmspec -P` over every generated spec (macro/syntax errors).
- `sync push --dry-run -P isv-pr` on one package per family plus bcrypt: proves
  `download_url` follows PyPI's redirects and `cargo_vendor` vendors the nested crate.

**OBS via PR #12**, bottom-up commits so failures localise:
1. `ppg:common:deps`: hatchling stack + dnspython bump → green on RockyLinux 8/9(/10 for
   dns), UBI 8/9, Leap 16, Tumbleweed; `python3-etcd` and `percona-patroni` cascade
   rebuilds green.
2. `ppg:devel:pgadmin`: build tools (cython, poetry-core, pdm-backend) and the leaf
   libraries with no intra-stack dependencies.
3. `ppg:devel:pgadmin`: the rest (OBS orders builds by `BuildRequires`).

**Acceptance for SP3:** all 71 pgadmin packages `succeeded` on UBI_9 x86_64 and aarch64;
the 6 common:deps packages (`python3-dns` and the five build-backend packages) `succeeded`
on every repo they build for; `local-npm-registry` and every other package in the PR
project unchanged.

## 8. Risks and mitigations

| Risk | Mitigation / observed outcome |
|---|---|
| RHEL pip 23.2.1 rejects Metadata-Version 2.4 wheels emitted by flit/hatchling | **Retired** — reproduced locally with pip 23.2.1 + flit-core 3.12.0 / hatchling 1.28.0: Flask and Pygments build and install fine (§2.4). |
| `setuptools_scm` (EPEL) cannot determine the version from a sdist | Did not occur: keyring, jaraco.*, importlib-resources, Flask-Compress built from PKG-INFO without `SETUPTOOLS_SCM_PRETEND_VERSION`. |
| Pillow 11.1 configure picks up codecs UBI-9 lacks | Did not occur: built with the jpeg/zlib-only `-C` flags as planned. |
| bcrypt cargo goes online | Occurred: `cargo_vendor` places `vendor/` and `.cargo/config.toml` under `src/_bcrypt/`, not the sdist root; fixed by `CARGO_HOME=$PWD/src/_bcrypt/.cargo` (`fce0164`). |
| gssapi needs exactly Cython 3.1.3 | Cython 3.1.3 resolved correctly; the failure was `%check` importing the source tree instead of the buildroot (fixed by `%{__ospython} -P -c "import ..."`, `52d93bc`). |
| dnspython 2 changes break python-etcd / patroni at runtime | Not exercised in PR #12 (label `no-dep-cascade`; PR project is UBI_9-only) — the cascade rebuild happens on merge; `python3-dns` 2.8.0 itself built successfully on UBI_9. |
| A package's first OBS build fails for a reason not foreseen here | Occurred, 12 packages failed the first build (9 on x86_64: backports-zstd, bcrypt, flask-principal, greenlet, gssapi, markupsafe, psycopg-c, qrcode, secretstorage; 3 only on aarch64: psycopg, ua-parser, wsproto); fixed by 10 commits over 3 rounds: RHEL setuptools 68 rejects PEP 639 `license = "…"` + `license-files` in 7 setuptools-family packages (alembic, backports-zstd, greenlet, mako, markupsafe, secretstorage, wsproto) → `%prep` sed to `license = {text = "…"}` (`176d706`); `%check` shadowed by the source tree for all 77 specs → `%{__ospython} -P` (`52d93bc`); flask-principal's PyPI metadata omits Flask/blinker → added as BuildRequires/Requires (`4441f17`); psycopg needs libpq at import → BuildRequires/Requires libpq (`2b65469`); psycopg-c refuses import unless psycopg is imported first → BuildRequires python3.12-psycopg, `%check` imports psycopg then psycopg_c (`3a385e0`); qrcode's `console_scripts.py` has an ambiguous shebang → removed in `%prep` (`d8ade24`); ua-parser's `setup_requires=["pyyaml"]` tries a live PyPI fetch → BuildRequires python3.12-pyyaml, drop `setup_requires` (`9836542`); bcrypt cargo_vendor path (see above, `fce0164`); greenlet's wheel installs an unpackaged `greenlet.h` header → added to `%files` (`abdc615`); WTForms' hatch build hook needs Babel to compile translations → BuildRequires python3.12-babel (`5498b3e`). |
| OBS rebuild storms from download-on-demand path-repo refreshes ("meta change") on a slow x86_64 scheduler | New: after the fixes, both PR projects rebuilt three more times with `_jobhistory` reason "meta change" (Rocky 9 / EPEL 9 DoD repos refreshing) — roughly 4 hours from first push to a settled board, not caused by our pushes (every sync logged `= project meta/config`); expect the same behaviour on merge, nothing to fix in our packages. |

## 9. Out of scope

`percona-pgadmin4` itself (SP4); Debian/Ubuntu; pytest-based `%check`; any other
product's Python dependencies; replacing RHEL `python3.12-*` packages.
