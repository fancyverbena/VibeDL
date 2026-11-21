import yt_dlp
import os
import re
import time
from audio_processor import get_ffmpeg_location

def clean_title(title):
    patterns = [
        r'\[.*?\]', r'\(.*?\)', r'【.*?】',
        r'Official\s*Video', r'Music\s*Video', r'MV', r'Full\s*HD'
    ]
    for p in patterns:
        title = re.sub(p, '', title, flags=re.IGNORECASE)
    title = re.sub(r'[\\/:*?"<>|]', '', title)
    title = title.strip()
    if not title:
        title = "unknown_title"
    return title

def get_unique_path(path):
    base, ext = os.path.splitext(path)
    counter = 1
    new_path = path
    while os.path.exists(new_path):
        new_path = f"{base} ({counter}){ext}"
        counter += 1
    return new_path

def format_time(seconds):
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m{s}s" if s else f"{m}m"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        parts = f"{h}h"
        if m:
            parts += f"{m}m"
        if s:
            parts += f"{s}s"
        return parts

# リトライしても直らない恒常エラーの判別パターン（yt-dlpのメッセージ）
PERMANENT_ERROR_PATTERNS = (
    "video is not available",
    "video unavailable",
    "this video is no longer available",
    "private video",
    "video is private",
    "age-restricted",
    "sign in to confirm your age",
    "account associated with this video has been terminated",
)

def is_permanent_error(exc):
    message = str(exc).lower()
    return any(pattern in message for pattern in PERMANENT_ERROR_PATTERNS)

COOKIE_ERROR_MESSAGE = (
    "ブラウザのCookieを読み込めませんでした。"
    "ブラウザを完全に終了してから再試行するか、設定で別のブラウザ、"
    "または cookies.txt ファイルを指定してください"
)

def is_cookie_error(exc):
    message = str(exc).lower()
    if "cookie" not in message:
        return False
    return any(p in message for p in (
        "could not copy", "decrypt", "failed to extract",
        "database", "lock",
    ))

def _cookie_opts(cookies_browser=None, cookies_file=None):
    """yt-dlp用のCookieオプションを返す。ファイル指定が優先。"""
    if cookies_file:
        return {'cookiefile': cookies_file}
    if cookies_browser:
        return {'cookiesfrombrowser': (cookies_browser,)}
    return {}

def download_audio(url, output_dir="downloads", output_format="mp3", bitrate="256k", progress_hook=None, start_sec=None, end_sec=None, name_template="{title}", cookies_browser=None, cookies_file=None):
    output_dir = os.path.abspath(output_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    outtmpl = os.path.join(output_dir, '%(title).100s [%(id)s].%(ext)s')

    postprocessors = []
    if output_format == "mp3":
        postprocessors.append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': bitrate.replace('k', ''),
        })
    elif output_format == "m4a":
        postprocessors.append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        })
    elif output_format == "wav":
        postprocessors.append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
        })
    elif output_format == "flac":
        postprocessors.append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'flac',
        })

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': outtmpl,
        'progress_hooks': [progress_hook] if progress_hook else [],
        'postprocessors': postprocessors,
        'postprocessor_args': [],
        **_cookie_opts(cookies_browser, cookies_file),
    }

    # 自動ダウンロード／同梱された FFmpeg を yt-dlp の変換にも使う。
    # これが無いと、PATH に FFmpeg が無い環境では変換が失敗する。
    ffmpeg_location = get_ffmpeg_location()
    if ffmpeg_location:
        ydl_opts['ffmpeg_location'] = ffmpeg_location

    if start_sec is not None and end_sec is not None:
        def section_func(info_dict, ydl):
            return [{'start_time': start_sec, 'end_time': end_sec, 'title': 'section'}]
        ydl_opts['download_ranges'] = section_func
        ydl_opts['force_keyframes_at_cuts'] = True

    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if 'entries' in info:
                    info = info['entries'][0]

                raw_path = ydl.prepare_filename(info)
                if output_format == "mp3":
                    raw_path = raw_path.rsplit('.', 1)[0] + ".mp3"
                elif output_format == "m4a":
                    raw_path = raw_path.rsplit('.', 1)[0] + ".m4a"
                elif output_format == "wav":
                    raw_path = raw_path.rsplit('.', 1)[0] + ".wav"
                elif output_format == "flac":
                    raw_path = raw_path.rsplit('.', 1)[0] + ".flac"

                # 範囲指定は download_ranges でダウンロード時に適用済み。
                # 以前はここで長さを推測して -ss 開始時刻 で再トリムしていたが、
                # 切り済みファイルに絶対時刻を再適用するため誤った区間に
                # なっていたので削除した。

                title_clean = clean_title(info.get('title', 'Unknown'))
                uploader_clean = clean_title(info.get('uploader', 'Unknown'))
                video_id = info.get('id', '')
                filename = name_template.format(title=title_clean, uploader=uploader_clean, id=video_id, ext=output_format)
                filename = re.sub(r'[\\/:*?"<>|]', '', filename)
                if not filename.strip():
                    filename = "unknown"
                if start_sec is not None and end_sec is not None:
                    time_suffix = f" [{format_time(start_sec)}-{format_time(end_sec)}]"
                else:
                    time_suffix = ""
                final_dest = get_unique_path(os.path.join(output_dir, f"{filename}{time_suffix}.{output_format}"))

                return {
                    'temp_raw': raw_path,
                    'dest_path': final_dest,
                    'title': title_clean,
                    'uploader': uploader_clean,
                    'thumb': info.get('thumbnail')
                }
        except Exception as e:
            if is_cookie_error(e):
                raise Exception(COOKIE_ERROR_MESSAGE) from e
            if is_permanent_error(e):
                # 待っても直らないエラーはリトライせず、理由を添えて即終了する。
                # 検索（flat）では利用可否が分からないため、検索結果にも
                # 利用不可の動画が混ざることがある。
                raise Exception(
                    "この動画は利用できませんでした"
                    "（地域制限・削除・非公開・年齢制限などの可能性があります）"
                ) from e
            if attempt < 2:
                print(f"\n⚠️ エラーが発生しました: {e}")
                print(f"再試行中...({attempt+2}/3)")
                time.sleep(2)
            else:
                raise e

def _flat_entry_to_dict(entry):
    """extract_flat のエントリを共通の辞書形式に変換する。変換できなければ None。"""
    if not entry:
        return None
    video_id = entry.get('id')
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    else:
        url = entry.get('url') or ''
        if not url.startswith('http'):
            return None
    thumb = entry.get('thumbnail')
    if not thumb and entry.get('thumbnails'):
        thumb = entry['thumbnails'][-1].get('url')
    return {
        'url': url,
        'title': entry.get('title') or 'Unknown',
        'uploader': entry.get('uploader') or entry.get('channel') or '',
        'duration': entry.get('duration'),
        'thumb': thumb,
    }


def _flat_extract(url_or_search, cookies_browser=None, cookies_file=None):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        **_cookie_opts(cookies_browser, cookies_file),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url_or_search, download=False)


def search_youtube(keyword, max_results=10, cookies_browser=None, cookies_file=None):
    """キーワードでYouTubeを検索し、候補のリストを返す（ダウンロードはしない）。"""
    info = _flat_extract(f"ytsearch{max_results}:{keyword}", cookies_browser, cookies_file)
    results = []
    for entry in info.get('entries') or []:
        item = _flat_entry_to_dict(entry)
        if item:
            results.append(item)
    return results


def get_playlist_entries(playlist_url, cookies_browser=None, cookies_file=None):
    """プレイリストを展開し、収録動画のリストを返す（ダウンロードはしない）。"""
    info = _flat_extract(playlist_url, cookies_browser, cookies_file)
    results = []
    for entry in info.get('entries') or []:
        item = _flat_entry_to_dict(entry)
        if item:
            results.append(item)
    return results


def get_video_info(url, cookies_browser=None, cookies_file=None):
    """単一動画のタイトル・投稿者・長さ・サムネイルを取得する。"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        **_cookie_opts(cookies_browser, cookies_file),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get('entries'):
        info = info['entries'][0]
    return {
        'title': info.get('title') or 'Unknown',
        'uploader': info.get('uploader') or '',
        'duration': info.get('duration'),
        'thumb': info.get('thumbnail'),
    }

def download_playlist(playlist_url, config, progress_hook=None):
    output_dir = os.path.abspath(config['output_folder'])
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
        if 'entries' not in info:
            raise Exception("プレイリスト情報が取得できませんでした。")
        entries = []
        for entry in info['entries']:
            entries.append({
                'url': entry['url'],
                'title': entry.get('title', 'Unknown')
            })
        return entries