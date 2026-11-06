"""The only module coupled to douyin-downloader's pinned internal APIs.

Upstream is installed as a dependency; no upstream source is vendored here.
"""
from pathlib import Path
from urllib.parse import urlparse

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core import UNSUPPORTED_URL_TYPE_DETAIL, DouyinAPIClient, DownloaderFactory, URLParser
from storage import FileManager
from utils.cookie_utils import parse_cookie_header, sanitize_cookies

from .network import proxy_for


def load_config(path=None):
    config = ConfigLoader(str(path) if path else None)
    config.zhenxia_proxy = config.get('proxy')
    config.update(proxy=proxy_for(config, 'douyin'))
    return config


class Engine:
    def __init__(self, config, data_dir):
        self.config = config
        self.cookie_manager = CookieManager(str(Path(data_dir) / '.cookies.json'))
        if not self.cookie_manager.cookie_file.exists() and config.get_cookies():
            self.cookie_manager.set_cookies(config.get_cookies())
        else:
            self.cookie_manager.get_cookies()
        self.file_manager = FileManager(config.get('path'))
        self.rate_limiter = RateLimiter(max_per_second=2)
        self.retry_handler = RetryHandler(max_retries=int(config.get('retry_times', 3)))
        self.queue_manager = QueueManager(max_workers=max(1, int(config.get('thread', 2))))

    def cookies(self):
        return self.cookie_manager.get_cookies()

    def save_cookie(self, value):
        cookies = sanitize_cookies(parse_cookie_header(value))
        if value.strip() and not cookies:
            raise ValueError('Cookie 格式无效')
        self.cookie_manager.set_cookies(cookies)
        return bool(cookies)

    async def resolve(self, url):
        if urlparse(url).hostname != 'v.douyin.com':
            return url
        async with DouyinAPIClient(self.cookies(), proxy=self.config.get('proxy')) as client:
            resolved = await client.resolve_short_url(url)
        parsed = urlparse(resolved or '')
        if parsed.hostname not in {'www.douyin.com', 'douyin.com'}:
            raise RuntimeError('短链接未解析到抖音作品')
        return 'https://www.douyin.com' + parsed.path.rstrip('/')

    async def download(self, url):
        parsed = URLParser.parse(url)
        if not parsed:
            raise ValueError('不支持的抖音链接')
        if str(parsed.get('type')) in UNSUPPORTED_URL_TYPE_DETAIL:
            raise ValueError(UNSUPPORTED_URL_TYPE_DETAIL[str(parsed['type'])])
        async with DouyinAPIClient(self.cookies(), proxy=self.config.get('proxy')) as client:
            downloader = DownloaderFactory.create(
                parsed['type'], self.config, client, self.file_manager, self.cookie_manager,
                None, self.rate_limiter, self.retry_handler, self.queue_manager,
                progress_reporter=None)
            if downloader is None:
                raise ValueError('此链接类型尚无下载器')
            result = await downloader.download(parsed)
            counts = {key: getattr(result, key) for key in ('total', 'success', 'failed', 'skipped')}
            if getattr(result, 'incomplete_reason', None):
                raise RuntimeError(result.incomplete_reason)
            return counts
