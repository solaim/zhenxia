import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('native_release', Path(__file__).parents[1] / 'packaging' / 'release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'zhenxia').mkdir()
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion="0.1.0"\n', encoding='utf-8')
    (tmp_path / 'zhenxia' / '__init__.py').write_text('__version__="0.1.0"\n', encoding='utf-8')
    return tmp_path


def test_tag_must_match_both_versions(project):
    assert str(release.validate_tag('v0.1.0', project)) == '0.1.0'
    for tag in ('v0.2.0', 'main', 'v0.1.0;echo unsafe'):
        with pytest.raises(ValueError):
            release.validate_tag(tag, project)
    (project / 'zhenxia' / '__init__.py').write_text('__version__="0.2.0"', encoding='utf-8')
    with pytest.raises(ValueError, match='__version__'):
        release.validate_tag('v0.1.0', project)


def test_missing_platform_blocks_publication(project, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match='all five'):
        release.publish('v0.1.0', project, project, 'owner/repo')
    assert calls == []


@pytest.mark.parametrize('prerelease', [False, True])
def test_publish_checksums_and_prerelease_flags(project, monkeypatch, prerelease):
    tag = 'v0.2.0-rc.1' if prerelease else 'v0.1.0'
    if prerelease:
        (project / 'pyproject.toml').write_text('[project]\nversion="0.2.0rc1"', encoding='utf-8')
        (project / 'zhenxia' / '__init__.py').write_text('__version__="0.2.0rc1"', encoding='utf-8')
    assets = []
    for target, extension in release.TARGETS.items():
        path = project / ('Zhenxia-' + target + extension)
        path.write_bytes(target.encode())
        assets.append(path)
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda command, **kw: calls.append((command, kw)))
    release.publish(tag, project, project, 'owner/repo')
    command, options = calls[0]
    assert command[:4] == ['gh', 'release', 'create', tag]
    assert '--verify-tag' in command
    assert ('--prerelease' in command) == prerelease
    assert options['check']
    for asset in assets:
        assert str(asset) in command
        assert hashlib.sha256(asset.read_bytes()).hexdigest() + '  ' + asset.name in (project / 'SHA256SUMS.txt').read_text(encoding='utf-8')
