#!UseOBSRepositories
#!BuildVersion: %!{PG_VERSION}-%!{PPG_RELEASE}
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_VERSION}-17-%!{PPG_RELEASE}-<RELEASE>
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_VERSION}-17-%!{PPG_RELEASE}
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_VERSION}-17
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_MAJOR_VERSION}-17

FROM percona-ubi9-minimal:latest

LABEL name="Percona Distribution for PostgreSQL Upgrade" \
      description="Upgrade container for Percona Distribution for PostgreSQL. Facilitates major version upgrades from PostgreSQL 17 to %!{PG_MAJOR_VERSION} using pg_upgrade." \
      vendor="Percona" \
      summary="Percona Distribution for PostgreSQL major version upgrade container" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"
LABEL version="<VERSION>"
LABEL release="<RELEASE>"

# openssl-fips-provider-so is not properly obsoleted by the newer openssl-fips-provider
# (el9_7+), causing a file conflict on /usr/lib64/ossl-modules/fips.so during dnf update.
# Force-remove it with rpm --nodeps so the subsequent dnf update can install the replacement.
RUN rpm -e --nodeps openssl-fips-provider-so
RUN microdnf -y update
RUN microdnf -y install \
    glibc-langpack-en systemd-rpm-macros file \
    mariadb-connector-c-config crypto-policies-scripts pkgconfig

ENV PPG_VERSION <VERSION>
ENV PPG_MAJOR_VERSION %!{PG_MAJOR_VERSION}
ENV OS_VER el9

RUN microdnf -y install \
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

RUN microdnf -y reinstall tzdata; \
    microdnf clean all

# pg_upgrade ships in percona-postgresqlN-server at /usr/pgsql-N/bin/pg_upgrade

# Install PG${PPG_MAJOR_VERSION} (target version) with all extensions including PostGIS
RUN set -ex; \
    microdnf install -y \
        percona-postgresql${PPG_MAJOR_VERSION}-server \
        percona-postgresql${PPG_MAJOR_VERSION}-contrib \
        percona-postgresql-common \
        percona-pg_tde${PPG_MAJOR_VERSION} \
        percona-pg_stat_monitor${PPG_MAJOR_VERSION} \
        percona-pg_repack${PPG_MAJOR_VERSION} \
        percona-pgaudit${PPG_MAJOR_VERSION} \
        percona-pgaudit${PPG_MAJOR_VERSION}_set_user \
        percona-pg_oidc_validator${PPG_MAJOR_VERSION} \
        percona-pgvector_${PPG_MAJOR_VERSION} \
        percona-postgresql${PPG_MAJOR_VERSION}-llvmjit \
        percona-pgvector_${PPG_MAJOR_VERSION}-llvmjit \
        percona-wal2json${PPG_MAJOR_VERSION} \
        percona-postgis35_${PPG_MAJOR_VERSION} \
        percona-postgis35_${PPG_MAJOR_VERSION}-client \
        percona-postgis35_${PPG_MAJOR_VERSION}-gui \
        percona-postgis35_${PPG_MAJOR_VERSION}-llvmjit \
        percona-postgis35_${PPG_MAJOR_VERSION}-utils \
        percona-pg_cron_${PPG_MAJOR_VERSION}; \
    microdnf clean all

# Install PG17 (source version for upgrade) with all extensions including PostGIS
RUN set -ex; \
    microdnf install -y \
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
    microdnf clean all; \
    rm -rf /var/cache/dnf /var/cache/yum

COPY LICENSE /licenses/LICENSE.Dockerfile
RUN cp /usr/share/doc/percona-postgresql${PPG_MAJOR_VERSION}/COPYRIGHT /licenses/COPYRIGHT.PostgreSQL

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
