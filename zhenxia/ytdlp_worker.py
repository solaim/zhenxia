"""Isolated yt-dlp execution. Input on stdin; only compact, safe metadata leaves staging."""
import json
import sys
import time
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import PostProcessor
from yt_dlp.utils import DownloadError

from .platforms import EXTRACTORS

MAX_BYTES = 2 * 1024 ** 3


class QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def download(request):
    max_bytes = int(request.get('max_bytes', MAX_BYTES))
    limit_error = '下载超过任务大小限制，请在偏好设置中调整'
    root = Path(request['directory']).resolve()
    results = []
    progress = {}
    last_report = 0

    def emit(values):
        nonlocal last_report
        stamp = time.monotonic()
        if values['phase'] == 'downloading' and stamp - last_report < .4:
            return
        last_report = stamp
        temporary = root / 'progress.tmp'
        temporary.write_text(json.dumps(values), encoding='utf-8')
        temporary.replace(root / 'progress.json')

    emit({'phase': 'extracting'})

    def check_progress(event):
        filename = event.get('filename', '')
        progress[filename] = event.get('downloaded_bytes', 0)
        total = event.get('total_bytes') or event.get('total_bytes_estimate')
        downloaded = event.get('downloaded_bytes') or 0
        emit({'phase': 'downloading' if event.get('status') == 'downloading' else 'processing',
              'downloaded': downloaded, 'total': total,
              'percent': min(100, downloaded / total * 100) if total else None,
              'speed': event.get('speed'), 'eta': event.get('eta'),
              'item': str((event.get('info_dict') or {}).get('title') or '')[:200],
              'format': str((event.get('info_dict') or {}).get('format_id') or '')[:60]})
        if max_bytes and sum(progress.values()) > max_bytes:
            raise DownloadError(limit_error)

    def reject(info, *, incomplete=False):
        if info.get('is_live') or info.get('live_status') in {'is_live', 'is_upcoming'}:
            raise DownloadError('暂不支持直播或尚未开始的视频')
        if max_bytes and (info.get('filesize') or info.get('filesize_approx') or 0) > max_bytes:
            raise DownloadError(limit_error)
        return None

    class Collect(PostProcessor):
        def run(self, info):
            path = Path(info['filepath']).resolve()
            if path.parent != root or not path.is_file() or path.stat().st_size == 0:
                raise DownloadError('下载结果文件无效')
            results.append({'file': path.name, 'id': str(info.get('id', '')),
                            'title': str(info.get('title') or '')[:2000],
                            'author': str(info.get('uploader') or info.get('channel') or '')[:500],
                            'url': request['url']})
            return [], info

    options = {
        'paths': {'home': str(root), 'temp': str(root)},
        'outtmpl': '%(id)s.%(ext)s', 'restrictfilenames': True,
        'format': 'bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b[height<=1080]/b[height<=?1080]',
        'merge_output_format': 'mp4',
        'noplaylist': True, 'playlistend': 10,
        'max_filesize': max_bytes or None, 'match_filter': reject,
        'socket_timeout': 20, 'retries': 2, 'fragment_retries': 2,
        'concurrent_fragment_downloads': 1, 'progress_hooks': [check_progress],
        'postprocessor_hooks': [lambda e: emit({'phase': 'processing'})],
        'quiet': True, 'no_warnings': True, 'logger': QuietLogger(),
        'cachedir': False, 'overwrites': False,
        'allowed_extractors': EXTRACTORS[request['platform']],
        'js_runtimes': {'node': {}}, 'remote_components': [],
        'windowsfilenames': True,
    }
    if request.get('cookiefile'):
        options['cookiefile'] = request['cookiefile']
    options['proxy'] = request.get('proxy') or ''  # Empty explicitly disables implicit OS/env proxy lookup.
    with YoutubeDL(options) as downloader:
        downloader.add_post_processor(Collect(downloader), when='after_move')
        downloader.extract_info(request['url'], download=True)
    if not results:
        raise DownloadError('未取得可下载视频，可能超过大小限制或需要登录验证')
    return results


def main():
    request = json.load(sys.stdin)
    result_file = Path(request['directory']) / 'result.json'
    try:
        result = {'items': download(request)}
    except Exception as exc:
        # Do not expose cookie values, signed media URLs, proxy credentials or local paths.
        message = str(exc)
        if 'Unexpected response from webpage request' in message and request['platform'] == 'tiktok':
            error = 'TikTok 返回了无法解析的网页响应，可能是验证、地区限制或页面变化；请尝试其他视频或配置该平台 Cookie'
        elif 'Domain Not Found' in message:
            error = '帖子引用的视频域名已不可用，请尝试其他视频链接'
        elif 'Requested format is not available' in message:
            error = '平台未提供符合当前画质要求的视频格式，请尝试其他视频或稍后重试'
        elif 'HTTP Error 404' in message:
            error = '视频媒体地址已失效或不可访问（HTTP 404），请稍后重试'
        elif 'HTTP Error 400' in message:
            error = '平台拒绝解析请求（HTTP 400），请检查平台 Cookie 或更新 yt-dlp'
        elif any(word in message.lower() for word in ['sign in', 'login', 'cookies', 'captcha', 'bot', '403', '429', 'private']):
            error = '平台要求登录或验证，请检查该平台 Cookie、网络或稍后重试'
        elif any(word in message.lower() for word in ['timed out', 'resolve', 'connection', 'network', 'proxy']):
            error = '无法连接视频平台，请检查网络或代理配置'
        elif any(word in message.lower() for word in ['ffmpeg', 'javascript', 'js runtime', 'ejs']):
            error = '下载组件不可用，请检查 FFmpeg 和 JavaScript 运行时'
        elif any(word in message for word in ['任务大小限制', '直播', '下载结果', '未取得']):
            error = message if len(message) < 100 and 'http' not in message else '下载超过限制或视频不可用'
        else:
            error = '视频解析或下载失败，请检查链接、平台限制或更新 yt-dlp'
        result = {'error': error}
    result_file.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
