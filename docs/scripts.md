# Scripts

Everything is a plain Python 3.10+ script — no build system. Each script prints what it did.

## `build_links_page.py`

Parses every configured `.txt` file, dedupes URLs, and writes `links.html` (the server-backed page).

```
python build_links_page.py
```

Output: `links.html` in the repo root. Console reports total cards, per-file counts, and per-domain counts.

Uses `.thumb_cache.json` for baked-in thumbnails but does not fetch anything. Run `fetch_thumbs.py` beforehand if you want previews.

## `build_static.py`

Same parse + classify + tag pipeline as `build_links_page.py`, plus:

- Reads the current `overrides.db` and bakes every user edit into the emitted HTML as the initial default state.
- Emits `site/index.html` — a fully self-contained page (no server, no external scripts).
- Uses `localStorage` for persistence.

```
python build_static.py
```

This is what GitHub Pages serves.

## `server.py`

Flask + SQLite backend. Serves `links.html` at `/` and a small JSON API under `/api`.

```
python server.py                # http://localhost:5000
```

Behavior:

- Creates `overrides.db` on first run.
- Auto-invokes `build_links_page.main()` if `links.html` doesn't exist.
- Waits for the port to actually bind before opening the browser (avoids race conditions on double-clicked exe launches).
- Persists cookies across pornhub anti-bot challenges via `ph_solver.py`.

Also drives `LinksApp.exe` — the PyInstaller build has this as its entry point.

## `fetch_thumbs.py`

Scrapes `og:image` for every URL from every source file and caches results to `.thumb_cache.json`.

```
python fetch_thumbs.py              # only fetches URLs not already in the cache
python fetch_thumbs.py --retry      # also retries previously-failed URLs
python fetch_thumbs.py --workers 8  # tune parallelism (default 4)
```

Empty strings in the cache mean "we tried and got nothing back" — dead videos, hosts without `og:image`, or Cloudflare 403s. `--retry` re-attempts those.

## `audit_links.py`

Read-only reconciliation. Compares:

- URLs the builder finds in `.txt` files
- URLs a broader regex would find (catches anything the builder misses)
- URLs that appear as cards in `links.html`
- URLs in the thumbnail cache

Prints a table of per-file counts and warns about any mismatch.

```
python audit_links.py
```

Use before rebuilding to see whether anything needs to be re-run.

## `move_to_bottom.py`

One-shot bulk reorder. Matches cards whose current effective caption contains a substring (or a regex with `--regex`) and moves them past the current maximum order value.

```
python move_to_bottom.py compilation cumpilation      # OR of substrings
python move_to_bottom.py --regex "\bcc\b"             # standalone-word regex
python move_to_bottom.py favorite --dry-run           # preview only
```

Requires the local server to be running on port 5000. Goes through the same `/api/override` endpoint the UI uses, so it's safe to run while the browser is open — the change appears on next reload or the next 5 s health check.

## `ph_solver.py`

Standalone helper — `fetch_thumbs.py` imports it. Solves pornhub's `leastFactor(p)` JavaScript proof-of-work challenge in Python by parsing the challenge script, replaying the arithmetic, and returning a valid `KEY` cookie value. Not meant to be run directly, but has a quick self-test:

```
python ph_solver.py "https://www.pornhub.com/view_video.php?viewkey=..."
```

## `LinksApp.spec`

PyInstaller spec for `LinksApp.exe`. Rebuild with:

```
python -m PyInstaller LinksApp.spec
```

The output lands in `dist/LinksApp.exe`. Move it to the repo root and delete `build/` and `dist/` to clean up.

## Typical workflow

Edit a `.txt` link list, then:

```
python audit_links.py               # see what changed
python build_links_page.py          # regenerate links.html
python fetch_thumbs.py              # grab any new thumbnails
python build_static.py              # regenerate site/index.html for deployment
git add -A && git commit -m "..."   # commit the static snapshot
git push                            # deploy via GitHub Pages
```

Running `LinksApp.exe` while doing edits is fine — the server serves the freshly rebuilt `links.html` on next browser reload.
