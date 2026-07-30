# videolinkcards

A local-first web app for turning plain-text lists of video URLs into a browseable card grid with inline previews, tags, ordering, comments, and search. Runs as a Flask + SQLite app on your own machine, or as a fully static single-file HTML page deployed to GitHub Pages.

**Live static demo:** https://t3dy.github.io/videolinkcards/

---

## What it does

Point the tool at `.txt` files that contain a mix of URLs and free-text captions. It:

- Extracts every URL, dedupes across files, and renders one card per URL.
- Uses the text preceding each URL as the card's title (either on the same line or the previous non-blank line).
- Classifies each URL by domain and, where possible, generates an iframe embed URL so the video can play inline with a click.
- Fetches an `og:image` thumbnail for each card and caches it locally.
- Auto-generates a set of tags from the words in each caption (minus a stop-word list).

Once cards are on screen, you can:

- Reorder cards individually — move up/down/top/bottom, move down 10, or jump to any position by number.
- Edit the caption inline (click the title) or via a per-card edit panel.
- Add or remove tags.
- Filter by search string, source file, domain, or by one or more tags.
- Delete cards (soft-delete with undo, hidden by default with a toggle to reveal).
- Add free-form comments to any card via a popup with optional voice input (Web Speech API).
- Every card shows its current 1-based position, kept live as you filter and reorder.

Two persistence modes:

- **Server mode** — Flask + SQLite on `localhost:5000`. Ships as a single-file `LinksApp.exe` you can double-click.
- **Static mode** — one self-contained HTML file, edits persist in the browser's `localStorage`. This is what gets deployed to GitHub Pages.

## Repository layout

```
videolinkcards/
├── README.md
├── docs/
│   ├── architecture.md    — end-to-end diagram + data flow
│   ├── scripts.md         — every script + example invocations
│   └── data-model.md      — DB schema, override precedence, effective values
├── site/
│   └── index.html         — the deployed static snapshot (also served by GitHub Pages)
├── build_links_page.py    — parses .txt sources → generates the dynamic (server-backed) HTML
├── build_static.py        — same, plus DB bake-in → self-contained static HTML
├── server.py              — Flask API + static-file server for local use
├── fetch_thumbs.py        — scrapes og:image for each card, caches to .thumb_cache.json
├── audit_links.py         — reconciles txt files ↔ generated HTML ↔ thumbnail cache
├── move_to_bottom.py      — one-shot bulk reorder by caption pattern
├── ph_solver.py           — solves pornhub's JS bot-challenge cookie for thumb fetching
└── LinksApp.spec          — PyInstaller spec for the bundled .exe
```

Not in the repo:

- The user's raw `.txt` link lists (private, listed in `.gitignore`).
- `overrides.db` (per-user local edits).
- `LinksApp.exe` and PyInstaller build artifacts.
- Any actual video files.

See [docs/architecture.md](docs/architecture.md) for how the pieces fit together, [docs/scripts.md](docs/scripts.md) for what each script does, and [docs/data-model.md](docs/data-model.md) for the override schema.

## Running it locally (server mode)

Prereqs: Python 3.10+, `pip install flask pyinstaller`.

```
# One-time build of the page
python build_links_page.py

# One-time thumbnail fetch (respects .thumb_cache.json — re-runs are cheap)
python fetch_thumbs.py

# Serve it
python server.py     # opens http://localhost:5000 in your browser
```

Or use the packaged single-file exe:

```
python -m PyInstaller LinksApp.spec       # build LinksApp.exe
LinksApp.exe                              # double-click to launch
```

## Building the static site

```
python build_static.py                    # writes site/index.html
```

The static build reads the current `overrides.db` and bakes every user edit (caption, tags, order, deletion, comment) into the HTML as the initial default state. Visitors' further edits go to their own browser's `localStorage`; nothing round-trips back to your DB.

## Configuring source files

Edit `SOURCE_DIRS` and `SOURCE_FILES` near the top of [build_links_page.py](build_links_page.py):

```python
SOURCE_DIRS = [
    (HERE, ''),                                              # every *.txt next to this script
    (Path('C:/Users/PC/Desktop/p txt'), 'desktop/'),         # every *.txt in this folder
]
SOURCE_FILES = [
    (Path('C:/Users/PC/Downloads/l.txt'), 'downloads/'),     # a single specific file
]
```

The label prefix goes on the card's source badge so you can tell entries apart.

## Notes on privacy and hosting

- The deployed static site bakes every URL, thumbnail URL, caption, tag, and comment from your `overrides.db` into a public HTML file. Anyone with the URL can view them.
- Thumbnails load from the origin CDNs at page-view time — visitors' browsers make direct requests to those hosts.
- Some hosts block cross-origin iframe embeds; those cards fall back to a click-through to the source page.
- Search engines can index a GitHub Pages site. The static build sets `<meta name="robots" content="noindex,nofollow">`, but this is a request, not an enforcement.
- To keep a site private, use a private GitHub repo and forgo Pages, or host the HTML somewhere behind auth.

## License

No license specified — all rights reserved by default. Add a `LICENSE` file if you want to permit reuse.
