#!/bin/bash

set -euo pipefail

test -f /.kconfig && . /.kconfig
test -f /.profile && . /.profile

echo "Configure UBI image: [$kiwi_iname]..."

rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release
rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-beta

microdnf clean all || true

rm -rf {/target,}/usr/share/doc
rm -rf {/target,}/usr/share/man
rm -rf {/target,}/usr/share/info
rm -rf {/target,}/usr/share/locale/*

rm -rf {/target,}/var/log/{alternatives.log,lastlog,tallylog};
rm -rf {/target,}/run/*;
rm -f {/target,}/etc/{shadow-,group-,passwd-,.pwd.lock};
rm -f {/target,}/usr/lib/sysimage/rpm/.rpm.lock;
rm -f {/target,}/var/cache/ldconfig/aux-cache

rm -rf {/target,}/usr/share/zoneinfo
rm -rf {/target,}/usr/share/gnupg
rm -rf {/target,}/usr/share/icons
rm -f {/target,}/var/lib/rpm/__db.*
rm -f {/target,}/var/log/dnf*.log {/target,}/var/log/hawkey.log
