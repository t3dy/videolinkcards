# Architecture

## System overview

```
┌───────────────────────────────────────────────────────────────────────┐
│  SOURCES                                                              │
│    plain-text files with URLs + free-form captions                    │
│    configured via SOURCE_DIRS / SOURCE_FILES in build_links_page.py   │
└──────────┬────────────────────────────────────────────────────────────┘
           │
           │  parse_file()  →  URL, caption, source-file label, line #
           ↓
┌──────────────────────────┐     ┌──────────────────────────────────────┐
│  build_links_page.py     │────→│  links.html   (dynamic — server)     │
│  build_static.py         │────→│  site/index.html  (static — GH Pages)│
└────────┬─────────────────┘     └──────────────────────────────────────┘
         │                                     ↑
         │  classify() → (src_type, embed_url) │
         │  caption_to_tags() → [tag, ...]     │
         ↓                                     │
┌──────────────────────────┐                   │
│  .thumb_cache.json       │                   │
│  URL → og:image URL      │                   │
└────────┬─────────────────┘                   │
         │                                     │
         │  fetched by fetch_thumbs.py         │
         │  (uses ph_solver.py for pornhub)    │
         ↑                                     │
┌────────┴─────────────────┐                   │
│  origin CDNs             │                   │
│  (pornhub, xvideos, ...) │                   │
└──────────────────────────┘                   │
                                               │
┌──────────────────────────┐                   │
│  overrides.db (SQLite)   │───────────────────┘ (build_static.py bakes
│  user edits per URL:       ↑                    current DB values into
│    caption, tags, order,   │ (via Flask API)    the static default set)
│    deleted, comment        │
└────────┬─────────────────┘
         │
         │  Flask REST API — /api/overrides, /api/override, ...
         │  provided by server.py
         ↓
┌──────────────────────────┐
│  browser                 │  fetch → optimistic local update → POST
│    links.html + JS       │  or (static mode) → localStorage
└──────────────────────────┘
```

## Data flow

**Ingest**
- `iter_source_files()` walks configured directories and single-file paths, yielding `(Path, source_label)` for each `.txt`.
- `parse_file()` extracts URLs from each line, treating text before a URL as its caption. When a URL sits alone on a line, the previous non-blank line becomes its caption.
- `classify()` looks up each URL by domain and, when known, returns an iframe embed URL. Domains without a known embed shape become "link-only" cards.
- `caption_to_tags()` lowercases, strips diacritics, and splits captions into alphanumeric tokens minus a small stop-word list.

**Thumbnails**
- `fetch_thumbs.py` walks the same source files, filters out file-locker domains, and scrapes `<meta property="og:image">` for each URL.
- Results (or empty strings for failures) go to `.thumb_cache.json`, keyed by URL. Re-runs are incremental — only new URLs are fetched.
- Pornhub serves a JavaScript proof-of-work challenge to non-browser HTTP clients. `ph_solver.py` replicates the arithmetic and posts the resulting `KEY` cookie so the actual page can be fetched.

**Rendering**
- `build_links_page.py` emits `links.html` for the server-backed workflow: cards read/write overrides via `fetch()` calls to `/api`.
- `build_static.py` emits `site/index.html` for the static workflow: cards read/write overrides via `localStorage`. Current DB state is baked in as the initial default set so the deployed page reflects the curator's latest edits.

**Persistence**
- Server mode: SQLite at `overrides.db`, one row per URL that has any user edit.
- Static mode: browser `localStorage` under key `videolinkcards_overrides_v1`.
- Both use the same JSON shape per URL: `{ caption?, tags?, order?, deleted?, comment? }`.

## Runtime layers

### Frontend (`links.html` / `site/index.html`)

Vanilla HTML/CSS/JS. Everything is inlined into a single file — no external scripts, no build step for the frontend. The only network requests at page-load time are:

- Static mode: none. The `default-overrides` blob is inlined as a `<script type="application/json">`.
- Server mode: `GET /api/overrides` on load, periodic `GET /api/health` every 5 s.
- Both: lazy `img` requests for thumbnails as cards enter the viewport, and per-card iframe requests only after the user clicks Play.

State lives in a plain object `overrides = { [url]: { caption?, tags?, order?, deleted?, comment? } }` in the JS. Every user action follows the pattern: mutate the local object → re-render affected DOM → persist (POST or localStorage). Server mode does this optimistically and reverts on error; the online/offline badge in the header reflects the server-connection state.

### Backend (`server.py`)

Flask on `127.0.0.1:5000`. Six endpoints:

- `GET /` — serves `links.html`, auto-building it if missing.
- `GET /api/overrides` — returns all rows as `{ url: {...} }`.
- `POST /api/override` — merge-patch a single URL's row. `null` field clears that field. Empty rows are pruned automatically.
- `POST /api/override/clear` — delete a row entirely.
- `POST /api/overrides/bulk` — replace or merge a set of rows.
- `POST /api/overrides/wipe` — nuke the entire table.
- `GET /api/health` — liveness check.

SQLite operates in the default rollback-journal mode. No pool — each request opens a new connection and closes it via the `with` block. This is fine at localhost scale.

### Packaging (`LinksApp.spec`)

PyInstaller onefile build. When frozen, `server.py` detects `sys.frozen` and uses `Path(sys.executable).parent` as its data directory, so the exe reads/writes `overrides.db` and `links.html` next to itself rather than inside the bundled `_MEIxxx` temp dir.

The launcher waits for the port to bind before opening the browser, so double-click users don't get a race-condition "connection refused" tab.

## Extending

- **New domain with embed support:** add a regex + embed URL builder to `classify()` in `build_links_page.py`. `build_static.py` imports it, so both modes pick up the change on next rebuild.
- **New source directory:** add to `SOURCE_DIRS`. New individual file: add to `SOURCE_FILES`.
- **New override field:** add a column to the `overrides` table, update `row_to_obj` in `server.py`, and teach the frontend how to render/edit it. `isModified()` and the static build's baker also need to know about it.
