#!/bin/bash
# Add isolated customer hosting to an existing VectorCP AlmaLinux 9 host.
set -euo pipefail
[[ ${EUID} == 0 && -d /opt/vectorcp/vectorcp && -f /var/lib/vectorcp/control.sqlite3 ]] || exit 1
[[ ${1:-} == --apply ]] || { echo 'Use --apply on the existing dedicated VectorCP host.'; exit 0; }
# Block new jobs before checking existing ones. The marker is transient and the
# lock prevents two native service installers from changing units concurrently.
exec 9>/run/vectorcp-profile-maintenance.lock
flock -n 9 || { echo 'Another service-profile change is running.' >&2; exit 1; }
[[ ! -e /run/vectorcp-profile-maintenance ]] || { echo 'Inspect the previous interrupted profile change before retrying.' >&2; exit 1; }
install -m 0600 /dev/null /run/vectorcp-profile-maintenance
trap 'rm -f /run/vectorcp-profile-maintenance' EXIT
python3 - <<'PY'
import sqlite3
with sqlite3.connect('/var/lib/vectorcp/control.sqlite3') as db:
    if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
        raise SystemExit('A hosting job is running. Retry after it finishes.')
PY
if ! command -v php-fpm >/dev/null || ! command -v mariadbd >/dev/null; then
  dnf -y module enable php:8.3 mariadb:10.11
  dnf -y install php-fpm php-cli php-mysqlnd php-gd php-mbstring php-xml php-opcache php-intl php-zip mariadb-server mariadb e2fsprogs acl policycoreutils-python-utils
fi
[[ $(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;') == 8.3 ]] || { echo 'PHP 8.3 is required. Review the existing PHP installation.' >&2; exit 1; }
# Only the customer templates may run PHP or MariaDB on this dedicated host.
systemctl mask --now php-fpm.service mariadb.service
install -d -m 700 /var/lib/vectorcp/disks /var/lib/vectorcp/hosting
install -d -m 755 /srv/vectorcp/accounts /etc/vectorcp/hosting /run/vectorcp-hosting
install -d -m 0700 /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt
install -d -m 0755 /srv/vectorcp/acme
cat >/etc/systemd/system/vectorcp-customers.slice <<'UNIT'
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
  account="vectorcp-c$slot"
  getent passwd "$account" >/dev/null || useradd --system --no-create-home --home-dir "/srv/vectorcp/accounts/$slot" --shell /sbin/nologin "$account"
  usermod -aG "$account" nginx
  install -d -m 750 "/srv/vectorcp/accounts/$slot"
  cat >"/etc/systemd/system/vectorcp-customers-c$slot.slice" <<UNIT
[Unit]
Description=VectorCP customer $slot resources
[Slice]
MemoryHigh=320M
MemoryMax=448M
CPUQuota=75%
TasksMax=48
UNIT
  cat >"/etc/systemd/system/vectorcp-task$slot.socket" <<UNIT
[Unit]
Description=Root-only VectorCP customer $slot tasks
[Socket]
ListenStream=/run/vectorcp-hosting-tasks/$slot.sock
SocketUser=root
SocketGroup=root
SocketMode=0600
DirectoryMode=0700
Accept=yes
Service=vectorcp-task$slot@.service
[Install]
WantedBy=sockets.target
UNIT
  cat >"/etc/systemd/system/vectorcp-task$slot@.service" <<UNIT
[Unit]
Description=Bounded VectorCP customer $slot task
Requires=srv-vectorcp-accounts-$slot.mount
After=srv-vectorcp-accounts-$slot.mount
[Service]
User=$account
Group=$account
Slice=vectorcp-customers-c$slot.slice
ExecStart=/usr/bin/python3 /opt/vectorcp/vectorcp/hosting_task.py $slot
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
TemporaryFileSystem=/srv:ro /var/lib/vectorcp:ro /run/vectorcp:ro /run/vectorcp-hosting:ro
BindPaths=/srv/vectorcp/accounts/$slot
ReadWritePaths=/srv/vectorcp/accounts/$slot
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=256M
TasksMax=32
RuntimeMaxSec=210
UMask=0027
UNIT
  # A mount is skipped at boot until the customer image has been provisioned.
  cat >"/etc/systemd/system/srv-vectorcp-accounts-$slot.mount" <<UNIT
[Unit]
Description=VectorCP customer $slot bounded storage
ConditionPathExists=/var/lib/vectorcp/disks/$slot.img
Before=vectorcp-php@$slot.service vectorcp-db@$slot.service nginx.service
Wants=vectorcp-php@$slot.service vectorcp-db@$slot.service
[Mount]
What=/var/lib/vectorcp/disks/$slot.img
Where=/srv/vectorcp/accounts/$slot
Type=ext4
Options=loop,nodev,nosuid,noexec
[Install]
WantedBy=multi-user.target
UNIT
  systemctl enable "srv-vectorcp-accounts-$slot.mount"
done
# The fixed templates take only a two-digit slot allocated by the root agent.
cat >/etc/systemd/system/vectorcp-php@.service <<'UNIT'
[Unit]
Description=Isolated VectorCP PHP customer %i
ConditionPathExists=/etc/vectorcp/hosting/%i.conf
Requires=srv-vectorcp-accounts-%i.mount
After=srv-vectorcp-accounts-%i.mount
[Service]
User=vectorcp-c%i
Group=vectorcp-c%i
Slice=vectorcp-customers-c%i.slice
ExecStart=/usr/sbin/php-fpm --nodaemonize --fpm-config /etc/vectorcp/hosting/%i.conf
Restart=on-failure
RuntimeDirectory=vectorcp-hosting/%i
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
TemporaryFileSystem=/srv:ro /run/vectorcp:ro /var/lib/vectorcp:ro /run/vectorcp-hosting:ro
BindPaths=/srv/vectorcp/accounts/%i /run/vectorcp-hosting/%i
ReadWritePaths=/srv/vectorcp/accounts/%i /run/vectorcp-hosting/%i
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=256M
TasksMax=12
[Install]
WantedBy=multi-user.target
UNIT
cat >/etc/systemd/system/vectorcp-db@.service <<'UNIT'
[Unit]
Description=Isolated VectorCP MariaDB customer %i
ConditionPathExists=/srv/vectorcp/accounts/%i/private/mysql/mysql
Requires=srv-vectorcp-accounts-%i.mount
After=srv-vectorcp-accounts-%i.mount
[Service]
User=vectorcp-c%i
Group=vectorcp-c%i
Slice=vectorcp-customers-c%i.slice
ExecStart=/usr/libexec/mariadbd --no-defaults --datadir=/srv/vectorcp/accounts/%i/private/mysql --socket=/srv/vectorcp/accounts/%i/private/run/mysql.sock --pid-file=/srv/vectorcp/accounts/%i/private/run/mysql.pid --skip-networking --skip-log-bin --skip-name-resolve --innodb-buffer-pool-size=32M --innodb-log-file-size=16M --max-connections=8 --table-open-cache=64 --performance-schema=OFF --aria-pagecache-buffer-size=8M --key-buffer-size=4M --tmp-table-size=8M --max-heap-table-size=8M --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
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
TemporaryFileSystem=/srv:ro /run/vectorcp:ro /var/lib/vectorcp:ro
BindPaths=/srv/vectorcp/accounts/%i
ReadWritePaths=/srv/vectorcp/accounts/%i
RestrictAddressFamilies=AF_UNIX
MemoryMax=192M
TasksMax=32
TimeoutStartSec=90
TimeoutStopSec=60
[Install]
WantedBy=multi-user.target
UNIT
# Labels persist across remount and relabel. The DB subtree has its own labels.
semanage fcontext -a -t httpd_sys_rw_content_t '/srv/vectorcp/accounts(/.*)?' 2>/dev/null || semanage fcontext -m -t httpd_sys_rw_content_t '/srv/vectorcp/accounts(/.*)?'
semanage fcontext -a -t mysqld_db_t '/srv/vectorcp/accounts/[0-9]+/private/mysql(/.*)?' 2>/dev/null || semanage fcontext -m -t mysqld_db_t '/srv/vectorcp/accounts/[0-9]+/private/mysql(/.*)?'
semanage fcontext -a -t mysqld_var_run_t '/srv/vectorcp/accounts/[0-9]+/private/run(/.*)?' 2>/dev/null || true
semanage fcontext -a -t httpd_var_run_t '/run/vectorcp-hosting(/.*)?' 2>/dev/null || true
restorecon -R /srv/vectorcp/accounts /run/vectorcp-hosting /etc/vectorcp
# Only controlled hosting configuration and certificate paths are added.
install -d /etc/systemd/system/vectorcp-agent.service.d
cat >/etc/systemd/system/vectorcp-agent.service.d/hosting.conf <<'UNIT'
[Service]
ReadWritePaths=/etc/vectorcp/hosting /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt /srv/vectorcp/acme
MemoryMax=384M
TasksMax=48
UNIT
# Renewal covers the owner IP certificate and future customer certificates.
if [[ -f /etc/systemd/system/vectorcp-cert-renew.service ]]; then
  sed -i 's/ --cert-name vectorcp-panel-ip//' /etc/systemd/system/vectorcp-cert-renew.service
fi
systemctl daemon-reload
printf '1\n' >/var/lib/vectorcp/hosting/enabled
chmod 600 /var/lib/vectorcp/hosting/enabled
restorecon -R /srv/vectorcp/acme
nginx -t
systemctl restart nginx vectorcp-agent vectorcp-web
ready=false
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8765/healthz; then ready=true; break; fi
  sleep 1
done
[[ $ready == true ]] || { echo 'Panel services did not recover; inspect their journal before retrying.' >&2; exit 1; }
echo 'Isolated hosting services prepared. No customer workloads started.'
