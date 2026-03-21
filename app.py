import yt_dlp
import os
import subprocess

def download_and_normalize(url, target_lufs=-14.0):
    temp_wav = "temp_raw.wav"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'temp_raw.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
        }],
    }

    print(f"--- 1. ダウンロード開始 ---")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio_file')

        print(f"--- 2. 音量調整中 (-14 LUFS) ---")
        clean_title = "".join([c for c in title if c.isalnum() or c in (' ', '_')]).strip()
        final_filename = f"{clean_title}.mp3"
        subprocess.run([
            'ffmpeg', '-y', '-i', temp_wav, 
            '-af', f'loudnorm=I={target_lufs}:TP=-2.0:LRA=11', 
            '-ab', '256k', 
            final_filename
        ], check=True)

        print(f"--- 3. 完了！ ---")
        print(f"保存先: {final_filename}")

    except Exception as e:
        print(f"エラー発生: {e}")
        print("※もし 'ffmpegが見つかりません' と出る場合は、一度PCを再起動するか、ターミナルを立ち上げ直してください。")
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

if __name__ == "__main__":
    video_url = input("YouTubeのURLを入力してください: ")
    download_and_normalize(video_url)