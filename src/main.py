import winreg
import os
from downloader import download_audio
from audio_processor import normalize_audio

REG_PATH = r"Software\VibeDL"

def get_config():
    """レジストリから設定を読み込む。なければデフォルトを返す"""
    config = {
        "target_lufs": -14.0,
        "true_peak": -2.0,
        "output_folder": "downloads"
    }
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            config["target_lufs"] = float(winreg.QueryValueEx(key, "TargetLUFS")[0])
            config["true_peak"] = float(winreg.QueryValueEx(key, "TruePeak")[0])
            config["output_folder"] = winreg.QueryValueEx(key, "OutputFolder")[0]
    except FileNotFoundError:
        pass
    return config

def save_config(config):
    """設定をレジストリに書き込む"""
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "TargetLUFS", 0, winreg.REG_SZ, str(config["target_lufs"]))
        winreg.SetValueEx(key, "TruePeak", 0, winreg.REG_SZ, str(config["true_peak"]))
        winreg.SetValueEx(key, "OutputFolder", 0, winreg.REG_SZ, config["output_folder"])

def change_settings(config):
    print("\n--- 設定変更 ---")
    print(f"1: 目標音量 ({config['target_lufs']} LUFS)")
    print(f"2: 保存フォルダ ({config['output_folder']})")
    
    choice = input("\n変更番号を入力 (0で戻る): ")
    if choice == "1":
        config["target_lufs"] = float(input("新LUFS (-20 ～ -5): "))
    elif choice == "2":
        config["output_folder"] = input("新フォルダ名: ")
    
    save_config(config)
    print("設定をWindowsに保存しました。")
    return config

def main():
    config = get_config()
    while True:
        print(f"\n========== VibeDL (Target: {config['target_lufs']} LUFS) ==========")
        print("1: ダウンロード / 2: 設定変更 / 0: 終了")
        
        cmd = input("選択: ")
        if cmd == "1":
            url = input("URL: ").strip()
            if not url: continue
            raw = download_audio(url, output_dir=config['output_folder'])
            final = normalize_audio(raw, target_lufs=config['target_lufs'])
            if final and os.path.exists(raw): os.remove(raw)
            print(f"✨ 完了: {os.path.basename(final)}")
        elif cmd == "2":
            config = change_settings(config)
        elif cmd == "0":
            break

if __name__ == "__main__":
    main()