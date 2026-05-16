#!UseOBSRepositories
#!BuildVersion: %!{PGBOUNCER_VERSION}
#!BuildTag: percona-pgbouncer:<VERSION>-<RELEASE>
#!BuildTag: percona-pgbouncer:<VERSION>

FROM percona-ubi9-minimal:latest

LABEL name="Percona PgBouncer" \
      description="PgBouncer is a lightweight connection pooler for PostgreSQL that offers various pooling modes (session, transaction, statement), low memory usage, support for multiple backend hosts, and the ability to reconfigure or restart it online without downtime." \
      vendor="Percona" \
      summary="Lightweight connection pooler for PostgreSQL" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"

LABEL version="<VERSION>"
LABEL release="<RELEASE>"

ARG PG_VERSION=%!{PG_VERSION}

ENV PG_VERSION=${PG_VERSION}

RUN groupadd -g 1001 pgbouncer; \
    useradd -u 1001 -r -g 1001 -s /sbin/nologin \
        -c "Default Application User" pgbouncer

RUN set -ex; \
    dnf -y update; \
    dnf -y install \
        file \
        perl \
        pkgconfig \
        c-ares

RUN set -ex; \
    dnf -y update; \
    dnf -y install \
        procps-ng \
        percona-pgbouncer; \
    dnf clean all; \
    rm -rf /var/cache/dnf /var/cache/yum

COPY LICENSE /licenses/LICENSE.Dockerfile

RUN touch /etc/pgbouncer/userlist.txt && \
    chown -R 1001 /var/log/pgbouncer /var/run/pgbouncer /etc/pgbouncer

COPY --chown=1001 ["entrypoint.sh", "/"]
USER 1001

ENTRYPOINT ["/entrypoint.sh"]

CMD ["/usr/bin/pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
