"""Explicit network configuration. Never infer the host OS proxy."""
import os
from urllib.parse import urlsplit


def validate_proxy(value):
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.port == 0 or parsed.path not in {'', '/'}
                or parsed.query or parsed.fragment):
            raise ValueError()
    except ValueError:
        raise ValueError('Proxy must be an HTTP(S) URL; use an HTTP/mixed proxy port, or an empty value for direct access') from None
    return value


def proxy_for(config, platform=None):
    if platform:
        key = 'ZHENXIA_PROXY_' + platform.upper()
        if key in os.environ:
            return validate_proxy(os.environ[key])
    if 'ZHENXIA_PROXY' in os.environ:
        return validate_proxy(os.environ['ZHENXIA_PROXY'])
    return validate_proxy(config.get('proxy'))
