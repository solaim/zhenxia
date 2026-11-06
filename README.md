# Zhenxia · 帧匣

**English** | [简体中文](README.zh-CN.md)

A self-hosted video downloader and media library. Paste a link to download videos, then search, preview, and manage your collection in the browser.

Supports Douyin, YouTube, TikTok, X / Twitter, and Bilibili, with download progress, retries, and an English / Chinese interface.

## Desktop packages (preview)

Published packages are available on [GitHub Releases](https://github.com/solaim/zhenxia/releases). For unreleased previews, open the [Native packages workflow](https://github.com/solaim/zhenxia/actions/workflows/native-packages.yml), select a successful run, and download the artifact for Windows x64, macOS Intel / Apple Silicon, or Linux x64 / ARM64. Sign in to GitHub to download artifacts.

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
3. Search, preview, or save videos from the Library. Reopening a video or audio file with saved progress lets you start over or resume. Progress stays in the current browser and is cleared when playback finishes. Removed files are moved to `Downloaded/.trash/`.
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

## Organize your library

Create folders manually with **Manage folders**, then choose **Organize** on a resource to assign its folder and tags. New downloads stay **Unfiled** until you move them. Each resource can belong to one folder and have multiple tags. Folder, tag, search, and media-type filters can be combined.

Rename or delete folders and tags from their management dialogs. Deleting a folder makes its resources unfiled; deleting a tag removes that label. Neither action deletes or moves media files. Organization is saved in `data/zhenxia.db` and survives rescans and restarts.

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

## Publishing a release

The native package workflow publishes a GitHub Release when a `v*` tag is pushed. First set the same version in `pyproject.toml` and `zhenxia/__init__.py`, commit it, then tag that commit:

```bash
git tag -a v0.1.0 -m "Zhenxia v0.1.0"
git push origin v0.1.0
```

The tagged commit must contain the release workflow (currently on `feature/native-packages`). CI validates the version, builds and tests all five platforms, then uploads the archives and `SHA256SUMS.txt` to a release with generated notes. A failed platform blocks publication. Tags such as `v0.2.0-rc.1` publish a prerelease (use package version `0.2.0rc1`); branch pushes and manual builds only produce preview artifacts. Releases do not expire after 14 days and public release downloads do not require a GitHub login. No extra token is needed: publishing uses the workflow's `GITHUB_TOKEN`.
