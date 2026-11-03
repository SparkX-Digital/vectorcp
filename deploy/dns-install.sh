#!/usr/bin/env bash
# Install a private authoritative DNS preview. Public port 53 stays closed.
set -euo pipefail
[[ ${1:-} == --apply ]] || { echo 'Usage: sudo bash dns-install.sh --apply'; exit 2; }
[[ $EUID == 0 && -d /opt/veyrapanel/veyra && -f /etc/almalinux-release ]] || { echo 'Requires an existing VectorCP installation on AlmaLinux 9.'; exit 1; }
if systemctl is-active --quiet named && [[ ! -f /etc/veyrapanel/dns/installed.json ]]; then
  echo 'An existing DNS service is running. Refusing to replace it.'; exit 1
fi
dnf -y install bind bind-utils
install -d -o root -g named -m 0750 /etc/veyrapanel/dns /var/named/veyrapanel
install -d -o named -g named -m 0700 /var/named/data/veyrapanel
[[ -e /etc/veyrapanel/dns/zones.conf ]] || install -o root -g named -m 0640 /dev/null /etc/veyrapanel/dns/zones.conf
cat > /etc/veyrapanel/dns/named.conf <<'CONF'
options {
  directory "/var/named/data/veyrapanel";
  listen-on port 53 { 127.0.0.1; };
  listen-on-v6 { none; };
  recursion no;
  allow-query { 127.0.0.1; };
  allow-transfer { none; };
  allow-update { none; };
  dnssec-validation no;
  notify no;
  minimal-responses yes;
  version "private-authoritative";
  pid-file "/run/veyra-dns/named.pid";
  session-keyfile "/run/veyra-dns/session.key";
  rate-limit { responses-per-second 10; };
};
controls { };
include "/etc/veyrapanel/dns/zones.conf";
CONF
chown root:named /etc/veyrapanel/dns/named.conf
chmod 0640 /etc/veyrapanel/dns/named.conf
semanage fcontext -a -t named_conf_t '/etc/veyrapanel/dns(/.*)?' 2>/dev/null || semanage fcontext -m -t named_conf_t '/etc/veyrapanel/dns(/.*)?'
semanage fcontext -a -t named_zone_t '/var/named/veyrapanel(/.*)?' 2>/dev/null || semanage fcontext -m -t named_zone_t '/var/named/veyrapanel(/.*)?'
semanage fcontext -a -t named_var_run_t '/var/run/veyra-dns(/.*)?' 2>/dev/null || semanage fcontext -m -t named_var_run_t '/var/run/veyra-dns(/.*)?'
restorecon -RF /etc/veyrapanel/dns /var/named/veyrapanel /var/named/data/veyrapanel
cat > /etc/systemd/system/veyra-dns.service <<'UNIT'
[Unit]
Description=VectorCP private authoritative DNS preview
After=network.target
[Service]
Group=named
Type=simple
ExecStartPre=/usr/sbin/named-checkconf -z /etc/veyrapanel/dns/named.conf
ExecStart=/usr/sbin/named -g -u named -c /etc/veyrapanel/dns/named.conf
ExecReload=/bin/kill -HUP $MAINPID
RuntimeDirectory=veyra-dns
RuntimeDirectoryMode=0770
Restart=on-failure
RestartSec=3
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/veyra-dns /var/named/data/veyrapanel
MemoryMax=128M
TasksMax=16
[Install]
WantedBy=multi-user.target
UNIT
install -d -m 0755 /etc/systemd/system/veyra-agent.service.d
cat > /etc/systemd/system/veyra-agent.service.d/dns.conf <<'UNIT'
[Service]
ReadWritePaths=/etc/veyrapanel/dns /var/named/veyrapanel
UNIT
named-checkconf -z /etc/veyrapanel/dns/named.conf
systemctl daemon-reload
systemctl enable --now veyra-dns
ready=false
for attempt in {1..20}; do
  if dig @127.0.0.1 version.bind TXT CH +short +time=1 +tries=1 | grep -q private-authoritative; then ready=true; break; fi
  sleep 0.2
done
[[ $ready == true ]] || { echo 'DNS service did not become ready; inspect its journal.'; exit 1; }
printf '%s\n' '{"mode":"private","listen":"127.0.0.1:53"}' > /etc/veyrapanel/dns/installed.json
chmod 0600 /etc/veyrapanel/dns/installed.json
echo 'Private authoritative DNS installed. No public firewall changes made.'
