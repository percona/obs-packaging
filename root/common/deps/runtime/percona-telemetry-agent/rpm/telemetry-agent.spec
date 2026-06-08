%global debug_package %{nil}
%define _log_dir /var/log/percona/telemetry-agent

Name:  percona-telemetry-agent
Version: 1.0.0
Release: 1%{?dist}
Summary: Percona Telemetry Agent
Group:  Applications/Databases
License: GPLv3
URL:  https://github.com/percona/telemetry-agent
Source: percona-telemetry-agent-%{version}.tar.gz
Source1: vendor.tar.gz

%if 0%{?suse_version} >= 1600
BuildRequires:  go >= 1.26
%endif

%if 0%{?rhel} >= 8
BuildRequires: golang >= 1.26.4
%endif

BuildRequires: make git
BuildRequires:  systemd
BuildRequires:  pkgconfig(systemd)
%if 0%{?suse_version}
BuildRequires:  fillup
Requires(post): fillup
Requires(pre):  shadow
%endif
Requires:  logrotate
Requires(post):   systemd
Requires(preun):  systemd
Requires(postun): systemd
%if 0%{?rhel} <= 7
Requires:  yum-utils
%endif

%description
Percona Telemetry Agent gathers information and metrics from Percona products installed on the host.

%prep
%autosetup -D -a 1

%build
GITCOMMIT=$(grep '^commit:' %{_sourcedir}/*%{name}.obsinfo | awk '{print $2}')
REVISION=$(echo $GITCOMMIT | cut -c1-7)

cat > VERSION <<EOF
VERSION=%{version}
REVISION=${REVISION}
GITCOMMIT=${GITCOMMIT}
GITBRANCH=v%{version}
COMPONENT_VERSION=%{version}
TELEMETRY_AGENT_RELEASE_FULLCOMMIT=${GITCOMMIT}
EOF

source ./VERSION
export VERSION
export GITBRANCH
export GITCOMMIT

%ifarch aarch64
export GOARCH=arm64
%else
export GOARCH=amd64
%endif

make build GOARCH=${GOARCH} COMPONENT_VERSION=${COMPONENT_VERSION} TELEMETRY_AGENT_RELEASE_FULLCOMMIT=${TELEMETRY_AGENT_RELEASE_FULLCOMMIT} VENDOR_BUILD_FLAGS="-mod=vendor"
cd %{_builddir}

%install
install -D -m 0660 /dev/null %{buildroot}/%{_log_dir}/telemetry-agent.log
install -D -m 0660 /dev/null  %{buildroot}/%{_log_dir}/telemetry-agent-error.log
install -Dm 755 bin/telemetry-agent %{buildroot}/%{_bindir}/percona-telemetry-agent
install -D -m 0644 packaging/conf/percona-telemetry-agent.logrotate %{buildroot}/%{_sysconfdir}/logrotate.d/percona-telemetry-agent
%if 0%{?suse_version}
install -D -m 0640 packaging/conf/percona-telemetry-agent.env %{buildroot}/%{_fillupdir}/sysconfig.percona-telemetry-agent
%else
install -m 0755 -d %{buildroot}/%{_sysconfdir}/sysconfig
install -D -m 0640 packaging/conf/percona-telemetry-agent.env %{buildroot}/%{_sysconfdir}/sysconfig/percona-telemetry-agent
%endif
install -m 0755 -d %{buildroot}/%{_unitdir}
install -m 0644 packaging/conf/percona-telemetry-agent.service %{buildroot}/%{_unitdir}/percona-telemetry-agent.service

%pre -n percona-telemetry-agent
if [ ! -d /run/percona-telemetry-agent ]; then
    install -m 0755 -d -oroot -groot /run/percona-telemetry-agent
fi
# Create new linux group
# For telemetry-agent to be able to read/remove the metric files
/usr/bin/getent group percona-telemetry || groupadd percona-telemetry >/dev/null 2>&1 || :
usermod -a -G percona-telemetry daemon >/dev/null 2>&1 || :

%post -n percona-telemetry-agent
%if 0%{?suse_version}
%fillup_only -n percona-telemetry-agent
%endif
chown -R daemon:percona-telemetry %{_log_dir} >/dev/null 2>&1 || :
chmod g+w %{_log_dir}
# Move the old logfiles, if present during update
if ls /var/log/percona/telemetry-agent*log* >/dev/null 2>&1; then
    chmod 0775  %{_log_dir}
    mv /var/log/percona/telemetry-agent*log* /var/log/percona/telemetry-agent/ >/dev/null 2>&1 || :
    chmod 0660  %{_log_dir}/telemetry-agent*log*
fi
# Create telemetry history directory
mkdir -p /usr/local/percona/telemetry/history
chown daemon:percona-telemetry /usr/local/percona/telemetry/history || :
chmod g+s /usr/local/percona/telemetry/history
chmod u+s /usr/local/percona/telemetry/history
chown daemon:percona-telemetry /usr/local/percona/telemetry || :
# Fix permissions to be able to create Percona telemetry uuid file
chgrp percona-telemetry /usr/local/percona
chmod 775 /usr/local/percona
%systemd_post percona-telemetry-agent.service
if [ $1 == 1 ]; then
      /usr/bin/systemctl enable percona-telemetry-agent >/dev/null 2>&1 || :
fi

%preun -n percona-telemetry-agent
%systemd_preun percona-telemetry-agent.service

%postun -n percona-telemetry-agent
if [ $1 == 0 ]; then
    %systemd_postun_with_restart percona-telemetry-agent.service
    systemctl daemon-reload
    groupdel percona-telemetry >/dev/null 2>&1 || :
fi

%posttrans -n percona-telemetry-agent
# Package update - add the group that was deleted, reload and restart the service
if [ $1 -ge 1 ]; then
    /usr/bin/getent group percona-telemetry || groupadd percona-telemetry >/dev/null 2>&1 || :
    usermod -a -G percona-telemetry daemon >/dev/null 2>&1 || :
    systemctl daemon-reload >/dev/null 2>&1 || true
    if systemctl is-enabled percona-telemetry-agent.service > /dev/null 2>&1; then
        #/usr/bin/systemctl enable percona-telemetry-agent.service >/dev/null 2>&1 || :
        /usr/bin/systemctl restart percona-telemetry-agent.service >/dev/null 2>&1 || :
    fi
fi

%files -n percona-telemetry-agent
%{_bindir}/percona-telemetry-agent
%if 0%{?suse_version}
%{_fillupdir}/sysconfig.percona-telemetry-agent
%else
%config(noreplace) %attr(0640,root,root) %{_sysconfdir}/sysconfig/percona-telemetry-agent
%endif
%config(noreplace) %attr(0644,root,root) /%{_sysconfdir}/logrotate.d/percona-telemetry-agent
%{_unitdir}/percona-telemetry-agent.service
%dir /var/log/percona
%dir %{_log_dir}
%{_log_dir}/telemetry-agent.log
%{_log_dir}/telemetry-agent-error.log

%changelog
* Wed Apr 03 2024 Surabhi Bhat <surabhi.bhat@percona.com>
- First build
