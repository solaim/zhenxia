# 帧匣 · Zhenxia

[English](README.md) | **简体中文**

自部署的多平台视频下载与资源库。粘贴链接即可下载，在浏览器中管理、搜索和预览收藏的视频。

支持抖音、YouTube、TikTok、X / Twitter 和哔哩哔哩，提供下载进度、失败重试和中英文界面。

## 桌面包（预览）

正式发布的包可在 [GitHub Releases](https://github.com/solaim/zhenxia/releases) 下载。未发布的预览包可打开 [Native packages 构建页面](https://github.com/solaim/zhenxia/actions/workflows/native-packages.yml)，选择成功的构建，下载 Windows x64、macOS Intel / Apple Silicon 或 Linux x64 / ARM64 对应的产物。下载构建产物需登录 GitHub。

完整解压后，Windows 双击 `Start Zhenxia.bat`，macOS 双击 `Start Zhenxia.command`，Linux 运行 `start-zhenxia.sh`，浏览器会自动打开。使用期间保留终端窗口，按 Ctrl+C 停止服务。包内包含 Python、Chromium、FFmpeg 和 Node.js。

预览包尚未签名，Windows 或 macOS 可能要求确认打开。Linux x64 面向 Ubuntu 22.04+，ARM64 面向 Ubuntu 24.04+ 及兼容桌面发行版，仍需系统提供 Chromium 所需的基础库。目前提供免安装压缩包，并非签名安装程序。

配置与下载保存在 Windows 的 `%LOCALAPPDATA%\Zhenxia`、macOS 的 `~/Library/Application Support/Zhenxia`、Linux 的 `${XDG_DATA_HOME:-~/.local/share}/Zhenxia`。升级时保留该目录即可；暂不自动迁移 Docker 数据。

## 启动

安装 [Docker](https://www.docker.com/)，然后执行：

```bash
git clone https://github.com/solaim/zhenxia.git
cd zhenxia
docker compose up -d --build
```

打开 [http://localhost:8000](http://localhost:8000)。首次启动自动生成配置，无需手动创建。

## 使用

1. 在首页粘贴视频链接或分享文本，点击下载。
2. 在「下载任务」查看进度，失败后可重试。
3. 在「资源库」搜索、预览或保存视频。再次打开有播放记录的视频或音频时，可选择重新开始或从上次位置继续；进度保存在当前浏览器，播放结束后清除。移除的文件保存在 `Downloaded/.trash/`。
4. 在「偏好设置」管理平台 Cookie 和下载大小上限。多平台任务默认上限为 2 GB，设为 `0` 表示不限；抖音独立引擎仍有单文件 2 GB 限制。

| 平台 | 支持的链接 |
| --- | --- |
| 抖音 | 视频、图集、作者主页、分享短链接 |
| YouTube | 单视频、Shorts、视频短链接 |
| TikTok | 单视频、分享短链接 |
| X / Twitter | 帖子中的视频 |
| 哔哩哔哩 | BV / av 视频链接 |

需要登录时，在设置页导入对应平台的 Cookie：抖音使用请求头 Cookie，其他平台使用 Netscape 格式的 Cookie 文件文本。TikTok 也可通过设置页的登录窗口完成授权。

部分视频可能因平台验证、地区、账号权限或网络限制而无法下载。暂不支持直播；只下载你有权保存的内容。

## 整理资源库

通过「管理文件夹」手动创建文件夹，再点击资源卡片的「整理」，选择文件夹并添加标签。新下载的资源保持「未分类」，不会自动分配。每个资源可以属于一个文件夹、拥有多个标签；文件夹、标签、搜索及媒体类型可组合筛选。

在管理弹窗中可重命名或删除文件夹与标签。删除文件夹后资源回到未分类；删除标签只移除该标签。这些操作不移动或删除媒体文件。分类保存在 `data/zhenxia.db`，刷新磁盘、重启后仍保留。

## 网络设置

默认直连。如需代理，编辑 `data/config.yml` 中的 `proxy`，然后重启：

```bash
docker compose restart web
```

Docker Desktop 访问宿主机代理时使用 `http://host.docker.internal:端口`，不要使用容器内的 `127.0.0.1`。也可通过环境变量为单个平台指定代理，例如：

```bash
ZHENXIA_PROXY_X=http://host.docker.internal:7897 docker compose up -d
```

将示例端口替换为自己的 HTTP / mixed 代理端口。

## 文件与维护

- `Downloaded/`：下载的视频。
- `data/`：配置、登录凭证和任务记录。备份时先停止服务，再复制这两个目录。

```bash
# 停止服务
docker compose stop

# 更新并启动
git pull
docker compose up -d --build
```

默认仅监听本机，适合个人使用，请勿直接暴露公网。

基于 [douyin-downloader](https://github.com/jiji262/douyin-downloader) 和 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 构建，使用 [MIT License](LICENSE)。

## 发布版本

推送 `v*` 标签后，原生包工作流自动发布 GitHub Release。先将 `pyproject.toml` 和 `zhenxia/__init__.py` 中的版本号改为一致并提交，再给该提交打标签：

```bash
git tag -a v0.1.0 -m "Zhenxia v0.1.0"
git push origin v0.1.0
```

标签指向的提交须包含发布工作流（目前在 `feature/native-packages` 分支）。CI 会校验版本、构建并验证五个平台，全部通过后上传压缩包和 `SHA256SUMS.txt`，自动生成发布说明；任一平台失败都不会发布。`v0.2.0-rc.1` 这样的标签发布为预发布版本（代码版本号使用 `0.2.0rc1`）。普通分支推送和手动构建只生成预览产物。Release 附件没有 14 天过期限制，公开仓库的附件无需登录即可下载。使用内置 `GITHUB_TOKEN`，不需要配置个人令牌。
