import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient

from zhenxia.adapter import load_config as ConfigLoader
from zhenxia.app import build_app
from zhenxia.browser import media_url
from zhenxia.jobs import JobManager
from zhenxia.library import Library
from zhenxia.store import Store


@pytest.fixture
def client(tmp_path):
    config_file = tmp_path / 'config.yml'
    config_file.write_text('cookies: ""\n', encoding='utf-8')
    config = ConfigLoader(str(config_file))
    config.update(path=str(tmp_path / 'media'))
    with TestClient(build_app(config)) as client:
        yield client


def test_home_and_static(client):
    assert '视频收藏室' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/style.css').status_code == 200


def test_library_preview_range_and_trash(client, tmp_path):
    media = tmp_path / 'media'
    (media / '示例.mp4').write_bytes(b'0123456789')
    (media / 'secret.json').write_text('secret', encoding='utf-8')
    (media / 'escape.mp4').symlink_to(tmp_path / 'config.yml')
    client.post('/api/v1/resources/scan')
    data = client.get('/api/v1/resources').json()
    assert data['total'] == 1
    assert data['bytes'] == 10
    resource = data['items'][0]['id']
    url = '/api/v1/resources/' + resource
    response = client.get(url + '/file', headers={'Range': 'bytes=2-5'})
    assert response.status_code == 206
    assert response.content == b'2345'
    assert 'attachment' in client.get(url + '/file?download=true').headers['content-disposition']
    assert client.get('/api/v1/resources?q=不存在').json()['total'] == 0
    assert client.get('/api/v1/resources?kind=image').json()['total'] == 0
    assert client.get('/api/v1/resources?limit=0').status_code == 422
    assert client.delete(url).status_code == 200
    assert client.get('/api/v1/resources').json()['total'] == 0
    assert len(list((media / '.trash').glob('*.mp4'))) == 1
    assert client.get(url + '/file').status_code == 404


def test_symlink_parent_not_exposed(tmp_path):
    root = tmp_path / 'root'
    outside = tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    (outside / 'private.mp4').write_bytes(b'secret')
    (root / 'linked').symlink_to(outside, target_is_directory=True)
    library = Library(root, Store(tmp_path / 'db.sqlite'))
    library.scan()
    assert library.list()['items'] == []


@pytest.mark.parametrize('url', ['https://evil.test/x','https://www.douyin.com.evil.test/video/1',
                                 'https://www.douyin.com:bad/video/1', 'abc',
                                 'http://localhost:8000/', 'https://www.douyin.com/'])
def test_invalid_links(client, url):
    assert client.post('/api/v1/download', json={'url': url}).status_code == 400


def test_share_text_and_cookie_persistence(client, tmp_path):
    async def execute(url):
        return {'total': 1, 'success': 1}
    client.app.state.job_manager.executor = execute
    response = client.post('/api/v1/download', json={'url': '复制打开抖音 https://www.douyin.com/video/123?foo=1 看视频'})
    assert response.status_code == 200
    assert response.json()['url'] == 'https://www.douyin.com/video/123'
    response = client.put('/api/v1/settings/cookie', json={'cookie':'ttwid=secret; odin_tt=value'})
    assert response.status_code == 200
    assert client.get('/api/v1/settings').json()['cookie_configured']
    assert 'secret' not in client.get('/api/v1/settings').text
    assert 'secret' in (tmp_path / '.cookies.json').read_text(encoding='utf-8')
    assert client.put('/api/v1/settings/cookie', json={'cookie':''}).status_code == 200
    assert not client.get('/api/v1/settings').json()['cookie_configured']


def test_cross_origin_mutation_blocked(client):
    assert client.put('/api/v1/settings/cookie', json={'cookie':'ttwid=stolen'},
                      headers={'Origin':'https://evil.test'}).status_code == 403


async def test_history_survives_restart_and_interrupted_is_failed(tmp_path):
    store = Store(tmp_path / 'db.sqlite')
    library = Library(tmp_path / 'media', store)
    async def execute(url):
        return {'total': 1, 'success': 1}
    manager = JobManager(execute, store, library)
    job = await manager.submit('https://www.douyin.com/video/123')
    await asyncio.gather(*list(manager.tasks))
    assert store.task(job.job_id)['status'] == 'success'
    data = store.task(job.job_id)
    data['status'] = 'running'
    store.save_task(data)
    restarted = JobManager(execute, Store(store.path), library)
    await restarted.start()
    assert (await restarted.get(job.job_id))['status'] == 'failed'
    assert '中断' in (await restarted.get(job.job_id))['error']


async def test_zero_results_is_not_success(tmp_path):
    store = Store(tmp_path / 'db.sqlite')
    library = Library(tmp_path / 'media', store)
    async def execute(url):
        return {'total': 0}
    manager = JobManager(execute, store, library)
    job = await manager.submit('x')
    await asyncio.gather(*list(manager.tasks))
    assert (await manager.get(job.job_id))['status'] == 'failed'


def test_media_hosts():
    assert media_url('https://v3.douyinvod.com/a.mp4')
    assert not media_url('http://127.0.0.1/a.mp4')
    assert not media_url('https://douyinvod.com.evil.test/a.mp4')


async def test_browser_stream_saves_mp4_and_cleans_temporary_files(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    import playwright.async_api as playwright_api

    from zhenxia import browser as module

    async def check(content, expected):
        callback = None
        page = MagicMock()

        def on(event, handler):
            nonlocal callback
            callback = handler

        page.on = on

        async def goto(*args, **kwargs):
            response = MagicMock()
            response.url = 'https://www.douyin.com/aweme/detail'
            response.json = AsyncMock(return_value={'aweme_detail': {
                'aweme_id': '123', 'desc': 'Test title', 'author': {'nickname': 'Author'},
                'video': {'play_addr': {'url_list': ['https://v3.douyinvod.com/test.mp4']}}}})
            await callback(response)

        page.goto = goto
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.add_cookies = AsyncMock()
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=playwright)
        monkeypatch.setattr(playwright_api, 'async_playwright', factory)

        async def chunks(*args):
            yield content

        response = MagicMock()
        response.status = 200
        response.content.iter_chunked = chunks
        session = MagicMock()
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        monkeypatch.setattr(module.aiohttp, 'ClientSession', session_factory)
        if expected:
            result = await module.download_video('123', tmp_path, {'ttwid': 'test'})
            assert result['success'] == 1
            assert (tmp_path / '123.mp4').read_bytes() == content
            assert json.loads((tmp_path / '123.info.json').read_text(encoding='utf-8'))['title'] == 'Test title'
            result = await module.download_video('123', tmp_path, {})
            assert result['skipped'] == 1
        else:
            with pytest.raises(ValueError, match='MP4'):
                await module.download_video('123', tmp_path, {})
        assert not list(tmp_path.glob('*.part'))
        browser.close.assert_awaited_once()

    await check(b'<html>Access denied</html>', False)
    await check(b'\x00\x00\x00\x18ftypisom' + b'0' * 2000, True)


def test_legacy_json_migration_is_idempotent_and_keeps_backup(tmp_path):
    from zhenxia.store import now
    history = tmp_path / 'web-jobs.json'
    history.write_text(json.dumps([{'job_id':'old1','url':'https://www.douyin.com/video/123',
                                   'status':'success','created_at':now(), 'total':1, 'success':1}]), encoding='utf-8')
    original = history.read_bytes()
    store = Store(tmp_path / 'db.sqlite')
    assert store.migrate_legacy(history) == 1
    assert store.migrate_legacy(history) == 0
    assert store.task('old1')['success'] == 1
    assert history.read_bytes() == original


def test_pagination_search_missing_files_and_metadata(tmp_path):
    store = Store(tmp_path / 'db.sqlite')
    library = Library(tmp_path / 'media', store)
    for i in range(4):
        (library.root / (str(i) + '.mp4')).write_bytes(b'video')
    (library.root / '0.info.json').write_text(json.dumps({'id':'123','title':'中文标题','author':'作者'}), encoding='utf-8')
    library.scan()
    assert library.list(limit=2)['total'] == 4
    assert len(library.list(limit=2, offset=2)['items']) == 2
    assert library.list('中文')['total'] == 1
    assert library.list('%')['total'] == 0
    assert library.list('作者')['total'] == 1
    resource = library.list('中文')['items'][0]
    (library.root / '0.mp4').unlink()
    with pytest.raises(FileNotFoundError):
        library.find(resource['id'])
    library.scan()
    assert library.list()['total'] == 3
    assert store.resource(resource['id'])['state'] == 'missing'
    (library.root / '0.mp4').write_bytes(b'restored')
    library.scan()
    assert library.list()['total'] == 4
    assert library.list('中文')['items'][0]['id'] == resource['id']


def test_lists_use_database_without_rescanning(client, monkeypatch):
    monkeypatch.setattr(client.app.state.library, 'files', lambda: (_ for _ in ()).throw(AssertionError('unexpected filesystem scan')))
    assert client.get('/api/v1/resources').status_code == 200


def test_task_resource_relation_and_retry(client, tmp_path):
    (tmp_path / 'media' / '123.mp4').write_bytes(b'video')
    client.post('/api/v1/resources/scan')
    async def execute(url):
        return {'total':1, 'success':1, 'resource_paths':['123.mp4']}
    client.app.state.job_manager.executor = execute
    job_id = client.post('/api/v1/download',json={'url':'https://www.douyin.com/video/123'}).json()['job_id']
    import time
    for _ in range(100):
        task = client.get('/api/v1/jobs/' + job_id).json()
        if task['status'] == 'success':
            break
        time.sleep(.01)
    assert task['status'] == 'success'
    assert len(task['resource_ids']) == 1
    retried = client.post('/api/v1/jobs/' + job_id + '/retry')
    assert retried.status_code == 200
    task = client.get('/api/v1/jobs/' + retried.json()['job_id']).json()
    assert task['job_id'] == job_id
    assert len(client.get('/api/v1/jobs').json()['jobs']) == 1


async def test_shutdown_records_interruption(tmp_path):
    store = Store(tmp_path / 'db.sqlite')
    library = Library(tmp_path / 'media', store)
    started = asyncio.Event()
    async def execute(url):
        started.set()
        await asyncio.Event().wait()
    manager = JobManager(execute, store, library)
    job = await manager.submit('x')
    await started.wait()
    await manager.shutdown()
    assert store.task(job.job_id)['status'] == 'failed'
    assert '中断' in store.task(job.job_id)['error']


def test_trash_database_failure_restores_original(tmp_path, monkeypatch):
    store = Store(tmp_path / 'db.sqlite')
    library = Library(tmp_path / 'media', store)
    path = library.root / 'test.mp4'
    path.write_bytes(b'video')
    library.scan()
    resource_id = library.list()['items'][0]['id']
    def fail(*args):
        raise RuntimeError('DB failure')
    monkeypatch.setattr(store, 'mark_trashed', fail)
    with pytest.raises(RuntimeError):
        library.trash(resource_id)
    assert path.read_bytes() == b'video'


def test_engine_is_installed_dependency_and_can_construct_downloader(tmp_path):
    import importlib.metadata
    from pathlib import Path

    import core

    from zhenxia.adapter import Engine, load_config

    config_path = tmp_path / 'config.yml'
    config_path.write_text('cookies: ""\n', encoding='utf-8')
    config = load_config(config_path)
    config.update(path=str(tmp_path / 'media'))
    engine = Engine(config, tmp_path)
    assert engine.cookies() == {}
    assert engine.file_manager.base_path.exists()
    assert importlib.metadata.version('douyin-downloader') == '2.0.0'
    assert 'site-packages' in str(Path(core.__file__))


def test_legacy_resource_associations_are_migrated_once(tmp_path):
    from zhenxia.store import now

    store = Store(tmp_path / 'db.sqlite')
    library = Library(tmp_path / 'media', store)
    video_id = '7701976661402635547'
    (library.root / (video_id + '.mp4')).write_bytes(b'video')
    library.scan()
    store.save_task({'job_id':'old', 'url':'https://www.douyin.com/video/' + video_id,
                     'status':'success', 'created_at':now(), 'total':1, 'skipped':1})
    store.link_legacy_resources()
    store.link_legacy_resources()
    assert len(store.task('old')['resource_ids']) == 1


def test_invalid_legacy_json_does_not_mark_migration_complete(tmp_path):
    history = tmp_path / 'web-jobs.json'
    history.write_text('invalid', encoding='utf-8')
    store = Store(tmp_path / 'db.sqlite')
    with pytest.raises(ValueError):
        store.migrate_legacy(history)
    history.write_text('[]', encoding='utf-8')
    assert store.migrate_legacy(history) == 0
    with store.connect() as db:
        assert db.execute('SELECT 1 FROM schema_migrations WHERE version=2').fetchone()


async def test_adapter_profile_download_uses_installed_factory(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from zhenxia import adapter

    config = adapter.load_config()
    config.update(path=str(tmp_path / 'media'))
    engine = adapter.Engine(config, tmp_path)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    monkeypatch.setattr(adapter, 'DouyinAPIClient', lambda *a, **k: client)
    downloader = MagicMock()
    downloader.download = AsyncMock(return_value=SimpleNamespace(
        total=1, success=1, failed=0, skipped=0, incomplete_reason=None))
    factory = MagicMock(return_value=downloader)
    monkeypatch.setattr(adapter.DownloaderFactory, 'create', factory)
    result = await engine.download('https://www.douyin.com/user/MS4wLjABAAAAexample')
    assert result['success'] == 1
    assert factory.call_args.args[0] == 'user'
    downloader.download.assert_awaited_once()


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=aqz-KE-bpKQ&list=PLabc',
    'https://www.tiktok.com/@author/video/12345',
    'https://x.com/author/status/12345',
    'https://www.bilibili.com/video/BV1xx411c7mD',
])
def test_multiplatform_dispatch_and_resource_relation(client, tmp_path, monkeypatch, url):
    from zhenxia.platforms import normalize_link
    platform, canonical = normalize_link(url)
    async def download(actual_platform, actual_url):
        assert actual_platform == platform
        assert actual_url == canonical
        directory = tmp_path / 'media' / platform
        directory.mkdir(exist_ok=True)
        (directory / 'test.mp4').write_bytes(b'video')
        return {'total':1, 'success':1, 'resource_paths':[platform + '/test.mp4']}
    monkeypatch.setattr(client.app.state.multi_engine, 'download', download)
    response = client.post('/api/v1/download', json={'url':url})
    assert response.status_code == 200
    assert response.json()['url'] == canonical
    import time
    for _ in range(100):
        task = client.get('/api/v1/jobs/' + response.json()['job_id']).json()
        if task['status'] in {'success','failed'}:
            break
        time.sleep(.01)
    assert task['status'] == 'success', task
    assert len(task['resource_ids']) == 1


def test_platform_cookie_api_does_not_expose_credentials(client, tmp_path):
    cookie = '# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret-value\n'
    response = client.put('/api/v1/settings/cookies/youtube', json={'cookie':cookie})
    assert response.status_code == 200
    data = client.get('/api/v1/settings').json()
    assert any(p['id'] == 'youtube' and p['cookie_configured'] for p in data['platforms'])
    assert not data['cookie_configured']
    assert 'secret-value' not in json.dumps(data)
    assert client.put('/api/v1/settings/cookies/x', json={'cookie':cookie}).status_code == 400
    assert client.put('/api/v1/settings/cookies/youtube', json={'cookie':''}).status_code == 200
    assert not (tmp_path / 'platform-cookies/youtube.txt').exists()



def test_transcript_settings_keep_clear_and_never_expose_key(client, tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    settings = {'enabled':False,'api_url':'https://api.openai.com/v1/audio/transcriptions',
                'model':'gpt-4o-mini-transcribe','api_key_env':'OPENAI_API_KEY','api_key':'test-private-key'}
    response = client.put('/api/v1/settings/transcript',json=settings)
    assert response.status_code == 200
    assert response.json()['key_source'] == 'settings'
    assert 'test-private-key' not in response.text
    assert 'test-private-key' not in client.get('/api/v1/settings').text
    settings['api_key'] = ''
    assert client.put('/api/v1/settings/transcript',json=settings).json()['key_configured']
    monkeypatch.setenv('OPENAI_API_KEY','env-private-key')
    assert client.get('/api/v1/settings').json()['transcript']['key_source'] == 'env'
    settings['clear_key'] = True
    client.put('/api/v1/settings/transcript',json=settings)
    monkeypatch.delenv('OPENAI_API_KEY')
    assert not client.get('/api/v1/settings').json()['transcript']['key_configured']
    if os.name == 'posix':
        assert (tmp_path/'config.yml').stat().st_mode & 0o777 == 0o600
    settings['api_url'] = 'file:///etc/passwd'
    assert client.put('/api/v1/settings/transcript',json=settings).status_code == 400



def test_login_owner_cookie_and_cross_origin_protection(client, monkeypatch):
    async def wait():
        await asyncio.Event().wait()
    monkeypatch.setattr(client.app.state.login,'run',wait)
    assert client.get('/api/v1/login/status').status_code == 403
    assert client.get('/api/v1/login/frame').status_code == 403
    response=client.post('/api/v1/login/tiktok')
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    assert 'token' not in response.text
    assert client.get('/api/v1/login/status').status_code == 200
    assert client.post('/api/v1/login/action',json={'kind':'text','text':'secret'},
                       headers={'Origin':'https://evil.test'}).status_code == 403
    assert client.delete('/api/v1/login/tiktok/credentials').status_code == 409
    assert client.delete('/api/v1/login/session').status_code == 200
    assert client.delete('/api/v1/login/tiktok/credentials').status_code == 200


def test_download_limits_persist_and_validate(client, tmp_path):
    assert client.get('/api/v1/settings').json()['download_limits'] == {'max_gb': 2}
    for value in (8, 0, 0.5):
        response = client.put('/api/v1/settings/download-limits', json={'max_gb': value})
        assert response.status_code == 200
        assert client.get('/api/v1/settings').json()['download_limits']['max_gb'] == value
        from zhenxia.download_settings import DownloadSettings
        assert DownloadSettings(tmp_path).public()['max_gb'] == value
    for value in (-1, 1025, 'NaN'):
        assert client.put('/api/v1/settings/download-limits', json={'max_gb': value}).status_code == 422
    assert client.put('/api/v1/settings/download-limits', json={'max_gb': 4}, headers={'Origin': 'https://evil.test'}).status_code == 403


def test_vimeo_removed(client):
    assert 'vimeo' not in [p['id'] for p in client.get('/api/v1/settings').json()['platforms']]
    assert client.post('/api/v1/download', json={'url': 'https://vimeo.com/123456'}).status_code == 400
    assert client.put('/api/v1/settings/cookies/vimeo', json={'cookie': ''}).status_code == 400
