import winreg
import os
import sys
from downloader import download_audio
from audio_processor import normalize_audio

REG_PATH = r"Software\VibeDL"

def get_config():
    config = {"target_lufs": -14.0, "output_folder": "downloads"}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            config["target_lufs"] = float(winreg.QueryValueEx(key, "TargetLUFS")[0])
            config["output_folder"] = winreg.QueryValueEx(key, "OutputFolder")[0]
    except FileNotFoundError: pass
    return config

def save_config(config):
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "TargetLUFS", 0, winreg.REG_SZ, str(config["target_lufs"]))
        winreg.SetValueEx(key, "OutputFolder", 0, winreg.REG_SZ, config["output_folder"])

def my_hook(d):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%')
        print(f"\r[Downloading] {p}  完成まであと {d.get('_eta_str', '??')} ", end='')
    elif d['status'] == 'finished':
        print("\n[Done] ダウンロード完了。音質調整に移行します...")

def main():
    config = get_config()
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"========== VibeDL (Setting: {config['target_lufs']} LUFS) ==========")
        print("1: YouTubeダウンロード / 2: 保存先・音量設定 / 0: 終了")
        
        choice = input("\n選択 > ")
        if choice == "1":
            url = input("URLを入力: ").strip()
            if not url: continue
            try:
                raw = download_audio(url, config['output_folder'], progress_hook=my_hook)
                final = normalize_audio(raw, target_lufs=config['target_lufs'])
                if final and os.path.exists(raw): os.remove(raw)
                print(f"\n✨ 成功: {os.path.basename(final)}")
                input("\nEnterでメニューに戻る...")
            except Exception as e:
                print(f"\n❌ エラー: {e}")
                input()
        elif choice == "2":
            print(f"\n現在の保存先: {config['output_folder']}")
            config['output_folder'] = input("新しいフォルダ名 (空欄で維持): ") or config['output_folder']
            config['target_lufs'] = float(input("目標音量LUFS (-20 ～ -5): ") or config['target_lufs'])
            save_config(config)
            print("設定を保存しました。")
        elif choice == "0": break

if __name__ == "__main__":
    main()