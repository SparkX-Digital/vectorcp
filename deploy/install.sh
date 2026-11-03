#!/usr/bin/env bash
# Dedicated AlmaLinux 9 host only. Checks are the default; --apply makes changes.
set -Eeuo pipefail
umask 077
mode=${1:---check}
open_http=${2:-}
if [[ $mode == --help ]]; then
  echo 'Usage: bash deploy/install.sh [--check | --apply] [--open-http]'
  echo 'Installs the first release with a private panel accessed through SSH forwarding.'
  exit 0
fi
[[ $mode == --check || $mode == --apply ]] || { echo 'Invalid mode.' >&2; exit 2; }
[[ -z $open_http || $open_http == --open-http ]] || { echo 'Invalid option.' >&2; exit 2; }
[[ $# -le 2 && $(uname -s) == Linux && $EUID == 0 ]] || { echo 'Run as root on Linux.' >&2; exit 1; }
source /etc/os-release
[[ ${ID:-} == almalinux && ${VERSION_ID%%.*} == 9 ]] || { echo 'AlmaLinux 9 is required.' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { echo 'This development installer targets x86-64. Other architectures are not yet verified.' >&2; exit 1; }
for location in /opt/vectorcp /var/lib/vectorcp /srv/vectorcp /etc/vectorcp; do
  [[ ! -e $location ]] || { echo "Existing application at $location. A fresh host is required." >&2; exit 1; }
done
# Detect existing hosting services without assuming a particular panel vendor.
if ss -H -lnt | awk '{print $4}' | grep -Eq ':(80|443|2082|2083|2086|2087|2222|8080|8090|8443)$'; then
  echo 'A web or hosting-control port is already in use. A fresh host is required.' >&2
  exit 1
fi
if compgen -G '/var/lib/*/control.sqlite3' >/dev/null; then
  echo 'An existing control database was found. Use its verified upgrade procedure.' >&2
  exit 1
fi
for package in nginx httpd mariadb-server postfix dovecot; do
  if rpm -q "$package" >/dev/null 2>&1; then
    echo "Existing hosting component $package detected. Review before installation." >&2
    exit 1
  fi
done
if id vectorcp-web >/dev/null 2>&1; then
  echo 'The vectorcp-web account already exists. Review before installation.' >&2
  exit 1
fi
echo "Preflight: $PRETTY_NAME, $(uname -m)"
free -m
df -h /
ss -lntup
if [[ $mode == --check ]]; then
  echo 'Checks complete. No changes made.'
  exit 0
fi
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dnf -y install python3 nginx policycoreutils-python-utils curl tar
useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /sbin/nologin vectorcp-web
install -d -m 0755 /opt/vectorcp /srv/vectorcp/sites
install -d -m 0700 /var/lib/vectorcp /var/lib/vectorcp/install-backups
tar --exclude='__pycache__' --exclude='*.pyc' -C "$project_dir" -cf - vectorcp | tar -C /opt/vectorcp -xf -
chown -R root:root /opt/vectorcp /srv/vectorcp /var/lib/vectorcp
find /opt/vectorcp -type d -exec chmod 0755 {} +
find /opt/vectorcp -type f -exec chmod 0644 {} +
chmod 0755 /srv/vectorcp /srv/vectorcp/sites
cp -a /etc/nginx/nginx.conf /var/lib/vectorcp/install-backups/nginx.conf
install -m 0644 "$project_dir/deploy/nginx.conf" /etc/nginx/nginx.conf
if [[ $(getenforce) != Disabled ]]; then
  semanage fcontext -a -t httpd_sys_content_t '/srv/vectorcp(/.*)?' || semanage fcontext -m -t httpd_sys_content_t '/srv/vectorcp(/.*)?'
  restorecon -RF /srv/vectorcp
fi
if ! /usr/sbin/nginx -t; then
  cp -a /var/lib/vectorcp/install-backups/nginx.conf /etc/nginx/nginx.conf
  echo 'Nginx validation failed. Its previous configuration was restored.' >&2
  exit 1
fi
install -m 0644 "$project_dir/deploy/vectorcp-agent.service" /etc/systemd/system/vectorcp-agent.service
install -m 0644 "$project_dir/deploy/vectorcp-web.service" /etc/systemd/system/vectorcp-web.service
systemctl daemon-reload
systemctl enable --now nginx vectorcp-agent vectorcp-web
if [[ $open_http == --open-http ]] && command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
  firewall-cmd --permanent --add-service=http
  firewall-cmd --reload
fi
ready=false
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8765/healthz; then
    ready=true
    break
  fi
  sleep 1
done
[[ $ready == true ]] || { echo 'Services did not become ready. Inspect their journal logs.' >&2; exit 1; }
echo
echo 'Services started. The panel is loopback-only, with no public administrative port.'
echo 'Create a 30-minute administrator setup token with:'
echo '  cd /opt/vectorcp && python3 -m vectorcp.agent --setup-token'
echo 'Then connect through an SSH tunnel and open the token through the setup form.'
echo 'Review README.md for the development release scope and installation limits.'
