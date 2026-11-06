"""Paths and worker dispatch for source and standalone distributions."""
import os
import shutil
import sys
from pathlib import Path


def frozen():
    return bool(getattr(sys, 'frozen', False))


def configure_runtime():
    if frozen():
        bundle = Path(sys._MEIPASS)
        os.environ['PATH'] = str(bundle / 'bin') + os.pathsep + os.environ.get('PATH', '')
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(bundle / 'browsers')


def user_directory():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    return base / 'Zhenxia'


def worker_command():
    if frozen():
        return [sys.executable, '--ytdlp-worker']
    return [sys.executable, '-m', 'zhenxia.ytdlp_worker']


def check_runtime():
    from playwright.sync_api import sync_playwright

    for tool in ('ffmpeg', 'ffprobe', 'node'):
        if not shutil.which(tool):
            raise RuntimeError('Missing bundled runtime: ' + tool)
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            raise RuntimeError('Missing bundled Chromium')
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        browser.close()
    from . import ytdlp_worker  # noqa: F401
    if not (Path(__file__).parent / 'static' / 'index.html').is_file():
        raise RuntimeError('Missing application assets')
    print('Runtime check passed', flush=True)
