import sqlite3
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from zhenxia.adapter import load_config
from zhenxia.app import build_app
from zhenxia.store import Store


@pytest.fixture
def archive(tmp_path):
    config_file = tmp_path / 'config.yml'
    config_file.write_text('cookies: ""\n', encoding='utf-8')
    config = load_config(str(config_file))
    config.update(path=str(tmp_path / 'media'))
    with TestClient(build_app(config)) as client:
        root = tmp_path / 'media'
        (root / 'a.mp4').write_bytes(b'video-a')
        (root / 'b.mp4').write_bytes(b'video-b')
        (root / 'cover.png').write_bytes(b'image')
        assert client.post('/api/v1/resources/scan').status_code == 200
        items = {item['name']: item for item in client.get('/api/v1/resources').json()['items']}
        yield client, root, items


def create(client, kind, name):
    response = client.post('/api/v1/collections/' + kind, json={'name': name})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_new_downloads_and_scans_never_auto_classify(archive):
    client, root, items = archive
    assert client.get('/api/v1/collections').json() == {'folders': [], 'tags': []}
    folder = create(client, 'folders', '手动建立')
    tag = create(client, 'tags', '收藏')
    client.put('/api/v1/resources/' + items['a.mp4']['id'] + '/organization', json={'folder_id': folder, 'tag_ids': [tag]})
    (root / 'new.mp4').write_bytes(b'new video')
    client.post('/api/v1/resources/scan')
    data = {item['name']: item for item in client.get('/api/v1/resources').json()['items']}
    assert data['a.mp4']['folder_id'] == folder
    assert data['a.mp4']['tags'] == [{'id': tag, 'name': '收藏'}]
    assert data['new.mp4']['folder_id'] is None and data['new.mp4']['tags'] == []
    assert client.get('/api/v1/resources?folder=__unfiled__').json()['total'] == 3
    # Classification survives a database reconnect and filesystem reconciliation.
    store = Store(root.parent / 'zhenxia.db')
    assert store.resources(folder=folder, tag=tag)['total'] == 1


def test_folder_tag_filters_rename_and_delete_preserve_files(archive):
    client, root, items = archive
    folder = create(client, 'folders', '旅行')
    tags = [create(client, 'tags', name) for name in ('风景', '周末')]
    resource_id = items['a.mp4']['id']
    result = client.put('/api/v1/resources/' + resource_id + '/organization', json={'folder_id': folder, 'tag_ids': tags + tags})
    assert result.status_code == 200
    assert len(result.json()['tags']) == 2
    filtered = client.get('/api/v1/resources', params={'folder': folder, 'tag': tags[0], 'kind': 'video', 'q': 'a.mp4', 'limit': 1}).json()
    assert filtered['total'] == 1 and filtered['bytes'] == len(b'video-a')
    assert filtered['items'][0]['folder_name'] == '旅行'
    assert client.get('/api/v1/resources', params={'folder': folder, 'tag': tags[0], 'kind': 'image'}).json()['total'] == 0
    counts = client.get('/api/v1/collections').json()
    assert counts['folders'][0]['count'] == 1
    assert all(tag['count'] == 1 for tag in counts['tags'])
    assert client.put('/api/v1/collections/folders/' + folder, json={'name': '旅行回忆'}).status_code == 200
    assert client.put('/api/v1/collections/tags/' + tags[0], json={'name': '自然'}).status_code == 200
    item = client.get('/api/v1/resources', params={'folder': folder}).json()['items'][0]
    assert item['folder_name'] == '旅行回忆' and any(t['name'] == '自然' for t in item['tags'])
    assert client.delete('/api/v1/collections/folders/' + folder).status_code == 200
    item = next(i for i in client.get('/api/v1/resources').json()['items'] if i['id'] == resource_id)
    assert item['folder_id'] is None and len(item['tags']) == 2
    assert client.delete('/api/v1/collections/tags/' + tags[0]).status_code == 200
    item = next(i for i in client.get('/api/v1/resources').json()['items'] if i['id'] == resource_id)
    assert len(item['tags']) == 1
    assert (root / 'a.mp4').read_bytes() == b'video-a'
    assert client.get('/api/v1/resources/' + resource_id + '/file').status_code == 200


def test_validation_atomicity_and_same_origin(archive):
    client, _, items = archive
    folder = create(client, 'folders', '  Videos  ')
    tag = create(client, 'tags', 'Favorite')
    assert client.post('/api/v1/collections/folders', json={'name': 'videos'}).status_code == 409
    assert client.post('/api/v1/collections/folders', json={'name': '   '}).status_code == 400
    assert client.post('/api/v1/collections/tags', json={'name': 'x' * 81}).status_code == 422
    assert client.post('/api/v1/collections/invalid', json={'name': 'oops'}).status_code == 400
    endpoint = '/api/v1/resources/' + items['a.mp4']['id'] + '/organization'
    assert client.put(endpoint, json={'folder_id': folder, 'tag_ids': [tag]}).status_code == 200
    for body in ({'tag_ids': ['missing']}, {'folder_id': 'missing'}, {'tag_ids': ['x'] * 31}):
        assert client.put(endpoint, json=body).status_code in (400, 422)
    item = client.get('/api/v1/resources', params={'folder': folder}).json()['items'][0]
    assert item['tags'][0]['id'] == tag
    assert client.put('/api/v1/resources/missing/organization', json={}).status_code == 404
    assert client.delete('/api/v1/collections/tags/missing').status_code == 404
    assert client.put('/api/v1/collections/folders/missing', json={'name': 'x'}).status_code == 404
    for method, url, body in (
        ('POST', '/api/v1/collections/folders', {'name': 'cross-site'}),
        ('PUT', endpoint, {}),
        ('DELETE', '/api/v1/collections/tags/' + tag, None),
    ):
        assert client.request(method, url, json=body, headers={'Origin': 'https://evil.test'}).status_code == 403
    assert client.put(endpoint, json={}).status_code == 200
    item = next(i for i in client.get('/api/v1/resources').json()['items'] if i['id'] == items['a.mp4']['id'])
    assert item['folder_id'] is None and item['tags'] == []


def test_trashed_and_missing_items_do_not_count_but_restore_keeps_labels(archive):
    client, root, items = archive
    folder = create(client, 'folders', 'To watch')
    tag = create(client, 'tags', 'Saved')
    endpoint = '/api/v1/resources/' + items['a.mp4']['id']
    client.put(endpoint + '/organization', json={'folder_id': folder, 'tag_ids': [tag]})
    payload = (root / 'a.mp4').read_bytes()
    (root / 'a.mp4').unlink()
    client.post('/api/v1/resources/scan')
    assert client.get('/api/v1/collections').json()['tags'][0]['count'] == 0
    (root / 'a.mp4').write_bytes(payload)
    client.post('/api/v1/resources/scan')
    assert client.get('/api/v1/resources', params={'folder': folder, 'tag': tag}).json()['total'] == 1
    assert client.delete(endpoint).status_code == 200
    assert client.get('/api/v1/collections').json()['folders'][0]['count'] == 0
    assert client.get('/api/v1/collections').json()['tags'][0]['count'] == 0
    assert client.put(endpoint + '/organization', json={}).status_code == 404


def test_existing_database_migrates_without_automatic_folders(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE resources (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
            size INTEGER NOT NULL, modified REAL NOT NULL, type TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'ready', video_id TEXT, title TEXT,
            author TEXT, source_url TEXT, trash_path TEXT, deleted_at TEXT)''')
        db.execute("INSERT INTO resources (id,name,path,size,modified,type) VALUES ('old','old.mp4','old.mp4',10,1,'video/mp4')")
    store = Store(path)
    assert store.collections() == {'folders': [], 'tags': []}
    assert store.resources()['items'][0]['folder_id'] is None
    folder = store.save_collection('folders', 'Archive')['id']
    store.organize_resource('old', folder, [])
    assert Store(path).resources()['items'][0]['folder_id'] == folder


def test_favicon_is_served_and_linked(archive):
    client, _, _ = archive
    assert 'href="/static/favicon.svg"' in client.get('/').text
    response = client.get('/static/favicon.svg')
    assert response.status_code == 200 and 'image/svg+xml' in response.headers['content-type']
    assert ElementTree.fromstring(response.content).tag.endswith('svg')
