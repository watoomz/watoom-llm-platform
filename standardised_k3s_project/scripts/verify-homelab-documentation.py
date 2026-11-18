#!/usr/bin/env python3
"""Check maintained documentation links and Glance anchors without network access.

Uses the Python standard library. Run render-glance-guide.py --check separately
with markdown-it-py to check source/generated drift.
"""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / 'config/glance/guide'


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = []
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag in ('script', 'img') and attrs.get('src'):
            self.links.append(attrs['src'])
        if tag == 'link' and attrs.get('href'):
            self.links.append(attrs['href'])


def check_link(source, href, failures):
    url = urlsplit(href.strip('<>'))
    if url.scheme or url.netloc:
        return  # External destinations are not qualified by this check.
    if url.path.startswith('/guide/'):
        target = GUIDE / (unquote(url.path[len('/guide/'):]) or 'index.html')
    elif url.path.startswith('/'):
        return  # Glance dashboard routes (/, /llm-lab, /guide-api) are served by the app, not files.
    elif url.path:
        target = source.parent / unquote(url.path)
    else:
        target = source
    if not target.exists():
        failures.append(f'{source.relative_to(ROOT)}: missing target {href}')
    elif url.fragment and target.suffix == '.html':
        if unquote(url.fragment) not in Page(target.read_text()).ids:
            failures.append(f'{source.relative_to(ROOT)}: missing anchor {href}')


def main():
    failures = []
    # Preserved retired pages retain historical relative links; validate maintained sources.
    documents = [ROOT / 'README.md', *sorted(p for p in (ROOT / 'docs').rglob('*.md')
                         if 'retired-guide-pages' not in p.parts),
                 *sorted(GUIDE.glob('*.md')),
                 ROOT / 'manifests/10-infrastructure/llm/README.md']
    for source in documents:
        for href in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', source.read_text()):
            check_link(source, href, failures)
    pages = sorted(path.name for path in GUIDE.glob('*.html'))
    for name in pages:
        source = GUIDE / name
        page = Page(source.read_text())
        duplicates = [ident for ident, count in Counter(page.ids).items() if count > 1]
        if duplicates:
            failures.append(f'{name}: duplicate IDs {duplicates}')
        for href in page.links:
            check_link(source, href, failures)
    for name, anchor in re.findall(r'/guide/([a-z0-9-]*\.html)?#([A-Za-z0-9_-]+)',
                                   (ROOT / 'config/glance/glance.yml').read_text()):
        target = GUIDE / (name or 'index.html')
        if not target.exists() or anchor not in Page(target.read_text()).ids:
            failures.append(f'Glance dashboard: missing guide anchor {name or "index.html"}#{anchor}')
    for failure in failures:
        print('FAIL', failure)
    print(f'RESULT={"FAIL" if failures else "PASS"}; '
          f'{len(documents)} Markdown documents, {len(pages)} guide pages')
    print('Scope: local targets, HTML fragments/assets, duplicate IDs and dashboard anchors. '
          'External links, Markdown fragments, browser rendering and live health require separate checks.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
