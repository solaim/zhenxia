"""Persistent per-task budget for the multi-platform engine."""
import json
import os
import tempfile
from pathlib import Path


class DownloadSettings:
    def __init__(self, directory):
        self.path = Path(directory) / 'download-settings.json'
        self.value = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'max_gb': 2}

    def public(self):
        return dict(self.value)

    def save(self, max_gb):
        value = {'max_gb': max_gb}
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix='.download-settings-')
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(value, stream)
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
        self.value = value
        return self.public()
