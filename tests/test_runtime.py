import os
import sys
from pathlib import Path

from zhenxia import runtime


def test_user_directory_platforms(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    assert runtime.user_directory() == tmp_path / 'local' / 'Zhenxia'
    monkeypatch.setattr(sys, 'platform', 'darwin')
    assert runtime.user_directory() == tmp_path / 'Library' / 'Application Support' / 'Zhenxia'
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg'))
    assert runtime.user_directory() == tmp_path / 'xdg' / 'Zhenxia'


def test_frozen_runtime_and_worker_dispatch(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setenv('PATH', '/existing')
    # Undo environment changes at the end of this test.
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', '/old')
    runtime.configure_runtime()
    assert runtime.worker_command() == [sys.executable, '--ytdlp-worker']
    assert str(tmp_path / 'bin') in os.environ['PATH']
    assert os.environ['PLAYWRIGHT_BROWSERS_PATH'] == str(tmp_path / 'browsers')


def test_source_worker_dispatch(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    assert runtime.worker_command() == [sys.executable, '-m', 'zhenxia.ytdlp_worker']
