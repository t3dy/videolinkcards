"""Local Flask server for the links page.

Persists user overrides (caption, tags, order, deleted, comment) in SQLite at
D:\\p\\overrides.db. Serves links.html (built by build_links_page.py).

Run:  python server.py     →  http://localhost:5000
"""
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort

# When packaged as a PyInstaller onefile exe, sys.executable is the .exe
# and Path(__file__).parent lives inside a temp _MEIxxx bundle. We want the
# DB and HTML next to the .exe (i.e., D:\p\).
if getattr(sys, 'frozen', False):
    HERE = Path(sys.executable).parent
else:
    HERE = Path(__file__).parent

DB_PATH = HERE / 'overrides.db'
HTML_PATH = HERE / 'links.html'

app = Flask(__name__)


# ---------- DB ----------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    with get_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS overrides (
                url        TEXT PRIMARY KEY,
                caption    TEXT,
                tags       TEXT,      -- JSON array string, NULL = use defaults
                order_value REAL,     -- NULL = use defaults
                deleted    INTEGER NOT NULL DEFAULT 0,
                comment    TEXT,      -- free-form notes
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_overrides_deleted ON overrides(deleted)')


def row_to_obj(row):
    """Convert a sqlite row to the same shape the frontend expects."""
    if row is None:
        return None
    out = {}
    if row['caption'] is not None:
        out['caption'] = row['caption']
    if row['tags'] is not None:
        try:
            out['tags'] = json.loads(row['tags'])
        except Exception:
            out['tags'] = []
    if row['order_value'] is not None:
        out['order'] = row['order_value']
    if row['deleted']:
        out['deleted'] = True
    if row['comment'] is not None and row['comment'] != '':
        out['comment'] = row['comment']
    return out


def is_empty_override(obj):
    """True if an override object has no user data."""
    if not obj:
        return True
    return not any(k in obj for k in ('caption', 'tags', 'order', 'deleted', 'comment'))


# ---------- Routes ----------

@app.route('/')
def index():
    if not HTML_PATH.exists():
        # Auto-build the page on first run if it's missing.
        # When frozen, call the module directly (sys.executable is the .exe).
        try:
            sys.path.insert(0, str(HERE))
            from build_links_page import main as build_main
            build_main()
        except Exception as e:
            return (f'<h1>links.html is missing and auto-build failed</h1>'
                    f'<pre>{e}</pre>'
                    f'<p>Run <code>python build_links_page.py</code> in {HERE} to build it.</p>',
                    500)
    return send_file(HTML_PATH)


@app.route('/api/overrides', methods=['GET'])
def get_overrides():
    """Return all overrides as {url: {...}} object."""
    with get_db() as db:
        rows = db.execute('SELECT * FROM overrides').fetchall()
    result = {}
    for r in rows:
        obj = row_to_obj(r)
        if obj:
            result[r['url']] = obj
    return jsonify(result)


@app.route('/api/override', methods=['POST'])
def upsert_override():
    """Merge-patch a single override. Body: {url, caption?, tags?, order?, deleted?, comment?}.

    Fields present in body are written; absent fields are left unchanged.
    Use null to clear an individual field (e.g. {caption: null}).
    """
    body = request.get_json(force=True) or {}
    url = body.get('url')
    if not url or not isinstance(url, str):
        abort(400, 'url required')

    fields = {}
    if 'caption' in body:
        fields['caption'] = body['caption'] or None
    if 'tags' in body:
        v = body['tags']
        if v is None:
            fields['tags'] = None
        else:
            if not isinstance(v, list):
                abort(400, 'tags must be a list')
            fields['tags'] = json.dumps(v)
    if 'order' in body:
        v = body['order']
        fields['order_value'] = float(v) if v is not None else None
    if 'deleted' in body:
        fields['deleted'] = 1 if body['deleted'] else 0
    if 'comment' in body:
        fields['comment'] = body['comment'] or None

    if not fields:
        abort(400, 'no fields to set')

    with get_db() as db:
        existing = db.execute('SELECT * FROM overrides WHERE url = ?', (url,)).fetchone()
        if existing:
            sets = ', '.join(f'{k} = ?' for k in fields)
            sets += ", updated_at = datetime('now')"
            params = list(fields.values()) + [url]
            db.execute(f'UPDATE overrides SET {sets} WHERE url = ?', params)
        else:
            cols = ['url'] + list(fields.keys())
            placeholders = ', '.join(['?'] * len(cols))
            values = [url] + list(fields.values())
            db.execute(f'INSERT INTO overrides ({", ".join(cols)}) VALUES ({placeholders})', values)

        # If the row now has zero user data, prune it.
        row = db.execute('SELECT * FROM overrides WHERE url = ?', (url,)).fetchone()
        obj = row_to_obj(row)
        if is_empty_override(obj):
            db.execute('DELETE FROM overrides WHERE url = ?', (url,))
            obj = {}

    return jsonify({'url': url, 'override': obj})


@app.route('/api/override/clear', methods=['POST'])
def clear_override():
    """Delete a single override row entirely. Body: {url}."""
    body = request.get_json(force=True) or {}
    url = body.get('url')
    if not url:
        abort(400, 'url required')
    with get_db() as db:
        db.execute('DELETE FROM overrides WHERE url = ?', (url,))
    return jsonify({'url': url, 'cleared': True})


@app.route('/api/overrides/bulk', methods=['POST'])
def bulk_replace():
    """Merge a bulk overrides object. Body: {overrides: {url: {...}, ...}, mode: 'merge'|'replace'}."""
    body = request.get_json(force=True) or {}
    incoming = body.get('overrides') or {}
    mode = body.get('mode', 'merge')
    if not isinstance(incoming, dict):
        abort(400, 'overrides must be an object')

    with get_db() as db:
        if mode == 'replace':
            db.execute('DELETE FROM overrides')

        for url, obj in incoming.items():
            if not isinstance(obj, dict):
                continue
            fields = {}
            if 'caption' in obj:
                fields['caption'] = obj['caption'] or None
            if 'tags' in obj:
                if obj['tags'] is None:
                    fields['tags'] = None
                else:
                    fields['tags'] = json.dumps(obj['tags'])
            if 'order' in obj:
                fields['order_value'] = float(obj['order']) if obj['order'] is not None else None
            if 'deleted' in obj:
                fields['deleted'] = 1 if obj['deleted'] else 0
            if 'comment' in obj:
                fields['comment'] = obj['comment'] or None

            if not fields:
                continue

            existing = db.execute('SELECT 1 FROM overrides WHERE url = ?', (url,)).fetchone()
            if existing and mode == 'merge':
                sets = ', '.join(f'{k} = ?' for k in fields)
                sets += ", updated_at = datetime('now')"
                params = list(fields.values()) + [url]
                db.execute(f'UPDATE overrides SET {sets} WHERE url = ?', params)
            else:
                if existing:
                    db.execute('DELETE FROM overrides WHERE url = ?', (url,))
                cols = ['url'] + list(fields.keys())
                placeholders = ', '.join(['?'] * len(cols))
                values = [url] + list(fields.values())
                db.execute(f'INSERT INTO overrides ({", ".join(cols)}) VALUES ({placeholders})', values)

    return jsonify({'imported': len(incoming), 'mode': mode})


@app.route('/api/overrides/wipe', methods=['POST'])
def wipe():
    with get_db() as db:
        db.execute('DELETE FROM overrides')
    return jsonify({'wiped': True})


@app.route('/api/health')
def health():
    with get_db() as db:
        count = db.execute('SELECT COUNT(*) as n FROM overrides').fetchone()['n']
    return jsonify({'ok': True, 'overrides': count, 'db': str(DB_PATH)})


if __name__ == '__main__':
    import threading
    init_db()
    print(f'DB: {DB_PATH}')
    print(f'HTML: {HTML_PATH}')
    print('Open http://localhost:5000')

    # Delay the browser open until the server is actually listening.
    # (Otherwise the browser races ahead and shows ERR_CONNECTION_REFUSED.)
    def open_browser_when_ready():
        import socket, time
        for _ in range(60):  # up to 30 seconds
            try:
                with socket.create_connection(('127.0.0.1', 5000), timeout=0.5):
                    pass
                break
            except OSError:
                time.sleep(0.5)
        try:
            webbrowser.open('http://localhost:5000')
        except Exception:
            pass

    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    app.run(host='127.0.0.1', port=5000, debug=False)
