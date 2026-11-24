"""Build the VectorCP static public website from reviewed project material."""
from pathlib import Path
import hashlib
import html
import json
import re
import shutil
import zipfile

import argparse

SITE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--panel-source', type=Path, required=True)
parser.add_argument('--development-archive', type=Path, required=True)
parser.add_argument('--panel-image', type=Path, default=SITE/'source-material/panel-043-live.png')
parser.add_argument('--output', type=Path, default=SITE/'dist')
args = parser.parse_args()
SOURCE = args.panel_source.resolve()
DIST = args.output.resolve()
MATERIAL = SITE/'source-material'
ARCHIVE_NAME = args.development_archive.name
DOCS = {p.name: p.stem.replace('_', ' ').title() for p in sorted(SOURCE.glob('*.md'))}
DOCS.update({'README.md':'Documentation', 'DATABASE_ADMIN.md':'Database administration', 'PUBLIC_DNS.md':'Public DNS', 'DNS_RECOVERY.md':'DNS recovery', 'ACCOUNT_TRANSFERS.md':'Account transfers', 'MAIL_HOSTING.md':'Mail hosting', 'ACCOUNT_SECURITY.md':'Account security', 'BACKUP_SCHEDULING.md':'Backup scheduling', 'WEBSITE_ROUTING.md':'Website routing'})
CAPABILITY_STATUSES = re.findall(r'^\| VCP-.*?\| (Available|Partial|Planned) \|$', (SOURCE/'CAPABILITIES.md').read_text(), re.M)
CAPABILITY_COUNT = len(CAPABILITY_STATUSES)
VERSION = re.search(r'__version__ = "([^"]+)"', (SOURCE/'vectorcp/__init__.py').read_text())[1]
if ARCHIVE_NAME != 'VectorCP-'+VERSION+'-development-source.zip':
    parser.error('Use the development archive matching the current source version.')
import datetime
snapshot_date=re.search(r'^## '+re.escape(VERSION)+r' — (\d{1,2} \w+ \d{4})', (SOURCE/'CHANGELOG.md').read_text(),re.M)
if not snapshot_date:
    parser.error('The current source version needs a dated changelog entry.')
DATE_LABEL=snapshot_date[1]
DATE_ISO=datetime.datetime.strptime(DATE_LABEL,'%d %B %Y').date().isoformat()
if not (SOURCE/'README.md').is_file():
    parser.error('Pass --panel-source with a VectorCP source checkout.')
DIST.mkdir(parents=True, exist_ok=True)
(DIST / 'assets').mkdir(exist_ok=True)
(DIST / 'downloads').mkdir(exist_ok=True)
shutil.copyfile(args.panel_image, DIST / 'assets/panel-043-live.png')
shutil.copyfile(SOURCE / 'vectorcp/static/favicon.svg', DIST / 'assets/mark.svg')
shutil.copyfile(SOURCE/'assets/brand/vectorcp-wordmark.svg', DIST/'assets/wordmark.svg')
(DIST/'assets/brand').mkdir(exist_ok=True)
for brand_asset in (SOURCE/'assets/brand').glob('*.svg'):
    shutil.copyfile(brand_asset, DIST/'assets/brand'/brand_asset.name)
with zipfile.ZipFile(DIST/'downloads/VectorCP-brand-kit.zip', 'w', zipfile.ZIP_DEFLATED) as kit:
    for brand_asset in sorted((SOURCE/'assets/brand').glob('*.svg')):
        kit.writestr(zipfile.ZipInfo('VectorCP-brand-kit/'+brand_asset.name, (2026,1,1,0,0,0)), brand_asset.read_bytes())
    kit.writestr(zipfile.ZipInfo('VectorCP-brand-kit/BRANDING.md', (2026,1,1,0,0,0)), (SOURCE/'BRANDING.md').read_bytes())
    kit.writestr(zipfile.ZipInfo('VectorCP-brand-kit/LICENSE', (2026,1,1,0,0,0)), (SOURCE/'LICENSE').read_bytes())
for filename in ['VectorCP-0.4.2-source.zip', 'VectorCP-0.4.2-source.zip.sha256', 'VectorCP-0.4.3-mailboxes-development-source.zip', 'VectorCP-0.4.3-mailboxes-development-source.zip.sha256']:
    shutil.copyfile(MATERIAL / filename, DIST / 'downloads' / filename)
shutil.copyfile(args.development_archive, DIST/'downloads'/ARCHIVE_NAME)
(DIST/'downloads'/(ARCHIVE_NAME+'.sha256')).write_text(hashlib.sha256(args.development_archive.read_bytes()).hexdigest()+'  '+ARCHIVE_NAME+'\n')

GITHUB = 'https://github.com/SparkX-Digital/vectorcp'

def put(path, content):
    out = DIST / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content.strip() + '\n')

def inline(text):
    tokens = []
    def stash(value):
        tokens.append(value)
        return f'\x00{len(tokens)-1}\x00'
    text = re.sub(r'`([^`]+)`', lambda m: stash('<code>'+html.escape(m[1])+'</code>'), text)
    def link(m):
        label, url = m.groups()
        if url.endswith('.md') and not '://' in url:
            name = Path(url).stem.lower()
            url = '/docs/' if name == 'readme' else '/docs/'+name+'/'
        if not (url.startswith(('https://','/','#')) or url == 'mailto:'):
            return stash(html.escape(label))
        return stash('<a href="'+html.escape(url,quote=True)+'">'+html.escape(label)+'</a>')
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,text)
    text = html.escape(text)
    text = re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text)
    return re.sub(r'\x00(\d+)\x00',lambda m:tokens[int(m[1])],text)

def markdown(text, prefix="", heading_offset=1):
    anchors = {}
    lines = text.splitlines()
    result=[]
    i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        image = re.fullmatch(r'<img src="(assets/brand/[a-z0-9-]+\.svg)" alt="([^"]*)" width="(\d+)">', line)
        if image:
            result.append('<img class="brand-document" src="/'+image[1]+'" alt="'+html.escape(image[2],quote=True)+'" width="'+image[3]+'">');i+=1;continue
        if line.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                block.append(lines[i]);i+=1
            result.append('<pre><code>'+html.escape('\n'.join(block))+'</code></pre>');i+=1;continue
        h=re.match(r'^(#{1,6})\s+(.*)',line)
        if h:
            level=min(6,len(h[1])+heading_offset)
            anchor=prefix+re.sub(r'[^a-z0-9]+','-',h[2].lower()).strip('-')
            anchors[anchor]=anchors.get(anchor,0)+1
            if anchors[anchor]>1:anchor+='-'+str(anchors[anchor])
            result.append(f'<h{level} id="{anchor}">{inline(h[2])}</h{level}>');i+=1;continue
        if '|' in line and i+1<len(lines) and re.match(r'^\s*\|?\s*:?-{3}',lines[i+1]):
            cells=lambda value: [x.strip() for x in value.strip().strip('|').split('|')]
            header=cells(line);i+=2
            rows=[]
            while i<len(lines) and '|' in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]));i+=1
            result.append('<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+inline(x)+'</th>' for x in header)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>')
            continue
        bullet=re.match(r'^\s*(?:[-*]|\d+\.)\s+',line)
        if bullet:
            ordered=bool(re.match(r'^\s*\d+\.',line));tag='ol' if ordered else 'ul';items=[]
            while i<len(lines):
                item=re.match(r'^\s*(?:[-*]|\d+\.)\s+(.*)',lines[i])
                if not item:break
                parts=[item[1]];i+=1
                while i<len(lines) and lines[i].startswith('  ') and not re.match(r'^\s*(?:[-*]|\d+\.)\s+',lines[i]):
                    parts.append(lines[i].strip());i+=1
                items.append('<li>'+inline(' '.join(parts))+'</li>')
            result.append('<'+tag+'>'+''.join(items)+'</'+tag+'>');continue
        parts=[line];i+=1
        # Only a list beginning at 1 may interrupt an existing paragraph.
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#|```|[-*] |1\. )',lines[i]):
            parts.append(lines[i]);i+=1
        result.append('<p>'+inline(' '.join(parts))+'</p>')
    return '\n'.join(result)

def page(title,description,body,path='/',active=''):
    nav=''.join(f'<a href="{url}"'+(' aria-current="page"' if label.lower()==active else '')+f'>{label}</a>' for label,url in [('Features','/features/'),('Docs','/docs/'),('Roadmap','/roadmap/'),('Changelog','/changelog/')])
    schema={'@context':'https://schema.org','@type':'SoftwareApplication','name':'VectorCP','url':'https://vectorcp.net/','description':'Open-source hosting control panel for server owners, resellers and customers.','applicationCategory':'DeveloperApplication','operatingSystem':'AlmaLinux 9','softwareVersion':VERSION,'license':'https://opensource.org/license/mit','author':{'@type':'Organization','name':'SparkX Digital','url':'https://www.sparkxdigital.co.uk/'}}
    document=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · VectorCP</title><meta name="description" content="{html.escape(description,quote=True)}">
<link rel="canonical" href="https://vectorcp.net{path}"><link rel="icon" href="/assets/mark.svg" type="image/svg+xml">
<meta property="og:type" content="website"><meta property="og:title" content="{html.escape(title,quote=True)} · VectorCP"><meta property="og:description" content="{html.escape(description,quote=True)}"><meta property="og:url" content="https://vectorcp.net{path}"><meta property="og:image" content="https://vectorcp.net/assets/panel-043-live.png"><meta name="theme-color" content="#183e33">
<link rel="stylesheet" href="/assets/site.css"><script defer src="/assets/site.js"></script><script type="application/ld+json">{json.dumps(schema)}</script></head>
<body><a class="skip" href="#main">Skip to content</a><header class="site-header"><div class="wrap header-inner"><a class="brand" href="/" aria-label="VectorCP home"><img class="wordmark" src="/assets/wordmark.svg" width="158" height="34" alt="VectorCP"></a><button class="menu-toggle" aria-expanded="false" aria-controls="navigation" aria-label="Open navigation">Menu <span aria-hidden="true">☰</span></button><nav id="navigation" aria-label="Main navigation">{nav}<a class="source-link" href="{GITHUB}">GitHub <span aria-hidden="true">↗</span></a><a class="button small" href="/download/">Get VectorCP <span aria-hidden="true">↓</span></a></nav></div></header>
<main id="main">{body}</main><footer class="site-footer"><div class="wrap footer-top"><div><a class="brand" href="/"><img class="wordmark" src="/assets/wordmark.svg" width="158" height="34" alt="VectorCP"></a><p>Open-source hosting control.<br>Your hosting. Your control.</p></div><div class="footer-links"><a href="/docs/">Documentation</a><a href="/features/">Feature status</a><a href="/changelog/">Changelog</a><a href="/security/">Security</a><a href="{GITHUB}">Source code ↗</a></div></div><div class="wrap footer-bottom"><span>A <a href="https://www.sparkxdigital.co.uk/">SparkX Digital</a> project.</span><span>© 2026 VectorCP contributors · <a href="{GITHUB}/blob/main/LICENSE">MIT license</a></span></div></footer></body></html>'''
    put(('index.html' if path=='/' else path.strip('/')+'/index.html'),document)

page('Your hosting. Your control.','A self-hosted, open-source hosting panel for server owners, resellers and customers. Explore the features, documentation and development release.',f'''
<section class="hero"><div class="wrap hero-grid"><div class="hero-copy"><span class="eyebrow light"><span class="dot"></span> Open source. On your server.</span><h1>Your hosting.<br><em>Your control.</em></h1><p class="hero-lead">Websites, accounts and reseller hosting.<br>One panel. Source code you can make your own.</p><div class="actions"><a class="button lime" href="{GITHUB}">View on GitHub <span aria-hidden="true">↗</span></a><a class="text-link" href="/features/">Explore the features <span aria-hidden="true">→</span></a></div><p class="release-note"><span class="release-tag">v{VERSION} dev</span> {DATE_LABEL} <span aria-hidden="true">·</span> Development snapshot</p></div><figure class="product-shot"><div class="shot-top"><span class="window-dots" aria-hidden="true">● ● ●</span><span>VectorCP / Tools</span><span aria-hidden="true">↗</span></div><img src="/assets/panel-043-live.png" width="463" height="698" alt="VectorCP development Tools workspace with grouped account and website controls" fetchpriority="high"><figcaption>Actual interface · Development workspace</figcaption></figure></div><div class="hero-bottom wrap"><span>Self-hosted by design</span><span>Owners · Resellers · Customers</span><span>No activation fee</span></div></section>
<section class="section wrap introduction"><div><span class="eyebrow">The essentials, together</span><h2>A clearer place<br>to run your hosting.</h2></div><div><p class="large-copy">From a website's first files to a reseller's next customer, VectorCP brings everyday hosting work into one interface.</p><p>Built independently and released under MIT. Run it on your own dedicated Linux server, inspect the source and help shape what comes next.</p></div></section>
<section class="section wrap capabilities"><div class="section-title"><span class="eyebrow">In current development</span><a class="underlink" href="/features/">See the full feature status →</a></div><div class="capability-grid"><article><span class="feature-number">01 / HOST</span><h3>Websites that<br> have room to grow.</h3><p>Static sites, PHP, private databases, WordPress installation and domain HTTPS — managed from the same workspace.</p><a href="/features/#hosting">Website hosting →</a></article><article><span class="feature-number">02 / DELEGATE</span><h3>Your accounts.<br> Clear boundaries.</h3><p>Create customer and reseller plans, reserve resources and control what each account can manage.</p><a href="/features/#accounts">Plans and accounts →</a></article><article><span class="feature-number">03 / RECOVER</span><h3>Keep a copy.<br> Know what's happening.</h3><p>Schedule local website backups, inspect private databases and follow activity within each account's scope.</p><a href="/features/#recovery">Backups and activity →</a></article></div></section>
<section class="role-section"><div class="wrap role-grid"><div><span class="eyebrow">One panel, three roles</span><h2>The right workspace.<br>For every account.</h2><p>Delegation is part of the product, from the server owner to each customer's websites.</p></div><div class="role-selector"><div class="role-tabs" role="tablist" aria-label="Hosting roles"><button id="owner-tab" role="tab" aria-selected="true" aria-controls="role-owner" tabindex="0" data-role="owner">Owner</button><button id="reseller-tab" role="tab" aria-selected="false" aria-controls="role-reseller" tabindex="-1" data-role="reseller">Reseller</button><button id="customer-tab" role="tab" aria-selected="false" aria-controls="role-customer" tabindex="-1" data-role="customer">Customer</button></div><div class="role-panel" id="role-owner" role="tabpanel" aria-labelledby="owner-tab"><span class="role-symbol" aria-hidden="true">⌘</span><h3>The whole server, in view.</h3><p>Manage hosting plans, delegate reseller resources, create accounts and control service access. Owner locks and website holds take precedence.</p><ul><li>Customer and reseller packages</li><li>Account permissions and reservations</li><li>Server-wide jobs and activity</li></ul></div><div class="role-panel" id="role-reseller" role="tabpanel" aria-labelledby="reseller-tab" hidden><span class="role-symbol" aria-hidden="true">↗</span><h3>Your customers. Your workspace.</h3><p>Manage your own customers, websites and backups within the resources and permissions assigned by the server owner.</p><ul><li>Delegated customer management</li><li>Customer plans within your allocation</li><li>Scoped websites, files and backups</li></ul></div><div class="role-panel" id="role-customer" role="tabpanel" aria-labelledby="customer-tab" hidden><span class="role-symbol" aria-hidden="true">⊞</span><h3>Focus on your websites.</h3><p>Work with your own files, websites, applications and recovery copies without access to other customers' hosting data.</p><ul><li>Website and file management</li><li>PHP, databases and WordPress</li><li>Local website backup and restore</li></ul></div></div></div></section>
<section class="section wrap development"><div><span class="eyebrow">Built in the open</span><h2>See where it stands.<br>Help decide what's next.</h2></div><div><p>VectorCP is an early development project. The development snapshot adds optional mailboxes with encrypted SMTP/IMAP, portable website account transfers, account security, database administration and recovery controls. Webmail, mail filtering/signing and backups, broader migrations and DNSSEC remain open.</p><p>Every feature has a status. Verification notes explain what has been tested and where the limits are.</p><div class="actions"><a class="button" href="/roadmap/">Read the roadmap →</a><a class="underlink" href="/docs/contributing/">Contribute ↗</a></div></div></section>
<section class="closing wrap"><div><span class="eyebrow">Start with the source</span><h2>Hosting control.<br>Yours to build on.</h2></div><a class="button lime" href="/download/">Get VectorCP <span aria-hidden="true">↓</span></a></section>''')

features=[
('hosting','Static and PHP websites','Available','Nginx websites and customer-specific PHP-FPM services.'),
('hosting','Private databases','Available','A MariaDB instance per database-using customer, accessed through private Unix sockets.'),
('hosting','WordPress installation','Available','Official downloads and per-file checksum verification; fresh website required.'),
('hosting','Domain HTTPS','Available',"Let's Encrypt HTTP-01, DNS preflight and automatic renewal."),
('hosting','Redirects and error pages','Available','Domain redirects, HTTPS preferences and bounded custom error pages.'),
('accounts','Owner, reseller and customer roles','Available','Scoped accounts and delegated management, enforced by the agent.'),
('accounts','Plans and resource reservations','Available','Immutable packages and explicit assignment; existing volume resizing is not implemented.'),
('accounts','Bulk account operations','Available','Selected customer suspension and activation with per-account results.'),
('accounts','Customer isolation','Limited','Distinct identities, fixed storage volumes, namespaces and resource controls. Shared kernel; see documented limits.'),
('accounts','MFA and session controls','Available','Authenticator codes, recovery codes, password changes and scoped session revocation.'),
('recovery','File manager','Available','Verified bounded transfers, copy, move, search, permissions, trash and safe archive extraction.'),
('recovery','Local backup and restore','Available','Bounded full website copies with files and private SQL, with restore checks.'),
('recovery','Background jobs and activity','Available','Scoped progress and activity; interrupted jobs fail visibly.'),
('recovery','Scheduled local backups','Available','Daily, weekly or monthly UTC schedules, job history and retention after successful creation.'),
('recovery','Off-server backups','Limited','Owner-configured SFTP destinations with pinned keys and verified copies; independent recovery acceptance remains open.'),
('hosting','Database administration','Limited','Tables and paginated rows, scoped users and grants, bounded SQL import and export. See documented limits.'),
('dns','DNS editor and zone export','Limited','A/AAAA/CNAME/MX/TXT/NS/CAA/SRV editing with private preview, snapshots, recovery and ownership checks.'),
('dns','Public authoritative DNS','Limited','Explicit owner profile and per-zone activation. Private by default; independent delegation and redundancy acceptance remain open.'),
('dns','DNSSEC','Planned','Signing, rollover and parent DS publication remain to be built.'),
('mail','Mailboxes and email','Limited','Optional native mailboxes, SMTP/IMAPS, quotas and access recovery. Webmail, aliases, filtering, signing, mail backup and Internet delivery acceptance remain open.'),
('developer','Shell, FTP, cron and Git deployment','Planned','Controlled access and developer workflows are future work.'),
('platform','Portable account transfers','Limited','Versioned exports, verified resumable uploads, empty-target inspection and suspended import of files and primary SQL. Mail, extra SQL users and remote migration remain open.'),
('platform','Additional platforms and full-machine recovery','Planned','Dedicated AlmaLinux 9 x86-64 is exercised; other platforms and full-machine recovery remain open.'),
('platform','Signed updates and independent security review','Planned','Independent audit, wider capacity and complete recovery validation remain pending.')]
rows=''.join(f'<tr data-status="{status.lower()}" id="{area}"' + ('>' if index==next(i for i,v in enumerate(features) if v[0]==area) else f' data-area="{area}">')+f'<td><strong>{name}</strong></td><td><span class="status {status.lower()}">{status}</span></td><td>{detail}</td></tr>' for index,(area,name,status,detail) in enumerate(features))
# IDs identify sections once, rather than repeating a category's anchor.
seen=set()
def unique_id(m):
    name=m[1]
    if name in seen:return ''
    seen.add(name);return ' id="'+name+'"'
rows=re.sub(r' id="([^"]+)"',unique_id,rows)
page('Feature status','What works in VectorCP today, what has limits and what remains planned.',f'''<section class="page-hero wrap"><span class="eyebrow">An honest feature map</span><h1>Know what you're<br>working with.</h1><p>Development snapshot {VERSION} adds working hosting and management tools. Here is what is available, what has limits and what is still planned.</p></section><section class="wrap section feature-status"><div class="filter-bar" role="group" aria-label="Filter features by status"><button aria-pressed="true" data-filter="all">All features</button><button aria-pressed="false" data-filter="available">Available</button><button aria-pressed="false" data-filter="limited">Limited</button><button aria-pressed="false" data-filter="planned">Planned</button></div><p id="feature-count" class="muted" aria-live="polite">{len(features)} capability groups shown</p><div class="table-scroll"><table class="feature-table"><thead><tr><th>Capability</th><th>Status</th><th>What this means</th></tr></thead><tbody>{rows}</tbody></table></div><div class="note"><strong>Read the limits before deploying.</strong><p>This is an early development release. The complete product is still being built. The <a href="/docs/capabilities/">capability catalog</a> tracks {CAPABILITY_COUNT} customer and server workflows with individual statuses: {CAPABILITY_STATUSES.count('Available')} available, {CAPABILITY_STATUSES.count('Partial')} partial and {CAPABILITY_STATUSES.count('Planned')} planned. Review the <a href="/docs/features/">detailed feature map</a> and <a href="/docs/verification/">verification notes</a> for the exact scope and checks.</p></div></section>''','/features/','features')

page('Roadmap','VectorCP development priorities, capability gates and contribution guidance.',f'''<section class="page-hero wrap"><span class="eyebrow">The direction ahead</span><h1>Built step by step.<br>In the open.</h1><p>A complete hosting control panel is the goal. Working services, tested boundaries and recovery paths are how we get there.</p></section><section class="wrap docs-layout"><aside class="docs-sidebar"><span class="eyebrow">Development</span><a href="/features/">Current feature status</a><a href="/docs/contributing/">Contribution guide</a><a href="{GITHUB}/issues">Issues and proposals ↗</a></aside><article class="prose">{markdown((SOURCE/'ROADMAP.md').read_text())}</article></section>''','/roadmap/','roadmap')

for filename in DOCS:
    title=DOCS[filename]
    path='/docs/' if filename=='README.md' else '/docs/'+Path(filename).stem.lower()+'/'
    links=''.join(f'<a href="{url}"'+(' aria-current="page"' if url==path else '')+f'>{label}</a>' for label,url in [('Getting started','/docs/'),('Architecture','/docs/architecture/'),('Product specification','/docs/product/'),('Capability catalog','/docs/capabilities/'),('Feature coverage','/docs/features/'),('File manager','/docs/file_manager/'),('Account security','/docs/account_security/'),('Database administration','/docs/database_admin/'),('Backup scheduling','/docs/backup_scheduling/'),('Mail hosting','/docs/mail_hosting/'),('Public DNS','/docs/public_dns/'),('DNS recovery','/docs/dns_recovery/'),('Account transfers','/docs/account_transfers/'),('Website routing','/docs/website_routing/'),('Bulk operations','/docs/bulk_operations/'),('Linux acceptance','/docs/linux_acceptance/'),('Verification','/docs/verification/'),('Contributing','/docs/contributing/'),('Changelog','/changelog/'),('Brand assets','/docs/branding/'),('Release process','/docs/releasing/'),('Security policy','/docs/security/')])
    page(title,'VectorCP '+title.lower()+': current project guidance, supported behavior and documented limits.',f'''<section class="docs-heading wrap"><span class="eyebrow">VectorCP documentation</span><h1>{title}</h1><p>Development snapshot {VERSION} · Updated {DATE_LABEL} · AlmaLinux 9 x86-64</p><form class="docs-search" role="search" aria-label="Documentation search"><label for="docs-query">Search documentation</label><div class="search-controls"><input id="docs-query" name="q" type="search" placeholder="Try mail aliases, backups or installation" maxlength="100" autocomplete="off"><button class="button small" type="submit">Search</button></div><p id="docs-search-status" role="status" aria-live="polite"></p><ul id="docs-search-results" hidden></ul></form><noscript><p class="muted">Browse the guides below. Documentation search is available when JavaScript is enabled.</p></noscript></section><section class="wrap docs-layout"><aside class="docs-sidebar"><button class="docs-menu-toggle" aria-expanded="false" aria-controls="docs-menu-links" hidden>Browse documentation <span aria-hidden="true">⌄</span></button><nav id="docs-menu-links" class="docs-menu-links" aria-label="Documentation">{links}<a href="{GITHUB}/blob/main/{filename}">View source ↗</a></nav></aside><article class="prose">{markdown((SOURCE/filename).read_text())}{'<p><a class="button" href="/downloads/VectorCP-brand-kit.zip">Download the brand kit ↓</a></p>' if filename=='BRANDING.md' else ''}</article></section>''',path,'docs')

checksum=hashlib.sha256((DIST/'downloads'/ARCHIVE_NAME).read_bytes()).hexdigest()
release_sections=re.split(r'^## ',(SOURCE/'CHANGELOG.md').read_text(),flags=re.M)[1:]
cards=[]
for section in release_sections:
    title,_,body=section.partition('\n')
    if title.strip()=='Unreleased':continue
    label,_,description=title.partition(' — ')
    anchor='version-'+re.sub(r'[^a-z0-9]+','-',label.lower()).strip('-')
    date=re.search(r'(\d{1,2}) (\w+) (\d{4})',description)
    date_html=html.escape(description)
    if date:
        import datetime
        iso=datetime.datetime.strptime(date.group(0),'%d %B %Y').date().isoformat()
        date_html='<time datetime="'+iso+'">'+html.escape(description)+'</time>'
    content=markdown(body,prefix=anchor+'-',heading_offset=0)
    if not cards:
        cards.append('<article class="release-card current-release" id="'+anchor+'"><div class="release-meta"><span class="status limited">Latest development snapshot</span><h2>'+html.escape(label)+'</h2><p>'+date_html+'</p></div><div class="prose">'+content+'</div></article>')
    else:
        cards.append('<details class="release-card" id="'+anchor+'"><summary><span><strong>'+html.escape(label)+'</strong><span class="release-date">'+date_html+'</span></span><span class="release-expand" aria-hidden="true">+</span></summary><div class="prose">'+content+'</div></details>')
page('Changelog','VectorCP version history with dated development snapshots, implemented changes and known limits.', '<section class="page-hero wrap"><span class="eyebrow">Product updates</span><h1>What’s new<br>in VectorCP.</h1><p>Every update, with its version, date and the work behind it.</p><div class="actions"><a class="button" href="/download/">Get the latest snapshot ↓</a><a class="underlink" href="'+GITHUB+'/commits/main/">Source history ↗</a></div></section><section class="wrap release-history"><div class="note"><strong>Development snapshots</strong><p>VectorCP is in active development. These entries record verified source updates; they do not mark stable production releases. Earlier builds sharing version 0.4.3 have dated snapshot identifiers. Original downloads stay unchanged.</p></div>'+''.join(cards)+'</section>', '/changelog/','changelog')

page('Download VectorCP',f'Download the VectorCP {VERSION} development source snapshot and SHA-256 checksum. Read the installation requirements before deploying.',f'''<section class="page-hero wrap"><span class="eyebrow">MIT-licensed source</span><h1>Start with<br>VectorCP.</h1><p>Explore the source, try it on a dedicated test server and help build what comes next.</p></section><section class="wrap section download-grid"><article class="download-card"><span class="status limited">Unreleased development snapshot</span><h2>VectorCP <span>{VERSION}</span></h2><p>Version {VERSION} · <time datetime="{DATE_ISO}">{DATE_LABEL}</time>. Development source snapshot. Native AlmaLinux 9 x86-64 installation, hosting, upgrade and rollback checks have passed. This is an unreleased integration snapshot from merged source, not a new stable release. Wider production acceptance remains pending. Includes the application, service templates, installers, tests and documentation.</p><a class="button" href="/downloads/{ARCHIVE_NAME}" download>Download source ZIP ↓</a><a class="underlink" href="/downloads/{ARCHIVE_NAME}.sha256" download>SHA-256 checksum</a><p><a class="underlink" href="/changelog/">Read the version history and changes →</a></p><p><a class="underlink" href="/downloads/VectorCP-0.4.2-source.zip">Previous frozen snapshot: 0.4.2</a></p><details><summary>Verify your download</summary><p>Compare the archive's SHA-256 with this value:</p><pre class="checksum"><code>{checksum}</code></pre><p>The archive is unsigned. The checksum checks file integrity; it is not a publisher signature.</p></details></article><div class="prose"><h2>Before you install</h2><ul><li>A dedicated AlmaLinux 9 server. The x86-64 target has been exercised.</li><li>Root access and a clean hosting environment. The installer checks for an existing hosting stack.</li><li>Read the documented storage, workload and backup limits.</li><li>Use a test server while the product is in early development.</li></ul><p>The initial installer defaults to a read-only preflight. Follow the full guide for installation, owner setup and public HTTPS.</p><a class="button outline" href="/docs/#installation">Read the installation guide →</a><p class="muted">The public repository may contain documentation and metadata updates beyond this frozen snapshot. Refer to each artifact's own version and verification notes.</p></div></section>''','/download/')

page('Security','VectorCP security boundaries, development limitations and responsible reporting guidance.',f'''<section class="page-hero wrap"><span class="eyebrow">Security and reporting</span><h1>Clear boundaries.<br>Visible limits.</h1><p>VectorCP is early software. An independent security audit and production support commitment have not been established.</p></section><section class="wrap section prose narrow"><h2>Report a suspected vulnerability privately</h2><p>Do not put credentials, customer data or exploit details for a live installation in public issues. Consult the <a href="{GITHUB}/security/policy">repository security policy</a> for the current private reporting route and availability.</p><h2>How the current panel is separated</h2><p>An unprivileged frontend sends bounded requests to a local agent. Customer workloads have distinct Unix identities, fixed storage volumes, private mount namespaces and resource controls. This is shared-kernel isolation.</p><h2>What still needs work</h2><p>Email account recovery, secret encryption, signed updates, broader service-helper review, hostile workload testing and clean recovery drills remain planned work. Read the <a href="/docs/security/">full security policy</a> and <a href="/docs/verification/">verification notes</a> before choosing the panel for customer workloads.</p><h2>Ordinary bugs and improvements</h2><p>Use <a href="{GITHUB}/issues">GitHub Issues</a> for non-security problems and proposals, with synthetic examples and redacted evidence.</p></section>''','/security/')

page('Page not found','The requested VectorCP page could not be found.','''<section class="page-hero wrap error-page"><span class="eyebrow">404 / Page not found</span><h1>Let's get you<br>back on track.</h1><p>This page may have moved, or the address may be incomplete.</p><div class="actions"><a class="button" href="/">Go to the homepage →</a><a class="underlink" href="/docs/">Browse the docs</a></div></section>''','/404/')
shutil.copyfile(DIST/'404/index.html',DIST/'404.html')

put('assets/site.css',r'''
:root{--ink:#173e33;--green:#315c4b;--lime:#d9ef98;--paper:#f7f8f2;--line:#dce2d8;--muted:#66756c;--radius:15px}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:100px}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;-webkit-font-smoothing:antialiased}a{color:inherit;text-underline-offset:4px}button{font:inherit;cursor:pointer}img{max-width:100%;height:auto}button,a{-webkit-tap-highlight-color:transparent}a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #78a646;outline-offset:5px}h1,h2,h3,p,figure{margin:0}h1,h2,h3{line-height:1.08;letter-spacing:-.055em}h1{font-size:clamp(49px,6.7vw,90px);font-weight:650}h2{font-size:clamp(32px,4vw,51px);font-weight:600}h3{font-size:29px;font-weight:600}p{margin-top:20px}p:first-child{margin-top:0}.wrap{width:min(1180px,calc(100% - 88px));margin-inline:auto}.site-header{height:87px;background:rgba(247,248,242,.98);position:sticky;top:0;z-index:10;border-bottom:1px solid var(--line)}.header-inner{display:flex;height:100%;align-items:center;justify-content:space-between}.brand{display:inline-flex;align-items:center;color:var(--ink);font-size:26px;letter-spacing:-1.4px;text-decoration:none;font-weight:760;white-space:nowrap}.brand img{margin-right:8px}.brand span{font-weight:400}.site-header nav{display:flex;align-items:center;gap:31px}.site-header nav>a{font-size:14px;text-decoration:none;font-weight:530}.site-header nav>a[aria-current]{text-decoration:underline;text-decoration-thickness:2px}.source-link{margin-left:16px}.button{display:inline-flex;align-items:center;justify-content:center;gap:29px;padding:15px 24px;color:white;background:var(--green);border:1px solid var(--green);border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;line-height:1.5;white-space:nowrap;transition:background .16s,transform .16s}.button:hover{background:var(--ink);transform:translateY(-1px)}.button.small{padding:11px 18px;gap:15px}.button.lime{color:var(--ink);background:var(--lime);border-color:var(--lime)}.button.lime:hover{background:#e6f7bd}.button.outline{background:transparent;color:var(--ink);border-color:var(--line);white-space:normal}.actions{display:flex;gap:26px;align-items:center;margin-top:33px}.text-link,.underlink{font-size:14px;font-weight:550}.text-link{color:white;text-decoration:none}.text-link:hover,.underlink:hover{text-decoration:underline}.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:11px;line-height:1.5;font-weight:650;display:block;margin-bottom:24px}.hero{background:var(--ink);color:white;overflow:hidden}.hero-grid{display:grid;grid-template-columns:1.25fr .82fr;gap:70px;align-items:center;padding-top:67px;padding-bottom:52px}.hero .eyebrow{color:#d5e5c4;display:flex;gap:9px;align-items:center}.dot{width:6px;height:6px;background:var(--lime);border-radius:50%;display:inline-block}.hero h1{font-size:clamp(52px,6.3vw,84px);letter-spacing:-.055em;font-weight:580}.hero h1 em{color:var(--lime);font-style:normal}.hero-lead{font-size:19px;line-height:1.6;color:#d5dfd9;margin-top:29px;letter-spacing:-.025em}.release-note{display:flex;align-items:center;gap:10px;font-size:12px;color:#b8cdc2;margin-top:28px}.release-tag{border:1px solid #678477;border-radius:4px;padding:1px 7px;color:#e2eddc}.product-shot{width:100%;max-width:385px;justify-self:end;background:#edf2e7;padding:9px 9px 0;border:1px solid #819585;border-radius:14px;box-shadow:0 25px 80px #061f2366;transform:rotate(1deg)}.shot-top{height:31px;display:flex;align-items:center;justify-content:space-between;font-size:9px;color:#536e5c;padding:0 6px 8px;letter-spacing:.02em}.window-dots{letter-spacing:3px;font-size:8px;color:#8aa18b}.product-shot>img{display:block;width:100%;border-radius:5px 5px 0 0;max-height:470px;object-fit:cover;object-position:top;border:1px solid #ccd5c5}.product-shot figcaption{font-size:9px;color:#657664;text-align:center;letter-spacing:.03em;padding:9px}.hero-bottom{display:flex;justify-content:space-between;gap:20px;border-top:1px solid #416052;padding-top:21px;padding-bottom:24px;color:#bccfc4;font-size:11px;letter-spacing:.03em}.section{padding-top:88px;padding-bottom:88px}.introduction,.development{display:grid;grid-template-columns:1fr 1fr;gap:100px}.introduction p,.development p{color:var(--muted)}.introduction .large-copy{font-size:22px;letter-spacing:-.035em;color:var(--ink);line-height:1.5}.capabilities{padding-top:10px}.section-title{display:flex;align-items:center;justify-content:space-between;padding-bottom:22px;border-bottom:1px solid var(--line)}.section-title .eyebrow{margin:0}.capability-grid{display:grid;grid-template-columns:repeat(3,1fr)}.capability-grid article{padding:35px 32px 3px;border-right:1px solid var(--line)}.capability-grid article:first-child{padding-left:0}.capability-grid article:last-child{padding-right:0;border:0}.feature-number{display:block;font-size:10px;letter-spacing:.13em;color:var(--muted);margin-bottom:29px}.capability-grid p{font-size:14px;color:var(--muted);line-height:1.8;min-height:104px}.capability-grid a{display:inline-block;font-size:12px;margin-top:28px;font-weight:600;text-decoration:none}.capability-grid a:hover{text-decoration:underline}.role-section{background:#e9eee1;border-block:1px solid #dae2d0;padding-block:79px}.role-grid{display:grid;grid-template-columns:1fr 1fr;gap:100px;align-items:center}.role-grid>div>p{font-size:16px;color:var(--muted);max-width:400px}.role-selector{border-radius:var(--radius);background:var(--paper);border:1px solid #d5dfce;overflow:hidden}.role-tabs{display:flex;padding:10px;gap:5px;border-bottom:1px solid var(--line)}.role-tabs button{flex:1;border:0;border-radius:6px;font-size:12px;padding:11px 7px;color:var(--muted);background:transparent}.role-tabs button[aria-selected=true]{background:var(--ink);color:#fff}.role-panel{padding:29px 34px 30px}.role-panel[hidden]{display:none}.role-symbol{font-size:29px;line-height:1;display:inline-flex;margin-bottom:20px;color:#5c7a45}.role-panel h3{font-size:26px}.role-panel p{font-size:14px;color:var(--muted)}.role-panel ul{padding:0;list-style:none;font-size:12px;margin-top:24px;line-height:2.3}.role-panel li:before{content:'↳';padding-right:10px;color:#719457}.development .actions{gap:22px}.closing{background:var(--ink);color:#fff;border-radius:var(--radius);padding:48px 55px;display:flex;justify-content:space-between;align-items:center;margin-top:10px;margin-bottom:90px;gap:25px}.closing .eyebrow{color:#c7d8b9}.closing h2{font-size:44px}.site-footer{padding-block:43px 22px;border-top:1px solid var(--line);background:#eef1e8}.footer-top{display:flex;justify-content:space-between;gap:40px}.footer-top p{font-size:12px;color:var(--muted);line-height:1.8;margin-top:13px}.footer-links{display:grid;grid-template-columns:1fr 1fr;gap:15px 40px;align-content:start;padding-top:10px}.footer-links a{font-size:12px;text-decoration:none}.footer-links a:hover{text-decoration:underline}.footer-bottom{margin-top:39px;border-top:1px solid #d8dfd1;padding-top:20px;display:flex;justify-content:space-between;font-size:10px;color:var(--muted);gap:20px}.footer-bottom a{text-decoration:none}.page-hero{padding-block:77px 53px}.page-hero h1{font-size:clamp(48px,6vw,74px)}.page-hero>p{font-size:18px;line-height:1.7;color:var(--muted);max-width:640px;letter-spacing:-.02em}.feature-status{padding-top:17px}.filter-bar{display:flex;flex-wrap:wrap;gap:9px}.filter-bar button{padding:8px 18px;background:none;border:1px solid var(--line);border-radius:6px;color:var(--ink);font-size:12px}.filter-bar button[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:white}.muted{color:var(--muted);font-size:13px}.table-scroll{overflow:auto;border:1px solid var(--line);border-radius:9px;margin-top:20px}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.7;text-align:left;background:#fcfcf8}th,td{padding:18px 20px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);background:#eaf0e3}tr:last-child td{border:0}tr[hidden]{display:none}.feature-table td:first-child{width:29%}.feature-table td:nth-child(2){width:17%}.feature-table td:last-child{color:var(--muted)}.status{font-size:10px;letter-spacing:.02em;font-weight:600;border-radius:4px;padding:4px 8px;display:inline-block;white-space:nowrap}.available{background:#e1edcf;color:#3a5a23}.limited{background:#f0ead4;color:#736137}.planned{background:#e8ece8;color:#68736b}.note{border-left:3px solid #7e9d5a;padding:19px 27px;background:#eef3e6;margin-top:34px;font-size:14px}.note p{color:var(--muted);margin-top:6px}.docs-heading{padding-top:57px;padding-bottom:37px;border-bottom:1px solid var(--line)}.docs-heading h1{font-size:53px}.docs-heading p{font-size:13px;color:var(--muted)}.docs-layout{display:grid;grid-template-columns:210px minmax(0,1fr);gap:65px;padding-block:45px 90px}.docs-sidebar{display:flex;flex-direction:column;gap:13px;font-size:12px;position:sticky;top:124px;align-self:start}.docs-sidebar a{text-decoration:none;color:var(--muted)}.docs-sidebar a[aria-current]{color:var(--ink);font-weight:650}.docs-sidebar .eyebrow{margin-bottom:4px}.prose{max-width:790px;font-size:15px;color:#465d50;min-width:0}.prose h2,.prose h3,.prose h4{color:var(--ink);letter-spacing:-.035em;line-height:1.2;margin-top:39px;margin-bottom:17px;scroll-margin-top:120px}.prose h2{font-size:31px}.prose h2:first-child{margin-top:0}.prose h3{font-size:24px}.prose h4{font-size:19px}.prose p{margin-top:15px}.prose ul,.prose ol{padding-left:23px}.prose li{margin-bottom:12px}.prose code{font-size:.86em;overflow-wrap:anywhere;color:var(--ink);background:#e9eee2;border-radius:4px;padding:2px 5px}.prose pre{background:#1e4035;color:#e1edda;border-radius:8px;padding:20px 22px;overflow:auto;line-height:1.65;font-size:12px}.prose pre code{background:none;padding:0;color:inherit;overflow-wrap:normal}.prose table{font-size:12px;min-width:560px}.narrow{max-width:790px;padding-top:10px}.download-grid{display:grid;grid-template-columns:1fr 1fr;gap:75px;padding-top:8px}.download-card{background:#edf2e5;border:1px solid var(--line);border-radius:var(--radius);padding:34px;align-self:start}.download-card h2{font-size:35px;margin-top:25px}.download-card h2 span{font-weight:400;color:#709058}.download-card p{font-size:14px;color:var(--muted)}.download-card .button{margin-top:27px}.download-card>.underlink{display:block;margin-top:19px;font-size:12px}.download-card details{border-top:1px solid #d1dcc5;margin-top:27px;padding-top:18px;font-size:12px}.download-card summary{cursor:pointer;font-weight:600}.download-card details p{font-size:12px}.checksum{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;line-height:1.8;padding:14px;background:#f9fbf3;border-radius:5px;color:var(--ink)}.download-grid>.prose{padding-top:8px}.download-grid>.prose h2{font-size:29px}.error-page{min-height:60vh}.menu-toggle{display:none}.skip{position:absolute;left:16px;top:-60px;background:var(--lime);padding:8px 17px;z-index:100}.skip:focus{top:10px}
@media(min-width:1400px){.hero-grid{gap:110px}.product-shot{max-width:405px}.product-shot>img{max-height:500px}}
@media(max-width:1000px){.wrap{width:calc(100% - 54px)}.site-header nav{gap:18px}.source-link{margin-left:0}.hero-grid{gap:35px}.hero .actions{gap:18px;flex-wrap:wrap}.hero h1{font-size:62px}.introduction,.development,.role-grid{gap:45px}.capability-grid article{padding-inline:23px}.capability-grid p{min-height:155px}.docs-layout{gap:35px;grid-template-columns:170px minmax(0,1fr)}.download-grid{gap:35px}.role-panel{padding-inline:25px}}
@media(max-width:740px){.wrap{width:calc(100% - 40px)}.site-header{height:72px}.brand{font-size:24px}.menu-toggle{display:flex;gap:10px;border:1px solid var(--line);padding:6px 11px;border-radius:5px;background:transparent;color:var(--ink);font-size:12px}.site-header nav{display:none;position:absolute;top:71px;left:0;right:0;padding:22px;background:var(--paper);border-bottom:1px solid var(--line);box-shadow:0 10px 18px #213d3310;gap:22px;align-items:stretch}.site-header nav.open{display:flex;flex-direction:column}.site-header nav>a{padding-inline:9px}.hero-grid{grid-template-columns:1fr;padding-top:46px;padding-bottom:36px;gap:42px}.hero h1{font-size:clamp(48px,10vw,74px)}.hero-lead{font-size:17px}.hero .actions{gap:20px;flex-wrap:nowrap}.hero .button{padding:14px 18px;gap:18px}.hero .text-link{font-size:12px}.product-shot{justify-self:center;max-width:350px;transform:none}.product-shot>img{max-height:355px}.hero-bottom{gap:8px;font-size:9px;flex-wrap:wrap}.hero-bottom span:last-child{display:none}.section{padding-block:55px}.introduction,.development,.role-grid{grid-template-columns:1fr;gap:30px}.eyebrow{margin-bottom:18px}.introduction .large-copy{font-size:20px}.capabilities{padding-top:0}.section-title{align-items:start;gap:20px}.section-title .underlink{font-size:11px;max-width:125px}.capability-grid{grid-template-columns:1fr}.capability-grid article,.capability-grid article:first-child,.capability-grid article:last-child{padding:28px 0;border-right:0;border-bottom:1px solid var(--line)}.capability-grid article:last-child{border:0;padding-bottom:0}.capability-grid p{min-height:0;font-size:14px;max-width:460px}.feature-number{margin-bottom:18px}.capability-grid a{margin-top:18px}.capability-grid h3 br{display:none}.role-section{padding-block:52px}.role-panel{padding:25px}.closing{padding:30px;display:block;margin-top:0;margin-bottom:55px}.closing .button{margin-top:26px}.closing h2{font-size:37px}.footer-top{display:block}.footer-links{margin-top:25px;grid-template-columns:1fr 1fr;gap:14px}.footer-bottom{display:block;margin-top:25px}.footer-bottom span{display:block}.footer-bottom span+span{margin-top:8px}.page-hero{padding-top:48px;padding-bottom:35px}.page-hero h1{font-size:48px}.page-hero>p{font-size:16px}.feature-status{padding-top:5px}.feature-table{min-width:610px}th,td{padding:15px}.filter-bar{gap:7px}.filter-bar button{font-size:11px;padding:7px 12px}.note{padding:17px 19px}.docs-layout{display:block;padding-top:25px;padding-bottom:55px}.docs-sidebar{position:static;flex-direction:row;flex-wrap:wrap;gap:10px 19px;border-bottom:1px solid var(--line);padding-bottom:23px;margin-bottom:28px}.docs-sidebar .eyebrow{width:100%}.docs-heading{padding-top:38px;padding-bottom:24px}.docs-heading h1{font-size:41px}.prose{font-size:14px}.prose h2{font-size:27px}.prose h3{font-size:23px}.prose pre{font-size:11px;padding:16px}.download-grid{grid-template-columns:1fr;gap:32px;padding-top:0}.download-card{padding:26px}.download-card h2{font-size:32px}.narrow{padding-top:0}.development .actions{flex-wrap:wrap}}
.brand img.wordmark{width:158px;height:auto;display:block}.prose .brand-document{width:340px;max-width:100%;height:auto;display:block;margin:18px 0 28px}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*:before,*:after{transition:none!important}}
''')

put('assets/site.css',(DIST/'assets/site.css').read_text()+r'''
/* Shared controls and documentation/release patterns. */
html:not(.js) .docs-search{display:none}
@media(max-width:1000px){html:not(.js) .header-inner{flex-wrap:wrap}html:not(.js) .menu-toggle{display:none}html:not(.js) .site-header nav{display:flex;position:static;flex-wrap:wrap;flex-direction:row;width:100%;padding:12px 0;box-shadow:none;border:0;gap:5px}html:not(.js) .site-header nav a{font-size:13px}}
button,input,select{font:inherit}button,a,input{touch-action:manipulation}
.button,.filter-bar button,.role-tabs button{min-height:40px;display:inline-flex;align-items:center;justify-content:center}
:focus-visible{outline:3px solid #426c32;outline-offset:4px}
.docs-menu-links{display:flex;flex-direction:column;gap:2px;max-height:calc(100vh - 160px);overflow-y:auto;padding:2px 8px 6px 2px}
.docs-menu-links a{display:block;padding:8px 10px;border-radius:5px;font-size:13px;line-height:1.45}
.docs-menu-links a:hover{color:var(--ink);background:#e9eee2}.docs-menu-links a[aria-current=page]{background:#e4ecd9;color:var(--ink)}
.docs-menu-toggle{display:none}.docs-search{max-width:650px;margin-top:25px}.docs-search label{display:block;font-size:12px;font-weight:650;color:var(--ink);margin-bottom:8px}
.search-controls{display:flex;gap:9px}.search-controls input{width:100%;min-width:0;min-height:44px;border:1px solid #a7b7a7;border-radius:6px;padding:10px 13px;background:#fff;color:var(--ink);font-size:14px}
.search-controls .button{flex-shrink:0;min-height:44px;border:0;cursor:pointer}
#docs-search-status{margin-top:9px;font-size:12px;min-height:0}
#docs-search-results{list-style:none;padding:0;margin:12px 0 0;border:1px solid var(--line);border-radius:8px;background:#fff;overflow:hidden}
#docs-search-results[hidden]{display:none}#docs-search-results li+li{border-top:1px solid var(--line)}
#docs-search-results a{display:block;padding:14px 17px;text-decoration:none}#docs-search-results a:hover{background:#edf2e5}
#docs-search-results strong{display:block;color:var(--ink);font-size:14px}#docs-search-results span{display:block;font-size:12px;color:var(--muted);margin-top:4px;line-height:1.65}
.release-history{padding-bottom:80px;max-width:1000px}.release-history>.note{margin:0 0 35px}.release-card{border:1px solid var(--line);border-radius:10px;background:#fcfcf8;margin-bottom:16px;overflow:hidden;scroll-margin-top:110px}
.current-release{border-color:#9aac8e}.release-meta{padding:30px 36px;background:#eaf0e1;border-bottom:1px solid var(--line)}.release-meta h2{font-size:39px;margin:17px 0 10px}.release-meta p{font-size:13px;color:var(--muted);margin:0}
.release-card>.prose{padding:25px 36px 32px;max-width:none}.release-card>.prose h4{font-size:21px}.release-card>.prose h4:first-child{margin-top:0}
.release-card summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:23px 30px;cursor:pointer}.release-card summary::-webkit-details-marker{display:none}
.release-card summary strong{font-size:20px;letter-spacing:-.025em;overflow-wrap:anywhere}.release-date{display:block;font-size:12px;color:var(--muted);margin-top:6px;line-height:1.65}.release-expand{font-size:25px;font-weight:400;line-height:1;color:#587044}.release-card[open] .release-expand{transform:rotate(45deg)}.release-card summary:hover{background:#edf2e5}
.prose h5,.prose h6{font-size:17px;color:var(--ink);margin-block:25px 12px}.prose pre{max-width:100%}.prose :target{scroll-margin-top:120px}
@media(max-width:1000px){.header-inner{position:relative}.menu-toggle{display:block;min-height:44px}.site-header nav{display:none;position:absolute;top:calc(100% + 1px);left:0;right:0;padding:15px 25px 22px;background:var(--paper);border:1px solid var(--line);border-radius:0 0 8px 8px;box-shadow:0 12px 18px #183e3310}.site-header nav.open{display:flex;flex-direction:column;align-items:stretch;gap:4px}.site-header nav a{padding:12px;min-height:44px}.site-header nav .button{margin-top:8px}.docs-layout{gap:35px;grid-template-columns:190px minmax(0,1fr)}}
@media(max-width:780px){.button,.filter-bar button,.role-tabs button{min-height:44px}.docs-layout{display:block}.docs-sidebar{display:block;margin-bottom:25px;padding-bottom:18px}.docs-menu-links{max-height:none;padding:10px 0 0;gap:2px}.docs-menu-links a{padding:12px 10px;min-height:44px;font-size:14px}.js .docs-menu-links{display:none}.js .docs-menu-links.open{display:flex}.docs-menu-toggle:not([hidden]){display:flex;align-items:center;justify-content:space-between;width:100%;padding:13px 15px;background:#edf2e5;border:1px solid var(--line);border-radius:6px;color:var(--ink);font-size:14px;min-height:46px}.docs-heading h1{overflow-wrap:anywhere}.docs-heading{padding-top:32px}.docs-search{margin-top:22px}.search-controls{gap:7px}.search-controls .button{padding-inline:15px}.search-controls input{font-size:16px}.release-history{padding-bottom:45px}.release-meta{padding:24px}.release-meta h2{font-size:34px}.release-card>.prose{padding:20px 24px 27px}.release-card summary{padding:20px 22px}.release-card summary strong{font-size:18px}.release-date{font-size:12px}.page-hero .actions{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
''')

put('assets/site.js',r'''
const menu = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
menu?.addEventListener('click', () => {
  const open = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(open));
  menu.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  navigation.classList.toggle('open', open);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') {
    menu.click(); menu.focus();
  }
});
const tabs = [...document.querySelectorAll('[data-role]')];
function activateRole(button) {
  for (const tab of tabs) {
    const selected = tab === button;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
  }
}
for (const [index, tab] of tabs.entries()) {
  tab.addEventListener('click', () => activateRole(tab));
  tab.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); activateRole(tabs[next]); tabs[next].focus(); }
  });
}
const filters = [...document.querySelectorAll('[data-filter]')];
const rows = [...document.querySelectorAll('tr[data-status]')];
for (const filter of filters) {
  filter.addEventListener('click', () => {
    for (const item of filters) item.setAttribute('aria-pressed', String(item === filter));
    for (const row of rows) row.hidden = filter.dataset.filter !== 'all' && row.dataset.status !== filter.dataset.filter;
    const count = rows.filter(row => !row.hidden).length;
    document.getElementById('feature-count').textContent = `${count} ${count === 1 ? 'capability' : 'capabilities'} shown`;
  });
}
''')

search_entries=[]
for filename,title in DOCS.items():
    text=(SOURCE/filename).read_text()
    path='/docs/' if filename=='README.md' else '/docs/'+Path(filename).stem.lower()+'/'
    plain=re.sub(r'[`#*|]','',re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',re.sub(r'<[^>]*>','',text)))
    headings=re.findall(r'^#{1,4}\s+(.+)$',text,re.M)
    search_entries.append({'title':title,'url':path,'summary':' '.join(plain.split())[:180],'text':' '.join(plain.split())[:60000],'headings':headings})
put('assets/docs-index.json',json.dumps(search_entries,ensure_ascii=False))

put('assets/site.js',(DIST/'assets/site.js').read_text()+r'''
document.documentElement.classList.add('js');
const docsMenu = document.querySelector('.docs-menu-toggle');
const docsLinks = document.querySelector('#docs-menu-links');
if (docsMenu && docsLinks) {
  docsMenu.hidden = false;
  docsMenu.addEventListener('click', () => {
    const open = docsMenu.getAttribute('aria-expanded') !== 'true';
    docsMenu.setAttribute('aria-expanded', String(open)); docsLinks.classList.toggle('open', open);
  });
  docsMenu.addEventListener('keydown', event => {
    if (event.key === 'Escape' && docsMenu.getAttribute('aria-expanded') === 'true') docsMenu.click();
  });
}
const docsSearch = document.querySelector('.docs-search');
if (docsSearch) {
  const input = docsSearch.querySelector('input');
  const status = document.querySelector('#docs-search-status');
  const list = document.querySelector('#docs-search-results');
  let indexPromise, sequence = 0, timer;
  async function search() {
    const current = ++sequence, query = input.value.trim().toLowerCase().slice(0, 100);
    list.replaceChildren(); list.hidden = true;
    if (query.length < 2) { status.textContent = query ? 'Enter at least two characters.' : ''; return; }
    status.textContent = 'Searching documentation…';
    try {
      if (!indexPromise) indexPromise = fetch('/assets/docs-index.json', {credentials:'omit'}).then(response => {
        if (!response.ok) throw new Error('Search index unavailable');
        return response.json();
      }).catch(error => { indexPromise = null; throw error; });
      const entries = await indexPromise;
      if (current !== sequence) return;
      const terms = query.split(/\s+/), results = entries.filter(entry => typeof entry.title === 'string' && /^\/docs\/(?:[a-z_]+\/)?$/.test(entry.url) && terms.every(term => entry.text.toLowerCase().includes(term))).map(entry => ({...entry,score:terms.reduce((score,term) => score + (entry.title.toLowerCase().includes(term)?100:0) + (entry.headings.join(' ').toLowerCase().includes(term)?10:0),0)})).sort((a,b) => b.score-a.score || a.title.localeCompare(b.title)).slice(0,8);
      for (const entry of results) {
        const item = document.createElement('li'), link = document.createElement('a'), title = document.createElement('strong'), summary = document.createElement('span');
        link.href = entry.url; title.textContent = entry.title; summary.textContent = entry.summary;
        link.append(title,summary); item.append(link); list.append(item);
      }
      list.hidden = results.length === 0;
      status.textContent = results.length ? `${results.length} ${results.length===1?'guide':'guides'} found. Use Tab to open a result.` : 'No matching guides. Try a shorter phrase or browse documentation below.';
    } catch (error) {
      if (current === sequence) status.textContent = 'Search is temporarily unavailable. Try again or browse documentation below.';
    }
  }
  docsSearch.addEventListener('submit',event => { event.preventDefault(); clearTimeout(timer); search(); });
  input.addEventListener('input',() => { clearTimeout(timer); ++sequence; timer = setTimeout(search,180); });
  input.addEventListener('keydown',event => { if (event.key==='Escape') { input.value='';clearTimeout(timer);++sequence;list.replaceChildren();list.hidden=true;status.textContent=''; } });
}
''')

index_version=hashlib.sha256((DIST/'assets/docs-index.json').read_bytes()).hexdigest()[:12]
put('assets/site.js',(DIST/'assets/site.js').read_text().replace("fetch('/assets/docs-index.json'","fetch('/assets/docs-index.json?v="+index_version+"'"))

# Version asset URLs so browsers/CDNs receive a changed file immediately.
asset_versions = {asset.relative_to(DIST/'assets').as_posix(): hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
                  for asset in (DIST/'assets').rglob('*') if asset.is_file()}
for built_page in DIST.rglob('*.html'):
    if built_page.name == '__qa.html':
        continue
    rendered = built_page.read_text()
    for asset_name, asset_version in asset_versions.items():
        rendered = rendered.replace('/assets/'+asset_name+'"', '/assets/'+asset_name+'?v='+asset_version+'"')
    built_page.write_text(rendered)

put('robots.txt','User-agent: *\nAllow: /\nSitemap: https://vectorcp.net/sitemap.xml')
paths=['/','/features/','/docs/','/roadmap/','/download/','/security/','/changelog/'] + ['/docs/'+Path(x).stem.lower()+'/' for x in DOCS if x != 'README.md']
put('sitemap.xml','<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>https://vectorcp.net'+path+'</loc></url>' for path in paths)+'</urlset>')
put('website-directives.htaccess',r'''
# Add these site-specific directives to the existing addon-domain .htaccess.
# Preserve the host-generated PHP configuration and ACME validation files.
Options -Indexes
DirectoryIndex index.html
ErrorDocument 404 /404.html
<FilesMatch "^(php\.ini|\.user\.ini)$">
Require all denied
</FilesMatch>
<IfModule mod_headers.c>
Header always set X-Content-Type-Options "nosniff"
Header always set Referrer-Policy "strict-origin-when-cross-origin"
Header always set Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'none'"
</IfModule>
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteCond %{REQUEST_URI} !^/\.well-known/acme-challenge/
RewriteCond %{HTTPS} !=on [OR]
RewriteCond %{HTTP_HOST} ^www\.vectorcp\.net$ [NC]
RewriteRule ^ https://vectorcp.net%{REQUEST_URI} [R=301,L,NE]
</IfModule>
''')
print(json.dumps({'website':str(SITE),'html_pages':len(list(DIST.rglob('*.html'))),'files':len([p for p in DIST.rglob('*') if p.is_file()]),'source_snapshot_sha256':checksum}))
