"""Runs as the customer inside a fixed, sandboxed systemd socket service.

Only root can connect to this local socket. Input never becomes shell syntax.
"""
import json
import re
import subprocess
import sys


def main():
    slot = sys.argv[1]
    if not re.fullmatch(r'(0[1-9]|1[0-6])', slot):
        raise ValueError('Invalid slot')
    raw = sys.stdin.buffer.readline(16385)
    if len(raw) > 16384:
        raise ValueError('Request too large')
    request = json.loads(raw)
    root = '/srv/veyrapanel/accounts/' + slot
    action = request.get('action')
    if action == 'initialize_database':
        argv = ['/usr/bin/mariadb-install-db', '--no-defaults', '--datadir=' + root + '/private/mysql',
                '--auth-root-authentication-method=socket', '--auth-root-socket-user=root', '--skip-test-db']
        payload = None
    elif action == 'install_wordpress':
        site_id = request.get('site_id')
        if isinstance(site_id, bool) or not isinstance(site_id, int) or not 1 <= site_id <= 2147483647:
            raise ValueError('Invalid website')
        argv = ['/usr/bin/php', '/opt/veyrapanel/veyra/wp-install.php', root + '/sites/%d/public' % site_id]
        payload = json.dumps(request.get('input', {})).encode()
    elif action == 'wordpress_https':
        site_id = request.get('site_id')
        domain = request.get('domain', '')
        if not isinstance(site_id, int) or not 1 <= site_id <= 2147483647 or not re.fullmatch(r'[a-z0-9.-]{4,253}', domain):
            raise ValueError('Invalid website')
        argv = ['/usr/bin/php', '/opt/veyrapanel/veyra/wp-https.php', root + '/sites/%d/public' % site_id, domain]
        payload = None
    else:
        raise ValueError('Unknown task')
    result = subprocess.run(argv, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    diagnostic = ''
    if result.returncode:
        diagnostic = re.sub(r'[A-Za-z0-9_-]{24,}', '[redacted]', (result.stderr + result.stdout)[-4000:].decode('utf-8', 'replace'))
    print(json.dumps({'ok': result.returncode == 0, 'diagnostic': diagnostic}), flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'ok': False, 'diagnostic': 'Customer task failed before completion.'}), flush=True)
