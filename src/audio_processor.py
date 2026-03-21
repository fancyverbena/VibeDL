import subprocess
import os
import sys

def get_ffmpeg_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'ffmpeg.exe')
    return 'ffmpeg'

def normalize_audio(input_path, target_lufs=-14.0):
    ffmpeg_bin = get_ffmpeg_path()
    output_path = input_path.replace(".mp3", "_vibe.mp3")
    filter_str = f"loudnorm=I={target_lufs}:TP=-2.0:LRA=11"
    cmd = [
        ffmpeg_bin, '-y', '-i', input_path,
        '-af', filter_str,
        '-b:a', '256k',
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except subprocess.CalledProcessError:
        return None