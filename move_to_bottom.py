"""Move cards whose caption matches a given pattern to the bottom of the list.

Usage:
    python move_to_bottom.py "\\bcc\\b"                     # cc as standalone word
    python move_to_bottom.py compilation cumpilation        # multiple substrings (OR)
    python move_to_bottom.py --regex "\\b(cc|jc)\\b"        # explicit regex flag

Matches against the *effective* caption of each card (user override in the
DB if set, otherwise the default caption parsed from the source text file).
Substring matches are case-insensitive by default. Multiple positional
patterns are OR'd together.

Requires the LinksApp server running on localhost:5000.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
API = 'http://localhost:5000/api'

sys.path.insert(0, str(HERE))
from build_links_page import parse_file, iter_source_files


def api(path, method='GET', body=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header('Content-Type', 'application/json')
    data = json.dumps(body).encode() if body else None
    with urllib.request.urlopen(req, data=data, timeout=30) as r:
        return json.loads(r.read())


def build_matcher(patterns, is_regex):
    """Return a compiled regex that matches if ANY pattern hits."""
    if is_regex:
        alt = '|'.join(f'(?:{p})' for p in patterns)
    else:
        alt = '|'.join(re.escape(p) for p in patterns)
    return re.compile(alt, re.IGNORECASE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('patterns', nargs='+',
                    help='One or more substrings (OR-matched). Use --regex to treat as regex.')
    ap.add_argument('--regex', action='store_true',
                    help='Treat patterns as regexes. Default: literal substrings.')
    ap.add_argument('--dry-run', action='store_true',
                    help='Show what would be moved, do not update the DB.')
    args = ap.parse_args()

    matcher = build_matcher(args.patterns, args.regex)

    # Collect all cards, deduped.
    all_cards = []
    seen = set()
    for f, label in iter_source_files():
        for e in parse_file(f, source_label=label):
            if e['url'] in seen:
                continue
            seen.add(e['url'])
            all_cards.append((e['url'], e['caption']))
    total = len(all_cards)

    try:
        overrides = api('/overrides')
    except Exception as e:
        print(f'ERROR: cannot reach server at {API}: {e}')
        print('Start LinksApp.exe first.')
        return

    def effective_caption(url, default):
        cap = overrides.get(url, {}).get('caption')
        return cap if cap else (default or '')

    matches = []
    for url, default_cap in all_cards:
        cap = effective_caption(url, default_cap)
        if matcher.search(cap):
            matches.append((url, cap))

    if not matches:
        print(f'No cards match {args.patterns!r}.')
        return

    print(f'Matched {len(matches)} card(s):')
    for url, cap in matches:
        print(f'  - {cap[:80]:<80}  {url[:60]}')

    if args.dry_run:
        print('\n[dry run] nothing changed.')
        return

    default_max = total - 1
    override_orders = [
        v['order'] for v in overrides.values()
        if isinstance(v.get('order'), (int, float))
    ]
    override_max = max(override_orders) if override_orders else 0
    current_max = max(default_max, override_max)

    print(f'\nCurrent max order = {current_max}. '
          f'Assigning matches to {current_max + 1}..{current_max + len(matches)}')
    ok = 0
    for i, (url, _cap) in enumerate(matches, 1):
        try:
            api('/override', method='POST', body={'url': url, 'order': current_max + i})
            ok += 1
        except Exception as e:
            print(f'  FAILED for {url}: {e}')

    print(f'\nDone. Moved {ok}/{len(matches)} cards. Reload the page to see the new order.')


if __name__ == '__main__':
    main()
