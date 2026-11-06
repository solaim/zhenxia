"""帧匣 Web 与 API。下载引擎接口统一经由 adapter 调用。"""

from __future__ import annotations

import asyncio
import hashlib
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .adapter import Engine
from .credentials import PlatformCookies
from .download_settings import DownloadSettings
from .jobs import JobManager, QueueFull
from .library import Library
from .login import LoginBusy, LoginSession
from .network import proxy_for
from .platforms import PLATFORMS, normalize_link
from .store import Store
from .transcript_settings import TranscriptSettings
from .ytdlp import YtDlpEngine


class DownloadRequest(BaseModel):
    url: str


class CookieRequest(BaseModel):
    cookie: str


class LoginAction(BaseModel):
    kind: str
    x: float = 0
    y: float = 0
    text: str = ''
    key: str = ''
    end_x: float = 0
    end_y: float = 0


class TranscriptRequest(BaseModel):
    enabled: bool = False
    api_url: str
    api_key_env: str = 'OPENAI_API_KEY'
    api_key: str = ''
    clear_key: bool = False
    model: str = 'gpt-4o-mini-transcribe'


class DownloadLimitsRequest(BaseModel):
    max_gb: float = Field(ge=0, le=1024, allow_inf_nan=False)


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class OrganizeRequest(BaseModel):
    folder_id: str | None = None
    tag_ids: List[str] = Field(default_factory=list, max_length=30)


class JobResponse(BaseModel):
    job_id: str
    status: str
    url: str


def build_app(config) -> FastAPI:
    data_dir = Path(config.config_path).resolve().parent if config.config_path else Path("data").resolve()
    store = Store(data_dir / "zhenxia.db")
    engine = Engine(config, data_dir)
    library = Library(config.get("path"), store)
    credentials = PlatformCookies(data_dir)
    transcript = TranscriptSettings(config)
    download_settings = DownloadSettings(data_dir)
    multi_engine = YtDlpEngine(library.root, credentials, proxy_for({'proxy': getattr(config, 'zhenxia_proxy', config.get('proxy'))}))
    multi_engine.platform_proxies = {platform: proxy_for({'proxy': getattr(config, 'zhenxia_proxy', config.get('proxy'))}, platform) for platform in PLATFORMS if platform != 'douyin'}
    login = LoginSession(credentials, multi_engine.platform_proxies['tiktok'])
    # Serialize upstream execution to associate newly written files with the correct task.
    download_lock = asyncio.Lock()

    async def executor(url):
        async with download_lock:
            platform, url = normalize_link(url)
            if platform != 'douyin':
                multi_engine.max_bytes = int(download_settings.public()['max_gb'] * 1024 ** 3)
                return await multi_engine.download(platform, url)
            url = await engine.resolve(url)
            match = re.fullmatch(r"https://www\.douyin\.com/video/(\d+)", url)
            if match:
                from .browser import download_video
                result = await download_video(match.group(1), library.root, engine.cookies(),
                                              config.get("proxy"))
                result["resource_paths"] = [match.group(1) + ".mp4"]
                return result
            before = await asyncio.to_thread(library.snapshot)
            try:
                result = await engine.download(url)
            finally:
                await asyncio.to_thread(library.scan)
            after = await asyncio.to_thread(library.snapshot)
            result["resource_paths"] = [p for p in after if before.get(p) != after[p]]
            return result

    manager = JobManager(executor, store, library, max_concurrency=1)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.to_thread(store.migrate_legacy, data_dir / "web-jobs.json")
        await manager.start()
        await asyncio.to_thread(library.scan)
        await asyncio.to_thread(store.link_legacy_resources)
        try:
            yield
        finally:
            await login.close()
            await manager.shutdown()

    app = FastAPI(
        title="帧匣 API",
        version="1.0",
        description="帧匣：视频下载与 SQLite 资源管理",
        lifespan=lifespan,
    )
    app.state.job_manager = manager
    app.state.engine = engine
    app.state.login = login
    app.state.multi_engine = multi_engine
    app.state.store = store
    app.state.library = library

    @app.get("/api/v1/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/download", response_model=JobResponse)
    async def create_job(req: DownloadRequest) -> JobResponse:
        if not req.url.strip():
            raise HTTPException(status_code=400, detail="url is required")
        try:
            _, url = normalize_link(req.url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            job = await manager.submit(url)
        except QueueFull as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        return JobResponse(job_id=job.job_id, status=job.status, url=job.url)

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> Dict[str, Any]:
        job = await manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/api/v1/jobs")
    async def list_jobs() -> Dict[str, List[Dict[str, Any]]]:
        jobs = await manager.list_jobs()
        return {"jobs": jobs}

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "不允许跨站操作"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "不允许跨站操作"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; frame-ancestors 'none'"
        if request.url.path in {"/docs", "/redoc"}:
            del response.headers["Content-Security-Policy"]
        if request.url.path.startswith("/api/") or request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/resources")
    async def resources(q: str = "", kind: str = "all", offset: int = Query(0, ge=0),
                        limit: int = Query(60, ge=1, le=200), folder: str | None = None,
                        tag: str | None = None):
        return await asyncio.to_thread(library.list, q, kind, offset, limit, folder, tag)

    async def collection_action(action, *args):
        try:
            return await asyncio.to_thread(action, *args)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=409 if str(exc) == 'Name already exists' else 400, detail=str(exc))

    @app.get('/api/v1/collections')
    async def collections():
        return await asyncio.to_thread(store.collections)

    @app.post('/api/v1/collections/{kind}', status_code=201)
    async def create_collection(kind: str, req: CollectionRequest):
        return await collection_action(store.save_collection, kind, req.name)

    @app.put('/api/v1/collections/{kind}/{collection_id}')
    async def rename_collection(kind: str, collection_id: str, req: CollectionRequest):
        return await collection_action(store.save_collection, kind, req.name, collection_id)

    @app.delete('/api/v1/collections/{kind}/{collection_id}')
    async def delete_collection(kind: str, collection_id: str):
        await collection_action(store.delete_collection, kind, collection_id)
        return {'ok': True}

    @app.put('/api/v1/resources/{resource_id}/organization')
    async def organize_resource(resource_id: str, req: OrganizeRequest):
        return await collection_action(store.organize_resource, resource_id, req.folder_id, req.tag_ids)

    @app.post("/api/v1/resources/scan")
    async def scan_resources():
        return await asyncio.to_thread(library.scan)

    @app.post("/api/v1/jobs/{job_id}/retry", response_model=JobResponse)
    async def retry_job(job_id: str):
        previous = await manager.get(job_id)
        if previous is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        if previous["status"] not in {"failed", "success"}:
            raise HTTPException(status_code=409, detail="任务仍在运行")
        try:
            job = await manager.retry(job_id)
        except QueueFull as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=409 if str(exc) == '任务仍在运行' else 404, detail=str(exc))
        return JobResponse(job_id=job.job_id, status=job.status, url=job.url)

    def find_resource(resource_id):
        try:
            return library.find(resource_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="资源不存在")

    @app.get("/api/v1/resources/{resource_id}/file")
    async def resource_file(resource_id: str, download: bool = False):
        path = await asyncio.to_thread(find_resource, resource_id)
        return FileResponse(path, filename=path.name,
                            content_disposition_type="attachment" if download else "inline")

    @app.delete("/api/v1/resources/{resource_id}")
    async def delete_resource(resource_id: str):
        try:
            await asyncio.to_thread(library.trash, resource_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="资源不存在")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

    @app.get("/api/v1/settings")
    async def settings():
        return {"cookie_configured": bool(engine.cookies()),
                "browser_enabled": True,
                "transcript": transcript.public(),
                "download_limits": download_settings.public(),
                "platforms": [{"id": key, "name": name,
                               "cookie_configured": bool(engine.cookies()) if key == 'douyin' else credentials.configured(key)}
                              for key, name in PLATFORMS.items()]}

    @app.put('/api/v1/settings/download-limits')
    async def save_download_limits(req: DownloadLimitsRequest):
        return await asyncio.to_thread(download_settings.save, req.max_gb)

    @app.put("/api/v1/settings/cookie")
    async def save_cookie(req: CookieRequest):
        try:
            configured = await asyncio.to_thread(engine.save_cookie, req.cookie)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"cookie_configured": configured}

    @app.put("/api/v1/settings/cookies/{platform}")
    async def save_platform_cookie(platform: str, req: CookieRequest):
        try:
            configured = await asyncio.to_thread(credentials.save, platform, req.cookie)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"cookie_configured": configured}

    @app.put('/api/v1/settings/transcript')
    async def save_transcript(req: TranscriptRequest):
        try:
            return await asyncio.to_thread(transcript.save, req.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    def login_owner(request):
        if not login.owns(request.cookies.get('zhenxia_login')):
            raise HTTPException(status_code=403, detail='Login session not owned by this browser')

    @app.post('/api/v1/login/tiktok')
    async def start_login(request: Request):
        try:
            token = await login.start(request.cookies.get('zhenxia_login'))
        except LoginBusy:
            raise HTTPException(status_code=409, detail='A login session is already in use')
        response = JSONResponse(login.status())
        response.set_cookie('zhenxia_login', token, max_age=660, httponly=True,
                            secure=request.url.scheme == 'https', samesite='strict', path='/api/v1/login')
        return response

    @app.get('/api/v1/login/status')
    async def login_status(request: Request):
        login_owner(request)
        return login.status()

    @app.get('/api/v1/login/frame')
    async def login_frame(request: Request):
        login_owner(request)
        try:
            frame = await login.frame()
        except Exception:
            raise HTTPException(status_code=503, detail='Login frame unavailable')
        return Response(frame or b'', status_code=200 if frame else 204, media_type='image/jpeg')

    @app.post('/api/v1/login/action')
    async def login_action(request: Request, action: LoginAction):
        login_owner(request)
        try:
            await asyncio.wait_for(login.act(action.model_dump()), timeout=10)
        except (ValueError, asyncio.TimeoutError):
            raise HTTPException(status_code=400, detail='Login action unavailable')
        return {'ok': True}

    @app.delete('/api/v1/login/session')
    async def cancel_login(request: Request):
        login_owner(request)
        await login.close()
        return login.status()

    @app.delete('/api/v1/login/tiktok/credentials')
    async def clear_tiktok_login():
        async with login.lock:
            if login.state in {'starting', 'waiting'}:
                raise HTTPException(status_code=409, detail='Close the login window first')
            await asyncio.to_thread(credentials.save, 'tiktok', '')
        return {'ok': True}

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        html = (static / "index.html").read_text(encoding='utf-8')
        for asset in ('app.js', 'i18n.js', 'style.css'):
            version = hashlib.sha256((static / asset).read_bytes()).hexdigest()[:12]
            html = html.replace('/static/' + asset, '/static/' + asset + '?v=' + version)
        return HTMLResponse(html)

    return app
