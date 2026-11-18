# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [common-tools-2] - 2026-11-18

### Added

### Changed
- percona-pgbackrest: update upstream version 2.60.1
- percona-pgadmin4 (ubi9) [container image]: update image common-tools-1 → common-tools-2
  - updated: curl 8.23.0-3.1.el9 -> 8.23.0-3.2.el9
  - updated: libcurl 8.23.0-3.1.el9 -> 8.23.0-3.2.el9
  - updated: libicu 67.1-11.2.el9 -> 67.1-11.3.el9
  - updated: percona-pgadmin4 9.17-2.5.el9 -> 9.17-2.7.el9
  - updated: percona-pgadmin4-gunicorn 9.17-2.5.el9 -> 9.17-2.7.el9
  - updated: percona-postgresql14 14.25-1.1.el9 -> 14.25-3.1.el9
  - updated: percona-postgresql14-libs 14.25-1.1.el9 -> 14.25-3.1.el9
  - updated: percona-postgresql15 15.20-1.1.el9 -> 15.20-3.1.el9
  - updated: percona-postgresql15-libs 15.20-1.1.el9 -> 15.20-3.1.el9
  - updated: percona-postgresql16 16.16-1.1.el9 -> 16.16-3.1.el9
  - updated: percona-postgresql16-libs 16.16-1.1.el9 -> 16.16-3.1.el9
  - updated: percona-postgresql17 17.12.1-1.1.el9 -> 17.12.1-2.1.el9
  - updated: percona-postgresql17-libs 17.12.1-1.1.el9 -> 17.12.1-2.1.el9
  - updated: percona-postgresql18 18.7.1-1.1.el9 -> 18.7.1-2.1.el9
  - updated: percona-postgresql18-ecpg-libs 18.7.1-1.1.el9 -> 18.7.1-2.1.el9
  - updated: percona-postgresql18-libs 18.7.1-1.1.el9 -> 18.7.1-2.1.el9
  - updated: python3.12-alembic 1.19.1-2.4.el9 -> 1.19.1-2.6.el9
  - updated: python3.12-annotated-doc 0.0.5-2.4.el9 -> 0.0.5-2.6.el9
  - updated: python3.12-authlib 1.9.1-2.3.el9 -> 1.9.1-2.4.el9
  - updated: python3.12-babel 2.18.0-2.3.el9 -> 2.18.0-2.5.el9
  - updated: python3.12-backports-zstd 1.7.0-2.3.el9 -> 1.7.0-2.5.el9
  - updated: python3.12-bcrypt 5.0.0-2.3.el9 -> 5.0.0-2.5.el9
  - updated: python3.12-bidict 0.23.1-2.3.el9 -> 0.23.1-2.5.el9
  - updated: python3.12-blinker 1.9.0-2.3.el9 -> 1.9.0-2.5.el9
  - updated: python3.12-brotli 1.2.1-2.3.el9 -> 1.2.1-2.5.el9
  - updated: python3.12-certifi 2026.10.23-2.3.el9 -> 2026.10.23-2.5.el9
  - updated: python3.12-cffi 2.1.1-2.3.el9 -> 2.1.1-2.5.el9
  - updated: python3.12-click 8.1.7-3.2.el9 -> 8.1.7-3.4.el9
  - updated: python3.12-cryptography 50.0.1-2.3.el9 -> 50.0.1-2.5.el9
  - updated: python3.12-dateutil 2.9.0.post0-3.2.el9 -> 2.9.0.post0-3.4.el9
  - updated: python3.12-decorator 5.3.1-2.3.el9 -> 5.3.1-2.5.el9
  - updated: python3.12-dns 2.9.0-3.2.el9 -> 2.9.2-1.1.el9
  - updated: python3.12-email-validator 2.3.0-2.4.el9 -> 2.3.0-2.9.el9
  - updated: python3.12-flask 3.1.3-2.4.el9 -> 3.1.3-2.6.el9
  - updated: python3.12-flask-babel 4.0.0-2.3.el9 -> 4.0.0-2.5.el9
  - updated: python3.12-flask-compress 1.24-2.3.el9 -> 1.24-2.5.el9
  - updated: python3.12-flask-login 0.6.3-2.3.el9 -> 0.6.3-2.5.el9
  - updated: python3.12-flask-mail 0.10.0-2.3.el9 -> 0.10.0-2.5.el9
  - updated: python3.12-flask-migrate 4.1.0-2.2.el9 -> 4.1.0-2.4.el9
  - updated: python3.12-flask-paranoid 0.3.0-2.3.el9 -> 0.3.0-2.5.el9
  - updated: python3.12-flask-principal 0.4.0-2.3.el9 -> 0.4.0-2.5.el9
  - updated: python3.12-flask-security-too 5.8.1-2.2.el9 -> 5.8.1-2.5.el9
  - updated: python3.12-flask-socketio 5.6.1-2.3.el9 -> 5.6.1-2.5.el9
  - updated: python3.12-flask-sqlalchemy 3.1.1-2.2.el9 -> 3.1.1-2.4.el9
  - updated: python3.12-flask-wtf 1.3.0-2.3.el9 -> 1.3.0-2.5.el9
  - updated: python3.12-greenlet 3.5.5-2.3.el9 -> 3.5.5-2.5.el9
  - updated: python3.12-gssapi 1.11.1-2.3.el9 -> 1.11.1-2.5.el9
  - updated: python3.12-gunicorn 26.2.0-2.3.el9 -> 26.2.0-2.5.el9
  - updated: python3.12-h11 0.16.0-2.3.el9 -> 0.16.0-2.5.el9
  - updated: python3.12-itsdangerous 2.2.0-2.3.el9 -> 2.2.0-2.5.el9
  - updated: python3.12-jaraco-classes 3.4.0-2.4.el9 -> 3.4.0-2.6.el9
  - updated: python3.12-jaraco-context 6.1.0-2.3.el9 -> 6.1.0-2.5.el9
  - updated: python3.12-jaraco-functools 4.1.0-2.4.el9 -> 4.1.0-2.6.el9
  - updated: python3.12-jeepney 0.9.0-2.3.el9 -> 0.9.0-2.5.el9
  - updated: python3.12-jinja2 3.1.6-2.4.el9 -> 3.1.6-2.6.el9
  - updated: python3.12-joserfc 1.7.7-1.7.el9 -> 1.7.7-1.8.el9
  - updated: python3.12-jsonformatter 0.3.4-2.3.el9 -> 0.3.4-2.5.el9
  - updated: python3.12-keyring 25.2.1-2.2.el9 -> 25.2.1-2.3.el9
  - updated: python3.12-ldap3 2.9.1-2.3.el9 -> 2.9.1-2.5.el9
  - updated: python3.12-libgravatar 1.0.4-2.3.el9 -> 1.0.4-2.5.el9
  - updated: python3.12-libpass 1.9.3-2.3.el9 -> 1.9.3-2.5.el9
  - updated: python3.12-mako 1.4.1-2.4.el9 -> 1.4.1-2.6.el9
  - updated: python3.12-markdown-it-py 4.2.0-2.4.el9 -> 4.2.0-2.6.el9
  - updated: python3.12-markupsafe 3.0.3-2.3.el9 -> 3.0.3-2.5.el9
  - updated: python3.12-mdurl 0.1.2-2.3.el9 -> 0.1.2-2.5.el9
  - updated: python3.12-more-itertools 11.1.0-2.3.el9 -> 11.1.0-2.5.el9
  - updated: python3.12-paramiko 3.5.1-2.2.el9 -> 3.5.1-2.3.el9
  - updated: python3.12-pillow 13.0.0-2.3.el9 -> 13.0.0-2.5.el9
  - updated: python3.12-psutil 6.1.1-3.2.el9 -> 6.1.1-3.4.el9
  - updated: python3.12-psycopg 3.3.4-2.4.el9 -> 3.3.4-2.6.el9
  - updated: python3.12-psycopg-c 3.3.4-2.2.el9 -> 3.3.4-2.4.el9
  - updated: python3.12-pyasn1 0.6.5-2.3.el9 -> 0.6.5-2.5.el9
  - updated: python3.12-pygments 2.21.0-2.3.el9 -> 2.21.0-2.5.el9
  - updated: python3.12-pynacl 1.6.2-2.3.el9 -> 1.6.2-2.5.el9
  - updated: python3.12-pyotp 2.9.0-2.3.el9 -> 2.9.0-2.5.el9
  - updated: python3.12-python-engineio 4.13.5-2.2.el9 -> 4.13.5-2.4.el9
  - updated: python3.12-python-socketio 5.16.4-2.2.el9 -> 5.16.4-2.4.el9
  - updated: python3.12-pytz 2026.3.post1-2.3.el9 -> 2026.3.post1-2.5.el9
  - updated: python3.12-qrcode 8.2-2.3.el9 -> 8.2-2.5.el9
  - updated: python3.12-rich 15.0.0-2.2.el9 -> 15.0.0-2.4.el9
  - updated: python3.12-secretstorage 3.5.0-2.2.el9 -> 3.5.0-2.3.el9
  - updated: python3.12-setuptools 80.10.2-2.2.el9 -> 80.10.2-2.4.el9
  - updated: python3.12-shellingham 1.5.4-2.2.el9 -> 1.5.4-2.4.el9
  - updated: python3.12-simple-websocket 1.1.0-2.2.el9 -> 1.1.0-2.4.el9
  - updated: python3.12-six 1.17.0-3.2.el9 -> 1.17.0-3.4.el9
  - updated: python3.12-sqlalchemy 2.0.52-2.2.el9 -> 2.0.52-2.4.el9
  - updated: python3.12-sqlparse 0.6.0-2.3.el9 -> 0.6.0-2.5.el9
  - updated: python3.12-sshtunnel 0.4.0-2.2.el9 -> 0.4.0-2.3.el9
  - updated: python3.12-typer 0.26.8-2.2.el9 -> 0.26.8-2.4.el9
  - updated: python3.12-typing-extensions 4.16.0-2.3.el9 -> 4.16.0-2.5.el9
  - updated: python3.12-ua-parser 0.18.0-2.2.el9 -> 0.18.0-2.4.el9
  - updated: python3.12-user-agents 2.2.0-2.2.el9 -> 2.2.0-2.4.el9
  - updated: python3.12-werkzeug 3.1.8-2.3.el9 -> 3.1.8-2.5.el9
  - updated: python3.12-wsproto 1.3.2-2.2.el9 -> 1.3.2-2.4.el9
  - updated: python3.12-wtforms 3.2.2-2.2.el9 -> 3.2.2-2.4.el9
- percona-pgbackrest (ubi10) [container image]: update image common-tools-1 → common-tools-2
  - updated: curl 8.23.0-3.1.el10 -> 8.23.0-3.2.el10
  - updated: libcurl 8.23.0-3.1.el10 -> 8.23.0-3.2.el10
  - updated: percona-pgbackrest 2.60.0-4.2.el10 -> 2.60.1-1.2.el10
  - updated: percona-postgresql18-ecpg-libs 18.7.1-1.1.el10 -> 18.7.1-2.1.el10
  - updated: percona-postgresql18-libs 18.7.1-1.1.el10 -> 18.7.1-2.1.el10
- percona-pgbackrest (ubi8) [container image]: update image common-tools-1 → common-tools-2
  - updated: curl 8.23.0-3.2.el8 -> 8.23.0-3.3.el8
  - updated: libcurl 8.23.0-3.2.el8 -> 8.23.0-3.3.el8
  - updated: percona-pgbackrest 2.60.0-4.3.el8 -> 2.60.1-1.2.el8
  - updated: percona-postgresql18-ecpg-libs 18.7.1-1.1.el8 -> 18.7.1-2.1.el8
  - updated: percona-postgresql18-libs 18.7.1-1.1.el8 -> 18.7.1-2.1.el8
  - updated: perl-IO-Socket-SSL 2.066-1.8.el8 -> 2.066-1.9.el8
  - updated: perl-Mozilla-CA 20160104-1.9.el8 -> 20160104-1.10.el8
  - updated: perl-Net-SSLeay 1.88-1.23.el8 -> 1.88-1.24.el8
- percona-pgbackrest (ubi9) [container image]: update image common-tools-1 → common-tools-2
  - updated: curl 8.23.0-3.1.el9 -> 8.23.0-3.2.el9
  - updated: libcurl 8.23.0-3.1.el9 -> 8.23.0-3.2.el9
  - updated: percona-pgbackrest 2.60.0-4.3.el9 -> 2.60.1-1.2.el9
  - updated: percona-postgresql18-ecpg-libs 18.7.1-1.1.el9 -> 18.7.1-2.1.el9
  - updated: percona-postgresql18-libs 18.7.1-1.1.el9 -> 18.7.1-2.1.el9
- percona-pgbouncer (ubi10) [container image]: update image common-tools-1 → common-tools-2
  - updated: curl 8.23.0-3.1.el10 -> 8.23.0-3.2.el10
  - updated: libcurl 8.23.0-3.1.el10 -> 8.23.0-3.2.el10
  - updated: percona-pgbouncer 1.26.1-5.1.el10 -> 1.26.1-5.2.el10
  - updated: percona-postgresql18-ecpg-libs 18.7.1-1.1.el10 -> 18.7.1-2.1.el10
  - updated: percona-postgresql18-libs 18.7.1-1.1.el10 -> 18.7.1-2.1.el10
  - updated: python3.12-psycopg2 2.9.13-5.6.el10 -> 2.9.13-5.8.el10
- percona-pgbouncer (ubi8) [container image]: update image common-tools-1 → common-tools-2
  - updated: c-ares 1.19.1-2.3.el8 -> 1.19.1-2.4.el8
  - updated: curl 8.23.0-3.2.el8 -> 8.23.0-3.3.el8
  - updated: libcurl 8.23.0-3.2.el8 -> 8.23.0-3.3.el8
  - updated: percona-pgbouncer 1.26.1-5.2.el8 -> 1.26.1-5.3.el8
  - updated: percona-postgresql18-ecpg-libs 18.7.1-1.1.el8 -> 18.7.1-2.1.el8
  - updated: percona-postgresql18-libs 18.7.1-1.1.el8 -> 18.7.1-2.1.el8
  - updated: perl-IO-Socket-SSL 2.066-1.8.el8 -> 2.066-1.9.el8
  - updated: perl-Mozilla-CA 20160104-1.9.el8 -> 20160104-1.10.el8
  - updated: perl-Net-SSLeay 1.88-1.23.el8 -> 1.88-1.24.el8
  - updated: python3.12-psycopg2 2.9.13-5.6.el8 -> 2.9.13-5.8.el8
- percona-pgbouncer (ubi9) [container image]: update image common-tools-1 → common-tools-2
  - updated: c-ares 1.19.1-2.2.el9 -> 1.19.1-2.3.el9
  - updated: curl 8.23.0-3.1.el9 -> 8.23.0-3.2.el9
  - updated: libcurl 8.23.0-3.1.el9 -> 8.23.0-3.2.el9
  - updated: percona-pgbouncer 1.26.1-5.1.el9 -> 1.26.1-5.3.el9
  - updated: percona-postgresql18-ecpg-libs 18.7.1-1.1.el9 -> 18.7.1-2.1.el9
  - updated: percona-postgresql18-libs 18.7.1-1.1.el9 -> 18.7.1-2.1.el9
  - updated: python3.12-psycopg2 2.9.13-5.8.el9 -> 2.9.13-5.11.el9

### Security
- Not scanned: percona-pgbackrest (no scanner for unknown upstream)
- UBI base-image package CVEs are not covered by this scan.

## [common-tools-1] - 2026-11-12

### Added

### Changed
- percona-pgadmin4 (ubi9) [container image]: update image ? → common-tools-1
  - updated: percona-postgresql14 14.24-6.2.el9 -> 14.25-1.1.el9
  - updated: percona-postgresql14-libs 14.24-6.2.el9 -> 14.25-1.1.el9
  - updated: percona-postgresql15 15.19-5.2.el9 -> 15.20-1.1.el9
  - updated: percona-postgresql15-libs 15.19-5.2.el9 -> 15.20-1.1.el9
  - updated: percona-postgresql16 16.15-8.1.el9 -> 16.16-1.1.el9
  - updated: percona-postgresql16-libs 16.15-8.1.el9 -> 16.16-1.1.el9
  - updated: percona-postgresql17 17.11.1-8.3.el9 -> 17.12.1-1.1.el9
  - updated: percona-postgresql17-libs 17.11.1-8.3.el9 -> 17.12.1-1.1.el9
  - updated: percona-postgresql18 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
- percona-pgbackrest (ubi10) [container image]: update image ? → common-tools-1
  - updated: percona-pgbackrest 2.60.0-4.1.el10 -> 2.60.0-4.2.el10
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
  - updated: percona-postgresql18-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
- percona-pgbackrest (ubi8) [container image]: update image ? → common-tools-1
  - updated: curl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: libcurl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: percona-pgbackrest 2.60.0-4.1.el8 -> 2.60.0-4.3.el8
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: percona-postgresql18-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: perl-IO-Socket-SSL 2.066-1.6.el8 -> 2.066-1.8.el8
  - updated: perl-Mozilla-CA 20160104-1.7.el8 -> 20160104-1.9.el8
  - updated: perl-Net-SSLeay 1.88-1.20.el8 -> 1.88-1.23.el8
- percona-pgbackrest (ubi9) [container image]: update image ? → common-tools-1
  - updated: percona-pgbackrest 2.60.0-4.1.el9 -> 2.60.0-4.3.el9
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
- percona-pgbouncer (ubi10) [container image]: update image ? → common-tools-1
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
  - updated: percona-postgresql18-libs 18.6.1-8.1.el10 -> 18.7.1-1.1.el10
  - updated: python3.12-psycopg2 2.9.13-5.5.el10 -> 2.9.13-5.6.el10
- percona-pgbouncer (ubi8) [container image]: update image ? → common-tools-1
  - updated: c-ares 1.19.1-2.2.el8 -> 1.19.1-2.3.el8
  - updated: curl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: libcurl 8.23.0-3.1.el8 -> 8.23.0-3.2.el8
  - updated: percona-pgbouncer 1.26.1-5.1.el8 -> 1.26.1-5.2.el8
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: percona-postgresql18-libs 18.6.1-8.1.el8 -> 18.7.1-1.1.el8
  - updated: perl-IO-Socket-SSL 2.066-1.6.el8 -> 2.066-1.8.el8
  - updated: perl-Mozilla-CA 20160104-1.7.el8 -> 20160104-1.9.el8
  - updated: perl-Net-SSLeay 1.88-1.20.el8 -> 1.88-1.23.el8
  - updated: python3.12-psycopg2 2.9.13-5.4.el8 -> 2.9.13-5.6.el8
- percona-pgbouncer (ubi9) [container image]: update image ? → common-tools-1
  - updated: percona-postgresql18-ecpg-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: percona-postgresql18-libs 18.6.1-8.1.el9 -> 18.7.1-1.1.el9
  - updated: python3.12-psycopg2 2.9.13-5.6.el9 -> 2.9.13-5.8.el9

### Security
- UBI base-image package CVEs are not covered by this scan.

