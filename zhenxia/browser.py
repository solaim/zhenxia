"""Download a single video from details returned by a normal browser page visit.

This intentionally stays in the web server: CLI/shared core is unchanged.
"""
import asyncio
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import aiohttp

from .progress import report


def media_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    return parsed.scheme == 'https' and any(
        host == domain or host.endswith('.' + domain)
        for domain in ('douyinvod.com', 'bytecdn.cn', 'bytedance.com', 'douyin.com', 'snssdk.com')
    )


async def download_video(video_id, root, cookies, proxy=None):
    from playwright.async_api import async_playwright

    root = Path(root)
    target = root / (video_id + '.mp4')
    if target.is_file() and not target.is_symlink() and target.stat().st_size > 0:
        return {'total': 1, 'success': 0, 'failed': 0, 'skipped': 1}
    async with async_playwright() as playwright:
        options = {'headless': True, 'args': ['--no-sandbox']}
        if proxy:
            options['proxy'] = {'server': proxy}
        browser = await playwright.chromium.launch(**options)
        try:
            context = await browser.new_context()
            if cookies:
                await context.add_cookies([{'name': k, 'value': v, 'domain': '.douyin.com', 'path': '/'}
                                           for k, v in cookies.items()])
            page = await context.new_page()
            detail = asyncio.get_running_loop().create_future()

            async def receive(response):
                if '/aweme/detail' not in response.url:
                    return
                try:
                    item = (await response.json()).get('aweme_detail') or {}
                    if str(item.get('aweme_id')) == video_id and not detail.done():
                        detail.set_result(item)
                except Exception:
                    return

            page.on('response', receive)
            await page.goto('https://www.douyin.com/video/' + video_id,
                            wait_until='domcontentloaded', timeout=45000)
            try:
                item = await asyncio.wait_for(detail, timeout=45)
            except asyncio.TimeoutError:
                raise RuntimeError('页面未返回视频详情，可能需要更新 Cookie、完成验证，或视频不可见')
            urls = ((item.get('video') or {}).get('play_addr') or {}).get('url_list') or []
            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for url in urls:
                    if not media_url(url):
                        continue
                    temporary = root / ('.' + uuid4().hex + '.part')
                    try:
                        async with session.get(url, proxy=proxy, allow_redirects=False,
                                               headers={'Referer': 'https://www.douyin.com/'}) as response:
                            if response.status != 200:
                                continue
                            size = 0
                            started = time.monotonic()
                            last_report = 0
                            raw_total = response.headers.get('Content-Length')
                            total = int(raw_total) if isinstance(raw_total, str) and raw_total.isdigit() else None
                            first = True
                            with temporary.open('xb') as output:
                                async for chunk in response.content.iter_chunked(256 * 1024):
                                    if first:
                                        if b'ftyp' not in chunk[:100]:
                                            raise ValueError('服务器未返回 MP4 文件')
                                        first = False
                                    size += len(chunk)
                                    if size > 2 * 1024 ** 3:
                                        raise ValueError('视频超过 2 GB 单文件限制')
                                    output.write(chunk)
                                    elapsed = time.monotonic() - started
                                    if elapsed - last_report >= .3:
                                        last_report = elapsed
                                        speed = size / max(elapsed, .001)
                                        report(phase='downloading', downloaded=size, total=total,
                                               percent=min(100, size / total * 100) if total else None,
                                               speed=speed, eta=max(0, (total-size)/speed) if total else None)
                            if size < 1000:
                                continue
                            os.replace(str(temporary), str(target))
                            metadata = {'id': video_id, 'title': item.get('desc', ''),
                                        'author': (item.get('author') or {}).get('nickname', ''),
                                        'url': 'https://www.douyin.com/video/' + video_id}
                            (root / (video_id + '.info.json')).write_text(
                                json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
                            return {'total': 1, 'success': 1, 'failed': 0, 'skipped': 0}
                    finally:
                        if temporary.exists():
                            temporary.unlink()
            raise RuntimeError('未取得可下载的 MP4 地址；图集、受限或已删除作品暂不支持')
        finally:
            await browser.close()
