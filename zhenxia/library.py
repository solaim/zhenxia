"""SQLite-backed archive with explicit filesystem reconciliation."""
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from threading import RLock
from uuid import uuid4

MEDIA = {'.mp4', '.webm', '.mov', '.mkv', '.jpg', '.jpeg', '.png', '.webp', '.mp3', '.m4a'}


class Library:
    def __init__(self, root, store):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.lock = RLock()

    def valid(self, path):
        try:
            relative = path.relative_to(self.root)
            return (path.is_file() and path.suffix.lower() in MEDIA
                    and not any(p.startswith('.') for p in relative.parts)
                    and not any(p.is_symlink() for p in [path, *path.parents] if p != self.root)
                    and self.root in path.resolve().parents)
        except (OSError, ValueError):
            return False

    def files(self):
        for folder, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.') and not (Path(folder) / d).is_symlink()]
            for name in files:
                path = Path(folder) / name
                if self.valid(path):
                    yield path

    def describe(self, path):
        relative = path.relative_to(self.root).as_posix()
        stat = path.stat()
        metadata = {}
        sidecar = path.with_suffix('.info.json')
        if sidecar.is_file() and not sidecar.is_symlink() and sidecar.stat().st_size < 65536:
            try:
                metadata = json.loads(sidecar.read_text(encoding='utf-8'))
                if not isinstance(metadata, dict):
                    metadata = {}
            except (ValueError, OSError):
                pass
        match = re.search(r'(\d{19})', path.name)
        video_id = metadata.get('id') or (match.group(1) if match else None)
        return {'id': hashlib.sha256(relative.encode()).hexdigest()[:24],
                'name': path.name, 'path': relative, 'size': stat.st_size,
                'modified': stat.st_mtime, 'type': mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                'video_id': video_id, 'title': metadata.get('title'), 'author': metadata.get('author') or metadata.get('uploader'),
                'source_url': metadata.get('url') or metadata.get('webpage_url') or ('https://www.douyin.com/video/' + video_id if match else None)}

    def scan(self):
        with self.lock:
            items = []
            for path in self.files():
                try:
                    items.append(self.describe(path))
                except FileNotFoundError:
                    continue
            self.store.sync_resources(items)
            return {'indexed': len(items)}

    def list(self, query='', kind='all', offset=0, limit=60, folder=None, tag=None):
        return self.store.resources(query, kind, offset, limit, folder, tag)

    def find(self, resource_id):
        item = self.store.resource(resource_id)
        if not item or item['state'] != 'ready':
            raise FileNotFoundError(resource_id)
        path = self.root / item['path']
        if not self.valid(path):
            raise FileNotFoundError(resource_id)
        return path

    def trash(self, resource_id):
        with self.lock:
            path = self.find(resource_id)
            folder = self.root / '.trash'
            if folder.is_symlink():
                raise ValueError('回收目录不能是符号链接')
            folder.mkdir(exist_ok=True)
            target = folder / (uuid4().hex + '_' + path.name)
            path.rename(target)
            try:
                self.store.mark_trashed(resource_id, target.relative_to(self.root).as_posix())
            except Exception:
                target.rename(path)
                raise

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in self.files()}
