#!UseOBSRepositories
#!BuildVersion: %!{PGBACKREST_VERSION}
#!BuildTag: percona-pgbackrest:<VERSION>-<RELEASE>
#!BuildTag: percona-pgbackrest:<VERSION>

FROM percona-ubi9-minimal:latest

LABEL name="Percona pgBackRest" \
      description="pgBackRest is a simple, reliable backup and restore system for PostgreSQL that can seamlessly scale up to the largest databases and workloads." \
      vendor="Percona" \
      summary="Reliable PostgreSQL Backup & Restore" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"

LABEL version="<VERSION>"
LABEL release="<RELEASE>"

ARG PG_VERSION=%!{PG_VERSION}

ENV PG_VERSION=${PG_VERSION}

RUN set -ex; \
    dnf -y update; \
    dnf -y install \
        file \
        perl \
        pkgconfig

RUN set -ex; \
    dnf -y update; \
    dnf -y install \
        percona-pgbackrest \
        procps-ng \
        gettext \
        nss_wrapper; \
    dnf clean all; \
    rm -rf /var/cache/dnf /var/cache/yum

COPY LICENSE /licenses/LICENSE.Dockerfile
COPY pgbackrest.conf /etc/pgbackrest.conf

USER 26

CMD ["/usr/bin/pgbackrest", "version"]
