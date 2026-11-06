"""Per-platform Netscape cookies, never mixed with the Douyin session."""
import os
import tempfile
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path

from .platforms import COOKIE_DOMAINS


class PlatformCookies:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / 'platform-cookies'
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)

    def path(self, platform):
        if platform not in COOKIE_DOMAINS:
            raise ValueError('不支持此平台的 Cookie')
        return self.root / (platform + '.txt')

    def configured(self, platform):
        return self.path(platform).is_file()

    def save(self, platform, value):
        target = self.path(platform)
        if not value.strip():
            target.unlink(missing_ok=True)
            return False
        if len(value.encode()) > 1024 * 1024:
            raise ValueError('Cookie 文件超过 1 MB')
        descriptor, name = tempfile.mkstemp(dir=self.root, prefix='.')
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(value.strip() + '\n')
            jar = MozillaCookieJar(str(temporary))
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
            except (LoadError, ValueError):
                raise ValueError('请粘贴 Netscape 格式的 Cookie 文件内容') from None
            cookies = list(jar)
            domains = COOKIE_DOMAINS[platform]
            if not cookies or any(not any(c.domain.lstrip('.') == d or c.domain.lstrip('.').endswith('.' + d)
                                          for d in domains) for c in cookies):
                raise ValueError('Cookie 域名与所选平台不匹配')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return True
