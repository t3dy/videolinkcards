"""Audit: do all URLs in *.txt files appear as cards in links.html and the thumb cache?

Reports:
  - URLs in txt files that DON'T appear in links.html (missed by builder)
  - URLs in links.html that DON'T appear in any txt file (stale/orphan)
  - URLs in cards that lack a thumbnail entry in .thumb_cache.json
  - .txt files the builder is currently skipping
  - Per-file URL counts

This is a read-only check. Run after editing .txt files but before deciding
whether to rebuild. If anything is missing, run:
    python build_links_page.py
    python fetch_thumbs.py
"""
import html as html_mod
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent

# Use the SAME parser as the builder so we audit against its real behavior.
from build_links_page import parse_file, classify, load_thumb_cache, iter_source_files

# A *broader* URL regex than the builder's, to also catch things the
# builder might miss (e.g. URLs followed by trailing punctuation, weird hosts).
BROAD_URL_RE = re.compile(r'https?://[^\s<>"\'\\]+', re.IGNORECASE)


def parse_links_html(path: Path):
    """Return the set of URLs that appear as cards in links.html (HTML-unescaped)."""
    if not path.exists():
        return set()
    text = path.read_text(encoding='utf-8')
    raw = re.findall(r'<article class="card"[^>]*\sdata-url="([^"]+)"', text)
    return {html_mod.unescape(u) for u in raw}


def main():
    # Source files from the shared SOURCE_DIRS list.
    used = [(f, label) for f, label in iter_source_files()]

    print('=' * 70)
    print(f'Source files: {len(used)} parsed across all source directories')
    print('=' * 70)

    # 1) URLs the BUILDER finds (its real output).
    builder_urls = set()
    per_file_builder = defaultdict(set)
    for f, label in used:
        for e in parse_file(f, source_label=label):
            builder_urls.add(e['url'])
            per_file_builder[label].add(e['url'])

    # 2) URLs a generous regex finds (a wider net).
    #    Also split on inline 'https?://' so "xvideosURL1https://xvideosURL2"
    #    counts as two URLs (matching the builder's behavior).
    SPLIT_RE = re.compile(r'(?=https?://)', re.IGNORECASE)
    broad_urls = set()
    per_file_broad = defaultdict(set)
    line_index = {}     # url -> [(label, line)] for reporting
    for f, label in used:
        for i, line in enumerate(f.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            for raw in BROAD_URL_RE.findall(line):
                for piece in SPLIT_RE.split(raw):
                    if not piece.lower().startswith(('http://', 'https://')):
                        continue
                    m = re.match(r'https?://[^\s<>"\'\\]+', piece, re.I)
                    if not m:
                        continue
                    u = m.group(0).rstrip('.,;)\\')
                    broad_urls.add(u)
                    per_file_broad[label].add(u)
                    line_index.setdefault(u, []).append((label, i))

    # 3) URLs in the rendered cards.
    rendered_urls = parse_links_html(HERE / 'links.html')

    # 4) Thumbnail cache.
    thumbs = load_thumb_cache()

    # Print per-file counts.
    print(f'{"File":<32} {"broad":>6} {"parsed":>7} {"diff":>5}')
    print('-' * 56)
    for f, label in used:
        b = len(per_file_broad.get(label, set()))
        p = len(per_file_builder.get(label, set()))
        diff = b - p
        marker = '  !' if diff else ''
        print(f'{label:<32} {b:>6} {p:>7} {diff:>5}{marker}')
    print('-' * 56)
    print(f'{"TOTAL UNIQUE":<32} {len(broad_urls):>6} {len(builder_urls):>7}')
    print()

    # Builder gaps: what the broad regex caught that the builder didn't.
    missed_by_builder = broad_urls - builder_urls
    if missed_by_builder:
        print(f'[!] {len(missed_by_builder)} URL(s) caught by broad regex but MISSED by builder:')
        for u in sorted(missed_by_builder):
            srcs = line_index.get(u, [])[:3]
            loc = ', '.join(f'{name}:{line}' for name, line in srcs)
            print(f'  - {u}')
            print(f'      at {loc}')
        print()
    else:
        print('[ok] Builder catches every URL the broad regex finds.')
        print()

    # Cards missing from page render.
    if not (HERE / 'links.html').exists():
        print('[!] links.html does NOT exist. Run: python build_links_page.py')
        print()
    else:
        in_builder_not_rendered = builder_urls - rendered_urls
        in_rendered_not_builder = rendered_urls - builder_urls
        if in_builder_not_rendered:
            print(f'[!] {len(in_builder_not_rendered)} URL(s) parsed but NOT in links.html '
                  f'(rebuild needed):')
            for u in sorted(in_builder_not_rendered)[:20]:
                print(f'  - {u}')
            if len(in_builder_not_rendered) > 20:
                print(f'  ... and {len(in_builder_not_rendered) - 20} more')
            print()
        else:
            print(f'[ok] All {len(builder_urls)} parsed URLs appear in links.html.')
            print()
        if in_rendered_not_builder:
            print(f'[!] {len(in_rendered_not_builder)} URL(s) in links.html but no longer in any '
                  f'txt file (rebuild will drop them):')
            for u in sorted(in_rendered_not_builder)[:10]:
                print(f'  - {u}')
            print()

    # Thumbnail coverage.
    NO_THUMB = ('filejoker.net', 'rapidgator.net', 'rg.to', 'dfiles.eu',
                'depositfiles.com', 'filefactory.com')
    thumbable = [u for u in builder_urls if not any(d in u for d in NO_THUMB)]
    not_cached = [u for u in thumbable if u not in thumbs]
    cached_no_thumb = [u for u in thumbable if u in thumbs and not thumbs[u]]
    cached_ok = [u for u in thumbable if u in thumbs and thumbs[u]]
    print('Thumbnail cache:')
    print(f'  {len(cached_ok):>4} URLs have a thumbnail')
    print(f'  {len(cached_no_thumb):>4} URLs were tried but no thumbnail returned (dead / no og:image)')
    print(f'  {len(not_cached):>4} URLs not yet attempted')
    if not_cached:
        print('       → run: python fetch_thumbs.py')

    # Classification check: any URLs classified as raw domain (no embed + no special handler)?
    raw_domain = []
    for u in builder_urls:
        src_type, embed = classify(u)
        if not embed and src_type not in (
            'pornzog', 'tnaflix', 'megatube', 'spankbang',
        ) and not any(d in u for d in NO_THUMB) and '.' in src_type:
            raw_domain.append((u, src_type))
    if raw_domain:
        print()
        print(f'[i] {len(raw_domain)} URL(s) fell through to default domain handling (no embed wired):')
        by_dom = defaultdict(int)
        for u, t in raw_domain:
            by_dom[t] += 1
        for dom, n in sorted(by_dom.items(), key=lambda x: -x[1])[:10]:
            print(f'  - {dom}: {n}')

    print()
    print('=' * 70)
    print(f'Summary: {len(builder_urls)} unique URLs across {len(used)} txt files')
    print('=' * 70)


if __name__ == '__main__':
    main()
