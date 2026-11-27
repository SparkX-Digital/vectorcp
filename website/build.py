"""Build the VectorCP static public website from reviewed project material."""
from pathlib import Path
import hashlib
import html
import json
import re
import shutil
import zipfile
from string import Template

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
for filename in ['VectorCP-0.4.2-source.zip', 'VectorCP-0.4.2-source.zip.sha256', 'VectorCP-0.4.3-mailboxes-development-source.zip', 'VectorCP-0.4.3-mailboxes-development-source.zip.sha256', 'VectorCP-0.4.4-development-source.zip', 'VectorCP-0.4.4-development-source.zip.sha256']:
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

# Shared, original templates keep the public site separate from panel runtime.
ICONS = {
    'web': '<rect x="3" y="4" width="26" height="23" rx="3"/><path d="M3 11h26M8 7h.01M12 7h.01M9 17h5M9 22h12"/>',
    'accounts': '<circle cx="12" cy="10" r="4"/><path d="M4 27v-4a8 8 0 0 1 16 0v4M23 6a4 4 0 0 1 0 8M25 19a6 6 0 0 1 4 6v2"/>',
    'backup': '<path d="M7 10a12 12 0 1 1-2 14M3 5v8h8M16 8v9l6 3"/>',
    'server': '<rect x="4" y="3" width="24" height="11" rx="2"/><rect x="4" y="18" width="24" height="11" rx="2"/><path d="M9 8h.01M9 23h.01M15 8h8M15 23h8"/>',
    'code': '<path d="m11 7-8 9 8 9M21 7l8 9-8 9M18 3l-4 26"/>',
    'mail': '<rect x="3" y="6" width="26" height="21" rx="3"/><path d="m4 8 12 10L28 8"/>'
}
def icon(name):
    return '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'+ICONS[name]+'</svg>'

def template(name, **values):
    return Template((SITE/'templates'/name).read_text()).substitute(**values)

def page(title,description,body,path='/',active=''):
    schema={'@context':'https://schema.org','@type':'SoftwareApplication','name':'VectorCP','url':'https://vectorcp.net/','description':'Open-source hosting control panel for server owners, resellers and customers.','applicationCategory':'DeveloperApplication','operatingSystem':'AlmaLinux 9','softwareVersion':VERSION,'license':'https://opensource.org/license/mit','author':{'@type':'Organization','name':'SparkX Digital','url':'https://www.sparkxdigital.co.uk/'}}
    document=template('base.html',title=html.escape(title,quote=True),description=html.escape(description,quote=True),body=body,path=path,github=GITHUB,version=VERSION,schema=json.dumps(schema))
    document=re.sub(r'<a\b[^>]*>.*?</a>',lambda match: re.sub(r'[↗→↓]','',match[0]),document,flags=re.S)
    if path!='/':
        document=document.replace('<a class="nav-link" href="'+path+'">','<a class="nav-link" aria-current="page" href="'+path+'">')
    put(('index.html' if path=='/' else path.strip('/')+'/index.html'),document)

page('Website and server management, on your terms',
     'Free, open-source hosting control for server owners, resellers and website owners. Explore VectorCP features, development status and self-hosted installation.',
     template('home.html',github=GITHUB,version=VERSION,date=DATE_LABEL,**{name+'_icon':icon(name) for name in ICONS}))



solutions=json.loads((SITE/'solutions.json').read_text())
for solution in solutions:
    assert re.fullmatch(r'[a-z-]+',solution['slug'])
    guides=''.join('<a href="'+html.escape(url,quote=True)+'">'+html.escape(label)+'</a>' for label,url in solution['guides'])
    body=template('solution.html',eyebrow=html.escape(solution['eyebrow']),heading=html.escape(solution['heading']),description=html.escape(solution['description']),icon=icon(solution['icon']),content=markdown(solution['content']),guides=guides)
    page(solution['title'],solution['description'],body,'/solutions/'+solution['slug']+'/','solutions')
solution_cards=''.join('<a class="audience-card" href="/solutions/'+x['slug']+'/"><span class="audience-icon">'+icon(x['icon'])+'</span><h3>'+html.escape(x['eyebrow'][4:])+'</h3><p>'+html.escape(x['description'])+'</p><span class="inline-link">Explore the workflow</span></a>' for x in solutions)
page('Solutions for your hosting work','Explore VectorCP workflows for hosting providers, agencies, developers and website owners.',
     '<section class="page-hero wrap"><span class="eyebrow">One platform, different perspectives</span><h1>Find your hosting workflow.</h1><p>Manage your own websites or the accounts behind a hosting service. Start with the tools and boundaries that fit your work.</p></section><section class="section wrap"><div class="audience-grid">'+solution_cards+'</div><div class="note"><strong>A development preview you can inspect.</strong><p>Review the <a href="/features/">feature catalog</a> and <a href="/docs/verification/">verification notes</a> before installing on a dedicated test server.</p></div></section>', '/solutions/','solutions')
page('Free and open-source hosting control','Use, inspect and adapt VectorCP under the MIT license. Learn what self-hosting means and how to contribute.',
     '<section class="page-hero wrap"><span class="eyebrow">Free software. Your server.</span><h1>Open source.<br>Open to possibilities.</h1><p>Read the code, adapt the panel and build on it for your own websites or hosting business. VectorCP is released under the MIT license.</p><div class="actions"><a class="button" href="/download/">Download the source</a><a class="inline-link" href="'+GITHUB+'">Browse on GitHub</a></div></section><section class="section open-section"><div class="wrap open-points"><article><h3>No activation fee.</h3><p>VectorCP does not require a paid software license or a recurring activation subscription. You provide the server and pay for any infrastructure and external services you choose.</p><a class="inline-link" href="'+GITHUB+'/blob/main/LICENSE">Read the MIT license</a></article><article><h3>Source you can inspect.</h3><p>The repository contains the application, service templates, installers, tests and documentation. The website also provides immutable development source snapshots and integrity checksums.</p><a class="inline-link" href="/changelog/">Explore the version history</a></article><article><h3>A project you can shape.</h3><p>Suggest a focused improvement, report a reproducible problem or contribute a tested change. Follow the public roadmap and contribution guidance.</p><a class="inline-link" href="/docs/contributing/">Start contributing</a></article></div></section><section class="section wrap"><div class="section-heading"><h2>Self-hosted means you operate it.</h2><p>Run VectorCP on a dedicated test server using the supported installation guide. You are responsible for server updates, access, routing and independently verified recovery. This development preview is not a managed hosting service.</p></div><div class="note"><strong>Check the current scope.</strong><p>VectorCP is not yet a stable production release. Independent security review, broader capacity acceptance and complete disaster recovery remain open. See the <a href="/features/">feature status</a> and <a href="/docs/verification/">verification notes</a>.</p></div></section>', '/open-source/','open source')
page('About VectorCP','Learn about VectorCP, the independent open-source hosting control panel from SparkX Digital.',
     '<section class="page-hero wrap"><span class="eyebrow">About the project</span><h1>Your hosting.<br>Your control.</h1><p>VectorCP is an independent, MIT-licensed hosting control panel developed as a SparkX Digital open-source project.</p></section><section class="wrap narrow prose"><h2>Why we’re building it</h2><p>Website hosting involves more than a domain and a folder. Server owners need to manage services and resources. Resellers need clear delegation. Customers need a usable workspace for their websites. VectorCP brings these responsibilities together in source that can be inspected and improved.</p><h2>Progress you can follow</h2><p>The project is in active development. We publish current capability statuses, verification notes, dated development snapshots and known limits. The goal is a capable hosting panel; the public catalog records the work still needed to get there.</p><p><a href="/roadmap/">Read the roadmap</a> or explore the <a href="/changelog/">version history</a>.</p><h2>Help build the next update</h2><p>Use the <a href="/docs/contributing/">contribution guide</a> for proposed changes and GitHub issues for reproducible problems. Follow the <a href="/security/">security reporting guidance</a> for vulnerabilities.</p><h2>About this website</h2><p>This website provides static product information, documentation and downloads. It does not create hosting accounts or collect sign-ups. Fonts and website assets are served locally. Links to GitHub and SparkX Digital lead to separate services.</p><p>Website typefaces are Manrope and Source Sans 3, distributed under their included <a href="/assets/fonts/manrope-OFL.txt">Manrope font license</a> and <a href="/assets/fonts/source-sans-3-OFL.txt">Source Sans 3 font license</a>.</p></section>', '/about/')

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
('mail','Mailboxes and email','Limited','Optional native mailboxes/aliases, SMTP/IMAPS, quotas and root-only local message recovery. Webmail, filtering, signing, scheduled/offsite mail backups and Internet delivery acceptance remain open.'),
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
page('Changelog','VectorCP version history with dated development snapshots, implemented changes and known limits.', '<section class="page-hero wrap"><span class="eyebrow">Product updates</span><h1>What’s new<br>in VectorCP.</h1><p>Every update, with its version, date and the work behind it.</p><div class="actions"><a class="button" href="/download/">Get the latest snapshot ↓</a><a class="underlink" href="'+GITHUB+'/commits/main/">Source history ↗</a></div></section><section class="wrap release-history"><div class="note"><strong>Development snapshots</strong><p>VectorCP is in active development. These entries record verified source updates; they do not mark stable production releases. Earlier builds sharing version 0.4.3 have dated snapshot identifiers. Original downloads stay unchanged.</p></div>'+''.join(cards)+'<section class="prose website-history">'+markdown((SITE/'CHANGELOG.md').read_text())+'</section></section>', '/changelog/','changelog')

page('Download VectorCP',f'Download the VectorCP {VERSION} development source snapshot and SHA-256 checksum. Read the installation requirements before deploying.',f'''<section class="page-hero wrap"><span class="eyebrow">MIT-licensed source</span><h1>Start with<br>VectorCP.</h1><p>Explore the source, try it on a dedicated test server and help build what comes next.</p></section><section class="wrap section download-grid"><article class="download-card"><span class="status limited">Unreleased development snapshot</span><h2>VectorCP <span>{VERSION}</span></h2><p>Version {VERSION} · <time datetime="{DATE_ISO}">{DATE_LABEL}</time>. Development source snapshot. Native AlmaLinux 9 x86-64 installation, hosting, upgrade and rollback checks have passed. This is an unreleased integration snapshot from merged source, not a new stable release. Wider production acceptance remains pending. Includes the application, service templates, installers, tests and documentation.</p><a class="button" href="/downloads/{ARCHIVE_NAME}" download>Download source ZIP ↓</a><a class="underlink" href="/downloads/{ARCHIVE_NAME}.sha256" download>SHA-256 checksum</a><p><a class="underlink" href="/changelog/">Read the version history and changes →</a></p><p><a class="underlink" href="/downloads/VectorCP-0.4.4-development-source.zip">Previous development snapshot: 0.4.4</a> · <a class="underlink" href="/downloads/VectorCP-0.4.2-source.zip">Frozen 0.4.2 snapshot</a></p><details><summary>Verify your download</summary><p>Compare the archive's SHA-256 with this value:</p><pre class="checksum"><code>{checksum}</code></pre><p>The archive is unsigned. The checksum checks file integrity; it is not a publisher signature.</p></details></article><div class="prose"><h2>Before you install</h2><ul><li>A dedicated AlmaLinux 9 server. The x86-64 target has been exercised.</li><li>Root access and a clean hosting environment. The installer checks for an existing hosting stack.</li><li>Read the documented storage, workload and backup limits.</li><li>Use a test server while the product is in early development.</li></ul><p>The initial installer defaults to a read-only preflight. Follow the full guide for installation, owner setup and public HTTPS.</p><a class="button outline" href="/docs/#installation">Read the installation guide →</a><p class="muted">The public repository may contain documentation and metadata updates beyond this frozen snapshot. Refer to each artifact's own version and verification notes.</p></div></section>''','/download/')

page('Security','VectorCP security boundaries, development limitations and responsible reporting guidance.',f'''<section class="page-hero wrap"><span class="eyebrow">Security and reporting</span><h1>Clear boundaries.<br>Visible limits.</h1><p>VectorCP is early software. An independent security audit and production support commitment have not been established.</p></section><section class="wrap section prose narrow"><h2>Report a suspected vulnerability privately</h2><p>Do not put credentials, customer data or exploit details for a live installation in public issues. Consult the <a href="{GITHUB}/security/policy">repository security policy</a> for the current private reporting route and availability.</p><h2>How the current panel is separated</h2><p>An unprivileged frontend sends bounded requests to a local agent. Customer workloads have distinct Unix identities, fixed storage volumes, private mount namespaces and resource controls. This is shared-kernel isolation.</p><h2>What still needs work</h2><p>Email account recovery, secret encryption, signed updates, broader service-helper review, hostile workload testing and clean recovery drills remain planned work. Read the <a href="/docs/security/">full security policy</a> and <a href="/docs/verification/">verification notes</a> before choosing the panel for customer workloads.</p><h2>Ordinary bugs and improvements</h2><p>Use <a href="{GITHUB}/issues">GitHub Issues</a> for non-security problems and proposals, with synthetic examples and redacted evidence.</p></section>''','/security/')

page('Page not found','The requested VectorCP page could not be found.','''<section class="page-hero wrap error-page"><span class="eyebrow">404 / Page not found</span><h1>Let's get you<br>back on track.</h1><p>This page may have moved, or the address may be incomplete.</p><div class="actions"><a class="button" href="/">Go to the homepage →</a><a class="underlink" href="/docs/">Browse the docs</a></div></section>''','/404/')
shutil.copyfile(DIST/'404/index.html',DIST/'404.html')

# Static design assets are reviewed source; fonts remain self-hosted.
shutil.copytree(SITE/'assets',DIST/'assets',dirs_exist_ok=True)
for screenshot in MATERIAL.glob('panel-045-*.jpg'):
    shutil.copyfile(screenshot,DIST/'assets'/screenshot.name)

put('assets/site.js',r'''
const menu = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
const navGroups = [...document.querySelectorAll('.nav-group')];
if (menu && navigation) {
  menu.hidden = false;
  menu.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    menu.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    navigation.classList.toggle('open', open);
    if (!open) navGroups.forEach(group => { group.open = false; });
  });
}
navigation?.addEventListener('click', event => {
  if (!event.target.closest('a')) return;
  navGroups.forEach(group => { group.open = false; });
  if (menu?.getAttribute('aria-expanded') === 'true') menu.click();
});
for (const group of navGroups) group.addEventListener('toggle', () => {
  if (group.open) for (const other of navGroups) if (other !== group) other.open = false;
});
document.addEventListener('click', event => {
  if (!event.target.closest('.site-header')) {
    navGroups.forEach(group => { group.open = false; });
    if (menu?.getAttribute('aria-expanded') === 'true') menu.click();
  }
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const group = navGroups.find(item => item.open);
  if (group) { group.open = false; group.querySelector('summary').focus(); }
  else if (menu?.getAttribute('aria-expanded') === 'true') { menu.click(); menu.focus(); }
});
const workflowTabs = [...document.querySelectorAll('[data-workflow]')];
function activateWorkflow(button, focus = false) {
  for (const tab of workflowTabs) {
    const selected = tab === button;
    tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
  }
  if (focus) button.focus();
}
for (const [index, tab] of workflowTabs.entries()) {
  tab.addEventListener('click', () => activateWorkflow(tab));
  tab.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % workflowTabs.length;
    if (event.key === 'ArrowLeft') next = (index + workflowTabs.length - 1) % workflowTabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = workflowTabs.length - 1;
    if (next !== undefined) { event.preventDefault(); activateWorkflow(workflowTabs[next], true); }
  });
}
if (workflowTabs.length) activateWorkflow(workflowTabs[0]);
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
paths=['/solutions/','/solutions/hosting-providers/','/solutions/agencies/','/solutions/developers/','/solutions/site-owners/','/open-source/','/about/','/','/features/','/docs/','/roadmap/','/download/','/security/','/changelog/'] + ['/docs/'+Path(x).stem.lower()+'/' for x in DOCS if x != 'README.md']
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
<FilesMatch "\.(html|json)$">
# Preserve copyable documentation examples through delivery intermediaries.
Header always set Cache-Control "no-cache, max-age=0, must-revalidate, no-transform"
</FilesMatch>
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
