"""Verify a built static site without network access or third-party packages."""
import argparse
import ast
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.canonicals, self.controls = set(), [], [], []
        self.headings = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img':
            assert 'alt' in attrs, 'Images need text alternatives'
        if 'aria-controls' in attrs:
            self.controls.extend(attrs['aria-controls'].split())
        if 'id' in attrs:
            assert attrs['id'] not in self.ids, 'Duplicate ID: ' + attrs['id']
            self.ids.add(attrs['id'])
        if tag == 'h1':
            self.headings += 1
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs['href'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])


def check(root):
    root = root.resolve()
    pages = {}
    for path in root.rglob('*.html'):
        parser = Page()
        parser.feed(path.read_text())
        assert parser.headings == 1, ('One main heading required', path)
        assert len(parser.canonicals) == 1 and parser.canonicals[0].startswith('https://vectorcp.net/'), path
        pages[path.resolve()] = parser
    links = 0
    for path, page in pages.items():
        for controlled in page.controls:
            assert controlled in page.ids, ('Missing controlled region', path, controlled)
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (root / url.path.lstrip('/') if url.path.startswith('/') else path.parent / url.path).resolve() if url.path else path
            assert target == root or root in target.parents, (path, link)
            if target.is_dir():
                target = target / 'index.html'
            assert target.is_file(), (path, link)
            if url.fragment and target in pages:
                assert unquote(url.fragment) in pages[target].ids, (path, link)
            links += 1
    # CSS dependencies are not HTML links, but are still required for a usable site.
    for stylesheet in (root / 'assets').rglob('*.css'):
        for value in re.findall(r'url\([\'"]?([^\)\'"\s]+)[\'"]?\)', stylesheet.read_text()):
            url = urlsplit(value)
            if url.scheme or url.netloc:
                continue
            asset = (root / url.path.lstrip('/') if url.path.startswith('/') else stylesheet.parent / url.path).resolve()
            assert root in asset.parents and asset.is_file(), ('Missing style asset', stylesheet, value)
    entries = json.loads((root / 'assets/docs-index.json').read_text())
    assert len(entries) >= 20
    for entry in entries:
        assert re.fullmatch(r'/docs/(?:[a-z_]+/)?', entry['url'])
        assert (root / entry['url'].lstrip('/') / 'index.html').is_file()
    history = (root / 'changelog/index.html').read_text()
    assert '0.4.5' in history and '<time datetime="2026-11-25">' in history
    assert '0.4.4' in history and '<time datetime="2026-11-24">' in history
    guide = (root / 'docs/mail_hosting/index.html').read_text()
    assert 'TCP 25, 587 and 993.' in guide
    assert '--mailbox user@example.net' in guide
    directives = (root / 'website-directives.htaccess').read_text()
    assert 'Cache-Control "no-cache, max-age=0, must-revalidate, no-transform"' in directives
    for checksum in (root / 'downloads').glob('*.sha256'):
        expected, name = checksum.read_text().strip().split(None, 1)
        assert hashlib.sha256((checksum.parent / name.strip()).read_bytes()).hexdigest() == expected
    # Regression checks for numeric paragraph wraps, duplicate heading anchors,
    # fenced command blocks and escaped text in the dependency-free renderer.
    tree = ast.parse(Path(__file__).with_name('build.py').read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('inline', 'markdown')]
    namespace = {'re': re, 'html': html, 'Path': Path}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'renderer', 'exec'), namespace)
    rendered = namespace['markdown']('Allow TCP 25, 587 and\n993. Use TLS.\n\n## Added\n\n## Added\n\n```sh\necho "<safe>"\n```')
    assert '<p>Allow TCP 25, 587 and 993. Use TLS.</p>' in rendered
    assert 'id="added-2"' in rendered and '&lt;safe&gt;' in rendered
    print(json.dumps({'html_pages': len(pages), 'local_links': links, 'search_guides': len(entries), 'checksums': 'passed', 'renderer_regressions': 'passed'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    check(parser.parse_args().root)
