#!UseOBSRepositories
#!BuildVersion: %!{PGADMIN_VERSION}
#!BuildTag: percona-pgadmin4:<VERSION>-<RELEASE>
#!BuildTag: percona-pgadmin4:<VERSION>
#!BuildTag: percona-pgadmin4:latest

FROM percona-ubi-minimal:latest

LABEL name="Percona pgAdmin 4" \
      description="pgAdmin 4 is the leading open source management tool for PostgreSQL. This image runs it in server mode under gunicorn, built from the Percona Distribution for PostgreSQL packages. Compared to the upstream dpage/pgadmin4 image: listens on 8080 as UID 5050, no bundled MTA, no PUID/PGID remapping." \
      vendor="Percona" \
      summary="pgAdmin 4 management tool for PostgreSQL" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"

LABEL version="%!{PGADMIN_VERSION}"
LABEL release="1"

RUN microdnf -y update && \
    microdnf -y install \
        percona-pgadmin4 \
        percona-pgadmin4-gunicorn \
        percona-postgresql14 \
        percona-postgresql15 \
        percona-postgresql16 \
        percona-postgresql17 \
        percona-postgresql18 && \
    microdnf clean all && rm -rf /var/cache/dnf /var/cache/yum

# Pin the sysusers-allocated pgadmin user to upstream's UID 5050, join group 0
# and make the writable trees group-0 writable so an OpenShift-assigned random
# UID (gid 0) can run; group-writable /etc/passwd enables the entrypoint's
# random-UID passwd fixup.
RUN usermod -u 5050 -aG 0 pgadmin && \
    mkdir -p /run/pgadmin && \
    chown -R 5050:0 /var/lib/pgadmin /var/log/pgadmin /run/pgadmin && \
    chmod -R g=u /var/lib/pgadmin /var/log/pgadmin /run/pgadmin && \
    chmod g=u /etc/passwd

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY LICENSE /licenses/LICENSE.Dockerfile

RUN chmod 0755 /usr/local/bin/entrypoint.sh

# Overridable defaults: docker/podman -e wins over ENV, and the RPM's
# config_distro.py applies PGADMIN_CONFIG_* at every import (better than
# upstream's bake-once). pg-13 stays unset: no PG 13 in the Percona tree.
# The RPM's config_distro.py carries this same map as its default (including a
# pg-13 entry we don't ship); this ENV is authoritative in the image, so if the
# path ever changes, change both.
ENV PGADMIN_CONFIG_DEFAULT_BINARY_PATHS="{'pg': '/usr/pgsql-18/bin', 'pg-14': '/usr/pgsql-14/bin', 'pg-15': '/usr/pgsql-15/bin', 'pg-16': '/usr/pgsql-16/bin', 'pg-17': '/usr/pgsql-17/bin', 'pg-18': '/usr/pgsql-18/bin'}" \
    PGADMIN_LISTEN_ADDRESS=0.0.0.0 \
    PGADMIN_LISTEN_PORT=8080 \
    HOME=/var/lib/pgadmin

EXPOSE 8080
VOLUME /var/lib/pgadmin

USER 5050

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
