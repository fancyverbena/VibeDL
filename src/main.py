import json
import os
import sys
from downloader import download_audio
from audio_processor import normalize_audio

CONFIG_FILE = "config.json"

def load_config():
    default_config = {
        "target_lufs": -14.0,
        "true_peak": -2.0,
        "output_folder": "downloads"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**default_config, **json.load(f)}
        except:
            return default_config
    else:
        save_config(default_config)
        return default_config

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def change_settings(config):
    while True:
        print("\n--- 設定変更メニュー ---")
        print(f"1: 目標音量 (現在: {config['target_lufs']} LUFS)")
        print(f"2: 最大ピーク (現在: {config['true_peak']} dB)")
        print(f"3: 保存フォルダ (現在: {config['output_folder']})")
        print("0: 戻る")
        
        choice = input("\n変更したい項目番号を入力してください: ")
        
        if choice == "1":
            val = input("新しい目標音量を入力 (-20.0 ～ -5.0): ")
            config['target_lufs'] = float(val)
        elif choice == "2":
            val = input("新しい最大ピークを入力 (-5.0 ～ 0.0): ")
            config['true_peak'] = float(val)
        elif choice == "3":
            val = input("新しい保存フォルダ名を入力: ")
            config['output_folder'] = val
        elif choice == "0":
            save_config(config)
            print("設定を保存しました。")
            break
    return config

def main():
    config = load_config()
    
    while True:
        print(f"\n========== VibeDL (Target: {config['target_lufs']} LUFS) ==========")
        print("1: YouTubeからダウンロード")
        print("2: 設定を変更する")
        print("0: 終了")
        
        menu_choice = input("\n選択してください: ")
        
        if menu_choice == "1":
            url = input("YouTube URLを入力してください: ").strip()
            if not url: continue
            
            try:
                print("\n[1/2] ダウンロード開始...")
                raw_file = download_audio(url, output_dir=config['output_folder'])
                
                print(f"[2/2] 音量最適化中 ({config['target_lufs']} LUFS)...")
                final_file = normalize_audio(raw_file, target_lufs=config['target_lufs'])
                
                if final_file:
                    if os.path.exists(raw_file): os.remove(raw_file)
                    print(f"\n✨ 完了: {os.path.basename(final_file)}")
            except Exception as e:
                print(f"❌ エラー: {e}")
                
        elif menu_choice == "2":
            config = change_settings(config)
        elif menu_choice == "0":
            break

if __name__ == "__main__":
    main()