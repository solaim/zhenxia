# Zhenxia · 帧匣

**English** | [简体中文](README.zh-CN.md)

A self-hosted video downloader and media library. Paste a link to download videos, then search, preview, and manage your collection in the browser.

Supports Douyin, YouTube, TikTok, X / Twitter, and Bilibili, with download progress, retries, and an English / Chinese interface.

## Desktop packages (preview)

Native packages are being developed on `feature/native-packages`. Open the [Native packages workflow](https://github.com/solaim/zhenxia/actions/workflows/native-packages.yml), select a successful run, and download the artifact for Windows x64, macOS Intel / Apple Silicon, or Linux x64 / ARM64. Sign in to GitHub to download artifacts.

Extract the entire archive, then open `Start Zhenxia.bat` on Windows, `Start Zhenxia.command` on macOS, or `start-zhenxia.sh` on Linux. The app opens in your browser. Keep the terminal window open while using it; press Ctrl+C to stop. Python, Chromium, FFmpeg, and Node.js are included.

Preview packages are unsigned; Windows or macOS may ask you to approve opening them. Linux x64 packages target Ubuntu 22.04+; Linux ARM64 packages target Ubuntu 24.04+ and compatible desktop distributions. Both require system libraries used by Chromium. These are portable archives, not signed installers.

Settings and downloads are stored in `%LOCALAPPDATA%\Zhenxia` (Windows), `~/Library/Application Support/Zhenxia` (macOS), or `${XDG_DATA_HOME:-~/.local/share}/Zhenxia` (Linux). Keep this folder when upgrading. Docker data is not migrated automatically.

## Get started

Install [Docker](https://www.docker.com/), then run:

```bash
git clone https://github.com/solaim/zhenxia.git
cd zhenxia
docker compose up -d --build
```

Open [http://localhost:8000](http://localhost:8000). Configuration is created automatically on first launch.

## Usage

1. Paste a video link or share text on the home page and click Download.
2. Track progress in Download Tasks and retry failed downloads.
3. Search, preview, or save videos from the Library. Removed files are moved to `Downloaded/.trash/`.
4. Manage platform cookies and the download size limit in Settings. Multi-platform tasks default to 2 GB; set the limit to `0` for unlimited downloads. The separate Douyin engine retains a 2 GB limit per file.

| Platform | Supported links |
| --- | --- |
| Douyin | Videos, galleries, creator profiles, and short share links |
| YouTube | Individual videos, Shorts, and short video links |
| TikTok | Individual videos and short share links |
| X / Twitter | Videos in posts |
| Bilibili | BV / av video links |

When login is required, import cookies for that platform in Settings. Douyin accepts a Cookie request header; other platforms accept Netscape-format cookie file contents. TikTok also offers a login window in Settings.

Some videos may be unavailable due to platform verification, region, account permissions, or network restrictions. Live streams are not supported. Only download content you have permission to save.

## Network settings

Connections are direct by default. To use a proxy, edit `proxy` in `data/config.yml`, then restart:

```bash
docker compose restart web
```

On Docker Desktop, use `http://host.docker.internal:PORT` to reach a proxy on your host machine. Inside the container, `127.0.0.1` refers to the container itself. You can also set a proxy for a single platform:

```bash
ZHENXIA_PROXY_X=http://host.docker.internal:7897 docker compose up -d
```

Replace the example port with your own HTTP / mixed proxy port.

## Files and maintenance

- `Downloaded/`: downloaded videos.
- `data/`: configuration, login credentials, and task history. Stop the service before copying both directories for a backup.

```bash
# Stop the service
docker compose stop

# Update and start
git pull
docker compose up -d --build
```

The service listens on localhost by default and is intended for personal use. Do not expose it directly to the public internet.

Built with [douyin-downloader](https://github.com/jiji262/douyin-downloader) and [yt-dlp](https://github.com/yt-dlp/yt-dlp). Licensed under the [MIT License](LICENSE).
