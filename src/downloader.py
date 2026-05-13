import yt_dlp
import os
import re
import time
import subprocess
from audio_processor import get_ffmpeg_path

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

def download_audio(url, output_dir="downloads", output_format="mp3", bitrate="256k", progress_hook=None, start_sec=None, end_sec=None):
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

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': outtmpl,
        'progress_hooks': [progress_hook] if progress_hook else [],
        'postprocessors': postprocessors,
        'postprocessor_args': [],
    }

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

                if start_sec is not None and end_sec is not None:
                    try:
                        import mutagen
                        audio_info = mutagen.File(raw_path)
                        if audio_info is not None:
                            duration = audio_info.info.length
                            if duration > (end_sec - start_sec) * 1.1:
                                print("範囲指定を再適用中（FFmpegで切り出し）...")
                                trimmed_path = raw_path.rsplit('.', 1)[0] + "_trimmed." + output_format
                                cmd = [
                                    get_ffmpeg_path(),
                                    '-y', '-i', raw_path,
                                    '-ss', str(start_sec),
                                    '-to', str(end_sec),
                                    '-c', 'copy',
                                    trimmed_path
                                ]
                                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                os.remove(raw_path)
                                os.rename(trimmed_path, raw_path)
                    except:
                        pass

                cleaned_title = clean_title(info.get('title', 'Unknown'))
                if start_sec is not None and end_sec is not None:
                    time_suffix = f" [{format_time(start_sec)}-{format_time(end_sec)}]"
                else:
                    time_suffix = ""
                final_dest = get_unique_path(os.path.join(output_dir, f"{cleaned_title}{time_suffix}.{output_format}"))

                return {
                    'temp_raw': raw_path,
                    'dest_path': final_dest,
                    'title': cleaned_title,
                    'uploader': info.get('uploader', 'Unknown'),
                    'thumb': info.get('thumbnail')
                }
        except Exception as e:
            if attempt < 2:
                print(f"\n⚠️ エラーが発生しました: {e}")
                print(f"再試行中...({attempt+2}/3)")
                time.sleep(2)
            else:
                raise e

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