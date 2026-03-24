#!/bin/bash

set -euo pipefail

test -f /.kconfig && . /.kconfig
test -f /.profile && . /.profile

echo "Configure UBI image: [$kiwi_iname]..."

microdnf clean all || true

rm -rf {/target,}/usr/share/doc
rm -rf {/target,}/usr/share/man
rm -rf {/target,}/usr/share/info
rm -rf {/target,}/usr/share/locale/*

rm -rf {/target,}/var/log/{alternatives.log,lastlog,tallylog,zypper.log,zypp/history,YaST2}; \
    rm -rf {/target,}/run/*; \
    rm -f {/target,}/etc/{shadow-,group-,passwd-,.pwd.lock}; \
    rm -f {/target,}/usr/lib/sysimage/rpm/.rpm.lock; \
    rm -f {/target,}/var/lib/zypp/AnonymousUniqueId; \
    rm -f {/target,}/var/lib/zypp/AutoInstalled; \
    rm -f {/target,}/var/cache/ldconfig/aux-cache
