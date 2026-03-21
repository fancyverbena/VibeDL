import yt_dlp
import os
import re
import time

def clean_title(title):
    """タイトルから不要な記号や[Official Video]などを消去"""
    patterns = [
        r'\[.*?\]', r'\(.*?\)', r'【.*?】', 
        r'Official\s*Video', r'Music\s*Video', r'MV', r'Full\s*HD'
    ]
    for p in patterns:
        title = re.sub(p, '', title, flags=re.IGNORECASE)
    
    title = re.sub(r'[\\/:*?"<>|]', '', title)
    return title.strip()

def get_unique_path(path):
    """ファイルが既に存在する場合、(1), (2) と連番を振る"""
    base, ext = os.path.splitext(path)
    counter = 1
    new_path = path
    while os.path.exists(new_path):
        new_path = f"{base} ({counter}){ext}"
        counter += 1
    return new_path

def download_audio(url, output_dir="downloads", progress_hook=None):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook] if progress_hook else [],
    }

    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                raw_path = ydl.prepare_filename(info)
                cleaned_title = clean_title(info.get('title', 'Unknown'))
                final_dest = get_unique_path(os.path.join(output_dir, f"{cleaned_title}.mp3"))

                return {
                    'temp_raw': raw_path,
                    'dest_path': final_dest,
                    'title': cleaned_title,
                    'uploader': info.get('uploader', 'Unknown'),
                    'thumb': info.get('thumbnail')
                }
        except Exception as e:
            if attempt < 2:
                print(f"\n⚠️ 接続エラー。再試行中...({attempt+2}/3)")
                time.sleep(2)
            else:
                raise e