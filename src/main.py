from downloader import download_audio
from audio_processor import normalize_audio
import os

def main():
    print("========== VibeDL - Audio Downloader ==========")
    url = input("YouTube URLを入力してください: ").strip()
    
    if not url:
        print("URLが空です。")
        return

    try:
        print("\n[1/2] ダウンロード中...")
        raw_file = download_audio(url)
        
        print("[2/2] 音量を最適化中 (-14 LUFS)...")
        final_file = normalize_audio(raw_file)
        
        if final_file and os.path.exists(final_file):
            os.remove(raw_file)
            print(f"\n✨ 完了しました！")
            print(f"保存先: {final_file}")
        else:
            print("\n❌ 音量調整に失敗しました。")
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")

if __name__ == "__main__":
    main()