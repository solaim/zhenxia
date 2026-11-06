"""Explicit public URL routes; do not expose yt-dlp's generic URL extractor."""
import re
from urllib.parse import parse_qs, urlencode, urlsplit

PLATFORMS = {
    'douyin': '抖音 / Douyin', 'youtube': 'YouTube', 'tiktok': 'TikTok',
    'x': 'X / Twitter', 'bilibili': '哔哩哔哩 / Bilibili',
}
COOKIE_DOMAINS = {
    'youtube': ('youtube.com', 'google.com'), 'tiktok': ('tiktok.com',),
    'x': ('x.com', 'twitter.com'), 'bilibili': ('bilibili.com',),
}
EXTRACTORS = {
    'youtube': ['Youtube'], 'tiktok': ['TikTok', 'vm.tiktok'],
    'x': ['twitter', 'twitter:amplify', 'twitter:card'], 'bilibili': ['BiliBili'],
}


def normalize_link(text):
    links = re.findall(r'https?://[^\s<>"，。]+', text)
    if not links:
        raise ValueError('请输入视频链接或分享文本')
    try:
        parsed = urlsplit(links[0])
        host = (parsed.hostname or '').lower()
        if parsed.port is not None or parsed.username is not None or parsed.password is not None:
            raise ValueError()
    except ValueError:
        raise ValueError('链接格式无效') from None
    path = parsed.path.rstrip('/')
    if host in {'douyin.com', 'www.douyin.com', 'v.douyin.com'}:
        if host == 'v.douyin.com' and re.fullmatch(r'/[A-Za-z0-9_-]+', path):
            return 'douyin', 'https://' + host + path
        if host != 'v.douyin.com' and re.fullmatch(r'/(video|note|user)/[A-Za-z0-9_-]+', path):
            return 'douyin', 'https://www.douyin.com' + path
        raise ValueError('请使用视频、图集或作者主页链接')
    if host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}:
        video_id = None
        if host == 'youtu.be':
            video_id = path.lstrip('/')
        elif path == '/watch':
            video_id = parse_qs(parsed.query).get('v', [''])[0]
        else:
            match = re.fullmatch(r'/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})', path)
            video_id = match.group(1) if match else None
        if video_id and re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            return 'youtube', 'https://www.youtube.com/watch?' + urlencode({'v': video_id})
        raise ValueError('请使用单个视频链接，暂不支持频道、播放列表或直播')
    routes = [
        ('tiktok', {'www.tiktok.com', 'tiktok.com'}, r'/@[A-Za-z0-9_.-]+/video/\d+'),
        ('tiktok', {'vm.tiktok.com', 'vt.tiktok.com'}, r'/[A-Za-z0-9]+'),
        ('x', {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com'}, r'/(?:[A-Za-z0-9_]+/status|i/status)/\d+'),
        ('bilibili', {'bilibili.com', 'www.bilibili.com', 'm.bilibili.com'}, r'/video/(?:BV[A-Za-z0-9]+|av\d+)'),
    ]
    for platform, hosts, pattern in routes:
        if host in hosts:
            if re.fullmatch(pattern, path):
                canonical = {'x': 'x.com', 'bilibili': 'www.bilibili.com'}.get(platform, host)
                return platform, 'https://' + canonical + path
            raise ValueError('请使用单个视频链接，暂不支持频道、播放列表或直播')
    raise ValueError('暂不支持此平台，请使用抖音、YouTube、TikTok、X、哔哩哔哩 链接')
