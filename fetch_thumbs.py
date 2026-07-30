"""Fetch og:image for each embeddable URL and cache to .thumb_cache.json.

Re-running is cheap — only URLs not already in the cache (or marked failed
and forced via --retry) are fetched. Uses a thread pool for parallelism.
"""
import argparse
import concurrent.futures as cf
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.thumb_cache.json'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)\s*=\s*["\']og:image["\'][^>]*content\s*=\s*["\']([^"\']+)',
    re.IGNORECASE,
)
OG_RE_REV = re.compile(
    r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]*(?:property|name)\s*=\s*["\']og:image["\']',
    re.IGNORECASE,
)
THUMB_URL_RE = re.compile(
    r'(https?://[^\s"\'<>]+?\.(?:jpg|jpeg|png|webp))', re.IGNORECASE
)


def fetch(url: str, timeout: int = 15) -> str | None:
    """Return og:image URL or None. Solves pornhub JS challenge transparently."""
    from ph_solver import fetch_with_challenge
    html = fetch_with_challenge(url, timeout=timeout)
    if html is None:
        return None
    m = OG_RE.search(html) or OG_RE_REV.search(html)
    if m:
        return m.group(1)
    m = THUMB_URL_RE.search(html)
    return m.group(1) if m else None


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_cache(c: dict):
    CACHE.write_text(json.dumps(c, indent=2, sort_keys=True), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--retry', action='store_true',
                    help='Retry URLs previously marked as failed')
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()

    # Import from the sibling builder so we use the same source-dir list.
    sys.path.insert(0, str(HERE))
    from build_links_page import parse_file, classify, iter_source_files

    # Domains that are file-lockers with no scrapable thumbnail.
    NO_THUMB = ('filejoker.net', 'rapidgator.net', 'rg.to', 'dfiles.eu',
                'depositfiles.com', 'filefactory.com')

    urls = []
    for f, label in iter_source_files():
        for e in parse_file(f, source_label=label):
            u = e['url']
            if any(d in u for d in NO_THUMB):
                continue
            urls.append(u)
    urls = sorted(set(urls))

    cache = load_cache()
    todo = []
    for u in urls:
        if u not in cache:
            todo.append(u)
        elif args.retry and not cache[u]:
            todo.append(u)

    print(f'{len(urls)} embeddable URLs total, {len(todo)} to fetch')
    if not todo:
        return

    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch, u): u for u in todo}
        for fut in cf.as_completed(futures):
            u = futures[fut]
            try:
                result = fut.result()
            except Exception:
                result = None
            cache[u] = result or ''
            done += 1
            mark = 'OK ' if result else 'XX '
            print(f'  [{done}/{len(todo)}] {mark} {u[:80]}')
            if done % 10 == 0:
                save_cache(cache)

    save_cache(cache)
    ok = sum(1 for u in urls if cache.get(u))
    print(f'Done. {ok}/{len(urls)} have thumbnails.')


if __name__ == '__main__':
    main()
