import os
import winreg
from downloader import download_audio
from audio_processor import normalize_audio, embed_metadata

REG_PATH = r"Software\VibeDL"

def get_config():
    config = {"target_lufs": -14.0, "output_folder": "downloads"}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            config["target_lufs"] = float(winreg.QueryValueEx(key, "TargetLUFS")[0])
            config["output_folder"] = winreg.QueryValueEx(key, "OutputFolder")[0]
    except: pass
    return config

def save_config(config):
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "TargetLUFS", 0, winreg.REG_SZ, str(config["target_lufs"]))
        winreg.SetValueEx(key, "OutputFolder", 0, winreg.REG_SZ, config["output_folder"])

def my_hook(d):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%')
        print(f"\r[Downloading] {p} ", end='')
    elif d['status'] == 'finished':
        print("\n[Done] ダウンロード完了。")

def main():
    config = get_config()
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"========== VibeDL (Target: {config['target_lufs']} LUFS) ==========")
        print("1: YouTubeダウンロード / 2: 設定変更 / 0: 終了")
        
        choice = input("\n選択 > ")
        if choice == "1":
            url = input("URLを入力: ").strip()
            if not url: continue
            try:
                data = download_audio(url, config['output_folder'], progress_hook=my_hook)
                print("音量調整中...")
                out_file = normalize_audio(data['path'], config['target_lufs'])
                
                if out_file:
                    print("画像・曲名を埋め込み中...")
                    embed_metadata(out_file, data['title'], data['uploader'], data['thumb'])
                    os.remove(data['path'])
                    final_name = data['path'].replace(".mp3", "_Vibe.mp3")
                    if os.path.exists(final_name): os.remove(final_name)
                    os.rename(out_file, final_name)
                    print(f"✨ 完了: {os.path.basename(final_name)}")
                input("\nEnterで戻る...")
            except Exception as e:
                print(f"❌ エラー: {e}")
                input()
        elif choice == "2":
            config['output_folder'] = input(f"保存フォルダ ({config['output_folder']}): ") or config['output_folder']
            config['target_lufs'] = float(input(f"目標LUFS ({config['target_lufs']}): ") or config['target_lufs'])
            save_config(config)
        elif choice == "0": break

if __name__ == "__main__":
    main()