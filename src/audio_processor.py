import subprocess
import os
import sys
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TALB, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

def get_ffmpeg_info():
    bundled_path = None
    if hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, 'ffmpeg.exe')
        if not os.path.isfile(bundled_path):
            bundled_path = os.path.join(sys._MEIPASS, 'ffmpeg', 'ffmpeg.exe')
        if os.path.isfile(bundled_path):
            return {
                'path': bundled_path,
                'source': 'bundled',
                'location': bundled_path
            }

    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    local_ffmpeg = os.path.join(exe_dir, 'ffmpeg.exe')
    if os.path.isfile(local_ffmpeg):
        return {
            'path': local_ffmpeg,
            'source': 'local',
            'location': local_ffmpeg
        }

    return {
        'path': 'ffmpeg',
        'source': 'system',
        'location': 'システムPATHから検出'
    }

def get_ffmpeg_path():
    return get_ffmpeg_info()['path']

def normalize_audio(input_path, target_lufs=-14.0, ffmpeg_info=None):
    if ffmpeg_info is None:
        ffmpeg_info = get_ffmpeg_info()

    ffmpeg_bin = ffmpeg_info['path']
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_tmp{ext}"

    cmd = [
        ffmpeg_bin, '-y', '-i', input_path,
        '-af', f"loudnorm=I={target_lufs}:TP=-2.0:LRA=11",
        '-q:a', '2',
        output_path
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except subprocess.CalledProcessError:
        if os.path.exists(output_path):
            os.remove(output_path)
        return None

def embed_metadata(file_path, title, artist, thumb_url):
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.mp3':
        try:
            audio = MP3(file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        audio.tags.add(TALB(encoding=3, text="VibeDL"))

        if thumb_url:
            try:
                img_data = requests.get(thumb_url, timeout=10).content
                audio.tags.add(
                    APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data)
                )
            except requests.exceptions.RequestException:
                pass
        audio.save()

    elif ext == '.m4a':
        audio = MP4(file_path)
        audio['\xa9nam'] = title
        audio['\xa9ART'] = artist
        audio['\xa9alb'] = 'VibeDL'

        if thumb_url:
            try:
                img_data = requests.get(thumb_url, timeout=10).content
                audio['covr'] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
            except requests.exceptions.RequestException:
                pass
        audio.save()