"""Exercise the packaged app and isolated worker, without external platforms."""
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

exe = Path(sys.argv[1]).resolve()
subprocess.run([str(exe), '--self-check'], check=True, timeout=120)
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    # Invalid platform fails inside the worker and writes a result; never contact a website.
    subprocess.run([str(exe), '--ytdlp-worker'], input=json.dumps({
        'platform': 'unsupported', 'url': 'https://example.invalid/', 'directory': str(root)}),
        text=True, check=True, timeout=60)
    assert json.loads((root / 'result.json').read_text(encoding='utf-8')).get('error')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([str(exe), '--no-browser', '--config', str(root / 'config.yml'), '--port', str(port)], cwd=root)
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError('Packaged application exited early')
            try:
                base = 'http://127.0.0.1:' + str(port)
                with urllib.request.urlopen(base + '/api/v1/health', timeout=1) as response:
                    assert json.load(response)['status'] == 'ok'
                break
            except OSError:
                time.sleep(.5)
        else:
            raise RuntimeError('Packaged server did not become ready')
        for path in ('/', '/static/app.js', '/static/locales/en.json', '/api/v1/settings'):
            with urllib.request.urlopen(base + path, timeout=5) as response:
                assert response.status == 200
    finally:
        process.terminate()
        process.wait(timeout=30)
print('Packaged application smoke test passed')
