"""Bounded website routing. User input never becomes an Nginx directive."""
import json
import os
import re
import stat
from urllib.parse import unquote, urlsplit

from .core import DOMAIN, FILE_MAX, Fault, integer

OPERATIONS = {'sites.routing.get', 'sites.routing.save'}
ERROR_CODES = (400, 401, 403, 404, 405, 410, 429, 500, 502, 503, 504)


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS site_routing(
        site_id INTEGER PRIMARY KEY REFERENCES sites(id), revision INTEGER NOT NULL,
        force_https INTEGER NOT NULL, redirects TEXT NOT NULL, error_pages TEXT NOT NULL)''')


def settings(db, site_id):
    row = db.execute('SELECT * FROM site_routing WHERE site_id=?', (site_id,)).fetchone()
    if row is None:
        return {'revision': 0, 'force_https': True, 'redirects': [], 'error_pages': {}}
    return {'revision': row['revision'], 'force_https': bool(row['force_https']),
            'redirects': json.loads(row['redirects']), 'error_pages': json.loads(row['error_pages'])}


def source_path(value):
    if (not isinstance(value, str) or len(value) > 256 or not value.startswith('/')
            or not re.fullmatch(r'/[A-Za-z0-9_./-]*', value) or '//' in value
            or any(p.startswith('.') for p in value.split('/') if p)):
        raise Fault('Use a plain website path, such as /old-page or /old-folder/.')
    return value


def destination(value):
    if (not isinstance(value, str) or len(value) > 2048
            or not re.fullmatch(r"[A-Za-z0-9_./~:%?&=+@!,()*\[\]-]+", value)
            or re.search(r'%(?![A-Fa-f0-9]{2})|%(?:0[0-9a-f]|1[0-9a-f]|7f)', value, re.I)):
        raise Fault('Use an HTTP or HTTPS destination without credentials, fragments or control characters.')
    try:
        parts = urlsplit(value)
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or not DOMAIN.fullmatch(parts.hostname) or parts.username or parts.password
                or parts.fragment or (parts.port is not None and not 1 <= parts.port <= 65535)):
            raise ValueError()
    except ValueError:
        raise Fault('Use an HTTP or HTTPS destination with a public domain name.')
    return parts


def validate_rules(values, domain):
    if not isinstance(values, list) or len(values) > 20:
        raise Fault('Use at most 20 redirect rules per website.')
    result, seen = [], set()
    for item in values:
        keys = {'path', 'match', 'target', 'code', 'keep_query', 'append_path'}
        if not isinstance(item, dict) or set(item) != keys:
            raise Fault('Invalid redirect rule.')
        path = source_path(item['path'])
        if path.startswith('/_vectorcp_error/'):
            raise Fault('That path is reserved for website error pages.')
        if item['match'] not in ('exact', 'prefix'):
            raise Fault('Choose exact-path or folder-prefix matching.')
        if item['match'] == 'prefix' and not path.endswith('/'):
            raise Fault('A folder-prefix path must end with /.')
        if (path, item['match']) in seen:
            raise Fault('Each path and match type may appear only once.')
        seen.add((path, item['match']))
        code = integer(item['code'], 'redirect status', 301, 308)
        if code not in (301, 302, 307, 308):
            raise Fault('Choose status 301, 302, 307 or 308.')
        if not isinstance(item['keep_query'], bool) or not isinstance(item['append_path'], bool):
            raise Fault('Invalid redirect options.')
        target = destination(item['target'])
        if item['append_path'] and (item['match'] != 'prefix' or '?' in item['target'] or not target.path.endswith('/')):
            raise Fault('Keeping the remaining path requires a folder-prefix rule and a destination ending in / without a query.')
        result.append(dict(item))
    # Check same-site cycles using actual exact/longest-prefix precedence.
    def next_rule(path):
        matches = [(i, r) for i, r in enumerate(result) if
                   (path == r['path'] if r['match'] == 'exact' else path.startswith(r['path']))]
        return min(matches, key=lambda p: (p[1]['match'] != 'exact', -len(p[1]['path']))) if matches else None
    for start in range(len(result)):
        index, visited = start, set()
        while index is not None:
            if index in visited:
                raise Fault('These redirects create a loop on this website.')
            visited.add(index)
            parts = urlsplit(result[index]['target'])
            if parts.hostname != domain:
                break
            match = next_rule(unquote(parts.path) or '/')
            index = match[0] if match else None
    return result


def quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def render(site, config):
    """Return HTTP-context maps, locations and an optional root redirect."""
    maps, locations, root_rule = [], [], None
    for index, rule in enumerate(config['redirects']):
        name = 'vcp_s%d_r%d' % (site['id'], index)
        target = rule['target']
        if rule['append_path']:
            # Match the raw request URI: decoded captures could inject header controls.
            expression = '~^' + re.escape(rule['path']) + '(?<' + name + '_tail>[^?]*)(?:\\?.*)?$'
            maps.append('map $request_uri $%s_suffix { default ""; %s $%s_tail; }\n' %
                        (name, quote(expression), name))
            target += '$' + name + '_suffix'
        if rule['keep_query']:
            if '?' in rule['target']:
                maps.append('map $args $%s_query { "" ""; default "&$args"; }\n' % name)
                target += '$' + name + '_query'
            else:
                target += '$is_args$args'
        block = 'location %s %s { return %d %s; }\n' % (
            '=' if rule['match'] == 'exact' else '^~', rule['path'], rule['code'], quote(target))
        if rule['match'] == 'prefix' and rule['path'] == '/':
            root_rule = block
        else:
            locations.append(block)
    for code, path in sorted(config['error_pages'].items()):
        locations.append('error_page %s =%s /_vectorcp_error/%s;\n'
                         'location = /_vectorcp_error/%s { internal; disable_symlinks on; '
                         'types { } default_type text/html; try_files /%s =%s; }\n' %
                         (code, code, code, code, path, code))
    return ''.join(maps), ''.join(locations), root_rule


class Routing:
    def __init__(self, engine):
        self.engine = engine

    def dispatch(self, db, actor, site, method, data):
        current = settings(db, site['id'])
        if method == 'sites.routing.get':
            return dict(current, site_id=site['id'], tls=bool(site['tls']),
                        editable=site['status'] == 'active', error_codes=list(ERROR_CODES))
        if site['status'] != 'active':
            raise Fault('Activate this website before changing its routing.', 409)
        if set(data) != {'site_id', 'revision', 'force_https', 'redirects', 'error_pages'}:
            raise Fault('Invalid website routing settings.')
        revision = integer(data['revision'], 'routing revision', 0, 2147483646)
        if revision != current['revision']:
            raise Fault('Routing changed since you opened it. Reopen the settings before saving.', 409)
        if not isinstance(data['force_https'], bool):
            raise Fault('Invalid HTTPS preference.')
        rules = validate_rules(data['redirects'], site['domain'])
        pages = data['error_pages']
        if (not isinstance(pages, dict) or len(pages) > len(ERROR_CODES)
                or any(k not in {str(code) for code in ERROR_CODES} for k in pages)):
            raise Fault('Choose a supported HTTP error status.')
        for path in pages.values():
            if (not isinstance(path, str) or len(path) > 256
                    or not re.fullmatch(r'[A-Za-z0-9_./-]+\.html?', path)
                    or path.startswith('/') or any(p.startswith('.') for p in path.split('/'))):
                raise Fault('Choose an existing .html or .htm file inside this website.')
            parent, _, name = path.rpartition('/')
            with self.engine.directory(self.engine.site_root(site), parent) as fd:
                try:
                    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                except OSError:
                    raise Fault('The error page must be a readable, regular HTML file.', 409)
                try:
                    info = os.fstat(handle)
                    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= FILE_MAX:
                        raise Fault('Error pages must be nonempty regular HTML files up to 256 KB.')
                finally:
                    os.close(handle)
        candidate = {'revision': revision + 1, 'force_https': data['force_https'],
                     'redirects': rules, 'error_pages': pages}
        db.execute('INSERT OR REPLACE INTO site_routing VALUES(?,?,?,?,?)',
                   (site['id'], candidate['revision'], int(candidate['force_https']),
                    json.dumps(rules), json.dumps(pages)))
        self.engine.publish_config(site, site['status'], routing=candidate)
        self.engine.log(db, actor, 'site.routing_updated', site['domain'])
        return dict(candidate, ok=True)
