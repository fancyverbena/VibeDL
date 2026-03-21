import os
import sys
import winreg
from downloader import download_audio
from audio_processor import normalize_audio, embed_metadata

REG_PATH = r"Software\VibeDL"

def get_config():
    """レジストリから設定を読み込む。なければデフォルトを返す"""
    config = {"target_lufs": -14.0, "output_folder": "downloads"}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            config["target_lufs"] = float(winreg.QueryValueEx(key, "TargetLUFS")[0])
            config["output_folder"] = winreg.QueryValueEx(key, "OutputFolder")[0]
    except:
        pass
    return config

def save_config(config):
    """設定をレジストリに保存する"""
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "TargetLUFS", 0, winreg.REG_SZ, str(config["target_lufs"]))
        winreg.SetValueEx(key, "OutputFolder", 0, winreg.REG_SZ, config["output_folder"])

def progress_hook(d):
    """ダウンロード進捗を表示するコールバック"""
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%')
        eta = d.get('_eta_str', '??:??')
        print(f"\r[Downloading] {p} (残り時間: {eta}) ", end='')
    elif d['status'] == 'finished':
        print("\n[Done] ダウンロード完了。音量調整を開始します...")

def main():
    config = get_config()
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print(f"========== VibeDL v1.0 ==========")
        print(f" 現在の設定: {config['target_lufs']} LUFS / 保存先: {config['output_folder']}")
        print("---------------------------------")
        print(" 1: YouTubeからダウンロード")
        print(" 2: 設定を変更する (音量・保存先)")
        print(" 0: 終了")
        print("---------------------------------")
        
        choice = input("選択してください > ").strip()
        
        if choice == "1":
            url = input("\nYouTube URLを入力: ").strip()
            if not url: continue
            
            try:
                print("\n[1/3] 解析中...")
                data = download_audio(url, config['output_folder'], progress_hook=progress_hook)
                
                print(f"[2/3] 音量を最適化中 ({config['target_lufs']} LUFS)...")
                temp_out = normalize_audio(data['temp_raw'], config['target_lufs'])
                
                if temp_out:
                    print("[3/3] メタデータを埋め込み中...")
                    embed_metadata(temp_out, data['title'], data['uploader'], data['thumb'])
                    
                    if os.path.exists(data['dest_path']):
                        os.remove(data['dest_path'])
                    os.rename(temp_out, data['dest_path'])
                    
                    if os.path.exists(data['temp_raw']):
                        os.remove(data['temp_raw'])
                    
                    print(f"\n✨ 正常に完了しました！")
                    print(f"保存先: {data['dest_path']}")
                else:
                    print("\n❌ 音量調整に失敗しました。FFmpegを確認してください。")
                    
                input("\nEnterでメニューに戻る...")

            except Exception as e:
                print(f"\n❌ エラーが発生しました: {e}")
                input("\nEnterでメニューに戻る...")

        elif choice == "2":
            print("\n--- 設定変更 ---")
            new_folder = input(f"保存フォルダを入力 (現在: {config['output_folder']}): ").strip()
            if new_folder: config['output_folder'] = new_folder
            
            new_lufs = input(f"目標音量を入力 (現在: {config['target_lufs']} LUFS): ").strip()
            if new_lufs:
                try:
                    config['target_lufs'] = float(new_lufs)
                except:
                    print("❌ 数値を入力してください。")
            
            save_config(config)
            print("✅ 設定を保存しました。")
            input("\nEnterで戻る...")

        elif choice == "0":
            print("終了します。")
            break

if __name__ == "__main__":
    main()