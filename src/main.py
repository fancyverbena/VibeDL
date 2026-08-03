import os
import sys
import winreg
from downloader import download_audio, download_playlist
from audio_processor import (
    normalize_audio, embed_metadata,
    get_ffmpeg_info, check_ffmpeg, download_ffmpeg
)

REG_PATH = r"Software\VibeDL"

if os.name != 'nt':
    print("このアプリケーションはWindows専用です。")
    sys.exit(1)

def get_config():
    config = {
        "target_lufs": -14.0,
        "output_folder": "downloads",
        "output_format": "mp3",
        "bitrate": "256k",
        "normalize": True,
        "embed_metadata": True
    }
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            config["target_lufs"] = float(winreg.QueryValueEx(key, "TargetLUFS")[0])
            config["output_folder"] = winreg.QueryValueEx(key, "OutputFolder")[0]
            config["output_format"] = winreg.QueryValueEx(key, "OutputFormat")[0]
            config["bitrate"] = winreg.QueryValueEx(key, "Bitrate")[0]
            config["normalize"] = winreg.QueryValueEx(key, "Normalize")[0] == "True"
            config["embed_metadata"] = winreg.QueryValueEx(key, "EmbedMetadata")[0] == "True"
    except FileNotFoundError:
        pass
    except (TypeError, ValueError) as e:
        print(f"設定ファイルに問題があります: {e}。デフォルト値で動作します。")
    return config

def save_config(config):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "TargetLUFS", 0, winreg.REG_SZ, str(config["target_lufs"]))
        absolute_folder = os.path.abspath(config["output_folder"])
        winreg.SetValueEx(key, "OutputFolder", 0, winreg.REG_SZ, absolute_folder)
        config["output_folder"] = absolute_folder
        winreg.SetValueEx(key, "OutputFormat", 0, winreg.REG_SZ, config["output_format"])
        winreg.SetValueEx(key, "Bitrate", 0, winreg.REG_SZ, config["bitrate"])
        winreg.SetValueEx(key, "Normalize", 0, winreg.REG_SZ, str(config["normalize"]))
        winreg.SetValueEx(key, "EmbedMetadata", 0, winreg.REG_SZ, str(config["embed_metadata"]))

def progress_hook(d):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%')
        eta = d.get('_eta_str', '??:??')
        print(f"\r[Downloading] {p} (残り時間: {eta}) ", end='')
    elif d['status'] == 'finished':
        print("\n[Done] ダウンロード完了。音量調整を開始します...")

def parse_time_to_sec(timestr):
    timestr = timestr.strip()
    if not timestr:
        return None
    if ':' in timestr:
        parts = list(map(int, timestr.split(':')))
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            return None
    else:
        try:
            return int(timestr)
        except ValueError:
            return None

def process_item(url, config, ffmpeg_info, start_sec=None, end_sec=None):
    print("\n[1/3] 解析中...")
    data = download_audio(
        url,
        config['output_folder'],
        output_format=config['output_format'],
        bitrate=config['bitrate'],
        progress_hook=progress_hook,
        start_sec=start_sec,
        end_sec=end_sec
    )

    if not config["normalize"] and not config["embed_metadata"]:
        print("\n✨ ダウンロードが完了しました（後処理なし）。")
        print(f"保存先: {data['dest_path']}")
        return

    temp_out = data['temp_raw']
    if config["normalize"]:
        print(f"[2/3] 音量を最適化中 ({config['target_lufs']} LUFS)...")
        print(f"使用FFmpeg: {ffmpeg_info['source']}モード")
        normalized = normalize_audio(temp_out, config['target_lufs'], ffmpeg_info=ffmpeg_info)
        if not normalized:
            print("\n❌ 音量調整に失敗しました。FFmpegを確認してください。")
            if os.path.exists(temp_out):
                os.remove(temp_out)
            return
        temp_out = normalized

    if config["embed_metadata"]:
        print("[3/3] メタデータを埋め込み中...")
        embed_metadata(temp_out, data['title'], data['uploader'], data['thumb'])

    if os.path.exists(data['dest_path']):
        os.remove(data['dest_path'])
    os.rename(temp_out, data['dest_path'])

    if os.path.exists(data['temp_raw']) and data['temp_raw'] != temp_out:
        os.remove(data['temp_raw'])

    print(f"\n✨ 正常に完了しました！")
    print(f"保存先: {data['dest_path']}")

def main():
    config = get_config()
    config["output_folder"] = os.path.abspath(config["output_folder"])

    # --- FFmpeg チェック & 自動ダウンロード ---
    ffmpeg_info = get_ffmpeg_info()
    if not check_ffmpeg(ffmpeg_info['path']):
        print("⚠️ FFmpeg が見つからないか、正常に動作しません。")
        while True:
            ans = input("自動的にダウンロードしますか？ (y/n): ").strip().lower()
            if ans in ('y', 'n'):
                break
            print("y または n を入力してください。")
        if ans == 'y':
            def dl_progress(done, total):
                percent = (done / total) * 100 if total else 0
                print(f"\rFFmpeg ダウンロード中: {done}/{total} bytes ({percent:.1f}%)", end='')
            new_path = download_ffmpeg(progress_callback=dl_progress)
            if new_path:
                print("\n✅ FFmpeg のダウンロードが完了しました。")
                ffmpeg_info = get_ffmpeg_info()   # 再取得 (downloaded がヒット)
            else:
                print("\n❌ ダウンロードに失敗しました。FFmpeg なしで続行します。")
        else:
            print("FFmpeg なしで続行します。音量正規化は利用できません。")

    # --- メインループ ---
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"========== VibeDL v1.3 ==========")
        print(f" 保存先: {config['output_folder']}")
        print(f" フォーマット: {config['output_format']} / {config['bitrate']}")
        print(f" 音量正規化: {'ON' if config['normalize'] else 'OFF'} ({config['target_lufs']} LUFS)")
        print(f" メタデータ: {'ON' if config['embed_metadata'] else 'OFF'}")
        print(f" FFmpeg: {ffmpeg_info['source']}モード")
        if ffmpeg_info['source'] in ('bundled', 'local', 'downloaded'):
            print(f"  └ 場所: {ffmpeg_info['location']}")
        print("---------------------------------")
        print(" 1: YouTubeからダウンロード")
        print(" 2: プレイリストをダウンロード")
        print(" 3: 設定を変更する")
        print(" 0: 終了")
        print("---------------------------------")

        choice = input("選択してください > ").strip()

        if choice == "1":
            urls_input = input("\nYouTube URLを入力（複数可・スペース区切り）: ").strip()
            if not urls_input:
                continue
            urls = urls_input.split()

            start_sec = None
            end_sec = None
            if len(urls) == 1:
                time_input = input("時間指定（例: 1:30-2:45, 90-165） [省略可] > ").strip()
                if time_input:
                    parts = time_input.split('-')
                    if len(parts) == 2:
                        s = parse_time_to_sec(parts[0])
                        e = parse_time_to_sec(parts[1])
                        if s is not None and e is not None and s < e:
                            start_sec = s
                            end_sec = e
                        else:
                            print("⚠️ 時間の形式が無効です。時間指定をスキップします。")
                    else:
                        print("⚠️ 時間指定は「開始-終了」で入力してください。スキップします。")
            elif len(urls) > 1:
                print("ℹ️ 複数URLでは時間指定できません。")

            for url in urls:
                print(f"\n処理中: {url}")
                try:
                    process_item(url, config, ffmpeg_info, start_sec=start_sec, end_sec=end_sec)
                except Exception as e:
                    print(f"\n❌ エラーが発生しました: {e}")
            input("\nEnterでメニューに戻る...")

        elif choice == "2":
            url = input("\nプレイリストURLを入力: ").strip()
            if not url:
                continue
            try:
                print("\nプレイリストを解析中...")
                playlist = download_playlist(url, config, progress_hook=progress_hook)
                for entry in playlist:
                    try:
                        process_item(entry['url'], config, ffmpeg_info)
                    except Exception as e:
                        print(f"\n❌ エラーが発生しました ({entry['title']}): {e}")
                print("\n🎉 プレイリストの処理が完了しました。")
            except Exception as e:
                print(f"\n❌ エラーが発生しました: {e}")
            input("\nEnterでメニューに戻る...")

        elif choice == "3":
            print("\n--- 設定変更 ---")
            new_folder = input(f"保存フォルダ (現在: {config['output_folder']}): ").strip()
            folder_changed = False
            if new_folder:
                config['output_folder'] = new_folder
                folder_changed = True

            new_format = input(f"出力フォーマット mp3/m4a (現在: {config['output_format']}): ").strip().lower()
            if new_format in ("mp3", "m4a"):
                config['output_format'] = new_format
                folder_changed = True

            new_bitrate = input(f"ビットレート 例:192k/256k/320k (現在: {config['bitrate']}): ").strip()
            if new_bitrate:
                config['bitrate'] = new_bitrate
                folder_changed = True

            new_lufs = input(f"目標音量 LUFS (現在: {config['target_lufs']}): ").strip()
            lufs_changed = False
            if new_lufs:
                try:
                    config['target_lufs'] = float(new_lufs)
                    lufs_changed = True
                except ValueError:
                    print("❌ 無効な数値です。変更は破棄されます。")

            normalize_input = input(f"音量正規化 ON/OFF (現在: {'ON' if config['normalize'] else 'OFF'}): ").strip().upper()
            if normalize_input in ("ON", "OFF"):
                config['normalize'] = (normalize_input == "ON")
                folder_changed = True

            meta_input = input(f"メタデータ埋め込み ON/OFF (現在: {'ON' if config['embed_metadata'] else 'OFF'}): ").strip().upper()
            if meta_input in ("ON", "OFF"):
                config['embed_metadata'] = (meta_input == "ON")
                folder_changed = True

            if folder_changed or lufs_changed:
                save_config(config)
                print("✅ 設定を保存しました。")
            else:
                print("ℹ️ 設定は変更されませんでした。")
            input("\nEnterで戻る...")

        elif choice == "0":
            print("終了します。")
            break
        else:
            print("❌ 無効な選択です。")
            input("\nEnterで戻る...")

if __name__ == "__main__":
    main()