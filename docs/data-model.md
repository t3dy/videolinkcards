# Data model

## The card

A card represents one URL. Every card has these dimensions:

| Dimension | Source when unedited                     | Source when edited                       |
|-----------|------------------------------------------|-------------------------------------------|
| `caption` | text on same line before URL, or previous non-blank line | user override in DB / localStorage |
| `tags`    | words extracted from the caption (minus stop-words) | user override — replaces defaults entirely |
| `order`   | index in the deduped combined list       | user override — a float, sort ascending  |
| `deleted` | `false`                                  | `true` if user soft-deleted              |
| `comment` | none                                     | free-form text set by user               |

## Effective values

Precedence: **user override > default (parsed / computed) > empty**.

- `caption`: If the user override is a non-empty string, use it. Otherwise use the caption parsed from the source file. If neither, the card renders "(no caption)" in a muted style.
- `tags`: If the user override array is present (even `[]`), use it. Otherwise use auto-generated tags. Editing tags is all-or-nothing — the override replaces the default set. Reset the card to fall back to defaults.
- `order`: If a numeric override exists, use it. Otherwise use `data-default-order` from the HTML (assigned at build time — embeddable cards get 0..N, link-only cards get N+1..N+M).
- `deleted`: Boolean override wins; default is not deleted.
- `comment`: Present override wins; default is none.

## Order arithmetic

Order values are floats so cards can be inserted between existing ones without renumbering everything.

- **Move to top:** `min(visible_orders) - 1`
- **Move to bottom:** `max(visible_orders) + 1`
- **Move up / move down:** swap orders with the adjacent visible card
- **Move down 10:** compute the target visible index (current + 10, clipped to end) and slot between the cards at that position and the next
- **Move to position N:** slot between the visible cards currently at positions N-1 and N (excluding the moving card itself)

Positions displayed on cards (`#42`) are 1-based indexes into the *currently visible* list — they update as you filter or reorder.

## SQLite schema (`overrides.db`)

```sql
CREATE TABLE overrides (
    url         TEXT PRIMARY KEY,
    caption     TEXT,             -- NULL = use default
    tags        TEXT,             -- JSON array string, NULL = use default
    order_value REAL,             -- NULL = use default
    deleted     INTEGER NOT NULL DEFAULT 0,
    comment     TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_overrides_deleted ON overrides(deleted);
```

Rows with no user data are pruned automatically by the API. The server never inserts a row just because a URL exists — it only creates one when there's an edit to store.

## localStorage schema (static mode)

Same object shape as the DB, stored as a single JSON blob under `videolinkcards_overrides_v1`:

```json
{
  "https://example.com/video/abc": {
    "caption": "renamed by user",
    "tags": ["a", "b"],
    "order": 42.5,
    "comment": "note from voice input"
  },
  "https://example.com/video/xyz": {
    "deleted": true
  }
}
```

## API contract

All API endpoints accept and return JSON.

### `GET /api/overrides`
Return every non-empty override as `{ url: object }`. Fields omitted from an object are unset for that URL.

### `POST /api/override`
Merge-patch a single URL's row. Body:

```json
{
  "url": "https://example.com/video/abc",
  "caption": "new title",
  "tags": ["one", "two"],
  "order": 12.5,
  "deleted": false,
  "comment": "..."
}
```

Only the fields you send are updated. To clear a specific field, send `null` (e.g. `{"comment": null}`). If the resulting row has no user data, the server prunes it automatically.

### `POST /api/override/clear`
Delete a row entirely. Body: `{"url": "..."}`.

### `POST /api/overrides/bulk`
Merge or replace a bulk map. Body:

```json
{
  "overrides": { "https://...": { "caption": "..." }, ... },
  "mode": "merge"    // or "replace"
}
```

### `POST /api/overrides/wipe`
Delete every row. Body optional.

### `GET /api/health`
Returns `{"ok": true, "overrides": <count>, "db": "<path>"}`. The frontend polls this every 5 s to update the online/offline badge.

## Notes on determinism

`data-default-order` is assigned at build time from the position of the card in the combined `(embeddable + lockers)` list. If you rebuild after adding new source files, existing cards keep their old numeric positions because their URLs are still first-seen in the same order (parser walks sources in a stable sorted order and dedupes by URL). New cards get appended at the end. So user-set order values remain meaningful across rebuilds — nothing gets shuffled underneath your reorderings.
