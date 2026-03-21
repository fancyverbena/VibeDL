import subprocess
import os
import sys
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TALB, error

def get_ffmpeg_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'ffmpeg.exe')
    return 'ffmpeg'

def normalize_audio(input_path, target_lufs=-14.0):
    ffmpeg_bin = get_ffmpeg_path()
    output_path = input_path.replace(".mp3", "_tmp.mp3")
    
    cmd = [
        ffmpeg_bin, '-y', '-i', input_path,
        '-af', f"loudnorm=I={target_lufs}:TP=-2.0",
        '-b:a', '256k', output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except:
        return None

def embed_metadata(file_path, title, artist, thumb_url):
    try:
        audio = MP3(file_path, ID3=ID3)
    except error:
        audio = MP3(file_path)
        audio.add_tags()

    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text="VibeDL"))

    if thumb_url:
        try:
            img_data = requests.get(thumb_url, timeout=10).content
            audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data))
        except:
            pass
    audio.save()