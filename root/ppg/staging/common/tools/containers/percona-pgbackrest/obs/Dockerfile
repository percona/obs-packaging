#!UseOBSRepositories
#!BuildVersion: %!{PGBACKREST_VERSION}
#!BuildTag: percona-pgbackrest:<VERSION>-<RELEASE>
#!BuildTag: percona-pgbackrest:<VERSION>
#!BuildTag: percona-pgbackrest:latest

ARG UBI_BASE=registry.access.redhat.com/ubi9/ubi-minimal:latest
FROM $UBI_BASE

ARG RHEL_VER

LABEL name="Percona pgBackRest" \
      description="pgBackRest is a simple, reliable backup and restore system for PostgreSQL that can seamlessly scale up to the largest databases and workloads." \
      vendor="Percona" \
      summary="Reliable PostgreSQL Backup & Restore" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"

LABEL version="%!{PGBACKREST_VERSION}"
LABEL release="1"

RUN microdnf -y update
# ubi-minimal ships glibc-minimal-langpack (strict `glibc = ver`). OBS only
# uploads what this list expands to, and on UBI 10 glibc-langpack-en already
# satisfies glibc's langpack requirement, so without naming it here the minimal
# langpack never reaches the build and glibc cannot upgrade once the UBI
# repository moves ahead of the registry base image.
RUN microdnf -y install \
        glibc-minimal-langpack \
        file \
        perl \
        tar \
        pkgconfig \
        percona-pgbackrest \
        procps-ng \
        gettext \
        nss_wrapper

# The perl metapackage drags in perl-Archive-Tar and perl-IO-Compress, which
# nothing in the image uses and which carry open CVEs on EL8. Drop them the
# way the retired kiwi base image did; UBI 9/10 ship fixed versions.
RUN if [ "$RHEL_VER" = "el8" ]; then rpm -e --nodeps perl-Archive-Tar perl-IO-Compress; fi
RUN microdnf clean all && rm -rf /var/cache/dnf /var/cache/yum

COPY LICENSE /licenses/LICENSE.Dockerfile
COPY pgbackrest.conf /etc/pgbackrest.conf

USER 26

CMD ["/usr/bin/pgbackrest", "version"]
