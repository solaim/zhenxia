"""Persist upstream transcription settings without exposing credentials."""
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import yaml


class TranscriptSettings:
    def __init__(self, config):
        self.config = config

    def public(self):
        value = self.config.get('transcript') or {}
        env = value.get('api_key_env') or 'OPENAI_API_KEY'
        return {'enabled': bool(value.get('enabled')), 'model': value.get('model') or 'gpt-4o-mini-transcribe',
                'api_url': value.get('api_url') or 'https://api.openai.com/v1/audio/transcriptions',
                'api_key_env': env, 'key_configured': bool(os.environ.get(env) or value.get('api_key')),
                'key_source': 'env' if os.environ.get(env) else 'settings' if value.get('api_key') else 'none'}

    def save(self, values):
        url = values['api_url'].strip()
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise ValueError()
            parsed.port
        except ValueError:
            raise ValueError('转写接口地址无效') from None
        env = values['api_key_env'].strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', env):
            raise ValueError('环境变量名称无效')
        if not values['model'].strip():
            raise ValueError('模型名称不能为空')
        value = dict(self.config.get('transcript') or {})
        for key in ('enabled', 'api_url', 'api_key_env', 'model'):
            value[key] = values[key].strip() if isinstance(values[key], str) else values[key]
        if values.get('clear_key'):
            value['api_key'] = ''
        elif values.get('api_key', '').strip():
            value['api_key'] = values['api_key'].strip()
        path = Path(self.config.config_path)
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        data['transcript'] = value
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.config-')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
        self.config.update(transcript=value)
        return self.public()
