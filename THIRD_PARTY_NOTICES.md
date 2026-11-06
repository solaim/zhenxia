# Third-party components

Zhenxia application code is MIT licensed. Dependencies and system packages retain their own licenses; this document does not relicense those components.

- [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader): MIT; installed from a pinned Git commit. Existing attribution is preserved.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp): Unlicense for its Python source / PyPI distribution. Installed as a pinned dependency; no source is copied. Official bundled executable distributions can have different combined licenses; this application uses the PyPI package.
- [yt-dlp-ejs](https://github.com/yt-dlp/ejs): Unlicense with bundled MIT / ISC components; installed by yt-dlp's default extra.
- [FFmpeg](https://ffmpeg.org/legal.html): license depends on the build; the Docker image installs Debian's FFmpeg package. Preserve the package copyright notices when distributing images. The Python application invokes FFmpeg as an external process.
- [Node.js](https://github.com/nodejs/node/blob/main/LICENSE): MIT and third-party notices; provided by the official Node 22 Docker image.

## Integration assessment

Verified against official yt-dlp README and release 2026.10.26 on 2026-11-05. yt-dlp provides site-specific extractors, Python integration hooks, cookie support, format selection, and FFmpeg postprocessing. Full YouTube support requires yt-dlp-ejs and a supported JavaScript runtime. Release 2026.10.26 requires Python 3.11+.

A curated platform router and disabled generic extractor bound the application scope. Existing Douyin behavior remains separate. Site extractors need frequent updates and successful downloads depend on permissions, connectivity and anti-bot restrictions. Telegram client sessions are a separate integration, not covered here. DRM decryption is not provided.

Official references: [README / dependencies](https://github.com/yt-dlp/yt-dlp#dependencies), [supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md), [release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26).
