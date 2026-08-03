import subprocess
import os
import sys
import requests
import zipfile
import shutil
import tempfile
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TALB, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

def get_default_ffmpeg_download_dir():
    base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    return os.path.join(base, 'VibeDL', 'ffmpeg')

def check_ffmpeg(ffmpeg_path):
    try:
        subprocess.run([ffmpeg_path, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def download_ffmpeg(progress_callback=None):
    dest_dir = get_default_ffmpeg_download_dir()
    ffmpeg_exe = os.path.join(dest_dir, 'ffmpeg.exe')
    if os.path.isfile(ffmpeg_exe) and check_ffmpeg(ffmpeg_exe):
        return ffmpeg_exe

    os.makedirs(dest_dir, exist_ok=True)

    print("FFmpegのダウンロードを開始します...")
    try:
        response = requests.get(FFMPEG_DOWNLOAD_URL, stream=True, timeout=30)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_zip.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size:
                        progress_callback(downloaded, total_size)
            tmp_zip_path = tmp_zip.name

        print("ダウンロード完了。展開中...")
        with tempfile.TemporaryDirectory() as tmp_extract:
            with zipfile.ZipFile(tmp_zip_path, 'r') as zf:
                for member in zf.namelist():
                    if member.endswith('ffmpeg.exe') and 'bin' in member:
                        zf.extract(member, tmp_extract)
                        src = os.path.join(tmp_extract, member)
                        shutil.copy2(src, ffmpeg_exe)
                        break

        os.unlink(tmp_zip_path)  # 一時ZIP削除

        if os.path.isfile(ffmpeg_exe) and check_ffmpeg(ffmpeg_exe):
            print("FFmpegの準備が完了しました。")
            return ffmpeg_exe
        else:
            raise Exception("展開後のFFmpegが正常に動作しません。")
    except Exception as e:
        print(f"FFmpegのダウンロード/展開に失敗しました: {e}")
        if os.path.isfile(ffmpeg_exe):
            os.remove(ffmpeg_exe)
        return None

def get_ffmpeg_info():
    if hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, 'ffmpeg.exe')
        if os.path.isfile(bundled_path) and check_ffmpeg(bundled_path):
            return {'path': bundled_path, 'source': 'bundled', 'location': bundled_path}
        bundled_path2 = os.path.join(sys._MEIPASS, 'ffmpeg', 'ffmpeg.exe')
        if os.path.isfile(bundled_path2) and check_ffmpeg(bundled_path2):
            return {'path': bundled_path2, 'source': 'bundled', 'location': bundled_path2}

    dl_dir = get_default_ffmpeg_download_dir()
    dl_path = os.path.join(dl_dir, 'ffmpeg.exe')
    if os.path.isfile(dl_path) and check_ffmpeg(dl_path):
        return {'path': dl_path, 'source': 'downloaded', 'location': dl_path}

    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    local_ffmpeg = os.path.join(exe_dir, 'ffmpeg.exe')
    if os.path.isfile(local_ffmpeg) and check_ffmpeg(local_ffmpeg):
        return {'path': local_ffmpeg, 'source': 'local', 'location': local_ffmpeg}

    return {'path': 'ffmpeg', 'source': 'system', 'location': 'システムPATHから検出'}

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