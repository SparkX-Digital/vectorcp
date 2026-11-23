#!/usr/bin/env bash
# Owner-only optional profile. No DNS, firewall or registrar changes.
set -euo pipefail
cd /opt/vectorcp
exec /usr/bin/python3 -m vectorcp.mail_profile "$@"
