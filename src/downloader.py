import yt_dlp
import os

def download_audio(url, output_dir="downloads", progress_hook=None):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        'quiet': True,
        'progress_hooks': [progress_hook] if progress_hook else [],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return {
            'path': ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3",
            'title': info.get('title', 'Unknown'),
            'uploader': info.get('uploader', 'Unknown'),
            'thumb': info.get('thumbnail')
        }