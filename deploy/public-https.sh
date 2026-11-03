#!/usr/bin/env bash
# Initial IPv4 HTTPS publication on an already installed VectorCP host.
# --prepare keeps the administrative interface private; --publish exposes HTTPS.
set -Eeuo pipefail
umask 077
mode=${1:---check}
panel_ip=${2:-}
if [[ $mode == --help ]]; then
  echo 'Usage: bash deploy/public-https.sh [--check | --prepare | --publish] PUBLIC_IPV4'
  echo "--publish obtains a Let's Encrypt certificate, accepts its subscriber terms,"
  echo 'enables local reverse proxying and automatic renewal, and opens HTTPS publicly.'
  exit 0
fi
[[ $mode == --check || $mode == --prepare || $mode == --publish ]] || exit 2
[[ $# == 2 && $EUID == 0 && $(uname -s) == Linux ]] || { echo 'Root on Linux and an IPv4 address are required.' >&2; exit 1; }
panel_ip=$(python3 - "$panel_ip" <<'PY'
import ipaddress, sys
address = ipaddress.IPv4Address(sys.argv[1])
if not address.is_global:
    raise SystemExit('A public IPv4 address is required.')
print(address)
PY
)
source /etc/os-release
[[ $ID == almalinux && ${VERSION_ID%%.*} == 9 ]] || exit 1
test -f /opt/vectorcp/vectorcp/web.py
for unit in vectorcp-agent nginx firewalld; do systemctl is-active --quiet "$unit"; done
firewall_zone=$(firewall-cmd --get-default-zone)
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
state=/var/lib/vectorcp
backups=$state/install-backups/public-https
if [[ -f $state/public-https-prepared ]]; then
  [[ $(cat "$state/public-https-prepared") == "$panel_ip" ]] || { echo 'Prepared for another address. Review manually.' >&2; exit 1; }
fi
if [[ $mode == --check ]]; then
  echo "Initial public HTTPS configuration target: https://$panel_ip"
  echo "Firewall default zone: $firewall_zone"
  echo 'The existing SSH-only interface will remain available.'
  exit 0
fi
install -d -m 0700 "$backups"
render() { sed "s/__PANEL_IP__/$panel_ip/g" "$1"; }
reload_nginx() { /usr/sbin/nginx -t && systemctl reload nginx; }
if [[ $mode == --prepare ]]; then
  if [[ ! -f $state/public-https-prepared && ( -e /etc/nginx/conf.d/vectorcp-panel-http.conf || -e /etc/systemd/system/vectorcp-web-public.service ) ]]; then
    echo 'An existing public-panel configuration needs manual review.' >&2; exit 1
  fi
  dnf -y install python3.12 python3.12-pip
  if [[ ! -x /opt/vectorcp-certbot/bin/certbot ]]; then
    python3.12 -m venv /opt/vectorcp-certbot
    /opt/vectorcp-certbot/bin/pip install 'certbot==5.9.0'
  fi
  /opt/vectorcp-certbot/bin/certbot --version
  [[ -f $backups/nginx-before-panel.conf ]] || cp -a /etc/nginx/nginx.conf "$backups/nginx-before-panel.conf"
  install -d -m 0755 /srv/vectorcp/acme/.well-known/acme-challenge
  chmod 0755 /srv/vectorcp/acme /srv/vectorcp/acme/.well-known /srv/vectorcp/acme/.well-known/acme-challenge
  if [[ $(getenforce) != Disabled ]]; then restorecon -RF /srv/vectorcp/acme; fi
  render "$project/deploy/nginx-panel-http.conf" | sed 's/__HTTP_ACTION__/return 404;/' > /etc/nginx/conf.d/vectorcp-panel-http.conf
  chmod 0644 /etc/nginx/conf.d/vectorcp-panel-http.conf
  python3 - <<'PY'
from pathlib import Path
path = Path('/etc/nginx/nginx.conf')
content = path.read_text()
existing = '    include /etc/nginx/conf.d/vectorcp-site-*.conf;'
additional = '    include /etc/nginx/conf.d/vectorcp-panel-*.conf;'
if additional not in content:
    if existing not in content:
        raise SystemExit('Unexpected Nginx configuration. Inspect before changing it.')
    path.write_text(content.replace(existing, existing + '\n' + additional, 1))
PY
  if ! reload_nginx; then
    cp -a "$backups/nginx-before-panel.conf" /etc/nginx/nginx.conf
    /usr/sbin/nginx -t && systemctl reload nginx
    exit 1
  fi
  render "$project/deploy/vectorcp-web-public.service" > /etc/systemd/system/vectorcp-web-public.service
  chmod 0644 /etc/systemd/system/vectorcp-web-public.service
  systemctl daemon-reload
  systemctl enable --now vectorcp-web-public
  ready=false
  for attempt in {1..30}; do
    if curl --fail --silent -H "Host: $panel_ip" http://127.0.0.1:8008/healthz; then ready=true; break; fi
    sleep 1
  done
  [[ $ready == true ]] || exit 1
  printf '%s\n' "$panel_ip" > "$state/public-https-prepared"
  echo
  echo 'Private HTTPS backend and HTTP certificate-challenge routing are ready.'
  echo 'No public administrative HTTPS listener or firewall opening has been added.'
  exit 0
fi
test -f "$state/public-https-prepared"
if [[ -f $state/public-https-published ]]; then
  [[ $(cat "$state/public-https-published") == "$panel_ip" ]] || exit 1
  curl --fail --silent "https://$panel_ip/healthz"
  echo
  exit 0
fi
if firewall-cmd --zone="$firewall_zone" --query-service=https >/dev/null; then
  echo 'HTTPS is already open before initial publication. Review the partial state.' >&2
  exit 1
fi
# Certbot creates the key locally; its account and key files stay root-private.
/opt/vectorcp-certbot/bin/certbot certonly --non-interactive --agree-tos \
  --register-unsafely-without-email --cert-name vectorcp-panel-ip \
  --required-profile shortlived --preferred-challenges http-01 \
  --webroot --webroot-path /srv/vectorcp/acme --ip-address "$panel_ip" \
  --keep-until-expiring
if [[ $(getenforce) != Disabled ]]; then
  if [[ $(matchpathcon -n /etc/letsencrypt) != *:cert_t:* ]]; then
    semanage fcontext -a -t cert_t '/etc/letsencrypt(/.*)?'
  fi
  restorecon -RF /etc/letsencrypt
  setsebool -P httpd_can_network_relay on
fi
# Bind the final address while the firewall is still closed. Switching from a
# loopback listener to a wildcard listener cannot be done safely by Nginx reload.
render "$project/deploy/nginx-panel-https.conf" | sed 's/__LISTEN_ADDRESS__/443/' > /etc/nginx/conf.d/vectorcp-panel-https.conf
chmod 0644 /etc/nginx/conf.d/vectorcp-panel-https.conf
reload_nginx
sleep 1
# Validate certificate trust, the IP SAN, proxying and agent readiness before exposure.
curl --fail --silent --show-error --resolve "$panel_ip:443:127.0.0.1" "https://$panel_ip/healthz"
echo
install -d -m 0755 /usr/local/libexec
install -m 0755 "$project/deploy/vectorcp-cert-renew" /usr/local/libexec/vectorcp-cert-renew
install -m 0644 "$project/deploy/vectorcp-cert-renew.service" /etc/systemd/system/vectorcp-cert-renew.service
install -m 0644 "$project/deploy/vectorcp-cert-renew.timer" /etc/systemd/system/vectorcp-cert-renew.timer
systemctl daemon-reload
systemctl enable --now vectorcp-cert-renew.timer
render "$project/deploy/nginx-panel-http.conf" | sed "s|__HTTP_ACTION__|return 308 https://$panel_ip\$request_uri;|" > /etc/nginx/conf.d/vectorcp-panel-http.conf
chmod 0644 /etc/nginx/conf.d/vectorcp-panel-*.conf
reload_nginx
if ! firewall-cmd --permanent --zone="$firewall_zone" --query-service=https; then
  firewall-cmd --permanent --zone="$firewall_zone" --add-service=https
fi
if ! firewall-cmd --zone="$firewall_zone" --query-service=https; then
  firewall-cmd --zone="$firewall_zone" --add-service=https
fi
curl --fail --silent --show-error "https://$panel_ip/healthz"
echo
printf '%s\n' "$panel_ip" > "$state/public-https-published"
echo "Public HTTPS enabled at https://$panel_ip/"
echo 'Verify access externally and rehearse certificate renewal before handover.'
