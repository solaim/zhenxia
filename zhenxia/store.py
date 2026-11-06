"""SQLite storage. All request-time calls run in worker threads.

A short-lived connection per transaction avoids sharing connections across event
loops. WAL and busy_timeout support simultaneous reads and serialized writes.
"""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS download_tasks (
                    job_id TEXT PRIMARY KEY, url TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    total INTEGER NOT NULL DEFAULT 0, success INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0,
                    error TEXT, retry_of TEXT REFERENCES download_tasks(job_id));
                CREATE INDEX IF NOT EXISTS tasks_created ON download_tasks(created_at DESC);
                CREATE INDEX IF NOT EXISTS tasks_status ON download_tasks(status);
                CREATE TABLE IF NOT EXISTS resources (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
                    size INTEGER NOT NULL, modified REAL NOT NULL, type TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'ready', video_id TEXT, title TEXT,
                    author TEXT, source_url TEXT, trash_path TEXT, deleted_at TEXT);
                CREATE INDEX IF NOT EXISTS resources_state_modified ON resources(state, modified DESC);
                CREATE INDEX IF NOT EXISTS resources_video ON resources(video_id);
                CREATE TABLE IF NOT EXISTS task_resources (
                    job_id TEXT NOT NULL REFERENCES download_tasks(job_id) ON DELETE CASCADE,
                    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
                    PRIMARY KEY(job_id, resource_id));
            ''')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS tags (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS resource_tags (
                    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
                    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                    PRIMARY KEY(resource_id, tag_id));
                CREATE INDEX IF NOT EXISTS resource_tags_tag ON resource_tags(tag_id);
            ''')
            if 'folder_id' not in {row[1] for row in db.execute('PRAGMA table_info(resources)')}:
                db.execute('ALTER TABLE resources ADD COLUMN folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL')
            db.execute('CREATE INDEX IF NOT EXISTS resources_folder ON resources(folder_id)')
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES (5, ?)', (now(),))
            if 'progress' not in {row[1] for row in db.execute('PRAGMA table_info(download_tasks)')}:
                db.execute("ALTER TABLE download_tasks ADD COLUMN progress TEXT NOT NULL DEFAULT '{}'")
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES (4, ?)', (now(),))
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES (1, ?)', (now(),))

    @contextmanager
    def connect(self):
        with self.lock:
            db = sqlite3.connect(str(self.path), timeout=15)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA busy_timeout=15000')
            try:
                with db:
                    yield db
            finally:
                db.close()

    def migrate_legacy(self, history):
        history = Path(history)
        with self.connect() as db:
            if db.execute('SELECT 1 FROM schema_migrations WHERE version=2').fetchone():
                return 0
            items = json.loads(history.read_text(encoding='utf-8')) if history.exists() else []
            if not isinstance(items, list):
                raise ValueError('旧任务记录格式无效，请检查 web-jobs.json')
            for item in items:
                self._write_task(db, item)
            db.execute('INSERT INTO schema_migrations VALUES (2, ?)', (now(),))
            return len(items)

    def _write_task(self, db, item):
        columns = ('job_id', 'url', 'status', 'created_at', 'started_at', 'finished_at',
                   'total', 'success', 'failed', 'skipped', 'error', 'retry_of')
        values = [item.get(c, 0 if c in {'total', 'success', 'failed', 'skipped'} else None)
                  for c in columns]
        db.execute('''INSERT INTO download_tasks (job_id,url,status,created_at,started_at,finished_at,total,success,failed,skipped,error,retry_of) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,
                    started_at=excluded.started_at, finished_at=excluded.finished_at,
                    total=excluded.total, success=excluded.success, failed=excluded.failed,
                    skipped=excluded.skipped, error=excluded.error''', values)

        db.execute('UPDATE download_tasks SET progress=? WHERE job_id=?',
                   (json.dumps(item.get('progress') or {}), item['job_id']))

    @staticmethod
    def decode_task(row):
        result = dict(row)
        result['progress'] = json.loads(result.get('progress') or '{}')
        return result

    def save_task(self, item):
        with self.connect() as db:
            self._write_task(db, item)

    def recover_tasks(self):
        with self.connect() as db:
            db.execute("""UPDATE download_tasks SET status='failed', finished_at=?,
                error='服务重启，任务已中断；请重试' WHERE status IN ('pending','running')""", (now(),))

    def tasks(self, limit=500):
        with self.connect() as db:
            return [self.decode_task(row) for row in db.execute(
                'SELECT * FROM download_tasks ORDER BY created_at DESC LIMIT ?', (limit,))]

    def task(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM download_tasks WHERE job_id=?', (job_id,)).fetchone()
            if not row:
                return None
            result = self.decode_task(row)
            result['resource_ids'] = [r[0] for r in db.execute(
                'SELECT resource_id FROM task_resources WHERE job_id=?', (job_id,))]
            return result

    def sync_resources(self, items):
        with self.connect() as db:
            db.execute("UPDATE resources SET state='missing' WHERE state='ready'")
            for item in items:
                db.execute('''INSERT INTO resources
                    (id,name,path,size,modified,type,video_id,title,author,source_url)
                    VALUES (:id,:name,:path,:size,:modified,:type,:video_id,:title,:author,:source_url)
                    ON CONFLICT(path) DO UPDATE SET name=excluded.name, size=excluded.size,
                    modified=excluded.modified, type=excluded.type, state='ready',
                    video_id=COALESCE(excluded.video_id,resources.video_id),
                    title=COALESCE(excluded.title,resources.title),
                    author=COALESCE(excluded.author,resources.author),
                    source_url=COALESCE(excluded.source_url,resources.source_url),
                    trash_path=NULL,deleted_at=NULL''', item)

    def resources(self, query='', kind='all', offset=0, limit=60, folder=None, tag=None):
        conditions = ["state='ready'"]
        params = []
        if query:
            conditions.append("(instr(lower(name),lower(?))>0 OR instr(lower(path),lower(?))>0 OR instr(lower(COALESCE(title,'')),lower(?))>0 OR instr(lower(COALESCE(author,'')),lower(?))>0)")
            params.extend([query] * 4)
        if kind != 'all':
            conditions.append('type LIKE ?')
            params.append(kind + '/%')
        if folder == '__unfiled__':
            conditions.append('folder_id IS NULL')
        elif folder:
            conditions.append('folder_id=?')
            params.append(folder)
        if tag:
            conditions.append('EXISTS (SELECT 1 FROM resource_tags WHERE resource_id=resources.id AND tag_id=?)')
            params.append(tag)
        where = ' AND '.join(conditions)
        with self.connect() as db:
            totals = db.execute('SELECT COUNT(*), COALESCE(SUM(size),0) FROM resources WHERE ' + where, params).fetchone()
            items = [dict(row) for row in db.execute('SELECT * FROM resources WHERE ' + where +
                     ' ORDER BY modified DESC,id LIMIT ? OFFSET ?', params + [limit, offset])]
            self._decorate_resources(db, items)
        return {'items': items, 'total': totals[0], 'bytes': totals[1]}

    def resource(self, resource_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM resources WHERE id=?', (resource_id,)).fetchone()
            return dict(row) if row else None

    def mark_trashed(self, resource_id, trash_path):
        with self.connect() as db:
            db.execute("UPDATE resources SET state='trashed',trash_path=?,deleted_at=? WHERE id=?",
                       (trash_path, now(), resource_id))

    def link_resources(self, job_id, paths):
        with self.connect() as db:
            for path in paths:
                db.execute('''INSERT OR IGNORE INTO task_resources(job_id,resource_id)
                    SELECT ?,id FROM resources WHERE path=? AND state='ready' ''', (job_id, path))

    def link_legacy_resources(self):
        # Only successful legacy tasks can claim existing matching video files.
        with self.connect() as db:
            if db.execute('SELECT 1 FROM schema_migrations WHERE version=3').fetchone():
                return
            for task in db.execute("SELECT job_id,url FROM download_tasks WHERE status='success'").fetchall():
                match = re.fullmatch(r'https://www\.douyin\.com/video/(\d+)', task['url'])
                if match:
                    db.execute("""INSERT OR IGNORE INTO task_resources(job_id,resource_id)
                        SELECT ?,id FROM resources WHERE video_id=? AND state='ready' """,
                               (task['job_id'], match.group(1)))
            db.execute('INSERT INTO schema_migrations VALUES (3, ?)', (now(),))


    @staticmethod
    def _decorate_resources(db, items):
        folders = {row['id']: row['name'] for row in db.execute('SELECT id,name FROM folders')}
        by_id = {item['id']: item for item in items}
        for item in items:
            item['folder_name'] = folders.get(item['folder_id'])
            item['tags'] = []
        if not items:
            return
        placeholders = ','.join('?' for _ in items)
        for row in db.execute(
                'SELECT resource_id,tags.id,tags.name FROM resource_tags JOIN tags ON tags.id=tag_id '
                'WHERE resource_id IN (' + placeholders + ') ORDER BY tags.name_key,tags.id', list(by_id)):
            by_id[row['resource_id']]['tags'].append({'id': row['id'], 'name': row['name']})

    @staticmethod
    def _collection_table(kind):
        if kind not in ('folders', 'tags'):
            raise ValueError('Invalid collection type')
        return kind

    def collections(self):
        with self.connect() as db:
            folders = [dict(row) for row in db.execute(
                "SELECT folders.id,folders.name,COUNT(resources.id) AS count FROM folders "
                "LEFT JOIN resources ON resources.folder_id=folders.id AND resources.state='ready' "
                'GROUP BY folders.id ORDER BY folders.name_key,folders.id')]
            tags = [dict(row) for row in db.execute(
                "SELECT tags.id,tags.name,COUNT(resources.id) AS count FROM tags "
                "LEFT JOIN resource_tags ON tag_id=tags.id LEFT JOIN resources "
                "ON resources.id=resource_id AND resources.state='ready' "
                'GROUP BY tags.id ORDER BY tags.name_key,tags.id')]
            return {'folders': folders, 'tags': tags}

    def save_collection(self, kind, name, collection_id=None):
        table = self._collection_table(kind)
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError('Name must contain 1–80 characters')
        with self.connect() as db:
            if collection_id is not None and not db.execute(
                    'SELECT 1 FROM ' + table + ' WHERE id=?', (collection_id,)).fetchone():
                raise FileNotFoundError('Collection not found')
            identifier = collection_id or uuid4().hex
            try:
                if collection_id is None:
                    db.execute('INSERT INTO ' + table + ' (id,name,name_key) VALUES (?,?,?)',
                               (identifier, name, name.casefold()))
                else:
                    db.execute('UPDATE ' + table + ' SET name=?,name_key=? WHERE id=?',
                               (name, name.casefold(), identifier))
            except sqlite3.IntegrityError:
                raise ValueError('Name already exists') from None
            return {'id': identifier, 'name': name}

    def delete_collection(self, kind, collection_id):
        table = self._collection_table(kind)
        with self.connect() as db:
            cursor = db.execute('DELETE FROM ' + table + ' WHERE id=?', (collection_id,))
            if not cursor.rowcount:
                raise FileNotFoundError('Collection not found')

    def organize_resource(self, resource_id, folder_id, tag_ids):
        tag_ids = list(dict.fromkeys(tag_ids))
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM resources WHERE id=? AND state='ready'", (resource_id,)).fetchone():
                raise FileNotFoundError('Resource not found')
            if folder_id is not None and not db.execute('SELECT 1 FROM folders WHERE id=?', (folder_id,)).fetchone():
                raise ValueError('Folder not found')
            if len(tag_ids) > 30:
                raise ValueError('Select at most 30 tags')
            for tag_id in tag_ids:
                if not db.execute('SELECT 1 FROM tags WHERE id=?', (tag_id,)).fetchone():
                    raise ValueError('Tag not found')
            db.execute('UPDATE resources SET folder_id=? WHERE id=?', (folder_id, resource_id))
            db.execute('DELETE FROM resource_tags WHERE resource_id=?', (resource_id,))
            db.executemany('INSERT INTO resource_tags (resource_id,tag_id) VALUES (?,?)',
                           [(resource_id, tag_id) for tag_id in tag_ids])
            items = [dict(db.execute('SELECT * FROM resources WHERE id=?', (resource_id,)).fetchone())]
            self._decorate_resources(db, items)
            return items[0]
