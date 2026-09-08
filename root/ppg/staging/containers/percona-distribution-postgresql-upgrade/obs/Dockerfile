#!UseOBSRepositories
#!BuildVersion: %!{PG_VERSION}-%!{PPG_RELEASE}
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_VERSION}-%!{PPG_RELEASE}-<RELEASE>
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_VERSION}-%!{PPG_RELEASE}
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_VERSION}
#!BuildTag: percona-distribution-postgresql-upgrade:%!{PG_MAJOR_VERSION}

FROM percona-ubi-minimal:latest

LABEL name="Percona Distribution for PostgreSQL Upgrade" \
      description="Upgrade container for Percona Distribution for PostgreSQL. Facilitates major version upgrades from PostgreSQL 14, 15, 16, or 17 to %!{PG_MAJOR_VERSION} using pg_upgrade." \
      vendor="Percona" \
      summary="Percona Distribution for PostgreSQL major version upgrade container" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"
LABEL version="%!{PG_VERSION}-%!{PPG_RELEASE}"
LABEL release="%!{PPG_RELEASE}"

ARG PPG_REPO
ARG RHEL_VER

RUN microdnf -y update
RUN microdnf -y install \
    glibc-langpack-en systemd-rpm-macros file \
    mariadb-connector-c-config crypto-policies-scripts pkgconfig

ENV PPG_VERSION %!{PG_VERSION}-%!{PPG_RELEASE}
ENV PPG_MAJOR_VERSION %!{PG_MAJOR_VERSION}
ENV OS_VER ${RHEL_VER}

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

# Install every older PG major version this image can upgrade from, with the extensions
# that exist for that version, so a single image can upgrade from any of them to
# ${PPG_MAJOR_VERSION}. This block is expanded by percona-obs's sync tooling
# (expand_for_blocks) into one literal, fully-expanded RUN per version before the file
# ever reaches OBS — OBS's Dockerfile scanner statically resolves package names and
# cannot expand a real shell loop variable, so what OBS sees is never this block itself.
{{FOR pg_version IN 17,16,15,14}}
RUN set -ex; \
    microdnf install -y \
        percona-postgresql${pg_version}-server \
        percona-postgresql${pg_version}-contrib \
        percona-postgresql${pg_version}-llvmjit \
        percona-pg_stat_monitor${pg_version} \
        percona-pg_repack${pg_version} \
        percona-pgaudit${pg_version} \
        percona-pgaudit${pg_version}_set_user \
        percona-pgvector_${pg_version} \
        percona-pgvector_${pg_version}-llvmjit \
        percona-wal2json${pg_version} \
        percona-postgis35_${pg_version} \
        percona-postgis35_${pg_version}-llvmjit \
        percona-pg_cron_${pg_version}; \
    microdnf clean all
{{ENDFOR}}

# pg_tde is only packaged standalone from PG17 onward, so it's installed separately
# here rather than inside the loop above.
RUN set -ex; \
    microdnf install -y percona-pg_tde17; \
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
