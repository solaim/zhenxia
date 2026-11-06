"""Async process adapter: cancellation also stops FFmpeg/JavaScript descendants."""
import asyncio
import json
import os
import re
import shutil
import signal
import tempfile
from pathlib import Path

from .library import MEDIA
from .progress import report
from .runtime import worker_command


async def stop_process(process):
    if process.returncode is not None:
        return
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # Kill FFmpeg/Node descendants too, even when packaged without Python on PATH.
        killer = await asyncio.create_subprocess_exec(
            'taskkill', '/PID', str(process.pid), '/T', '/F',
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await killer.wait()
        if killer.returncode and process.returncode is None:
            process.kill()
    await process.wait()


class YtDlpEngine:
    def __init__(self, root, credentials, proxy=None):
        self.root = Path(root)
        self.credentials = credentials
        self.proxy = proxy
        self.platform_proxies = {}
        self.max_bytes = 2 * 1024 ** 3

    async def download(self, platform, url):
        staging = self.root / '.staging'
        if staging.is_symlink():
            raise ValueError('下载目录不能是符号链接')
        staging.mkdir(exist_ok=True)
        directory = Path(tempfile.mkdtemp(dir=staging))
        process = None
        try:
            cookie = self.credentials.path(platform)
            request = {'max_bytes': self.max_bytes, 'platform': platform, 'url': url, 'directory': str(directory), 'proxy': self.platform_proxies.get(platform, self.proxy)}
            if cookie.is_file():
                # yt-dlp may update its jar: never give a worker the shared credential file.
                copied = directory / 'cookies.txt'
                shutil.copyfile(cookie, copied)
                copied.chmod(0o600)
                request['cookiefile'] = str(copied)
            process = await asyncio.create_subprocess_exec(
                *worker_command(),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=os.name == 'posix')
            communication = asyncio.create_task(process.communicate(json.dumps(request).encode()))
            try:
                while not communication.done():
                    progress_file = directory / 'progress.json'
                    if progress_file.is_file():
                        try:
                            report(**json.loads(progress_file.read_text()))
                        except (OSError, ValueError):
                            pass
                    await asyncio.wait({communication}, timeout=.3)
                await communication
            finally:
                if not communication.done():
                    communication.cancel()
                    await asyncio.gather(communication, return_exceptions=True)
            result_file = directory / 'result.json'
            if process.returncode or not result_file.is_file():
                raise RuntimeError('下载进程异常退出，请检查运行环境')
            result = json.loads(result_file.read_text())
            if result.get('error'):
                raise RuntimeError(result['error'])
            return self.publish(platform, directory, result['items'])
        finally:
            if process is not None:
                await stop_process(process)
            shutil.rmtree(directory, ignore_errors=True)

    def publish(self, platform, directory, items):
        folder = self.root / platform
        if folder.is_symlink():
            raise ValueError('下载目录不能是符号链接')
        folder.mkdir(exist_ok=True)
        paths = []
        skipped = 0
        for item in items:
            source = directory / item['file']
            if source.parent != directory or source.is_symlink() or source.suffix.lower() not in MEDIA or not source.is_file():
                raise ValueError('下载结果文件无效')
            video_id = re.sub(r'[^A-Za-z0-9_-]', '_', item['id'])[:120]
            if not video_id:
                raise ValueError('下载结果文件无效')
            target = folder / (video_id + source.suffix.lower())
            if target.is_symlink():
                raise ValueError('下载目录不能是符号链接')
            if target.is_file() and target.stat().st_size > 0:
                skipped += 1
            else:
                target.with_suffix('.info.json').write_text(json.dumps(
                    {k: item[k] for k in ('id', 'title', 'author', 'url')}, ensure_ascii=False), encoding='utf-8')
                source.replace(target)
            paths.append(target.relative_to(self.root).as_posix())
        return {'total': len(paths), 'success': len(paths) - skipped, 'skipped': skipped,
                'failed': 0, 'resource_paths': paths}
