#!UseOBSRepositories
#!BuildVersion: %!{PGBOUNCER_VERSION}
#!BuildTag: percona-pgbouncer:<VERSION>-<RELEASE>
#!BuildTag: percona-pgbouncer:<VERSION>
#!BuildTag: percona-pgbouncer:latest

FROM percona-ubi-minimal:latest

LABEL name="Percona PgBouncer" \
      description="PgBouncer is a lightweight connection pooler for PostgreSQL that offers various pooling modes (session, transaction, statement), low memory usage, support for multiple backend hosts, and the ability to reconfigure or restart it online without downtime." \
      vendor="Percona" \
      summary="Lightweight connection pooler for PostgreSQL" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"

LABEL version="%!{PGBOUNCER_VERSION}"
LABEL release="1"

ARG PG_VERSION=%!{PG_VERSION}

ENV PG_VERSION=${PG_VERSION}

RUN microdnf -y update

RUN microdnf -y install \
        file \
        perl \
        tar \
        pkgconfig \
        c-ares \
        procps-ng \
        shadow-utils

RUN groupadd -g 1001 pgbouncer
RUN useradd -u 1001 -r -g 1001 -s /sbin/nologin -c "Default Application User" pgbouncer

RUN microdnf -y install percona-pgbouncer

RUN microdnf clean all && rm -rf /var/cache/dnf /var/cache/yum

COPY LICENSE /licenses/LICENSE.Dockerfile

RUN touch /etc/pgbouncer/userlist.txt
RUN chown -R 1001 /var/log/pgbouncer /var/run/pgbouncer /etc/pgbouncer

COPY --chown=1001 ["entrypoint.sh", "/"]
USER 1001

ENTRYPOINT ["/entrypoint.sh"]

CMD ["/usr/bin/pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
