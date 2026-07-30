"""Build a self-contained static version of links.html for GitHub Pages.

Reads:
  - All *.txt source files (via build_links_page.iter_source_files)
  - Thumbnail cache (.thumb_cache.json)
  - Current DB overrides (overrides.db) — these become the baked-in defaults
    so the deployed site starts in the state you've curated.

Emits:
  - site/index.html   (self-contained; every asset is inline or a CDN URL)

Persistence in the static version uses the browser's localStorage.
Server, DB, comment-modal server calls, and the online/offline badge are
removed. Everything else — filters, tags, numbering, move buttons, edit,
comments, voice input — works identically.
"""
import html
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
SITE_DIR = HERE / 'site'

sys.path.insert(0, str(HERE))
from build_links_page import (
    parse_file, classify, caption_to_tags,
    iter_source_files, load_thumb_cache,
)


def load_db_overrides():
    db_path = HERE / 'overrides.db'
    if not db_path.exists():
        return {}
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = db.execute('SELECT * FROM overrides').fetchall()
    out = {}
    for r in rows:
        obj = {}
        if r['caption']:
            obj['caption'] = r['caption']
        if r['tags']:
            try:
                obj['tags'] = json.loads(r['tags'])
            except Exception:
                pass
        if r['order_value'] is not None:
            obj['order'] = r['order_value']
        if r['deleted']:
            obj['deleted'] = True
        if r['comment']:
            obj['comment'] = r['comment']
        if obj:
            out[r['url']] = obj
    db.close()
    return out


def build_page():
    # 1. Parse all source files
    all_entries = []
    for f, label in iter_source_files():
        all_entries.extend(parse_file(f, source_label=label))

    thumbs = load_thumb_cache()
    JUNK_THUMB = ('pornhub_logo', 'www-static', 'video_converting')

    cards = []
    seen = set()
    for e in all_entries:
        if e['url'] in seen:
            continue
        seen.add(e['url'])
        src_type, embed = classify(e['url'])
        thumb = thumbs.get(e['url']) or None
        if thumb and any(j in thumb for j in JUNK_THUMB):
            thumb = None
        cards.append({**e, 'src_type': src_type, 'embed': embed, 'thumb': thumb})

    embeddable = [c for c in cards if c['embed']]
    lockers = [c for c in cards if not c['embed']]
    combined = embeddable + lockers

    # 2. Bake current DB overrides on top of auto-generated defaults.
    db_overrides = load_db_overrides()
    default_overrides = {}
    for c in combined:
        url = c['url']
        entry = {}
        ov = db_overrides.get(url, {})
        # Effective caption
        cap_default = c.get('caption') or ''
        cap = ov.get('caption') if ov.get('caption') else cap_default
        # Effective tags: user override > caption-word tags
        if 'tags' in ov:
            tags = ov['tags']
        else:
            seen_t = set()
            tags = [t for t in caption_to_tags(cap) if not (t in seen_t or seen_t.add(t))]
        if tags:
            entry['tags'] = tags
        # Effective order: user override > index
        if 'order' in ov:
            entry['order'] = ov['order']
        # Deleted flag
        if ov.get('deleted'):
            entry['deleted'] = True
        # Comment
        if ov.get('comment'):
            entry['comment'] = ov['comment']
        # Caption ONLY baked in if user edited it (so auto-parsed captions stay
        # dynamic — they're already rendered in the card HTML)
        if ov.get('caption'):
            entry['caption'] = ov['caption']
        if entry:
            default_overrides[url] = entry

    by_source = {}
    by_type = {}
    for c in cards:
        by_source[c['source']] = by_source.get(c['source'], 0) + 1
        by_type[c['src_type']] = by_type.get(c['src_type'], 0) + 1

    return combined, default_overrides, by_source, by_type, len(embeddable), len(lockers)


def render_card(c, index):
    cap = html.escape(c['caption']) if c['caption'] else ''
    url = html.escape(c['url'], quote=True)
    src = html.escape(c['source'])
    embed = c['embed']
    thumb_url = c.get('thumb')
    cap_html = (
        f'<div class="caption">{cap}</div>' if cap
        else '<div class="caption muted">(no caption)</div>'
    )
    if embed:
        embed_attr = f'data-embed="{html.escape(embed, quote=True)}"'
        if thumb_url:
            img = (f'<img class="poster" loading="lazy" '
                   f'src="{html.escape(thumb_url, quote=True)}" '
                   f'referrerpolicy="no-referrer" alt="">')
        else:
            img = '<div class="poster placeholder">No preview</div>'
        thumb = (f'<button class="thumb" type="button" {embed_attr}>'
                 f'{img}'
                 f'<span class="play-overlay"><span class="play-icon">&#9654;</span></span>'
                 f'</button>')
    elif thumb_url:
        thumb = (f'<a class="thumb static" href="{url}" target="_blank" rel="noopener noreferrer">'
                 f'<img class="poster" loading="lazy" '
                 f'src="{html.escape(thumb_url, quote=True)}" '
                 f'referrerpolicy="no-referrer" alt="">'
                 f'<span class="play-overlay"><span class="open-icon">&#8599;</span></span>'
                 f'</a>')
    else:
        thumb = '<div class="thumb static"><div class="poster placeholder">No preview</div></div>'

    return f'''
<article class="card" data-url="{url}" data-source="{src}" data-type="{html.escape(c['src_type'])}" data-default-order="{index}">
  <button class="edit-btn" type="button" title="Edit caption / tags" aria-label="Edit">&#9998;</button>
  <span class="pos-badge" title="Position in the current list">#{index + 1}</span>
  {thumb}
  <div class="move-bar">
    <button type="button" data-action="move-top" title="Move to top" aria-label="Move to top">&#8648;</button>
    <button type="button" data-action="move-up" title="Move up one" aria-label="Move up">&#8593;</button>
    <button type="button" data-action="move-down" title="Move down one" aria-label="Move down">&#8595;</button>
    <button type="button" data-action="move-down-10" title="Move down 10" aria-label="Move down 10">&#8659;</button>
    <button type="button" data-action="move-bottom" title="Move to bottom" aria-label="Move to bottom">&#8650;</button>
    <button type="button" data-action="goto-position" title="Move to specific position..." aria-label="Move to position">#</button>
    <button type="button" data-action="comment" class="comment-btn" title="Comment" aria-label="Comment">&#128172;</button>
    <span class="move-spacer"></span>
    <button type="button" data-action="delete" class="delete-btn" title="Delete" aria-label="Delete">&#10005;</button>
    <button type="button" data-action="restore" class="restore-btn" title="Restore" aria-label="Restore">&#8634;</button>
  </div>
  {cap_html}
  <div class="tags"></div>
  <div class="meta">
    <span class="badge type-{html.escape(c['src_type'])}">{html.escape(c['src_type'])}</span>
    <span class="badge src">{src}:{c['line']}</span>
  </div>
  <a class="open" href="{url}" target="_blank" rel="noopener noreferrer">Open &#8599;</a>
  <div class="edit-panel hidden">
    <label>Caption</label>
    <textarea class="edit-caption" rows="2"></textarea>
    <label>Tags <span class="hint">(comma-separated)</span></label>
    <input class="edit-tags" type="text" placeholder="e.g. favorite, tag, note">
    <div class="edit-buttons">
      <button type="button" data-action="reset" class="ghost">Reset card</button>
      <span class="spacer"></span>
      <button type="button" data-action="cancel" class="ghost">Cancel</button>
      <button type="button" data-action="save" class="primary">Save</button>
    </div>
  </div>
</article>'''


CSS = r'''
:root {
  --bg: #0f1115; --card: #1a1d24; --card-border: #2a2e38;
  --fg: #e6e8ef; --muted: #8a90a0; --accent: #ff7a3d;
  --link: #6db5ff; --tag: #4a9eff; --tag-bg: #16273d;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { padding: 14px 20px; border-bottom: 1px solid var(--card-border);
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  position: sticky; top: 0; background: var(--bg); z-index: 10; }
h1 { margin: 0 8px 0 0; font-size: 17px; font-weight: 600; }
.stats { color: var(--muted); font-size: 12px; }
select, input[type=search], input[type=text] {
  background: var(--card); color: var(--fg); border: 1px solid var(--card-border);
  padding: 6px 10px; border-radius: 6px; font-size: 13px; font-family: inherit; }
input[type=search] { min-width: 200px; }
.icon-btn { background: transparent; color: var(--muted); border: 1px solid var(--card-border);
  padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; font-family: inherit; }
.icon-btn:hover { color: var(--fg); border-color: var(--muted); }
.badge-static { background: #16273d; color: #6db5ff; padding: 2px 8px; border-radius: 999px; font-size: 11px; }

.tag-bar { padding: 8px 20px; border-bottom: 1px solid var(--card-border);
  display: flex; gap: 8px; align-items: flex-start; flex-wrap: nowrap;
  position: sticky; top: 62px; background: var(--bg); z-index: 9; max-height: 130px; }
#tag-search { width: 160px; flex-shrink: 0; }
#tag-pills { display: flex; flex-wrap: wrap; gap: 4px; flex: 1;
  max-height: 110px; overflow-y: auto; align-content: flex-start; padding-right: 4px; }
#tag-pills::-webkit-scrollbar { width: 6px; }
#tag-pills::-webkit-scrollbar-thumb { background: var(--card-border); border-radius: 3px; }
.tag-bar-label { color: var(--muted); font-size: 12px; }
.tag-pill { background: transparent; color: var(--tag); border: 1px solid var(--tag-bg);
  padding: 3px 10px; border-radius: 999px; cursor: pointer; font-size: 12px; font-family: inherit; }
.tag-pill:hover { background: var(--tag-bg); }
.tag-pill.active { background: var(--tag); color: #0f1115; border-color: var(--tag); }
.tag-bar .empty { color: var(--muted); font-size: 12px; font-style: italic; }
.link-btn { background: transparent; color: var(--accent); border: 0; cursor: pointer;
  font: inherit; font-size: 12px; text-decoration: underline; padding: 0; }

main { padding: 20px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.card { background: var(--card); border: 1px solid var(--card-border);
  border-radius: 10px; overflow: hidden; display: flex; flex-direction: column; position: relative; }
button.thumb, a.thumb, div.thumb { all: unset; cursor: pointer; aspect-ratio: 16/9;
  background: #000; display: block; position: relative; overflow: hidden; }
div.thumb.static { cursor: default; }
a.thumb.static { cursor: zoom-in; }
.thumb iframe { width: 100%; height: 100%; border: 0; }
.poster { width: 100%; height: 100%; object-fit: cover; display: block;
  transition: transform .25s ease, filter .25s ease; }
.poster.placeholder { display: flex; align-items: center; justify-content: center;
  color: var(--muted); font-size: 12px; background:
  repeating-linear-gradient(45deg, #15171c, #15171c 8px, #1a1d24 8px, #1a1d24 16px); }
button.thumb:hover .poster { transform: scale(1.04); filter: brightness(1.1); }
.play-overlay { position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center; pointer-events: none;
  background: linear-gradient(180deg, transparent 60%, rgba(0,0,0,0.45)); }
.play-overlay .play-icon, .open-icon {
  width: 56px; height: 56px; border-radius: 50%;
  background: rgba(0,0,0,0.55); border: 2px solid rgba(255,255,255,0.85);
  color: #fff; font-size: 22px; display: flex; align-items: center; justify-content: center;
  padding-left: 4px; backdrop-filter: blur(2px);
  transition: background .15s ease, transform .15s ease; }
.open-icon { font-size: 26px; padding-left: 0; }
button.thumb:hover .play-icon, a.thumb:hover .open-icon {
  background: var(--accent); border-color: var(--accent); color: #1a1d24; transform: scale(1.06); }

.edit-btn { position: absolute; top: 8px; right: 8px; z-index: 3;
  background: rgba(0,0,0,0.55); border: 1px solid rgba(255,255,255,0.3);
  color: #fff; width: 28px; height: 28px; border-radius: 50%; cursor: pointer;
  font-size: 14px; display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .15s ease, background .15s ease, border-color .15s ease; }
.card:hover .edit-btn, .card.editing .edit-btn { opacity: 1; }
.edit-btn:hover { background: var(--accent); border-color: var(--accent); color: #1a1d24; }
.pos-badge { position: absolute; top: 8px; left: 8px; z-index: 3;
  background: rgba(0,0,0,0.7); border: 1px solid rgba(255,255,255,0.25);
  color: #fff; padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums;
  pointer-events: none; transition: background .12s ease, color .12s ease, border-color .12s ease; }
.card.modified .pos-badge { background: var(--accent); color: #1a1d24; border-color: var(--accent); }
.card.deleted .pos-badge { opacity: 0.6; }

.caption { padding: 8px 12px 4px; font-size: 13px; word-break: break-word;
  cursor: text; border-radius: 4px; transition: background .12s ease, outline-color .12s ease;
  outline: 1px solid transparent; }
.caption:hover { background: rgba(255,255,255,0.03); }
.caption.editing-inline { outline-color: var(--accent); background: #0f1115;
  padding-top: 6px; padding-bottom: 4px; }
.caption.editing-inline:hover { background: #0f1115; }
.caption.muted { color: var(--muted); font-style: italic; }
.tags { display: flex; gap: 4px; flex-wrap: wrap; padding: 4px 12px 0; }
.tags:empty { padding: 0; }
.tag { font-size: 11px; padding: 1px 8px; border-radius: 999px;
  background: var(--tag-bg); color: var(--tag); cursor: pointer; }
.tag:hover { background: var(--tag); color: #0f1115; }
.meta { display: flex; gap: 6px; flex-wrap: wrap; padding: 6px 12px 8px; }
.badge { font-size: 11px; padding: 2px 7px; border-radius: 999px;
  background: #2a2e38; color: var(--muted); }
.badge.type-pornhub { background: #2c1f00; color: #ffa726; }
.badge.type-xvideos { background: #1a1f3a; color: #6db5ff; }
.badge.type-xhamster { background: #2a1a2a; color: #ff80c0; }
.badge.type-eporner { background: #1d2a1d; color: #7fd17f; }
.badge.type-spankbang { background: #2a1a1a; color: #ff8080; }
.open { color: var(--link); text-decoration: none; padding: 8px 12px 12px;
  font-size: 12px; border-top: 1px solid var(--card-border); margin-top: auto; }
.open:hover { text-decoration: underline; }

.move-bar { display: flex; gap: 4px; padding: 6px 10px 0; align-items: center; }
.move-spacer { flex: 1; }
.move-bar button { background: transparent; border: 1px solid var(--card-border);
  color: var(--muted); width: 26px; height: 24px; border-radius: 5px; cursor: pointer;
  font-size: 13px; line-height: 1; display: flex; align-items: center; justify-content: center;
  font-family: inherit; padding: 0; transition: border-color .12s ease, color .12s ease, background .12s ease; }
.move-bar button:hover { border-color: var(--accent); color: var(--accent);
  background: rgba(255,122,61,0.08); }
.move-bar button:active { background: rgba(255,122,61,0.18); }
.move-bar .delete-btn:hover { border-color: #ff5252; color: #ff5252;
  background: rgba(255,82,82,0.10); }
.move-bar .restore-btn { display: none; }
.move-bar .restore-btn:hover { border-color: #6dd17f; color: #6dd17f;
  background: rgba(109,209,127,0.10); }
.move-bar .comment-btn { position: relative; }
.move-bar .comment-btn.has-comment { border-color: var(--accent); color: var(--accent); }
.move-bar .comment-btn:hover { border-color: var(--link); color: var(--link);
  background: rgba(109,181,255,0.10); }
.card.deleted .move-bar .delete-btn { display: none; }
.card.deleted .move-bar .restore-btn { display: flex; }
body:not(.show-deleted) .card.deleted { display: none !important; }
body.show-deleted .card.deleted { opacity: 0.5; }
body.show-deleted .card.deleted:hover { opacity: 0.9; }

.edit-panel { border-top: 1px solid var(--card-border); padding: 10px 12px;
  background: #15171c; display: flex; flex-direction: column; gap: 6px; }
.edit-panel label { color: var(--muted); font-size: 11px; margin-top: 4px; }
.edit-panel .hint { font-style: italic; opacity: 0.7; }
.edit-panel textarea, .edit-panel input[type=text] {
  background: #0f1115; color: var(--fg); border: 1px solid var(--card-border);
  padding: 6px 8px; border-radius: 6px; font: inherit; font-size: 13px;
  width: 100%; resize: vertical; }
.edit-panel textarea:focus, .edit-panel input[type=text]:focus {
  outline: none; border-color: var(--accent); }
.edit-buttons { display: flex; gap: 4px; align-items: center; margin-top: 4px; }
.edit-buttons button { background: var(--card); color: var(--fg);
  border: 1px solid var(--card-border); border-radius: 6px; padding: 5px 10px;
  cursor: pointer; font: inherit; font-size: 12px; }
.edit-buttons button:hover { border-color: var(--muted); }
.edit-buttons .primary { background: var(--accent); color: #1a1d24; border-color: var(--accent);
  font-weight: 600; }
.edit-buttons .primary:hover { filter: brightness(1.1); }
.edit-buttons .ghost { background: transparent; }
.edit-buttons .spacer { flex: 1; }

.hidden { display: none !important; }

.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  background: var(--card); border: 1px solid var(--accent); color: var(--fg);
  padding: 10px 16px; border-radius: 8px; font-size: 13px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6); z-index: 100;
  opacity: 0; transition: opacity .2s ease; pointer-events: none; }
.toast.show { opacity: 1; pointer-events: auto; }

.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.65);
  display: flex; align-items: center; justify-content: center; z-index: 200;
  opacity: 0; pointer-events: none; transition: opacity .15s ease; }
.modal-backdrop.show { opacity: 1; pointer-events: auto; }
.modal { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px;
  width: 92vw; max-width: 600px; max-height: 88vh; display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(0,0,0,0.7); overflow: hidden; }
.modal-head { padding: 14px 18px; border-bottom: 1px solid var(--card-border);
  display: flex; align-items: center; gap: 10px; }
.modal-head h3 { margin: 0; font-size: 15px; font-weight: 600; flex: 1; }
.modal-head .modal-sub { color: var(--muted); font-size: 12px; flex: 999;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
.modal-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 8px;
  flex: 1; overflow: auto; }
.modal-body textarea { background: #0f1115; color: var(--fg); border: 1px solid var(--card-border);
  padding: 10px 12px; border-radius: 6px; font: inherit; font-size: 13px;
  resize: vertical; min-height: 160px; width: 100%; }
.modal-body textarea:focus { outline: none; border-color: var(--accent); }
.modal-toolbar { display: flex; gap: 6px; align-items: center; }
.mic-btn { background: var(--card); border: 1px solid var(--card-border);
  color: var(--fg); padding: 6px 12px; border-radius: 6px; cursor: pointer;
  font: inherit; font-size: 13px; display: flex; align-items: center; gap: 6px; }
.mic-btn:hover { border-color: var(--muted); }
.mic-btn.recording { background: #2a1a1a; color: #ff5252; border-color: #ff5252;
  animation: pulse 1.2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }
.modal-foot { padding: 12px 18px; border-top: 1px solid var(--card-border);
  display: flex; gap: 8px; justify-content: flex-end; align-items: center; }
.modal-foot .spacer { flex: 1; }
.modal-foot button { background: var(--card); color: var(--fg);
  border: 1px solid var(--card-border); border-radius: 6px; padding: 7px 14px;
  cursor: pointer; font: inherit; font-size: 13px; }
.modal-foot button:hover { border-color: var(--muted); }
.modal-foot button.primary { background: var(--accent); color: #1a1d24;
  border-color: var(--accent); font-weight: 600; }
.modal-foot button.primary:hover { filter: brightness(1.1); }
.modal-foot button.ghost { background: transparent; }
.modal-foot button.danger { color: #ff5252; }
'''


JS = r'''
// Static localStorage-only version. No server, no fetch, no health checks.
const STORAGE_KEY = 'videolinkcards_overrides_v1';

let defaultOverrides = {};
try {
  const el = document.getElementById('default-overrides');
  if (el) defaultOverrides = JSON.parse(el.textContent || '{}');
} catch {}

function loadOverrides() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}
function saveOverrides() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(overrides));
}
let overrides = loadOverrides();
const activeTags = new Set();

const cards = Array.from(document.querySelectorAll('.card'));
const grid = document.getElementById('grid');

function getOverride(url) { return overrides[url] || {}; }
function getDefault(url) { return defaultOverrides[url] || {}; }

// Effective helpers: user override > baked default > (parsed HTML for caption)
function effectiveTags(url) {
  const ov = overrides[url];
  if (ov && Array.isArray(ov.tags)) return ov.tags;
  const def = defaultOverrides[url];
  return (def && def.tags) ? def.tags : [];
}
function effectiveCaption(url, capEl) {
  const ov = overrides[url];
  if (ov && ov.caption != null && ov.caption !== '') return ov.caption;
  const def = defaultOverrides[url];
  if (def && def.caption) return def.caption;
  if (!capEl) return '';
  return capEl.dataset.original || capEl.textContent;
}
function effectiveComment(url) {
  const ov = overrides[url];
  if (ov && 'comment' in ov) return ov.comment || '';
  const def = defaultOverrides[url];
  return (def && def.comment) ? def.comment : '';
}
function effectiveDeleted(url) {
  const ov = overrides[url];
  if (ov && 'deleted' in ov) return !!ov.deleted;
  const def = defaultOverrides[url];
  return !!(def && def.deleted);
}
function effectiveOrder(card) {
  const url = card.dataset.url;
  const ov = overrides[url];
  if (ov && typeof ov.order === 'number') return ov.order;
  const def = defaultOverrides[url];
  if (def && typeof def.order === 'number') return def.order;
  return parseFloat(card.dataset.defaultOrder);
}

function isModified(url) {
  const o = overrides[url];
  if (!o) return false;
  return (o.caption != null) || (o.tags && o.tags.length) || (typeof o.order === 'number')
      || (o.deleted === true) || (o.comment != null && o.comment !== '');
}

function setOverride(url, patch) {
  const o = overrides[url] || {};
  for (const [k, v] of Object.entries(patch)) {
    if (v === null || (Array.isArray(v) && v.length === 0 && !(k in o))) delete o[k];
    else o[k] = v;
  }
  if (Object.keys(o).length === 0) delete overrides[url];
  else overrides[url] = o;
  saveOverrides();
}
function clearOverride(url) { delete overrides[url]; saveOverrides(); }

function applyOverridesToCard(card) {
  const url = card.dataset.url;
  const capEl = card.querySelector('.caption');
  if (!capEl.dataset.original) capEl.dataset.original = capEl.textContent;
  const cap = effectiveCaption(url, capEl);
  if (cap) {
    capEl.textContent = cap;
    capEl.classList.remove('muted');
  } else {
    capEl.textContent = capEl.dataset.original;
    if (capEl.dataset.original === '(no caption)') capEl.classList.add('muted');
  }
  const tagsEl = card.querySelector('.tags');
  tagsEl.innerHTML = '';
  for (const t of effectiveTags(url)) {
    const chip = document.createElement('span');
    chip.className = 'tag'; chip.dataset.tag = t; chip.textContent = t;
    chip.title = 'Filter by this tag';
    tagsEl.appendChild(chip);
  }
  card.classList.toggle('modified', isModified(url));
  card.classList.toggle('deleted', effectiveDeleted(url));
  const cmtBtn = card.querySelector('.comment-btn');
  if (cmtBtn) cmtBtn.classList.toggle('has-comment', !!effectiveComment(url));
}

function applySort() {
  const arr = Array.from(grid.querySelectorAll('.card'));
  arr.sort((a, b) => effectiveOrder(a) - effectiveOrder(b));
  for (const c of arr) grid.appendChild(c);
}
function updateAllPositions() {
  const visible = Array.from(grid.querySelectorAll('.card:not(.hidden)'));
  for (let i = 0; i < visible.length; i++) {
    const badge = visible[i].querySelector('.pos-badge');
    if (badge) badge.textContent = '#' + (i + 1);
  }
}
function orderForPosition(card, target) {
  const visibleCards = Array.from(grid.querySelectorAll('.card:not(.hidden)'));
  const M = visibleCards.length;
  if (M <= 1) return effectiveOrder(card);
  const others = visibleCards.filter(c => c !== card);
  const orders = others.map(effectiveOrder);
  if (target <= 1) return orders[0] - 1;
  if (target >= M) return orders[orders.length - 1] + 1;
  return (orders[target - 2] + orders[target - 1]) / 2;
}

function updateModifiedCount() {
  const n = Object.keys(overrides).filter(u => isModified(u)).length;
  document.getElementById('modified-count').textContent = n;
}
function updateDeletedCount() {
  const n = cards.filter(c => effectiveDeleted(c.dataset.url)).length;
  document.getElementById('deleted-count').textContent = n;
  const toggle = document.getElementById('toggle-deleted');
  toggle.classList.toggle('hidden', n === 0);
  const showing = document.body.classList.contains('show-deleted');
  toggle.textContent = (showing ? 'Hide deleted (' : 'Show deleted (') + n + ')';
}

function rebuildTagBar() {
  const allTags = new Map();
  for (const card of cards) {
    for (const t of effectiveTags(card.dataset.url))
      allTags.set(t, (allTags.get(t) || 0) + 1);
  }
  const pillBox = document.getElementById('tag-pills');
  pillBox.innerHTML = '';
  if (allTags.size === 0) {
    pillBox.innerHTML = '<span class="empty">No tags yet — click the &#9998; icon on a card to add some.</span>';
  } else {
    const sorted = [...allTags.entries()].sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1];
      return a[0].localeCompare(b[0]);
    });
    const tagFilterStr = (document.getElementById('tag-search').value || '').trim().toLowerCase();
    for (const [tag, count] of sorted) {
      if (tagFilterStr && !tag.includes(tagFilterStr)) continue;
      const pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'tag-pill';
      pill.dataset.tag = tag;
      pill.textContent = `${tag} (${count})`;
      if (activeTags.has(tag)) pill.classList.add('active');
      pill.addEventListener('click', () => {
        if (activeTags.has(tag)) activeTags.delete(tag); else activeTags.add(tag);
        rebuildTagBar(); applyFilter();
      });
      pillBox.appendChild(pill);
    }
    if (pillBox.children.length === 0)
      pillBox.innerHTML = '<span class="empty">No tags match this search.</span>';
  }
  document.getElementById('clear-tags').classList.toggle('hidden', activeTags.size === 0);
}

function applyFilter() {
  const q = document.getElementById('q');
  const srcSel = document.getElementById('src');
  const typeSel = document.getElementById('type');
  const term = q.value.trim().toLowerCase();
  const src = srcSel.value;
  const type = typeSel.value;
  for (const c of cards) {
    const cap = (c.querySelector('.caption').textContent || '').toLowerCase();
    const url = (c.dataset.url || '').toLowerCase();
    const cardTags = Array.from(c.querySelectorAll('.tag')).map(t => t.dataset.tag);
    const tagText = cardTags.join(' ').toLowerCase();
    const matchTerm = !term || cap.includes(term) || url.includes(term) || tagText.includes(term);
    const matchSrc = !src || c.dataset.source === src;
    const matchType = !type || c.dataset.type === type;
    let matchTags = true;
    if (activeTags.size > 0) {
      for (const t of activeTags) { if (!cardTags.includes(t)) { matchTags = false; break; } }
    }
    c.classList.toggle('hidden', !(matchTerm && matchSrc && matchType && matchTags));
  }
  updateAllPositions();
}

function toast(msg, undoFn) {
  const t = document.getElementById('toast');
  t.innerHTML = '';
  t.appendChild(document.createTextNode(msg));
  if (undoFn) {
    t.appendChild(document.createTextNode(' '));
    const btn = document.createElement('button');
    btn.className = 'link-btn'; btn.textContent = 'Undo';
    btn.addEventListener('click', () => { undoFn(); t.classList.remove('show'); });
    t.appendChild(btn);
  }
  t.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => t.classList.remove('show'), undoFn ? 6000 : 2200);
}

// ---------- Click handlers ----------
document.addEventListener('click', (e) => {
  const cap = e.target.closest('.caption');
  if (cap && !cap.isContentEditable
      && !e.target.closest('.edit-panel, button, a')
      && cap.parentElement && cap.parentElement.classList.contains('card')) {
    startInlineCaptionEdit(cap); return;
  }
  const tagChip = e.target.closest('.tag');
  if (tagChip && tagChip.dataset.tag && !tagChip.closest('.tag-bar')) {
    const t = tagChip.dataset.tag;
    if (activeTags.has(t)) activeTags.delete(t); else activeTags.add(t);
    rebuildTagBar(); applyFilter();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  const editBtn = e.target.closest('.edit-btn');
  if (editBtn) {
    const card = editBtn.closest('.card');
    const panel = card.querySelector('.edit-panel');
    const url = card.dataset.url;
    const capEl = card.querySelector('.caption');
    panel.querySelector('.edit-caption').value = effectiveCaption(url, capEl);
    panel.querySelector('.edit-tags').value = effectiveTags(url).join(', ');
    panel.classList.toggle('hidden');
    card.classList.toggle('editing', !panel.classList.contains('hidden'));
    if (!panel.classList.contains('hidden'))
      panel.querySelector('.edit-caption').focus();
    return;
  }
  const thumbBtn = e.target.closest('button.thumb');
  if (thumbBtn) {
    const url = thumbBtn.dataset.embed;
    if (!url) return;
    const wrap = document.createElement('div');
    wrap.className = 'thumb'; wrap.style.aspectRatio = '16/9';
    const iframe = document.createElement('iframe');
    iframe.src = url;
    iframe.allow = 'autoplay; fullscreen'; iframe.allowFullscreen = true;
    iframe.referrerPolicy = 'no-referrer';
    wrap.appendChild(iframe);
    thumbBtn.replaceWith(wrap);
    return;
  }
  const actionBtn = e.target.closest('[data-action]');
  if (actionBtn) { handleEditAction(actionBtn); return; }
});

function handleEditAction(actionBtn) {
  const action = actionBtn.dataset.action;
  const card = actionBtn.closest('.card');
  const panel = card.querySelector('.edit-panel');
  const url = card.dataset.url;

  if (action === 'cancel') {
    panel.classList.add('hidden'); card.classList.remove('editing'); return;
  }
  if (action === 'save') {
    const cap = panel.querySelector('.edit-caption').value.trim();
    const tagsRaw = panel.querySelector('.edit-tags').value;
    const tags = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);
    setOverride(url, { caption: cap || null, tags });
    applyOverridesToCard(card); rebuildTagBar(); applyFilter();
    updateModifiedCount();
    panel.classList.add('hidden'); card.classList.remove('editing');
    toast('Saved.'); return;
  }
  if (action === 'reset') {
    clearOverride(url);
    applyOverridesToCard(card); rebuildTagBar(); applyFilter(); applySort();
    updateModifiedCount(); updateDeletedCount();
    panel.classList.add('hidden'); card.classList.remove('editing');
    toast('Card reset to defaults.'); return;
  }
  if (action === 'delete') {
    const prev = overrides[url] ? { ...overrides[url] } : null;
    setOverride(url, { deleted: true });
    applyOverridesToCard(card); applyFilter();
    updateModifiedCount(); updateDeletedCount();
    toast('Card deleted.', () => {
      if (prev) overrides[url] = prev; else delete overrides[url];
      saveOverrides();
      applyOverridesToCard(card); applyFilter();
      updateModifiedCount(); updateDeletedCount();
    }); return;
  }
  if (action === 'restore') {
    setOverride(url, { deleted: false });
    applyOverridesToCard(card); applyFilter();
    updateModifiedCount(); updateDeletedCount();
    toast('Restored.'); return;
  }
  if (action === 'comment') { openCommentModal(card); return; }

  if (action === 'move-down-10') {
    const visibleCards = Array.from(grid.querySelectorAll('.card:not(.hidden)'));
    const idx = visibleCards.indexOf(card);
    const M = visibleCards.length;
    const targetIdx = Math.min(idx + 10, M - 1);
    if (targetIdx > idx) {
      setOverride(url, { order: orderForPosition(card, targetIdx + 1) });
      applyOverridesToCard(card); applySort(); updateAllPositions();
      updateModifiedCount();
    }
    return;
  }
  if (action === 'goto-position') {
    const visibleCards = Array.from(grid.querySelectorAll('.card:not(.hidden)'));
    const idx = visibleCards.indexOf(card);
    const M = visibleCards.length;
    const currentPos = idx + 1;
    const input = prompt(`Move to which position? (1–${M})`, String(currentPos));
    if (input === null) return;
    const target = parseInt(input.trim(), 10);
    if (!Number.isInteger(target) || target < 1 || target > M) {
      toast(`Invalid position — enter a number between 1 and ${M}.`); return;
    }
    if (target === currentPos) return;
    setOverride(url, { order: orderForPosition(card, target) });
    applyOverridesToCard(card); applySort(); updateAllPositions();
    updateModifiedCount(); return;
  }
  if (action.startsWith('move-')) {
    const visibleCards = Array.from(grid.querySelectorAll('.card:not(.hidden)'));
    const idx = visibleCards.indexOf(card);
    if (action === 'move-up' && idx > 0) swapOrder(card, visibleCards[idx - 1]);
    else if (action === 'move-down' && idx < visibleCards.length - 1) swapOrder(card, visibleCards[idx + 1]);
    else if (action === 'move-top') {
      const allOrders = visibleCards.map(effectiveOrder);
      setOverride(url, { order: Math.min(...allOrders) - 1 });
    } else if (action === 'move-bottom') {
      const allOrders = visibleCards.map(effectiveOrder);
      setOverride(url, { order: Math.max(...allOrders) + 1 });
    }
    applyOverridesToCard(card); applySort(); updateAllPositions();
    updateModifiedCount(); return;
  }
}

function swapOrder(a, b) {
  const oa = effectiveOrder(a);
  const ob = effectiveOrder(b);
  setOverride(a.dataset.url, { order: ob });
  setOverride(b.dataset.url, { order: oa });
  applyOverridesToCard(a); applyOverridesToCard(b);
}

// ---------- Inline caption edit ----------
function startInlineCaptionEdit(cap) {
  const card = cap.closest('.card');
  const url = card.dataset.url;
  const current = effectiveCaption(url, cap);
  cap.classList.remove('muted');
  cap.textContent = current;
  cap.contentEditable = 'true';
  cap.classList.add('editing-inline');
  cap.focus();
  const range = document.createRange();
  range.selectNodeContents(cap);
  const sel = window.getSelection();
  sel.removeAllRanges(); sel.addRange(range);
}
function commitInlineCaption(cap, save) {
  const card = cap.closest('.card');
  const url = card.dataset.url;
  cap.contentEditable = 'false';
  cap.classList.remove('editing-inline');
  if (save) {
    const newText = cap.textContent.trim();
    setOverride(url, { caption: newText || null });
    applyOverridesToCard(card); updateModifiedCount();
  } else {
    applyOverridesToCard(card);
  }
}
document.addEventListener('keydown', (e) => {
  const el = document.activeElement;
  if (!el || !el.classList || !el.classList.contains('editing-inline')) return;
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commitInlineCaption(el, true); el.blur(); }
  else if (e.key === 'Escape') { e.preventDefault(); commitInlineCaption(el, false); el.blur(); }
});
document.addEventListener('focusout', (e) => {
  const el = e.target;
  if (el && el.classList && el.classList.contains('editing-inline'))
    commitInlineCaption(el, true);
});

// ---------- Comment modal + voice input ----------
const commentModal = document.getElementById('comment-modal-backdrop');
const commentText = document.getElementById('comment-text');
const commentSub = document.getElementById('comment-modal-sub');
let commentCardUrl = null;
function openCommentModal(card) {
  commentCardUrl = card.dataset.url;
  const cap = card.querySelector('.caption').textContent;
  commentSub.textContent = cap;
  commentSub.title = commentCardUrl;
  commentText.value = effectiveComment(commentCardUrl);
  commentModal.classList.add('show');
  setTimeout(() => commentText.focus(), 50);
}
function closeCommentModal() { commentModal.classList.remove('show'); commentCardUrl = null; stopRecording(); }
document.getElementById('comment-cancel').addEventListener('click', closeCommentModal);
commentModal.addEventListener('click', (e) => { if (e.target === commentModal) closeCommentModal(); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && commentModal.classList.contains('show')) closeCommentModal();
});
document.getElementById('comment-save').addEventListener('click', () => {
  if (!commentCardUrl) return;
  setOverride(commentCardUrl, { comment: commentText.value.trim() || null });
  const card = cards.find(c => c.dataset.url === commentCardUrl);
  if (card) applyOverridesToCard(card);
  updateModifiedCount(); closeCommentModal(); toast('Comment saved.');
});
document.getElementById('comment-delete').addEventListener('click', () => {
  if (!commentCardUrl) return;
  setOverride(commentCardUrl, { comment: null });
  const card = cards.find(c => c.dataset.url === commentCardUrl);
  if (card) applyOverridesToCard(card);
  updateModifiedCount(); closeCommentModal(); toast('Comment deleted.');
});

let recognizer = null, recognizing = false, recognizerBaseText = '';
function getRecognizer() {
  if (recognizer) return recognizer;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  recognizer = new SR();
  recognizer.continuous = true;
  recognizer.interimResults = true;
  recognizer.lang = navigator.language || 'en-US';
  recognizer.onresult = (e) => {
    let finalText = '', interim = '';
    for (let i = 0; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t;
      else interim += t;
    }
    const combined = (recognizerBaseText
      + (recognizerBaseText && (finalText || interim) && !recognizerBaseText.endsWith(' ') ? ' ' : '')
      + finalText + interim).trimStart();
    commentText.value = combined;
    if (finalText) recognizerBaseText = combined;
  };
  recognizer.onerror = (e) => {
    document.getElementById('mic-status').textContent = 'Mic error: ' + (e.error || 'unknown');
    stopRecording();
  };
  recognizer.onend = () => {
    if (recognizing) { try { recognizer.start(); } catch { stopRecording(); } }
  };
  return recognizer;
}
function startRecording() {
  const r = getRecognizer();
  if (!r) { document.getElementById('mic-status').textContent = 'Voice input not supported in this browser (try Chrome).'; return; }
  recognizerBaseText = commentText.value;
  recognizing = true;
  document.getElementById('mic-btn').classList.add('recording');
  document.querySelector('#mic-btn .mic-label').textContent = 'Stop';
  document.getElementById('mic-status').textContent = 'Listening...';
  try { r.start(); } catch (e) {}
}
function stopRecording() {
  if (recognizer && recognizing) { try { recognizer.stop(); } catch {} }
  recognizing = false;
  document.getElementById('mic-btn').classList.remove('recording');
  document.querySelector('#mic-btn .mic-label').textContent = 'Voice input';
  document.getElementById('mic-status').textContent = '';
}
document.getElementById('mic-btn').addEventListener('click', () => {
  if (recognizing) stopRecording(); else startRecording();
});

// ---------- Header controls ----------
document.getElementById('q').addEventListener('input', applyFilter);
document.getElementById('src').addEventListener('change', applyFilter);
document.getElementById('type').addEventListener('change', applyFilter);
document.getElementById('clear-tags').addEventListener('click', () => {
  activeTags.clear(); rebuildTagBar(); applyFilter();
});
document.getElementById('tag-search').addEventListener('input', rebuildTagBar);
document.getElementById('toggle-deleted').addEventListener('click', () => {
  document.body.classList.toggle('show-deleted');
  updateDeletedCount();
});

// Export / Import / Reset all
document.getElementById('export-btn').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(overrides, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'videolinkcards_overrides.json';
  a.click(); URL.revokeObjectURL(a.href);
  toast('Exported overrides JSON.');
});
document.getElementById('import-btn').addEventListener('click', () => {
  document.getElementById('import-file').click();
});
document.getElementById('import-file').addEventListener('change', async (e) => {
  const file = e.target.files[0]; if (!file) return;
  try {
    const incoming = JSON.parse(await file.text());
    if (typeof incoming !== 'object' || Array.isArray(incoming))
      throw new Error('Expected an object');
    overrides = { ...overrides, ...incoming };
    saveOverrides();
    cards.forEach(applyOverridesToCard);
    rebuildTagBar(); applySort(); applyFilter();
    updateModifiedCount(); updateDeletedCount();
    toast(`Imported ${Object.keys(incoming).length} entries.`);
  } catch (err) { toast('Import failed: ' + err.message); }
  finally { e.target.value = ''; }
});
document.getElementById('reset-all-btn').addEventListener('click', () => {
  if (!confirm('Delete ALL your local edits (captions, tags, order, comments)? Baked-in defaults remain.')) return;
  overrides = {};
  saveOverrides();
  activeTags.clear();
  cards.forEach(applyOverridesToCard);
  rebuildTagBar(); applySort(); applyFilter();
  updateModifiedCount(); updateDeletedCount();
  toast('Local edits cleared.');
});

// ---------- Initial setup ----------
cards.forEach(applyOverridesToCard);
applySort();
rebuildTagBar();
applyFilter();
updateModifiedCount();
updateDeletedCount();
'''


def main():
    combined, default_overrides, by_source, by_type, n_embed, n_lockers = build_page()

    cards_html = '\n'.join(render_card(c, i) for i, c in enumerate(combined))
    source_options = ''.join(
        f'<option value="{html.escape(s)}">{html.escape(s)} ({n})</option>'
        for s, n in sorted(by_source.items())
    )
    type_options = ''.join(
        f'<option value="{html.escape(t)}">{html.escape(t)} ({n})</option>'
        for t, n in sorted(by_type.items(), key=lambda x: -x[1])
    )

    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>videolinkcards</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>videolinkcards</h1>
  <span class="stats">{len(combined)} unique ({n_embed} embeddable · {n_lockers} link-only)
    · <span id="modified-count">0</span> edited
    · <span id="deleted-count">0</span> deleted</span>
  <span class="badge-static" title="Edits persist in your browser's localStorage">static · localStorage</span>
  <button class="icon-btn hidden" id="toggle-deleted" title="Toggle visibility of deleted cards">Show deleted</button>
  <input type="search" id="q" placeholder="Search caption / url / tag">
  <select id="src"><option value="">All files</option>{source_options}</select>
  <select id="type"><option value="">All sources</option>{type_options}</select>
  <span style="flex:1"></span>
  <button class="icon-btn" id="export-btn" title="Download your local edits as JSON">Export</button>
  <button class="icon-btn" id="import-btn" title="Load edits from a JSON file">Import</button>
  <button class="icon-btn" id="reset-all-btn" title="Clear local edits">Reset all</button>
  <input type="file" id="import-file" accept="application/json" class="hidden">
</header>
<div class="tag-bar">
  <span class="tag-bar-label">Tags:</span>
  <input type="search" id="tag-search" placeholder="Filter tags...">
  <div class="tag-pills" id="tag-pills"></div>
  <button class="link-btn hidden" id="clear-tags">Clear filter</button>
</div>
<script id="default-overrides" type="application/json">{json.dumps(default_overrides, separators=(",", ":"))}</script>
<main id="grid">
{cards_html}
</main>
<div class="toast" id="toast"></div>
<div class="modal-backdrop" id="comment-modal-backdrop">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="comment-modal-title">
    <div class="modal-head">
      <h3 id="comment-modal-title">Comment</h3>
      <span class="modal-sub" id="comment-modal-sub"></span>
    </div>
    <div class="modal-body">
      <div class="modal-toolbar">
        <button class="mic-btn" id="mic-btn" type="button" title="Toggle voice input">
          <span class="mic-icon">&#127908;</span><span class="mic-label">Voice input</span>
        </button>
        <span class="modal-sub" id="mic-status"></span>
      </div>
      <textarea id="comment-text" placeholder="Type or dictate notes about this card..."></textarea>
    </div>
    <div class="modal-foot">
      <button type="button" id="comment-delete" class="ghost danger">Delete comment</button>
      <span class="spacer"></span>
      <button type="button" id="comment-cancel" class="ghost">Cancel</button>
      <button type="button" id="comment-save" class="primary">Save</button>
    </div>
  </div>
</div>
<script>{JS}</script>
</body>
</html>
'''

    SITE_DIR.mkdir(exist_ok=True)
    out = SITE_DIR / 'index.html'
    out.write_text(page, encoding='utf-8')
    print(f'Wrote {out} ({len(combined)} cards, {len(default_overrides)} baked overrides)')


if __name__ == '__main__':
    main()
