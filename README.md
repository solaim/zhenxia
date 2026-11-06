# 帧匣 · Zhenxia

收藏值得回看的每一帧。自部署的多平台视频下载与媒体资源库。

- Web 提交视频、分享文本和作者主页链接，查看状态、实时进度和失败原因。
- SQLite 管理任务、资源索引和任务与文件关联，支持搜索、类型筛选和分页。
- 视频预览、浏览器保存、移入本地回收目录；启动与手动刷新时同步磁盘。
- 本机保存 Cookie，API 不回显凭证；Docker 一键运行。

## 启动

```bash
docker compose up -d --build
```

访问 **http://localhost:8000**。首次启动自动生成 `data/config.yml`。默认只监听本机，没有多用户认证，请勿直接暴露公网。

## 界面语言

右上角可切换简体中文和 English。首次打开按浏览器语言选择，手动选择保存在当前浏览器，不影响其他用户。界面、操作提示、日期和应用内错误会随语言切换；第三方下载引擎的原始诊断保留原文。新增语言时在 `zhenxia/static/locales/` 添加 JSON 字典，并在 `i18n.js` 和语言选择器中注册。

## 网络与代理

开源默认直接连接，不内置任何代理服务器、个人端口或凭证，也不自动读取操作系统代理或通用 `HTTP_PROXY` / `HTTPS_PROXY`。Docker 中的 `127.0.0.1` 是容器自身。`data/config.yml` 和真实会话文件不进入 Git / Docker 构建上下文。

代理优先级：`ZHENXIA_PROXY_<PLATFORM>` → `ZHENXIA_PROXY` → `data/config.yml` 的 `proxy`。环境变量未设置表示沿用下一层；显式空值表示直连。平台名称为 `DOUYIN`、`YOUTUBE`、`TIKTOK`、`X`、`BILIBILI`。仅支持 HTTP / HTTPS 代理地址，SOCKS 请使用代理客户端提供的 HTTP / mixed 端口，避免不同下载引擎行为不一致。

| 运行环境 | 配置方式 |
| --- | --- |
| 可直连的本机 / 服务器 | 保持默认，无需代理 |
| Docker Desktop（macOS / Windows） | 使用 `http://host.docker.internal:<端口>` 访问宿主机代理 |
| Linux Docker Engine | 使用下面的 host-gateway 覆盖文件；宿主机代理需允许 Docker 网桥访问 |
| 远程服务器 / NAS | 使用服务器能够访问的代理地址；用户电脑的 localhost 不可直接使用 |
| 容器网络内的代理服务 | 使用同一 Docker 网络中的服务名，例如 `http://proxy:8080` |
| 本机 Python 运行 | 可使用 `http://127.0.0.1:<端口>`，环境变量规则相同 |

例如只让 YouTube 使用代理，其他平台直连（7897 仅为示例，请替换为自己的端口）：

```bash
ZHENXIA_PROXY='' ZHENXIA_PROXY_YOUTUBE=http://host.docker.internal:7897 docker compose up -d
```

Linux 宿主机代理：

```bash
ZHENXIA_PROXY_YOUTUBE=http://host.docker.internal:7897 docker compose -f compose.yaml -f compose.host-proxy.yaml up -d
```

不要为了连接代理将其无保护地暴露到公网；仅允许所需 Docker 网段访问。使用远程认证代理时，将凭证保存在本机受保护的配置或环境中，避免提交到 Git。代理不会通过 API 回显。更改环境变量后用 `docker compose up -d` 重建容器配置；只改 YAML 下载配置时执行 `docker compose restart web`。

排查时分开检查 DNS、TCP、代理握手与平台响应。停在“连接 / 解析”且没有媒体字节，通常应先检查容器网络；网站返回登录 / 人机验证时再配置该平台 Cookie。无法保证代理能解决账号权限、地区、平台验证或视频不可用问题。

## 数据与迁移

| 路径 | 用途 |
| --- | --- |
| `Downloaded/` | 媒体文件和可选元数据 |
| `Downloaded/.trash/` | 移除的媒体，可手动移回原路径后点刷新恢复 |
| `data/zhenxia.db` | SQLite：任务、资源、关联与迁移版本 |
| `data/.cookies.json` | 抖音会话凭证 |
| `data/platform-cookies/` | 各平台 Netscape Cookie 文件 |
| `data/config.yml` | 下载配置 |

视频仍存为普通文件，不将二进制内容存入 SQLite。SQLite 使用 WAL、外键和事务；请求中的数据库操作通过线程执行，避免阻塞异步服务。列表直接查询数据库，不在每次请求时遍历磁盘。

**从旧 Web 版迁移**：停止旧服务，将 `Downloaded/` 和 `data/` 复制到本项目，再启动。首次启动自动导入 `data/web-jobs.json`，保留原 JSON 作为备份；扫描已有媒体建立资源索引。迁移重复运行不会产生重复任务，重启时未完成任务标记为失败，可手动重试。启动和下载完成后自动同步；在磁盘上手动新增、删除或恢复文件后，点击页面「刷新」。

新数据库不依赖旧项目目录。任务记录最多显示最近 500 条，数据库保留完整记录，不再按 24 小时删除历史。上游可能产生的数据库与本应用数据库相互独立。

备份：先执行 `docker compose stop`，再复制整个 `data/` 和 `Downloaded/`（包含 SQLite WAL 文件），最后 `docker compose start`。不要在写入过程中只复制 `.db` 文件。

## 下载引擎依赖

[jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader) 以 **Git 依赖**安装，固定 commit：

```
1e08f03b8909b364fb6237d8f9f441e3fbf3d427
```

本仓库不复制上游 `core/`、`auth/`、`storage/` 等源码。仅 `zhenxia/adapter.py` 调用上游内部 Python API；更新引擎时修改 `pyproject.toml` 中的 commit，并执行适配层测试。上游 API 未承诺稳定，依赖不能直接跟随 main。单条视频另由本项目的 `zhenxia/browser.py` 通过正常浏览器页面获取 MP4 地址。

### 多平台：yt-dlp

[yt-dlp](https://github.com/yt-dlp/yt-dlp) 以 PyPI 依赖 `yt-dlp[default]==2026.10.26` 安装，不复制源码。Docker 自带 FFmpeg / ffprobe、Node.js 和 yt-dlp-ejs；YouTube 需要 JavaScript 运行时，应用显式启用 Node，不在任务运行时自动获取远程脚本或第三方插件。Python 最低版本随本次依赖升级为 3.11。

| 平台 | 本应用开放的链接 |
| --- | --- |
| 抖音 | 视频、图集、作者主页、短链接；保留现有引擎 |
| YouTube | 单视频、Shorts、视频短链接；带 list 的视频链接只下载该视频 |
| TikTok | 单视频、vm/vt 短链接；不支持图集 |
| X / Twitter | 单条帖子中的视频 |
| 哔哩哔哩 | BV / av 单视频链接；多 P 最多 10 项 |

按域名识别平台，拒绝任意 URL、内网地址和 yt-dlp Generic extractor。频道、播放列表、用户主页（抖音除外）、直播和 Telegram 未开放。平台解析器存在不代表所有视频都能下载，站点改版、区域、网络、登录验证和账号权限均可能使下载失败。失败信息显示在任务列表。

其他平台 Cookie 在设置页按平台独立导入 **Netscape Cookie 文件文本**，不可粘贴抖音式请求头；只接受所选平台域名，不自动读取宿主机浏览器。保存在 `data/platform-cookies/<platform>.txt`，文件权限 0600，API 仅返回是否配置。每次任务使用临时副本，避免不同平台和并发任务混用凭证。配置代理可编辑 `data/config.yml` 的 `proxy` 后重启服务，代理应能从容器内访问。

下载在独立子进程执行，超时或取消时终止整个进程组（Docker / Linux / macOS），同时停止 FFmpeg 和 JavaScript 子进程。临时文件写入隐藏目录 `Downloaded/.staging/`，仅完成文件进入 `Downloaded/<platform>/`；异常退出不会把视频片段计入资源库。强制断电可能遗留 staging，可在服务停止后清理。简化的标题、作者和来源元数据随媒体写入 `.info.json`，统一进入 SQLite 并关联下载任务。

优先选择兼容浏览器的 H.264/AAC，最高 1080p，格式不可用时回退；FFmpeg 合并音视频但不强制转码，部分格式仍需保存后用本地播放器打开。每任务最多 10 段媒体、下载总量约 2 GB、最长 10 分钟，不提供 DRM 解密。再次下载会重新获取到 staging，已有目标文件保留并计为跳过。

引擎升级：修改固定版本，运行测试并执行 `docker compose up -d --build`。不在运行中的容器内自更新。评估和依赖许可见 [第三方说明](THIRD_PARTY_NOTICES.md)。

本项目与 Douzy 桌面产品独立。保留上游 MIT 许可与署名，在页面页脚注明使用的开源项目。

## 限制

抖音与其他平台通过不同引擎下载。平台登录、验证、页面和网络变化仍会导致失败，不保证所有链接可下载。单条视频获取页面播放 MP4，不保证原始上传画质；单文件上限 2 GB，任务最长 10 分钟。作者主页与图集沿用上游能力和限制；短链接先解析。浏览器和上游引擎任务串行执行，避免资源归属混淆，不进行多进程/多副本部署。

移除仅移动媒体文件，元数据文件保留。受浏览器支持的编码影响，部分媒体可能只能保存，不能在线播放。只下载你有权保存的内容。

## 开发与测试

需要 Python 3.11+、Git、FFmpeg 和 Node.js 22+；Docker 使用 Python 3.12。

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m playwright install --with-deps chromium
python -m zhenxia --config data/config.yml
ruff check .
python -m pytest -q
```

本机开发在缺省配置下使用 `./Downloaded/`；Docker 的配置样例使用 `/app/Downloaded`。已有 Docker 配置用于本机开发时需将 path 改为本机路径。

前端位于 `zhenxia/static/`，不需要 Node 构建。OpenAPI 文档：`/docs`。

- `POST /api/v1/download`：提交链接或分享文本
- `GET /api/v1/jobs`、`GET /api/v1/jobs/{id}`：任务历史和关联资源
- `POST /api/v1/jobs/{id}/retry`：原地重试同一个任务，保留任务 ID 和创建时间
- `GET /api/v1/resources`：SQLite 搜索、筛选、分页
- `POST /api/v1/resources/scan`：同步磁盘资源
- `GET /api/v1/resources/{id}/file`：播放或下载（`?download=true`）
- `DELETE /api/v1/resources/{id}`：移入回收目录
- `GET /api/v1/settings`：各平台 Cookie 配置状态（不含凭证）
- `PUT /api/v1/settings/cookies/{platform}`：保存或清除平台 Netscape Cookie

详见 [贡献指南](CONTRIBUTING.md)、[安全说明](SECURITY.md) 与 [MIT License](LICENSE)。运行数据不进入 Git 或 Docker 镜像。

## 转写配置

偏好设置提供上游 `transcript` 配置：接口完整地址、模型、密钥环境变量名与本地备用密钥。密钥留空保留，勾选清除才删除本地密钥；环境变量值优先。Compose 默认传入宿主机 `OPENAI_API_KEY`，自定义变量名需要自行添加传入项。设置保存在权限 0600 的运行配置，不进入 Git，API 不回显密钥。当前仅上游抖音批量引擎会调用该功能；帧匣单视频和 yt-dlp 任务尚未接入。默认不启用，保存不会调用远程 API。启用后相关媒体会上传至配置的转写服务，可能收费。

## TikTok 引导登录

偏好设置 → TikTok 登录授权：在临时浏览器中完成 TikTok 自有账号、验证码或扫码登录；检测到非空登录会话 Cookie 后自动保存并关闭浏览器。Cookie 存在仅是登录信号，不保证账号权限、地区或下载验证通过。第三方登录弹窗暂不支持。

不暴露 VNC 或调试端口；通过同源 API 传输画面和有限操作。一次只允许一个登录窗口，用随机 HttpOnly / SameSite Strict 会话 Cookie 校验控制权，HTTPS 下附加 Secure。10 分钟超时、取消及服务停止时清理浏览器，不保存画面、输入或 profile；仅保存 TikTok 域名 Cookie，权限 0600，不回显凭证。仍是单用户本机应用，远程访问请使用受保护的 HTTPS 或 SSH 隧道。

重新登录使用全新上下文；登录失败保留旧凭证。清除仅删除本地 Cookie，不会撤销平台服务端会话。使用 TikTok 对应的代理设置，手动导入作为备用入口。完整账号登录需要用户自行完成。

在偏好设置中可调整多平台引擎的每任务下载上限（默认 2 GB，0 表示不限），设置持久保存在 data/download-settings.json，对后续执行的任务生效。抖音独立引擎不使用此设置。
