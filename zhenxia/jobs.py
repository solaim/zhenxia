"""Task execution backed by SQLite; interrupted jobs remain visible after restart."""
import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from .progress import reporter
from .store import now


@dataclass
class DownloadJob:
    job_id: str
    url: str
    status: str = 'pending'
    created_at: str = field(default_factory=now)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    error: Optional[str] = None
    retry_of: Optional[str] = None
    progress: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class QueueFull(Exception):
    pass


class JobManager:
    def __init__(self, executor, store, library, max_concurrency=2):
        self.executor = executor
        self.store = store
        self.library = library
        self.semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.live_progress = {}

    async def start(self):
        await asyncio.to_thread(self.store.recover_tasks)

    async def submit(self, url, retry_of=None):
        async with self.lock:
            if len(self.tasks) >= 50:
                raise QueueFull('队列已满，请等待现有任务完成')
            job = DownloadJob(uuid.uuid4().hex[:12], url, retry_of=retry_of)
            await asyncio.to_thread(self.store.save_task, job.to_dict())
            task = asyncio.create_task(self._run(job))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        return job

    async def retry(self, job_id):
        async with self.lock:
            previous = await asyncio.to_thread(self.store.task, job_id)
            if previous is None:
                raise ValueError('任务不存在')
            if previous['status'] not in {'failed', 'success'}:
                raise ValueError('任务仍在运行')
            if len(self.tasks) >= 50:
                raise QueueFull('队列已满，请等待现有任务完成')
            job = DownloadJob(job_id, previous['url'], created_at=previous['created_at'],
                              retry_of=previous.get('retry_of'))
            await asyncio.to_thread(self.store.save_task, job.to_dict())
            task = asyncio.create_task(self._run(job))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return job

    async def _run(self, job):
        def update(values):
            job.progress = values
            self.live_progress[job.job_id] = values
        token = reporter.set(update)
        try:
            async with self.semaphore:
                job.status = 'running'
                job.started_at = now()
                await asyncio.to_thread(self.store.save_task, job.to_dict())
                update({'phase': 'extracting'})
                counts = await asyncio.wait_for(self.executor(job.url), timeout=600)
                for key in ('total', 'success', 'failed', 'skipped'):
                    setattr(job, key, int(counts.get(key, 0)))
                job.status = 'success' if job.failed == 0 and job.total > 0 else 'failed'
                if job.total == 0:
                    job.error = '未获取到作品，请检查链接、Cookie 或平台验证'
                update({'phase': 'indexing'})
                await asyncio.to_thread(self.library.scan)
                await asyncio.to_thread(self.store.link_resources, job.job_id,
                                        counts.get('resource_paths', []))
        except asyncio.CancelledError:
            job.status = 'failed'
            job.error = '服务停止，任务已中断；请重试'
            raise
        except Exception as exc:
            job.status = 'failed'
            job.error = str(exc) or '下载超时或执行失败'
        finally:
            reporter.reset(token)
            job.progress = {**job.progress, 'phase': job.status}
            job.finished_at = now()
            await asyncio.to_thread(self.store.save_task, job.to_dict())
            self.live_progress.pop(job.job_id, None)

    async def get(self, job_id):
        job = await asyncio.to_thread(self.store.task, job_id)
        if job and job_id in self.live_progress:
            job['progress'] = self.live_progress[job_id]
        return job

    async def list_jobs(self, limit=500):
        jobs = await asyncio.to_thread(self.store.tasks, limit)
        for job in jobs:
            if job['job_id'] in self.live_progress:
                job['progress'] = self.live_progress[job['job_id']]
        return jobs

    async def shutdown(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # A queued coroutine may be cancelled before entering its finally block.
        await asyncio.to_thread(self.store.recover_tasks)
