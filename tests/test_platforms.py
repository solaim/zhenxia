import asyncio
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from zhenxia.credentials import PlatformCookies
from zhenxia.library import Library
from zhenxia.platforms import normalize_link
from zhenxia.store import Store
from zhenxia.ytdlp import YtDlpEngine


@pytest.mark.parametrize(('url', 'platform', 'expected'), [
    ('https://youtu.be/aqz-KE-bpKQ?t=2', 'youtube', 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'),
    ('https://www.youtube.com/watch?v=aqz-KE-bpKQ&list=PLabc&index=1', 'youtube', 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'),
    ('https://youtube.com/shorts/aqz-KE-bpKQ', 'youtube', 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'),
    ('https://www.tiktok.com/@author/video/12345?foo=1', 'tiktok', 'https://www.tiktok.com/@author/video/12345'),
    ('https://vm.tiktok.com/Abc123/', 'tiktok', 'https://vm.tiktok.com/Abc123'),
    ('https://twitter.com/author/status/12345?s=20', 'x', 'https://x.com/author/status/12345'),
    ('https://www.bilibili.com/video/BV1xx411c7mD/?spm_id=1', 'bilibili', 'https://www.bilibili.com/video/BV1xx411c7mD'),
    ('https://www.bilibili.com/bangumi/play/ep409983?from_spmid=666.25.episode.0', 'bilibili', 'https://www.bilibili.com/bangumi/play/ep409983'),
    ('https://m.bilibili.com/bangumi/play/ep409983/', 'bilibili', 'https://www.bilibili.com/bangumi/play/ep409983'),
    ('复制打开抖音 https://www.douyin.com/video/123?x=y 看视频', 'douyin', 'https://www.douyin.com/video/123'),
])
def test_normalize(url, platform, expected):
    assert normalize_link(url) == (platform, expected)


@pytest.mark.parametrize('url', [
    'https://youtube.com.evil.test/watch?v=aqz-KE-bpKQ',
    'https://user:pass@youtube.com/watch?v=aqz-KE-bpKQ',
    'https://youtube.com:443/watch?v=aqz-KE-bpKQ',
    'https://youtube.com:bad/watch?v=aqz-KE-bpKQ',
    'file:///etc/passwd', 'http://127.0.0.1/a.mp4', 'https://t.me/channel/123',
    'https://youtube.com/playlist?list=PLabc', 'https://youtube.com/@author',
    'https://youtube.com/watch?v=wrong', 'https://x.com/author',
    'https://vimeo.com/123456', 'https://www.tiktok.com/@author', 'https://vimeo.com/channels/123',
    'https://www.bilibili.com/video/../../secret',
    'https://www.bilibili.com/bangumi/play/ss409983',
    'https://www.bilibili.com/bangumi/play/ep',
    'https://www.bilibili.com/bangumi/play/ep409983/extra',
    'https://www.bilibili.com.evil.test/bangumi/play/ep409983',
    'https://user:secret@www.bilibili.com/bangumi/play/ep409983',
    'https://www.bilibili.com:443/bangumi/play/ep409983',
])
def test_reject_unsupported_and_ambiguous_links(url):
    with pytest.raises(ValueError):
        normalize_link(url)


def cookie_text(domain='.youtube.com'):
    return '# Netscape HTTP Cookie File\n' + domain + '\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret-value\n'


def test_cookies_validation_atomicity_and_platform_isolation(tmp_path):
    cookies = PlatformCookies(tmp_path)
    assert cookies.save('youtube', cookie_text())
    if os.name == 'posix':
        assert cookies.path('youtube').stat().st_mode & 0o777 == 0o600
    assert not cookies.configured('x')
    before = cookies.path('youtube').read_text(encoding='utf-8')
    with pytest.raises(ValueError, match='域名'):
        cookies.save('youtube', cookie_text('.twitter.com'))
    with pytest.raises(ValueError, match='Netscape'):
        cookies.save('youtube', 'SID=secret')
    assert cookies.path('youtube').read_text(encoding='utf-8') == before
    with pytest.raises(ValueError):
        cookies.path('../secret')
    assert not list(cookies.root.glob('.*'))
    assert not cookies.save('youtube', '')
    assert not cookies.configured('youtube')


def test_publish_metadata_search_and_repeat_download(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    directory = tmp_path / 'stage'
    directory.mkdir()
    media = directory / 'video.mp4'
    media.write_bytes(b'finished media')
    engine = YtDlpEngine(root, PlatformCookies(tmp_path))
    items = [{'file': 'video.mp4', 'id': 'aqz-KE-bpKQ', 'title': '测试标题',
              'author': 'Test author', 'url': 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'}]
    result = engine.publish('youtube', directory, items)
    assert result['success'] == 1
    store = Store(tmp_path / 'db.sqlite')
    library = Library(root, store)
    library.scan()
    resource = library.list('测试')['items'][0]
    assert resource['author'] == 'Test author'
    assert resource['source_url'] == items[0]['url']
    media.write_bytes(b'second download')
    assert engine.publish('youtube', directory, items)['skipped'] == 1
    assert library.find(resource['id']).read_bytes() == b'finished media'


def test_non_douyin_numeric_ids_do_not_invent_douyin_sources(tmp_path):
    library = Library(tmp_path / 'media', Store(tmp_path / 'db'))
    (library.root / 'test.mp4').write_bytes(b'video')
    (library.root / 'test.info.json').write_text(json.dumps({'id': '1234567890123456789'}), encoding='utf-8')
    library.scan()
    assert library.list()['items'][0]['source_url'] is None


def test_staging_and_incomplete_downloads_are_not_indexed(tmp_path):
    library = Library(tmp_path / 'media', Store(tmp_path / 'db'))
    folder = library.root / '.staging'
    folder.mkdir()
    (folder / 'partial.mp4').write_bytes(b'partial')
    (library.root / 'partial.mp4.part').write_bytes(b'partial')
    library.scan()
    assert library.list()['total'] == 0


async def test_cancel_kills_worker_and_cleans_staging(tmp_path, monkeypatch):
    from zhenxia import ytdlp
    root = tmp_path / 'media'
    root.mkdir()
    original = asyncio.create_subprocess_exec
    started = asyncio.Event()
    processes = []

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, '-c', 'import time; time.sleep(60)', **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(ytdlp.asyncio, 'create_subprocess_exec', spawn)
    engine = YtDlpEngine(root, PlatformCookies(tmp_path))
    task = asyncio.create_task(engine.download('youtube', 'https://youtu.be/aqz-KE-bpKQ'))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[0].returncode is not None
    assert not list((root / '.staging').iterdir())


@pytest.mark.parametrize(('platform', 'url', 'extractor_key', 'pattern'), [
    ('youtube', 'https://www.youtube.com/watch?v=aqz-KE-bpKQ', 'Youtube',
     r'https://www\.youtube\.com/watch\?v=(?P<id>[A-Za-z0-9_-]+)'),
    ('bilibili', 'https://www.bilibili.com/bangumi/play/ep409983', 'BiliBiliBangumi',
     r'https://www\.bilibili\.com/bangumi/play/ep(?P<id>[0-9]+)'),
])
def test_worker_uses_real_ytdlp_to_download_and_collect_metadata(tmp_path, monkeypatch, platform, url, extractor_key, pattern):
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.common import InfoExtractor

    from zhenxia import ytdlp_worker

    payload = b'\x00\x00\x00\x18ftypisom' + b'0' * 2048

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Content-Type', 'video/mp4')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class TestVideoIE(InfoExtractor):
        IE_NAME = extractor_key
        _VALID_URL = pattern

        @classmethod
        def ie_key(cls):
            return extractor_key

        def _real_extract(self, url):
            return {'id': self._match_id(url), 'title': '公开测试视频', 'uploader': 'Author',
                    'url': f'http://127.0.0.1:{server.server_port}/video.mp4', 'ext': 'mp4'}

    class Downloader(YoutubeDL):
        def __init__(self, options):
            super().__init__(options)
            self.add_info_extractor(TestVideoIE())

    monkeypatch.setattr(ytdlp_worker, 'YoutubeDL', Downloader)
    try:
        result = ytdlp_worker.download({'platform':platform, 'directory':str(tmp_path),
                                      'url':url})
        assert len(result) == 1
        assert result[0]['title'] == '公开测试视频'
        assert result[0]['author'] == 'Author'
        assert (tmp_path / result[0]['file']).read_bytes() == payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(sys.platform != 'linux', reason='Descendant state verification uses Linux /proc')
async def test_stopping_worker_kills_descendants(tmp_path):
    from zhenxia.ytdlp import stop_process
    process = await asyncio.create_subprocess_exec(sys.executable, '-c',
        'import subprocess,time,sys; child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
        'print(child.pid, flush=True); time.sleep(60)',
        stdout=asyncio.subprocess.PIPE, start_new_session=True)
    child_pid = int(await process.stdout.readline())
    await stop_process(process)
    assert process.returncode is not None
    # A terminated child can briefly remain a zombie until container init reaps it.
    for _ in range(50):
        try:
            state = Path(f'/proc/{child_pid}/stat').read_text(encoding='utf-8').split()[2]
        except (FileNotFoundError, ProcessLookupError):
            break
        if state == 'Z':
            break
        await asyncio.sleep(.02)
    else:
        pytest.fail('FFmpeg-like child remained alive after cancellation')


async def test_progress_visible_while_running_and_persisted(tmp_path):
    from zhenxia.jobs import JobManager
    from zhenxia.progress import report
    store = Store(tmp_path / 'progress.db')
    library = Library(tmp_path / 'media', store)
    ready = asyncio.Event()
    finish = asyncio.Event()
    async def execute(url):
        report(phase='downloading', downloaded=50, total=100, percent=50, speed=25, eta=2)
        ready.set()
        await finish.wait()
        return {'total':1, 'success':1}
    manager = JobManager(execute, store, library, 1)
    job = await manager.submit('test')
    await ready.wait()
    assert (await manager.get(job.job_id))['progress']['percent'] == 50
    assert (await manager.list_jobs())[0]['progress']['speed'] == 25
    finish.set()
    await asyncio.gather(*manager.tasks)
    assert Store(store.path).task(job.job_id)['progress']['phase'] == 'success'
    assert not manager.live_progress


async def test_retry_keeps_id_and_rejects_duplicate_retry(tmp_path):
    from zhenxia.jobs import JobManager
    store = Store(tmp_path / 'retry.db')
    library = Library(tmp_path / 'media', store)
    gate = asyncio.Event()
    async def execute(url):
        await gate.wait()
        return {'total':1,'success':1}
    manager = JobManager(execute, store, library, 1)
    job = await manager.submit('test')
    gate.set()
    await asyncio.gather(*list(manager.tasks))
    original = store.task(job.job_id)
    gate.clear()
    retry = await manager.retry(job.job_id)
    assert retry.job_id == job.job_id
    assert retry.created_at == original['created_at']
    assert retry.error is None and retry.progress == {}
    with pytest.raises(ValueError, match='仍在运行'):
        await manager.retry(job.job_id)
    assert len(store.tasks()) == 1
    gate.set()
    await asyncio.gather(*list(manager.tasks))



def test_x_embedded_video_extractors_enabled_without_generic():
    from yt_dlp import YoutubeDL

    from zhenxia.platforms import EXTRACTORS
    with YoutubeDL({'quiet': True, 'allowed_extractors':EXTRACTORS['x']}) as ydl:
        assert 'TwitterAmplify' in ydl._ies
        assert 'TwitterCard' in ydl._ies
        assert 'Generic' not in ydl._ies


def test_bilibili_bangumi_extractor_enabled_without_season_or_generic():
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.bilibili import BiliBiliBangumiIE

    from zhenxia.platforms import EXTRACTORS

    url = 'https://www.bilibili.com/bangumi/play/ep409983'
    assert BiliBiliBangumiIE.suitable(url)
    with YoutubeDL({'quiet': True, 'allowed_extractors': EXTRACTORS['bilibili']}) as ydl:
        assert 'BiliBili' in ydl._ies
        assert 'BiliBiliBangumi' in ydl._ies
        assert 'BiliBiliBangumiSeason' not in ydl._ies
        assert 'Generic' not in ydl._ies
