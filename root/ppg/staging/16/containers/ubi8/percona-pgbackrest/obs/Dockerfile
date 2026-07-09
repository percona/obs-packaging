#!UseOBSRepositories
#!BuildVersion: %!{PGBACKREST_VERSION}
#!BuildTag: percona-pgbackrest:<VERSION>-<RELEASE>
#!BuildTag: percona-pgbackrest:<VERSION>
#!BuildTag: percona-pgbackrest:latest

FROM percona-ubi8-minimal:latest

LABEL name="Percona pgBackRest" \
      description="pgBackRest is a simple, reliable backup and restore system for PostgreSQL that can seamlessly scale up to the largest databases and workloads." \
      vendor="Percona" \
      summary="Reliable PostgreSQL Backup & Restore" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"

LABEL version="%!{PGBACKREST_VERSION}"
LABEL release="1"

ARG PG_VERSION=%!{PG_VERSION}

ENV PG_VERSION=${PG_VERSION}

RUN set -ex; \
    microdnf -y update; \
    microdnf -y install \
        file \
        perl \
        tar \
        pkgconfig

RUN set -ex; \
    microdnf -y update; \
    microdnf -y install \
        percona-pgbackrest \
        procps-ng \
        gettext \
        nss_wrapper; \
    microdnf clean all; \
    rm -rf /var/cache/dnf /var/cache/yum

COPY LICENSE /licenses/LICENSE.Dockerfile
COPY pgbackrest.conf /etc/pgbackrest.conf

USER 26

CMD ["/usr/bin/pgbackrest", "version"]
