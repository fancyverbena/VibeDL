import os
import sys
from downloader import (
    download_audio, download_playlist, clean_title, get_unique_path,
)
from audio_processor import (
    normalize_audio, embed_metadata, split_into_chapters,
    get_ffmpeg_info, check_ffmpeg, download_ffmpeg
)
from license_check import is_pro as _license_is_pro
from config_store import get_config, save_config

if os.name != 'nt':
    print("このアプリケーションはWindows専用です。")
    sys.exit(1)

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
    pro = _license_is_pro(config.get('license_key', ''))
    data = download_audio(
        url,
        config['output_folder'],
        output_format=config['output_format'],
        bitrate=config['bitrate'],
        progress_hook=progress_hook,
        start_sec=start_sec,
        end_sec=end_sec,
        name_template=config.get('name_template', '{title}'),
        allow_folders=pro,
        with_subtitles=bool(pro and config.get('embed_lyrics')
                            and config.get('embed_metadata')),
        ratelimit=(int(float(config.get('rate_limit_mbps', 0)) * 1024 * 1024)
                   if float(config.get('rate_limit_mbps', 0)) > 0 else None),
    )

    # Pro: チャプター分割保存
    chapters = data.get('chapters') or []
    if pro and config.get('split_chapters') and len(chapters) >= 2 \
            and start_sec is None:
        parts = split_into_chapters(
            data['temp_raw'], chapters, ffmpeg_info=ffmpeg_info,
            bitrate=config['bitrate'])
        if parts:
            base, ext = os.path.splitext(data['dest_path'])
            for part in parts:
                temp_out = part['path']
                if config["normalize"]:
                    normalized = normalize_audio(
                        temp_out, config['target_lufs'],
                        ffmpeg_info=ffmpeg_info,
                        bitrate=config.get('bitrate'),
                        target_tp=float(config.get('loudnorm_tp', -2.0)))
                    if normalized:
                        temp_out = normalized
                if config["embed_metadata"]:
                    embed_metadata(temp_out, part['title'],
                                   data['uploader'], data['thumb'])
                dest = get_unique_path(
                    f"{base} [{part['index'] + 1:02d} "
                    f"{clean_title(part['title'])}]{ext}")
                if os.path.exists(dest):
                    os.remove(dest)
                os.rename(temp_out, dest)
                part_base, part_ext = os.path.splitext(part['path'])
                for leftover in (part['path'],
                                 f"{part_base}_tmp{part_ext}"):
                    if os.path.exists(leftover):
                        os.remove(leftover)
                print(f"保存先: {dest}")
            if os.path.exists(data['temp_raw']):
                os.remove(data['temp_raw'])
            print("\n✨ チャプター分割が完了しました。")
            return

    if not config["normalize"] and not config["embed_metadata"]:
        # 後処理が無い場合も、必ず最終ファイル名へリネームしてから
        # 保存先を表示する（以前は実ファイルと表示が食い違っていた）。
        if os.path.exists(data['dest_path']):
            os.remove(data['dest_path'])
        os.rename(data['temp_raw'], data['dest_path'])
        print("\n✨ ダウンロードが完了しました（後処理なし）。")
        print(f"保存先: {data['dest_path']}")
        return

    temp_out = data['temp_raw']
    if config["normalize"]:
        print(f"[2/3] 音量を最適化中 ({config['target_lufs']} LUFS)...")
        print(f"使用FFmpeg: {ffmpeg_info['source']}モード")
        normalized = normalize_audio(temp_out, config['target_lufs'], ffmpeg_info=ffmpeg_info, bitrate=config.get('bitrate'), target_tp=float(config.get('loudnorm_tp', -2.0)) if pro else -2.0)
        if not normalized:
            print("\n❌ 音量調整に失敗しました。FFmpegを確認してください。")
            if os.path.exists(temp_out):
                os.remove(temp_out)
            return
        temp_out = normalized

    if config["embed_metadata"]:
        print("[3/3] メタデータを埋め込み中...")
        embed_metadata(temp_out, data['title'], data['uploader'], data['thumb'], lyrics=data.get('lyrics'))

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

            new_format = input(f"出力フォーマット mp3/m4a/wav/flac/opus (現在: {config['output_format']}): ").strip().lower()
            if new_format in ("mp3", "m4a", "wav", "flac", "opus"):
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