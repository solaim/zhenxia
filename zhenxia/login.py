"""Temporary owner-bound browser, limited controls, no external debug port."""
import asyncio
import secrets
import time
from urllib.parse import urlsplit

WIDTH, HEIGHT = 1100, 760


def export_cookies(cookies):
    lines = ['# Netscape HTTP Cookie File']
    authenticated = False
    for c in cookies:
        domain = c['domain']
        if domain.lstrip('.') != 'tiktok.com' and not domain.lstrip('.').endswith('.tiktok.com'):
            continue
        fields = [domain, 'TRUE' if domain.startswith('.') else 'FALSE', c.get('path') or '/',
                  'TRUE' if c.get('secure') else 'FALSE', str(max(0, int(c.get('expires') or 0))), c['name'], c.get('value') or '']
        if any(any(char in str(f) for char in '\t\r\n') for f in fields):
            continue
        if c['name'] in {'sessionid', 'sessionid_ss', 'sid_tt'} and c.get('value'):
            authenticated = True
        if c.get('httpOnly'):
            fields[0] = '#HttpOnly_' + domain
        lines.append('\t'.join(fields))
    return authenticated, '\n'.join(lines) + '\n'


class LoginBusy(Exception):
    pass


class LoginSession:
    def __init__(self, credentials, proxy, ttl=600):
        self.credentials, self.proxy, self.ttl = credentials, proxy, ttl
        self.token = None
        self.state = 'idle'
        self.created = 0
        self.lock, self.io = asyncio.Lock(), asyncio.Lock()
        self.browser = self.context = self.page = self.playwright = self.task = None

    def owns(self, token):
        return bool(token and self.token and secrets.compare_digest(token, self.token))

    def status(self):
        return {'state': self.state, 'seconds_left': max(0, int(self.ttl - (time.monotonic() - self.created))),
                'width': WIDTH, 'height': HEIGHT}

    async def start(self, owner):
        async with self.lock:
            if self.state in {'starting', 'waiting'}:
                if self.owns(owner):
                    return self.token
                raise LoginBusy()
            await self.close()
            self.token = secrets.token_urlsafe(32)
            self.created, self.state = time.monotonic(), 'starting'
            self.task = asyncio.create_task(self.run())
            return self.token

    async def run(self):
        from playwright.async_api import async_playwright
        try:
            self.playwright = await async_playwright().start()
            options = {'headless': True, 'args': ['--no-sandbox']}
            if self.proxy:
                options['proxy'] = {'server': self.proxy}
            self.browser = await self.playwright.chromium.launch(**options)
            self.context = await self.browser.new_context(viewport={'width': WIDTH, 'height': HEIGHT},
                                                          accept_downloads=False, service_workers='block')

            async def restrict(route):
                if route.request.is_navigation_request():
                    host = urlsplit(route.request.url).hostname or ''
                    if host != 'tiktok.com' and not host.endswith('.tiktok.com'):
                        await route.abort()
                        return
                await route.continue_()

            await self.context.route('**/*', restrict)
            self.page = await self.context.new_page()
            self.context.on('page', lambda page: asyncio.create_task(page.close()) if page != self.page else None)
            await self.page.goto('https://www.tiktok.com/login', wait_until='domcontentloaded', timeout=45000)
            body = await self.page.inner_text('body', timeout=5000)
            if 'discontinued operating tiktok in hong kong' in body.lower():
                self.state = 'region_blocked'
                return
            self.state = 'waiting'
            while time.monotonic() - self.created < self.ttl:
                authenticated, text = export_cookies(await self.context.cookies())
                if authenticated:
                    await asyncio.to_thread(self.credentials.save, 'tiktok', text)
                    self.state = 'saved'
                    break
                await asyncio.sleep(2)
            else:
                self.state = 'expired'
        except asyncio.CancelledError:
            raise
        except Exception:
            self.state = 'failed'
        finally:
            await self.dispose()

    async def dispose(self):
        async with self.io:
            try:
                if self.browser:
                    await self.browser.close()
            finally:
                if self.playwright:
                    await self.playwright.stop()
                self.browser = self.context = self.page = self.playwright = None

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        if self.state in {'starting', 'waiting'}:
            self.state = 'cancelled'

    async def frame(self):
        async with self.io:
            if self.state != 'waiting' or not self.page:
                return None
            return await self.page.screenshot(type='jpeg', quality=75, timeout=8000)

    async def act(self, action):
        async with self.io:
            if self.state != 'waiting' or not self.page:
                raise ValueError('Login browser is not ready')
            kind = action['kind']
            if kind == 'click':
                x, y = action.get('x', -1), action.get('y', -1)
                if not (0 <= x <= WIDTH and 0 <= y <= HEIGHT):
                    raise ValueError('Invalid coordinates')
                await self.page.mouse.click(x, y)
            elif kind == 'drag':
                x, y, end_x, end_y = (action.get(k, -1) for k in ('x', 'y', 'end_x', 'end_y'))
                if not (0 <= x <= WIDTH and 0 <= end_x <= WIDTH and 0 <= y <= HEIGHT and 0 <= end_y <= HEIGHT):
                    raise ValueError('Invalid coordinates')
                await self.page.mouse.move(x, y)
                await self.page.mouse.down()
                try:
                    await self.page.mouse.move(end_x, end_y, steps=15)
                finally:
                    await self.page.mouse.up()
            elif kind == 'text':
                text = action.get('text', '')
                if len(text) > 500:
                    raise ValueError('Input too long')
                await self.page.keyboard.insert_text(text)
            elif kind == 'key':
                key = action.get('key')
                if key not in {'Tab', 'Enter', 'Backspace', 'Escape', 'ArrowDown', 'ArrowUp', 'ControlOrMeta+A'}:
                    raise ValueError('Unsupported key')
                await self.page.keyboard.press(key)
            elif kind == 'scroll':
                await self.page.mouse.wheel(0, max(-1000, min(1000, action.get('y', 0))))
            else:
                raise ValueError('Unsupported action')
