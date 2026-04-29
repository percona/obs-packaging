#!UseOBSRepositories
#!BuildVersion: 17.9
#!BuildTag: percona-distribution-postgresql-with-postgis:<VERSION>-<RELEASE>
#!BuildTag: percona-distribution-postgresql-with-postgis:<VERSION>
#!BuildTag: percona-distribution-postgresql-with-postgis:17

FROM percona-ubi9-minimal:latest

LABEL name="Percona Distribution for PostgreSQL" \
      description="Essential / key PostgreSQL17 components with PostGIS. Percona Distribution for PostgreSQL features core components, tools and add-ons from the community, tested to work together in demanding enterprise environments." \
      vendor="Percona" \
      summary="Percona base selection of PostgreSQL17 components with PostGIS" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"
LABEL version="17.9"
LABEL release="1"

# openssl-fips-provider-so is not properly obsoleted by the newer openssl-fips-provider
# (el9_7+), causing a file conflict on /usr/lib64/ossl-modules/fips.so during dnf update.
# Force-remove it with rpm --nodeps so the subsequent dnf update can install the replacement.
RUN rpm -e --nodeps openssl-fips-provider-so
RUN dnf -y update
RUN dnf -y install \
           glibc-langpack-en \
           systemd-rpm-macros \
           file \
           mariadb-connector-c-config \
           crypto-policies-scripts

ARG PPG_REPO=testing

ENV PPG_VERSION 17.9
ENV PPG_MAJOR_VERSION 17
ENV PPG_MINOR_VERSION 9
ENV OS_VER el9
ENV FULL_PERCONA_VERSION "${PPG_VERSION}.${OS_VER}"
ENV PPG_REPO ${PPG_REPO}
ENV PPG_REPO_VERSION "${PPG_MAJOR_VERSION}.${PPG_MINOR_VERSION}"

RUN set -ex; \
    dnf -y update;

RUN dnf -y install \
        bind-utils \
        gettext \
        hostname \
        perl \
        tar \
        bzip2 \
        lz4 \
        procps-ng
RUN dnf -y install  \
        nss_wrapper \
        shadow-utils \
        libpq \
        libedit

RUN dnf -y reinstall tzdata; \
    dnf clean all

ENV PGDATA /data/db
ENV PGROOT="/usr/pgsql-${PPG_MAJOR_VERSION}"
ENV PATH="/pgdata:${PGROOT}/bin:${PATH}"

RUN set -ex; \
    dnf install -y \
        percona-postgresql${PPG_MAJOR_VERSION}-server \
        percona-postgresql${PPG_MAJOR_VERSION}-contrib \
        percona-postgresql-common \
        percona-pg_tde${PPG_MAJOR_VERSION} \
        percona-pg_stat_monitor${PPG_MAJOR_VERSION} \
        percona-pg_repack${PPG_MAJOR_VERSION} \
        percona-pgaudit${PPG_MAJOR_VERSION} \
        percona-pgaudit${PPG_MAJOR_VERSION}_set_user \
        percona-pgbackrest \
	percona-pgvector_${PPG_MAJOR_VERSION} \
	percona-postgresql${PPG_MAJOR_VERSION}-llvmjit \
	percona-pgvector_${PPG_MAJOR_VERSION}-llvmjit \
	python3-etcd \
        percona-postgis35_${PPG_MAJOR_VERSION} \
        percona-postgis35_${PPG_MAJOR_VERSION}-client \
        percona-postgis35_${PPG_MAJOR_VERSION}-gui \
        percona-postgis35_${PPG_MAJOR_VERSION}-llvmjit \
        percona-postgis35_${PPG_MAJOR_VERSION}-utils \
        percona-wal2json${PPG_MAJOR_VERSION}; \
    dnf clean all; \
    rm -rf /var/cache/dnf /var/cache/yum $PGDATA && mkdir -p $PGDATA /docker-entrypoint-initdb.d; \
    chown -R postgres:postgres $PGDATA docker-entrypoint-initdb.d


RUN set -ex; \
    dnf -y update; \
    dnf install -y python3-click percona-patroni; \
    dnf clean all

RUN set -ex; \
    sed -ri "s!^#?(listen_addresses)\s*=\s*\S+.*!\1 = '*'!" /usr/pgsql-${PPG_MAJOR_VERSION}/share/postgresql.conf.sample; \
    grep -F "listen_addresses = '*'" /usr/pgsql-${PPG_MAJOR_VERSION}/share/postgresql.conf.sample

COPY LICENSE /licenses/LICENSE.Dockerfile
RUN cp /usr/share/doc/percona-postgresql${PPG_MAJOR_VERSION}/COPYRIGHT /licenses/COPYRIGHT.PostgreSQL

RUN set -eux; \
    dnf install -y gosu; \
    dnf clean all

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/data/db"]

RUN rm -f /etc/pgbackrest.conf

# add volumes to allow override of pg_hba.conf and postgresql.conf
# add volumes to offer a restore feature
# add volumes to allow storage of postgres WAL segment files
# add volumes for pgbackrest to write to
# The VOLUME directive must appear after all RUN directives to ensure the proper
# volume permissions are applied when building the image
VOLUME ["/sshd", "/pgconf", "/pgdata", "/pgwal", "/backrestrepo"]

ENTRYPOINT ["/entrypoint.sh"]

EXPOSE 5432

USER 26

CMD ["postgres"]
