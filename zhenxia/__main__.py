import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
import yaml

from .adapter import load_config
from .app import build_app
from .runtime import configure_runtime, frozen, user_directory


def open_when_ready(server, url):
    for _ in range(300):
        if server.started:
            webbrowser.open(url)
            return
        if server.should_exit:
            return
        time.sleep(.1)


def main():
    configure_runtime()
    parser = argparse.ArgumentParser(description='Zhenxia · 帧匣')
    parser.add_argument('--config', '-c')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    desktop = frozen()
    config_path = Path(args.config or (user_directory() / 'config.yml' if desktop else 'data/config.yml')).resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        media = config_path.parent / 'Downloaded' if desktop else Path('Downloaded').resolve()
        config_path.write_text(yaml.safe_dump({'path': str(media), 'cookies': '', 'proxy': ''}), encoding='utf-8')
        config_path.chmod(0o600)
    server = uvicorn.Server(uvicorn.Config(build_app(load_config(config_path)), host=args.host,
                                          port=args.port if args.port is not None else 8000))
    if not desktop:
        server.run()
        return
    # Bind once and pass the socket to Uvicorn; avoid races with other local apps.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((args.host, args.port if args.port is not None else 0))
        sock.listen(128)
        url = 'http://{}:{}'.format(args.host, sock.getsockname()[1])
        print('Zhenxia: ' + url + '\nData: ' + str(config_path.parent), flush=True)
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(server, url), daemon=True).start()
        server.run(sockets=[sock])
    finally:
        sock.close()


if __name__ == '__main__':
    main()
