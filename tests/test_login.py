import asyncio
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from zhenxia.credentials import PlatformCookies
from zhenxia.login import LoginBusy, LoginSession, export_cookies


def cookie(domain='.tiktok.com', name='sessionid', value='secret'):
    return {'domain':domain,'name':name,'value':value,'path':'/','secure':True,'httpOnly':True,'expires':-1}


def test_cookie_export_filters_other_sites_and_no_auth_on_tracking_cookie():
    authenticated, text = export_cookies([cookie(), cookie('.evil.test'),cookie(name='bad',value='bad\nline')])
    assert authenticated
    assert 'evil' not in text and 'bad' not in text
    assert '#HttpOnly_.tiktok.com' in text
    assert not export_cookies([cookie(name='tracking')])[0]
    assert not export_cookies([cookie('.tiktok.com.evil.test')])[0]


async def test_session_owner_cancel_and_slot_reuse(tmp_path, monkeypatch):
    session = LoginSession(PlatformCookies(tmp_path), '')
    async def wait():
        await asyncio.Event().wait()
    monkeypatch.setattr(session,'run',wait)
    token = await session.start(None)
    assert len(token) > 30 and session.owns(token)
    assert await session.start(token) == token
    with pytest.raises(LoginBusy):
        await session.start('someone-else')
    await session.close()
    assert session.state == 'cancelled'
    assert await session.start(None) != token
    await session.close()


@pytest.mark.parametrize('authenticated,expired',[(True,False),(False,True)])
async def test_capture_or_timeout_closes_browser(tmp_path, monkeypatch, authenticated, expired):
    import playwright.async_api as api
    session=LoginSession(PlatformCookies(tmp_path),'http://proxy:8080',ttl=1)
    session.created=time.monotonic()-2 if expired else time.monotonic()
    page=MagicMock()
    page.goto=AsyncMock()
    page.inner_text=AsyncMock(return_value='TikTok sign in')
    context=MagicMock()
    context.route=AsyncMock()
    context.new_page=AsyncMock(return_value=page)
    context.cookies=AsyncMock(return_value=[cookie()] if authenticated else [])
    browser=MagicMock()
    browser.new_context=AsyncMock(return_value=context)
    browser.close=AsyncMock()
    runtime=MagicMock()
    runtime.chromium.launch=AsyncMock(return_value=browser)
    runtime.stop=AsyncMock()
    monkeypatch.setattr(api,'async_playwright',lambda:SimpleNamespace(start=AsyncMock(return_value=runtime)))
    await session.run()
    assert session.state == ('saved' if authenticated else 'expired')
    assert session.credentials.configured('tiktok') == authenticated
    if authenticated:
        if os.name == 'posix':
            assert session.credentials.path('tiktok').stat().st_mode & 0o777 == 0o600
    browser.close.assert_awaited_once()
    runtime.stop.assert_awaited_once()
    assert session.page is None


async def test_controls_reject_arbitrary_commands(tmp_path):
    session=LoginSession(PlatformCookies(tmp_path),'')
    session.page=MagicMock()
    session.state='waiting'
    for action in [{'kind':'evaluate','text':'secret()'},{'kind':'click','x':-1,'y':2},
                   {'kind':'key','key':'F12'},{'kind':'text','text':'x'*501}]:
        with pytest.raises(ValueError):
            await session.act(action)
