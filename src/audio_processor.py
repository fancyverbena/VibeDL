import subprocess
import os
import sys
import json
import re
import hashlib
import requests
import zipfile
import shutil
import tempfile
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TALB, USLT, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE
from mutagen.flac import FLAC, Picture

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

def _fetch_expected_sha256(url):
    """公式の .sha256 ファイルから期待されるハッシュを取得する。

    取得できない・形式が不正な場合は None（検証を中止させる）。
    """
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        token = resp.text.strip().split()[0].lower()
        if re.fullmatch(r'[0-9a-f]{64}', token):
            return token
    except Exception as e:
        print(f"公式SHA256の取得に失敗しました: {e}")
    return None


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def download_ffmpeg(progress_callback=None):
    dest_dir = get_default_ffmpeg_download_dir()
    ffmpeg_exe = os.path.join(dest_dir, 'ffmpeg.exe')
    if os.path.isfile(ffmpeg_exe) and check_ffmpeg(ffmpeg_exe):
        return ffmpeg_exe

    os.makedirs(dest_dir, exist_ok=True)

    print("FFmpegのダウンロードを開始します...")
    tmp_zip_path = None
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

        # 展開前に、配布元が公開している SHA256 と照合する。
        # 取得できない場合も含め、検証できないものは使わない。
        print("ダウンロード完了。SHA256を検証中...")
        expected = _fetch_expected_sha256(FFMPEG_DOWNLOAD_URL + ".sha256")
        if expected is None:
            raise Exception("公式のSHA256を取得できなかったため、検証を中止しました。")
        actual = _file_sha256(tmp_zip_path)
        if actual != expected:
            raise Exception("SHA256が一致しませんでした。ダウンロードを中止します。")
        print("SHA256検証OK。展開中...")
        # ffmpeg.exe だけでなく ffprobe.exe も取り出す。
        # yt-dlp の後処理や情報取得には ffprobe が必要なため。
        wanted = {'ffmpeg.exe': ffmpeg_exe,
                  'ffprobe.exe': os.path.join(dest_dir, 'ffprobe.exe')}
        found = set()
        with tempfile.TemporaryDirectory() as tmp_extract:
            with zipfile.ZipFile(tmp_zip_path, 'r') as zf:
                for member in zf.namelist():
                    name = os.path.basename(member)
                    if name in wanted and 'bin' in member:
                        zf.extract(member, tmp_extract)
                        src = os.path.join(tmp_extract, member)
                        shutil.copy2(src, wanted[name])
                        found.add(name)

        if 'ffmpeg.exe' not in found:
            raise Exception("zip内にffmpeg.exeが見つかりませんでした。")

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
    finally:
        if tmp_zip_path and os.path.exists(tmp_zip_path):
            os.unlink(tmp_zip_path)

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

def get_ffmpeg_location():
    """yt-dlp の ffmpeg_location に渡す値。

    実ファイルが見つかった場合は、そのフォルダ（ffmpeg.exe と
    ffprobe.exe が並ぶ場所）を返す。システムPATH上の ffmpeg を
    使う場合は None を返し、yt-dlp の既定の探索に任せる。
    """
    path = get_ffmpeg_info()['path']
    if os.path.isfile(path):
        return os.path.dirname(path)
    return None

def _encoder_args(ext, bitrate):
    """出力形式に合わせたエンコーダ引数。

    bitrate（例 '256k'）が指定されればそれを反映し、無ければ従来通り
    可変品質 (-q:a 2) を使う。可逆形式はビットレート指定を無視する。
    """
    ext = ext.lower()
    if ext == '.flac':
        return ['-c:a', 'flac']
    if ext == '.wav':
        return ['-c:a', 'pcm_s16le']
    if ext == '.opus':
        return ['-c:a', 'libopus', '-b:a', bitrate or '160k']
    if bitrate:
        codec = 'aac' if ext == '.m4a' else 'libmp3lame'
        return ['-c:a', codec, '-b:a', bitrate]
    return ['-q:a', '2']


def _measure_loudness(ffmpeg_bin, input_path, target_lufs, target_tp=-2.0):
    """loudnorm の 1 パス目: 入力のラウドネスを測定して dict で返す。

    失敗したら None（呼び出し側は従来の 1 パス処理にフォールバック）。
    """
    filt = f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11:print_format=json"
    try:
        result = subprocess.run(
            [ffmpeg_bin, '-i', input_path, '-af', filt, '-f', 'null', '-'],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, timeout=600)
        m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', result.stderr or '')
        if not m:
            return None
        data = json.loads(m.group(0))
        needed = ('input_i', 'input_tp', 'input_lra', 'input_thresh',
                  'target_offset')
        if all(k in data for k in needed):
            return data
    except Exception as e:
        print(f"ラウドネス測定に失敗しました（1パス処理で続行）: {e}")
    return None


def normalize_audio(input_path, target_lufs=-14.0, ffmpeg_info=None,
                    bitrate=None, target_tp=-2.0):
    if ffmpeg_info is None:
        ffmpeg_info = get_ffmpeg_info()

    ffmpeg_bin = ffmpeg_info['path']
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_tmp{ext}"

    # 2パス loudnorm: まず測定し、その結果を渡すことで線形調整
    # （音質劣化の少ない一律ゲイン）が可能になる。測定できなければ
    # 従来の1パス処理にフォールバックする。
    measured = _measure_loudness(ffmpeg_bin, input_path, target_lufs,
                                 target_tp)
    if measured:
        loudnorm_filter = (
            f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11"
            f":measured_I={measured['input_i']}"
            f":measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}"
            f":measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true"
        )
    else:
        loudnorm_filter = f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11"

    cmd = [
        ffmpeg_bin, '-y', '-i', input_path,
        '-af', loudnorm_filter,
        *_encoder_args(ext, bitrate),
        output_path
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except subprocess.CalledProcessError:
        if os.path.exists(output_path):
            os.remove(output_path)
        return None

def trim_and_fade(input_path, trim_silence=False, fade_sec=0.0, ffmpeg_info=None):
    """先頭・末尾の無音トリミングとフェードイン／アウトを1パスで適用する。

    末尾側は areverse で反転してから同じ処理を行い、再反転することで
    長さを取得せずに処理できる。成功時は出力パス、不要／失敗時は None。
    """
    if not trim_silence and fade_sec <= 0:
        return None
    if ffmpeg_info is None:
        ffmpeg_info = get_ffmpeg_info()

    ffmpeg_bin = ffmpeg_info['path']
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_trim{ext}"

    filters = []
    if trim_silence:
        filters.append("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2")
    if fade_sec > 0:
        filters.append(f"afade=t=in:st=0:d={fade_sec}")
    filters.append("areverse")
    if trim_silence:
        filters.append("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2")
    if fade_sec > 0:
        filters.append(f"afade=t=in:st=0:d={fade_sec}")
    filters.append("areverse")

    cmd = [
        ffmpeg_bin, '-y', '-i', input_path,
        '-af', ','.join(filters),
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

def vtt_to_lyrics(vtt_text):
    """WebVTT 字幕テキストを歌詞用のプレーンテキストに変換する。

    タイムスタンプ・タグ・NOTE等を取り除き、自動字幕でよくある
    連続する重複行（ロールアップ表示の名残）を畳む。
    """
    lines = []
    for raw in vtt_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(('WEBVTT', 'NOTE', 'Kind:', 'Language:')):
            continue
        if '-->' in line:
            continue
        if line.isdigit():
            continue
        line = re.sub(r'<[^>]+>', '', line).strip()
        if not line:
            continue
        if lines and lines[-1] == line:
            continue
        lines.append(line)
    return '\n'.join(lines) or None


def split_into_chapters(input_path, chapters, ffmpeg_info=None,
                        bitrate=None):
    """音声ファイルをチャプター区間で分割する。

    成功したら [{'path':..., 'title':..., 'index':...}, ...] を返し、
    失敗したら None（生成済みの中間ファイルは掃除する）。
    """
    if ffmpeg_info is None:
        ffmpeg_info = get_ffmpeg_info()
    ffmpeg_bin = ffmpeg_info['path']
    base, ext = os.path.splitext(input_path)
    parts = []
    try:
        for i, ch in enumerate(chapters):
            start = float(ch.get('start_time', 0))
            end = ch.get('end_time')
            out_path = f"{base}_ch{i + 1:02d}{ext}"
            cmd = [ffmpeg_bin, '-y', '-ss', str(start), '-i', input_path]
            if end is not None:
                cmd += ['-to', str(float(end) - start)]
            cmd += [*_encoder_args(ext, bitrate), out_path]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            parts.append({'path': out_path,
                          'title': ch.get('title') or f"Chapter {i + 1}",
                          'index': i})
    except Exception:
        for part in parts:
            if os.path.exists(part['path']):
                os.remove(part['path'])
        return None
    return parts


def _fetch_thumbnail(thumb_url):
    """サムネイルを取得し、(bytes, mime) を返す。失敗時は (None, None)。

    ステータスコードと画像形式（マジックバイト）を確認し、エラーページ等
    のHTMLをカバー画像として埋め込んでしまう事故を防ぐ。
    """
    if not thumb_url:
        return None, None
    try:
        resp = requests.get(thumb_url, timeout=10)
        resp.raise_for_status()
        data = resp.content
        if not data or len(data) > 5 * 1024 * 1024:
            return None, None
        if data[:3] == b'\xff\xd8\xff':
            return data, 'image/jpeg'
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return data, 'image/png'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return data, 'image/webp'
    except requests.exceptions.RequestException:
        pass
    return None, None


def embed_metadata(file_path, title, artist, thumb_url, lyrics=None):
    ext = os.path.splitext(file_path)[1].lower()
    img_data, img_mime = _fetch_thumbnail(thumb_url)

    if ext in ('.mp3', '.wav'):
        # MP3 と WAV はどちらも ID3 タグで扱える
        if ext == '.mp3':
            try:
                audio = MP3(file_path, ID3=ID3)
            except ID3NoHeaderError:
                audio = MP3(file_path)
                audio.add_tags()
        else:
            audio = WAVE(file_path)

        if audio.tags is None:
            audio.add_tags()

        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        audio.tags.add(TALB(encoding=3, text="VibeDL"))
        if lyrics:
            audio.tags.add(USLT(encoding=3, lang='jpn', desc='', text=lyrics))

        if img_data:
            audio.tags.add(
                APIC(encoding=3, mime=img_mime, type=3, desc='Cover',
                     data=img_data)
            )
        audio.save()

    elif ext == '.m4a':
        audio = MP4(file_path)
        audio['\xa9nam'] = title
        audio['\xa9ART'] = artist
        audio['\xa9alb'] = 'VibeDL'
        if lyrics:
            audio['\xa9lyr'] = lyrics

        # MP4 のカバーは JPEG / PNG のみ対応
        if img_data and img_mime in ('image/jpeg', 'image/png'):
            fmt = (MP4Cover.FORMAT_JPEG if img_mime == 'image/jpeg'
                   else MP4Cover.FORMAT_PNG)
            audio['covr'] = [MP4Cover(img_data, imageformat=fmt)]
        audio.save()

    elif ext == '.flac':
        audio = FLAC(file_path)
        audio['title'] = title
        audio['artist'] = artist
        audio['album'] = 'VibeDL'
        if lyrics:
            audio['lyrics'] = lyrics

        if img_data:
            pic = Picture()
            pic.type = 3
            pic.mime = img_mime
            pic.desc = 'Cover'
            pic.data = img_data
            audio.add_picture(pic)
        audio.save()

    elif ext == '.opus':
        import base64
        from mutagen.oggopus import OggOpus
        audio = OggOpus(file_path)
        audio['title'] = title
        audio['artist'] = artist
        audio['album'] = 'VibeDL'
        if lyrics:
            audio['lyrics'] = lyrics

        if img_data:
            pic = Picture()
            pic.type = 3
            pic.mime = img_mime
            pic.desc = 'Cover'
            pic.data = img_data
            audio['metadata_block_picture'] = [
                base64.b64encode(pic.write()).decode('ascii')]
        audio.save()


def convert_audio(input_path, output_path, ffmpeg_info=None, bitrate=None):
    """ローカルファイルを別形式へ変換する（再エンコード）。"""
    if ffmpeg_info is None:
        ffmpeg_info = get_ffmpeg_info()
    ext = os.path.splitext(output_path)[1]
    cmd = [ffmpeg_info['path'], '-y', '-i', input_path,
           *_encoder_args(ext, bitrate), output_path]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return output_path
    except subprocess.CalledProcessError:
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


def update_tags(file_path, title=None, artist=None, album=None):
    """既存ファイルのタイトル/アーティスト/アルバムだけを書き換える。"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in ('.mp3', '.wav'):
            if ext == '.mp3':
                try:
                    audio = MP3(file_path, ID3=ID3)
                except ID3NoHeaderError:
                    audio = MP3(file_path)
                    audio.add_tags()
            else:
                audio = WAVE(file_path)
            if audio.tags is None:
                audio.add_tags()
            if title is not None:
                audio.tags.add(TIT2(encoding=3, text=title))
            if artist is not None:
                audio.tags.add(TPE1(encoding=3, text=artist))
            if album is not None:
                audio.tags.add(TALB(encoding=3, text=album))
            audio.save()
        elif ext == '.m4a':
            audio = MP4(file_path)
            if title is not None:
                audio['\xa9nam'] = title
            if artist is not None:
                audio['\xa9ART'] = artist
            if album is not None:
                audio['\xa9alb'] = album
            audio.save()
        elif ext in ('.flac', '.opus'):
            if ext == '.flac':
                audio = FLAC(file_path)
            else:
                from mutagen.oggopus import OggOpus
                audio = OggOpus(file_path)
            if title is not None:
                audio['title'] = title
            if artist is not None:
                audio['artist'] = artist
            if album is not None:
                audio['album'] = album
            audio.save()
        else:
            return False
    except Exception:
        return False
    return True


def read_tags(file_path):
    """タイトル/アーティスト/アルバムを読み出す（無い項目は ''）。"""
    result = {'title': '', 'artist': '', 'album': ''}
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in ('.mp3', '.wav'):
            audio = MP3(file_path) if ext == '.mp3' else WAVE(file_path)
            tags = getattr(audio, 'tags', None)
            if tags:
                for key, frame_id in (('title', 'TIT2'),
                                      ('artist', 'TPE1'),
                                      ('album', 'TALB')):
                    if frame_id in tags:
                        result[key] = str(tags[frame_id])
        elif ext == '.m4a':
            audio = MP4(file_path)
            for key, atom in (('title', '\xa9nam'), ('artist', '\xa9ART'),
                              ('album', '\xa9alb')):
                values = audio.get(atom)
                if values:
                    result[key] = str(values[0])
        elif ext in ('.flac', '.opus'):
            if ext == '.flac':
                audio = FLAC(file_path)
            else:
                from mutagen.oggopus import OggOpus
                audio = OggOpus(file_path)
            for key in result:
                values = audio.get(key)
                if values:
                    result[key] = str(values[0])
    except Exception:
        pass
    return result
