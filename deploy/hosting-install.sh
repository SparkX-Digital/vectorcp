#!/bin/bash
# Add isolated customer hosting to an existing VectorCP AlmaLinux 9 host.
set -euo pipefail
[[ ${EUID} == 0 && -d /opt/veyrapanel/veyra && -f /var/lib/veyrapanel/control.sqlite3 ]] || exit 1
[[ ${1:-} == --apply ]] || { echo 'Use --apply on the existing dedicated VectorCP host.'; exit 0; }
if ! command -v php-fpm >/dev/null || ! command -v mariadbd >/dev/null; then
  dnf -y module enable php:8.3 mariadb:10.11
  dnf -y install php-fpm php-cli php-mysqlnd php-gd php-mbstring php-xml php-opcache php-intl php-zip mariadb-server mariadb e2fsprogs acl policycoreutils-python-utils
fi
[[ $(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;') == 8.3 ]] || { echo 'PHP 8.3 is required. Review the existing PHP installation.' >&2; exit 1; }
# Only the customer templates may run PHP or MariaDB on this dedicated host.
systemctl mask --now php-fpm.service mariadb.service
install -d -m 700 /var/lib/veyrapanel/disks /var/lib/veyrapanel/hosting
install -d -m 755 /srv/veyrapanel/accounts /etc/veyrapanel/hosting /run/veyra-hosting
cat >/etc/systemd/system/veyra-customers.slice <<'UNIT'
[Unit]
Description=VectorCP customer workload budget
[Slice]
MemoryHigh=1800M
MemoryMax=2200M
CPUQuota=150%
TasksMax=512
UNIT
for n in $(seq 1 16); do
  slot=$(printf '%02d' "$n")
  account="veyra-c$slot"
  getent passwd "$account" >/dev/null || useradd --system --no-create-home --home-dir "/srv/veyrapanel/accounts/$slot" --shell /sbin/nologin "$account"
  usermod -aG "$account" nginx
  install -d -m 750 "/srv/veyrapanel/accounts/$slot"
  cat >"/etc/systemd/system/veyra-customers-c$slot.slice" <<UNIT
[Unit]
Description=VectorCP customer $slot resources
[Slice]
MemoryHigh=320M
MemoryMax=448M
CPUQuota=75%
TasksMax=48
UNIT
  cat >"/etc/systemd/system/veyra-task$slot.socket" <<UNIT
[Unit]
Description=Root-only VectorCP customer $slot tasks
[Socket]
ListenStream=/run/veyra-hosting-tasks/$slot.sock
SocketUser=root
SocketGroup=root
SocketMode=0600
DirectoryMode=0700
Accept=yes
Service=veyra-task$slot@.service
[Install]
WantedBy=sockets.target
UNIT
  cat >"/etc/systemd/system/veyra-task$slot@.service" <<UNIT
[Unit]
Description=Bounded VectorCP customer $slot task
Requires=srv-veyrapanel-accounts-$slot.mount
After=srv-veyrapanel-accounts-$slot.mount
[Service]
User=$account
Group=$account
Slice=veyra-customers-c$slot.slice
ExecStart=/usr/bin/python3 /opt/veyrapanel/veyra/hosting_task.py $slot
StandardInput=socket
StandardOutput=socket
StandardError=journal
NoNewPrivileges=true
CapabilityBoundingSet=
PrivateDevices=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectControlGroups=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectProc=invisible
RestrictSUIDSGID=true
TemporaryFileSystem=/srv:ro /var/lib/veyrapanel:ro /run/veyrapanel:ro /run/veyra-hosting:ro
BindPaths=/srv/veyrapanel/accounts/$slot
ReadWritePaths=/srv/veyrapanel/accounts/$slot
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=256M
TasksMax=32
RuntimeMaxSec=210
UMask=0027
UNIT
  # A mount is skipped at boot until the customer image has been provisioned.
  cat >"/etc/systemd/system/srv-veyrapanel-accounts-$slot.mount" <<UNIT
[Unit]
Description=VectorCP customer $slot bounded storage
ConditionPathExists=/var/lib/veyrapanel/disks/$slot.img
Before=veyra-php@$slot.service veyra-db@$slot.service nginx.service
Wants=veyra-php@$slot.service veyra-db@$slot.service
[Mount]
What=/var/lib/veyrapanel/disks/$slot.img
Where=/srv/veyrapanel/accounts/$slot
Type=ext4
Options=loop,nodev,nosuid,noexec
[Install]
WantedBy=multi-user.target
UNIT
  systemctl enable "srv-veyrapanel-accounts-$slot.mount"
done
# The fixed templates take only a two-digit slot allocated by the root agent.
cat >/etc/systemd/system/veyra-php@.service <<'UNIT'
[Unit]
Description=Isolated VectorCP PHP customer %i
ConditionPathExists=/etc/veyrapanel/hosting/%i.conf
Requires=srv-veyrapanel-accounts-%i.mount
After=srv-veyrapanel-accounts-%i.mount
[Service]
User=veyra-c%i
Group=veyra-c%i
Slice=veyra-customers-c%i.slice
ExecStart=/usr/sbin/php-fpm --nodaemonize --fpm-config /etc/veyrapanel/hosting/%i.conf
Restart=on-failure
RuntimeDirectory=veyra-hosting/%i
RuntimeDirectoryMode=0750
UMask=0027
NoNewPrivileges=true
CapabilityBoundingSet=
PrivateDevices=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectProc=invisible
ProcSubset=pid
RestrictSUIDSGID=true
LockPersonality=true
TemporaryFileSystem=/srv:ro /run/veyrapanel:ro /var/lib/veyrapanel:ro /run/veyra-hosting:ro
BindPaths=/srv/veyrapanel/accounts/%i /run/veyra-hosting/%i
ReadWritePaths=/srv/veyrapanel/accounts/%i /run/veyra-hosting/%i
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=256M
TasksMax=12
[Install]
WantedBy=multi-user.target
UNIT
cat >/etc/systemd/system/veyra-db@.service <<'UNIT'
[Unit]
Description=Isolated VectorCP MariaDB customer %i
ConditionPathExists=/srv/veyrapanel/accounts/%i/private/mysql/mysql
Requires=srv-veyrapanel-accounts-%i.mount
After=srv-veyrapanel-accounts-%i.mount
[Service]
User=veyra-c%i
Group=veyra-c%i
Slice=veyra-customers-c%i.slice
ExecStart=/usr/libexec/mariadbd --no-defaults --datadir=/srv/veyrapanel/accounts/%i/private/mysql --socket=/srv/veyrapanel/accounts/%i/private/run/mysql.sock --pid-file=/srv/veyrapanel/accounts/%i/private/run/mysql.pid --skip-networking --skip-log-bin --skip-name-resolve --innodb-buffer-pool-size=32M --innodb-log-file-size=16M --max-connections=8 --table-open-cache=64 --performance-schema=OFF --aria-pagecache-buffer-size=8M --key-buffer-size=4M --tmp-table-size=8M --max-heap-table-size=8M --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
Restart=on-failure
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=
PrivateDevices=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectProc=invisible
ProcSubset=pid
RestrictSUIDSGID=true
TemporaryFileSystem=/srv:ro /run/veyrapanel:ro /var/lib/veyrapanel:ro
BindPaths=/srv/veyrapanel/accounts/%i
ReadWritePaths=/srv/veyrapanel/accounts/%i
RestrictAddressFamilies=AF_UNIX
MemoryMax=192M
TasksMax=32
TimeoutStartSec=90
TimeoutStopSec=60
[Install]
WantedBy=multi-user.target
UNIT
# Labels persist across remount and relabel. The DB subtree has its own labels.
semanage fcontext -a -t httpd_sys_rw_content_t '/srv/veyrapanel/accounts(/.*)?' 2>/dev/null || semanage fcontext -m -t httpd_sys_rw_content_t '/srv/veyrapanel/accounts(/.*)?'
semanage fcontext -a -t mysqld_db_t '/srv/veyrapanel/accounts/[0-9]+/private/mysql(/.*)?' 2>/dev/null || semanage fcontext -m -t mysqld_db_t '/srv/veyrapanel/accounts/[0-9]+/private/mysql(/.*)?'
semanage fcontext -a -t mysqld_var_run_t '/srv/veyrapanel/accounts/[0-9]+/private/run(/.*)?' 2>/dev/null || true
semanage fcontext -a -t httpd_var_run_t '/run/veyra-hosting(/.*)?' 2>/dev/null || true
restorecon -R /srv/veyrapanel/accounts /run/veyra-hosting /etc/veyrapanel
# Only controlled hosting configuration and certificate paths are added.
install -d /etc/systemd/system/veyra-agent.service.d
cat >/etc/systemd/system/veyra-agent.service.d/hosting.conf <<'UNIT'
[Service]
ReadWritePaths=/etc/veyrapanel/hosting /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt /srv/veyrapanel/acme
MemoryMax=384M
TasksMax=48
UNIT
# Renewal covers the owner IP certificate and future customer certificates.
if [[ -f /etc/systemd/system/veyra-cert-renew.service ]]; then
  sed -i 's/ --cert-name veyra-panel-ip//' /etc/systemd/system/veyra-cert-renew.service
fi
systemctl daemon-reload
systemctl restart nginx
printf '1\n' >/var/lib/veyrapanel/hosting/enabled
chmod 600 /var/lib/veyrapanel/hosting/enabled
echo 'Isolated hosting services prepared. No customer workloads started.'
