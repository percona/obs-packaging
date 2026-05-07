#!UseOBSRepositories
#!BuildVersion: 18.3
#!BuildTag: percona-distribution-postgresql-upgrade:<VERSION>-17.9-<RELEASE>
#!BuildTag: percona-distribution-postgresql-upgrade:<VERSION>-17.9
#!BuildTag: percona-distribution-postgresql-upgrade:18-17

FROM percona-ubi9-minimal:latest

LABEL name="Percona Distribution for PostgreSQL Upgrade" \
      description="Upgrade container for Percona Distribution for PostgreSQL. Facilitates major version upgrades from PostgreSQL 17 to 18 using pg_upgrade." \
      vendor="Percona" \
      summary="Percona Distribution for PostgreSQL major version upgrade container" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"
LABEL version="18.3"
LABEL release="1"

# openssl-fips-provider-so is not properly obsoleted by the newer openssl-fips-provider
# (el9_7+), causing a file conflict on /usr/lib64/ossl-modules/fips.so during dnf update.
# Force-remove it with rpm --nodeps so the subsequent dnf update can install the replacement.
RUN rpm -e --nodeps openssl-fips-provider-so
RUN dnf -y update
RUN dnf -y install \
    glibc-langpack-en systemd-rpm-macros file \
    mariadb-connector-c-config crypto-policies-scripts pkgconfig

ENV PPG_VERSION 18.3
ENV PPG_MAJOR_VERSION 18
ENV OS_VER el9

RUN dnf -y install \
        bind-utils \
        gettext \
        hostname \
        perl \
        tar \
        bzip2 \
        lz4 \
        procps-ng \
        nss_wrapper \
        shadow-utils \
        libedit

RUN dnf -y reinstall tzdata; \
    dnf clean all

# pg_upgrade ships in percona-postgresqlN-server at /usr/pgsql-N/bin/pg_upgrade

# Install PG18 (target version) with all extensions including PostGIS
RUN set -ex; \
    dnf install -y \
        percona-postgresql18-server \
        percona-postgresql18-contrib \
        percona-postgresql-common \
        percona-pg_tde18 \
        percona-pg_stat_monitor18 \
        percona-pg_repack18 \
        percona-pgaudit18 \
        percona-pgaudit18_set_user \
        percona-pg_oidc_validator18 \
        percona-pgvector_18 \
        percona-postgresql18-llvmjit \
        percona-pgvector_18-llvmjit \
        percona-wal2json18 \
        percona-postgis35_18 \
        percona-postgis35_18-client \
        percona-postgis35_18-gui \
        percona-postgis35_18-llvmjit \
        percona-postgis35_18-utils \
        percona-pg_cron_18; \
    dnf clean all

# Install PG17 (source version for upgrade) with all extensions including PostGIS
RUN set -ex; \
    dnf install -y \
        percona-postgresql17-server \
        percona-postgresql17-contrib \
        percona-pg_tde17 \
        percona-pg_stat_monitor17 \
        percona-pg_repack17 \
        percona-pgaudit17 \
        percona-pgaudit17_set_user \
        percona-pgvector_17 \
        percona-postgresql17-llvmjit \
        percona-pgvector_17-llvmjit \
        percona-wal2json17 \
        percona-postgis35_17 \
        percona-postgis35_17-client \
        percona-postgis35_17-gui \
        percona-postgis35_17-llvmjit \
        percona-postgis35_17-utils \
        percona-pg_cron_17; \
    dnf clean all; \
    rm -rf /var/cache/dnf /var/cache/yum

COPY LICENSE /licenses/LICENSE.Dockerfile
RUN cp /usr/share/doc/percona-postgresql18/COPYRIGHT /licenses/COPYRIGHT.PostgreSQL

RUN mkdir -p /opt/crunchy/bin /pgolddata /pgnewdata /opt/crunchy/conf
COPY upgrade-scripts.tar.gz /tmp/upgrade-scripts.tar.gz
RUN mkdir -p /tmp/upgrade-scripts && \
    tar -xzf /tmp/upgrade-scripts.tar.gz -C /tmp/upgrade-scripts && \
    cp /tmp/upgrade-scripts/bin/upgrade/start.sh /tmp/upgrade-scripts/bin/common/*.sh /opt/crunchy/bin/ && \
    cp /tmp/upgrade-scripts/conf/upgrade/passwd.template /tmp/upgrade-scripts/conf/upgrade/group.template /opt/crunchy/conf/ && \
    cp /tmp/upgrade-scripts/bin/relocate-extensions.sh /usr/local/bin/relocate-extensions.sh && \
    rm -rf /tmp/upgrade-scripts /tmp/upgrade-scripts.tar.gz && \
    chown -R postgres:postgres /opt/crunchy /pgolddata /pgnewdata && \
    chmod -R g=u /opt/crunchy /pgolddata /pgnewdata && \
    chmod +x /opt/crunchy/bin/*.sh /usr/local/bin/relocate-extensions.sh

VOLUME /pgolddata /pgnewdata

ENV NSS_WRAPPER_SUBDIR="upgrade"

ENTRYPOINT ["/opt/crunchy/bin/uid_postgres.sh"]

USER 26

CMD ["/opt/crunchy/bin/start.sh"]
