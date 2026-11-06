import argparse
from pathlib import Path

import uvicorn

from .adapter import load_config
from .app import build_app


def main():
    parser = argparse.ArgumentParser(description='帧匣 · 本地视频收藏室')
    parser.add_argument('--config', '-c', default='data/config.yml')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(build_app(load_config(config_path)), host=args.host, port=args.port)


if __name__ == '__main__':
    main()
