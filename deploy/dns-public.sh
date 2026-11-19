#!/usr/bin/env bash
# Explicit owner action: switch an installed DNS service profile; no firewall edits.
set -euo pipefail
[[ ${1:-} == --apply ]] || { echo 'Usage: sudo bash dns-public.sh --apply --public --nameserver ns1.example.net --nameserver ns2.example.net --listen-ip SERVER_INTERFACE_IP (or --private)'; exit 2; }
shift
[[ $EUID == 0 && -f /etc/almalinux-release && -d /opt/vectorcp/vectorcp ]] || { echo 'Requires root and an installed VectorCP on AlmaLinux 9.'; exit 1; }
exec 9>/var/lib/vectorcp/profile-maintenance.lock
flock -n 9 || { echo 'Another service-profile change is running.' >&2; exit 1; }
[[ ! -e /run/vectorcp-profile-maintenance ]] || { echo 'Inspect the interrupted profile change before retrying.' >&2; exit 1; }
install -m 0600 /dev/null /run/vectorcp-profile-maintenance
trap 'rm -f /run/vectorcp-profile-maintenance' EXIT
cd /opt/vectorcp
exec_python_status=0
python3 -m vectorcp.dns_profile "$@" || exec_python_status=$?
if [[ $exec_python_status == 75 ]]; then
  trap - EXIT
  echo 'Maintenance marker retained: inspect DNS recovery before allowing further changes.' >&2
fi
exit "$exec_python_status"
