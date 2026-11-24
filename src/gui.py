"""VibeDL GUI (PySide6 / Qt)

wxPython 版から移行した GUI。見た目は QSS（Qt Style Sheets）で
一元管理し、カード型レイアウト + アクセントカラーで統一している。
ダウンロード・音声処理・設定保存は従来モジュールをそのまま使う。
"""
import csv
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import urllib.request
import winsound
from datetime import datetime

from PySide6.QtCore import (
    QPointF, QSize, Qt, QThread, QTime, QTimer, QUrl, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit,
    QProgressBar, QProgressDialog, QPushButton, QSpinBox, QTabWidget,
    QTimeEdit,
    QVBoxLayout, QWidget, QSystemTrayIcon, QStackedWidget,
)

from downloader import (
    JS_RUNTIMES, download_audio, search_youtube, get_playlist_entries,
    get_video_info, clean_title, get_unique_path,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except Exception:  # QtMultimedia が無い環境ではプレビューを無効化
    QAudioOutput = QMediaPlayer = None
from license_check import is_pro as _license_is_pro, parse_license_key

PRO_PURCHASE_URL = "https://buy.stripe.com/aFabJ2c9w9TubQO1GI0co01"
APP_VERSION = "1.1.0"
UPDATE_API_URL = ("https://api.github.com/repos/fancyverbena/VibeDL"
                  "/releases/latest")
from audio_processor import (
    convert_audio, normalize_audio, embed_metadata, read_tags,
    trim_and_fade, split_into_chapters, update_tags,
    get_ffmpeg_info, check_ffmpeg, download_ffmpeg,
)
from config_store import (
    get_config, save_config, load_download_history, save_download_history,
    load_presets, load_queue_items, save_presets, save_queue_items,
    load_watch_state, save_watch_state,
)

CURRENT_LANG = "ja"

TEXTS = {
    "log_processing": {"ja": "処理中: {url}", "en": "Processing: {url}"},
    "log_dl_done": {"ja": "[1/3] ダウンロード完了", "en": "[1/3] Download complete"},
    "phase_trim": {"ja": "無音トリミング／フェード処理中...", "en": "Trimming silence / applying fades..."},
    "log_trim": {"ja": "無音トリミング／フェード処理中...", "en": "Trimming silence / applying fades..."},
    "log_trim_done": {"ja": "トリミング／フェード完了", "en": "Trim/fade complete"},
    "log_trim_failed": {"ja": "トリミング／フェードに失敗しました。", "en": "Trim/fade failed."},
    "phase_normalize": {"ja": "音量最適化中...", "en": "Normalizing volume..."},
    "log_normalize": {"ja": "[2/3] 音量最適化中...", "en": "[2/3] Normalizing volume..."},
    "log_normalize_done": {"ja": "音量調整完了", "en": "Volume normalization complete"},
    "log_normalize_failed": {"ja": "音量調整に失敗しました。", "en": "Volume normalization failed."},
    "log_normalize_skip": {"ja": "音量正規化をスキップ", "en": "Skipping volume normalization"},
    "phase_metadata": {"ja": "メタデータ埋め込み中...", "en": "Embedding metadata..."},
    "log_metadata": {"ja": "[3/3] メタデータ埋め込み中...", "en": "[3/3] Embedding metadata..."},
    "log_complete": {"ja": "✨ 完了: {path}", "en": "✨ Done: {path}"},
    "log_error": {"ja": "❌ エラー ({url}): {err}", "en": "❌ Error ({url}): {err}"},
    "log_metadata_failed": {"ja": "⚠ メタデータの埋め込みに失敗しました（ファイルはそのまま保存します）: {err}", "en": "⚠ Failed to embed metadata (saving the file as-is): {err}"},
    "log_cancelled": {"ja": "⏹ キャンセルしました: {url}", "en": "⏹ Cancelled: {url}"},
    "section_download": {"ja": "ダウンロード", "en": "Download"},
    "search": {"ja": "検索", "en": "Search"},
    "search_tip": {"ja": "キーワードでYouTubeを検索", "en": "Search YouTube by keyword"},
    "start_label": {"ja": "開始 (秒 / mm:ss):", "en": "Start (sec / mm:ss):"},
    "end_label": {"ja": "終了 (秒 / mm:ss):", "en": "End (sec / mm:ss):"},
    "add_queue": {"ja": "キューに追加", "en": "Add to Queue"},
    "start_queue": {"ja": "キューを開始", "en": "Start Queue"},
    "clear_queue": {"ja": "キューをクリア", "en": "Clear Queue"},
    "cancel": {"ja": "キャンセル", "en": "Cancel"},
    "cancel_tip": {"ja": "実行中のダウンロードをすべてキャンセル", "en": "Cancel all running downloads"},
    "import_btn": {"ja": "インポート", "en": "Import"},
    "import_tip": {"ja": "テキストファイル（1行1URL）からキューに追加", "en": "Add from a text file (one URL per line)"},
    "open_folder": {"ja": "フォルダを開く", "en": "Open Folder"},
    "open_folder_tip": {"ja": "最後に保存したフォルダを開く", "en": "Open the folder of the last saved file"},
    "play": {"ja": "▶ 再生", "en": "▶ Play"},
    "play_tip": {"ja": "最後に完了したファイルを再生", "en": "Play the last completed file"},
    "history": {"ja": "履歴", "en": "History"},
    "history_tip": {"ja": "ダウンロード履歴", "en": "Download history"},
    "settings": {"ja": "設定", "en": "Settings"},
    "section_queue": {"ja": "キュー", "en": "Queue"},
    "section_log": {"ja": "ログ", "en": "Log"},
    "status_format": {"ja": "フォーマット: {fmt} / {br}", "en": "Format: {fmt} / {br}"},
    "status_normalize": {"ja": "正規化: {onoff} ({lufs} LUFS)", "en": "Normalize: {onoff} ({lufs} LUFS)"},
    "status_metadata": {"ja": "メタデータ: {onoff}", "en": "Metadata: {onoff}"},
    "speed": {"ja": "速度: {speed}", "en": "Speed: {speed}"},
    "eta": {"ja": "残り: {eta}", "en": "ETA: {eta}"},
    "clipboard_pasted": {"ja": "🔗 クリップボードからURLを貼り付けました", "en": "🔗 Pasted URL from clipboard"},
    "ffmpeg_not_found_title": {"ja": "FFmpeg 未検出", "en": "FFmpeg Not Found"},
    "ffmpeg_not_found_msg": {"ja": "FFmpegが見つかりません。自動ダウンロードしますか？", "en": "FFmpeg was not found. Download it automatically?"},
    "ffmpeg_without": {"ja": "FFmpeg なしで続行します。音量正規化は利用不可。", "en": "Continuing without FFmpeg. Volume normalization is unavailable."},
    "ffmpeg_downloading": {"ja": "FFmpegをダウンロード中...", "en": "Downloading FFmpeg..."},
    "ffmpeg_dialog": {"ja": "ダウンロードしています...", "en": "Downloading..."},
    "ffmpeg_dialog_title": {"ja": "FFmpeg ダウンロード", "en": "FFmpeg Download"},
    "ffmpeg_ready": {"ja": "FFmpeg の準備が完了しました。", "en": "FFmpeg is ready."},
    "ffmpeg_failed": {"ja": "FFmpeg のダウンロードに失敗しました。", "en": "Failed to download FFmpeg."},
    "input_error": {"ja": "入力エラー", "en": "Input Error"},
    "time_format_msg": {"ja": "開始・終了は「秒」または「mm:ss」で入力してください。", "en": "Enter start/end as seconds or mm:ss."},
    "end_after_start_msg": {"ja": "終了は開始より後を指定してください。", "en": "End must be after start."},
    "added_to_queue": {"ja": "キューに追加: {name}", "en": "Added to queue: {name}"},
    "playlist_expanding": {"ja": "プレイリストを展開中...", "en": "Expanding playlist..."},
    "playlist_empty": {"ja": "プレイリストに動画が見つかりませんでした", "en": "No videos found in the playlist"},
    "playlist_added": {"ja": "プレイリストから{n}件追加しました", "en": "Added {n} items from playlist"},
    "playlist_failed": {"ja": "プレイリストの展開に失敗しました: {msg}", "en": "Failed to expand playlist: {msg}"},
    "url_required": {"ja": "URLを入力してください。", "en": "Please enter a URL."},
    "info_title": {"ja": "情報", "en": "Info"},
    "queue_empty": {"ja": "キューが空です。", "en": "The queue is empty."},
    "cancel_requested": {"ja": "キャンセルを要求しました（ダウンロード中はすぐ、変換・音量調整中は工程の合間で止まります）", "en": "Cancellation requested (immediate while downloading; at phase boundaries during conversion/normalization)"},
    "status_cancelled": {"ja": "キャンセルしました", "en": "Cancelled"},
    "notify_complete": {"ja": "ダウンロード完了", "en": "Download complete"},
    "status_done": {"ja": "完了", "en": "Done"},
    "queue_cleared": {"ja": "キューをクリアしました。", "en": "Queue cleared."},
    "file_read_failed": {"ja": "ファイルの読み込みに失敗しました: {err}", "en": "Failed to read file: {err}"},
    "import_dialog_title": {"ja": "URLリストを選択", "en": "Select URL List"},
    "filter_text": {"ja": "テキストファイル (*.txt);;すべてのファイル (*.*)", "en": "Text files (*.txt);;All files (*.*)"},
    "error_title": {"ja": "エラー", "en": "Error"},
    "file_unreadable": {"ja": "ファイルを読み込めませんでした: {err}", "en": "Could not read the file: {err}"},
    "no_urls": {"ja": "URLが見つかりませんでした", "en": "No URLs found"},
    "urls_loaded": {"ja": "{n}件のURLを読み込みました", "en": "Loaded {n} URLs"},
    "search_title": {"ja": "YouTube検索", "en": "YouTube Search"},
    "keyword_placeholder": {"ja": "キーワードを入力", "en": "Enter keywords"},
    "search_status_initial": {"ja": "キーワードを入力して検索してください（最大10件）", "en": "Enter keywords to search (up to 10 results)"},
    "add_selected": {"ja": "選択をキューに追加", "en": "Add Selected to Queue"},
    "close": {"ja": "閉じる", "en": "Close"},
    "searching": {"ja": "検索中...", "en": "Searching..."},
    "results_found": {"ja": "{n}件見つかりました。複数選択もできます", "en": "Found {n} results. Multiple selection is supported"},
    "no_results": {"ja": "見つかりませんでした", "en": "No results found"},
    "search_failed": {"ja": "検索に失敗しました: {msg}", "en": "Search failed: {msg}"},
    "select_result": {"ja": "結果を選択してください。", "en": "Please select a result."},
    "history_title": {"ja": "ダウンロード履歴", "en": "Download History"},
    "missing_file_suffix": {"ja": "（ファイルなし）", "en": " (file missing)"},
    "history_empty": {"ja": "履歴はまだありません", "en": "No history yet"},
    "play2": {"ja": "再生", "en": "Play"},
    "redownload": {"ja": "再ダウンロード", "en": "Re-download"},
    "file_not_found": {"ja": "ファイルが見つかりません。", "en": "File not found."},
    "settings_title": {"ja": "設定", "en": "Settings"},
    "format_label": {"ja": "フォーマット:", "en": "Format:"},
    "bitrate_label": {"ja": "ビットレート:", "en": "Bitrate:"},
    "folder_label": {"ja": "保存先:", "en": "Output folder:"},
    "browse": {"ja": "参照", "en": "Browse"},
    "name_pattern_label": {"ja": "ファイル名パターン:", "en": "Filename pattern:"},
    "tab_output": {"ja": "出力", "en": "Output"},
    "normalize_cb": {"ja": "音量正規化", "en": "Volume normalization"},
    "lufs_label": {"ja": "目標 LUFS:", "en": "Target LUFS:"},
    "tp_label": {"ja": "トゥルーピーク上限 (dBTP)（Pro）:", "en": "True peak ceiling (dBTP) (Pro):"},
    "split_chapters_cb": {"ja": "チャプターごとに分割して保存（Pro）", "en": "Split into chapters (Pro)"},
    "embed_lyrics_cb": {"ja": "字幕があれば歌詞として埋め込む（Pro）", "en": "Embed subtitles as lyrics when available (Pro)"},
    "log_chapter_split": {"ja": "チャプター分割: {count} ファイルに分割します", "en": "Splitting into {count} chapter files"},
    "log_chapter_failed": {"ja": "チャプター分割に失敗したため、通常の1ファイルで保存します", "en": "Chapter split failed; saving as a single file"},
    "template_note": {"ja": "使用可能: {title} {uploader} {id} {date}（投稿日）。'/' を入れるとフォルダ分けできます（Pro）", "en": "Available: {title} {uploader} {id} {date} (upload date). Use '/' to create subfolders (Pro)."},
    "meta_cb": {"ja": "メタデータ埋め込み", "en": "Embed metadata"},
    "tab_processing": {"ja": "処理", "en": "Processing"},
    "trim_cb": {"ja": "無音トリミング（先頭・末尾）", "en": "Trim silence (start/end)"},
    "fade_cb": {"ja": "フェードイン／アウト", "en": "Fade in / out"},
    "fade_sec_label": {"ja": "フェード時間（秒）:", "en": "Fade duration (sec):"},
    "sound_cb": {"ja": "完了時に通知音を鳴らす", "en": "Play a sound when finished"},
    "toast_cb": {"ja": "完了時にトースト通知を表示", "en": "Show a toast notification when finished"},
    "tab_notif": {"ja": "通知", "en": "Notifications"},
    "dark_cb": {"ja": "ダークモード", "en": "Dark mode"},
    "theme_label": {"ja": "テーマ", "en": "Theme"},
    "theme_light": {"ja": "ライト", "en": "Light"},
    "theme_dark": {"ja": "ダーク", "en": "Dark"},
    "theme_system": {"ja": "システムに合わせる", "en": "Follow system"},
    "tray_cb": {"ja": "閉じるボタンでタスクトレイに格納", "en": "Minimize to tray on close"},
    "tray_show": {"ja": "表示", "en": "Show"},
    "tray_quit": {"ja": "終了", "en": "Quit"},
    "tray_minimized": {"ja": "タスクトレイに格納しました（ダウンロードは継続します）", "en": "Minimized to tray (downloads continue)"},
    "update_cb": {"ja": "起動時にアップデートを確認", "en": "Check for updates on startup"},
    "update_check_btn": {"ja": "今すぐアップデートを確認", "en": "Check for updates now"},
    "update_available_title": {"ja": "アップデートがあります", "en": "Update available"},
    "update_available_msg": {"ja": "新しいバージョン {tag} が公開されています（現在 {current}）。\nダウンロードページを開きますか？", "en": "A new version {tag} is available (current: {current}).\nOpen the download page?"},
    "update_latest_msg": {"ja": "すでに最新バージョンです（{current}）", "en": "You are on the latest version ({current})"},
    "update_failed_msg": {"ja": "アップデートの確認に失敗しました", "en": "Failed to check for updates"},
    "schedule_cb": {"ja": "予約ダウンロード（指定時刻に自動で開始）", "en": "Scheduled download (auto-start at the set time)"},
    "schedule_time_label": {"ja": "開始時刻", "en": "Start time"},
    "log_scheduled_start": {"ja": "予約時刻になったためダウンロードを開始します", "en": "Scheduled time reached; starting downloads"},
    "webhook_label": {"ja": "Discord Webhook URL（完了通知）", "en": "Discord Webhook URL (completion notice)"},
    "webhook_msg": {"ja": "✅ VibeDL: ダウンロードが完了しました（{name}）", "en": "✅ VibeDL: Download complete ({name})"},
    "webhook_msg_multi": {"ja": "✅ VibeDL: {n}件のダウンロードが完了しました", "en": "✅ VibeDL: {n} downloads complete"},
    "export_csv_btn": {"ja": "CSVエクスポート", "en": "Export CSV"},
    "csv_filter": {"ja": "CSVファイル (*.csv)", "en": "CSV files (*.csv)"},
    "export_done": {"ja": "履歴をCSVに書き出しました", "en": "History exported to CSV"},
    "watch_label": {"ja": "新着監視（Pro）: チャンネルやプレイリストのURLを登録すると、新着動画を起動時と30分ごとに確認し、自動でキューに追加します", "en": "Watch for new videos (Pro): register channel/playlist URLs; new uploads are checked on startup and every 30 minutes and added to the queue automatically"},
    "watch_ph": {"ja": "チャンネルまたはプレイリストのURL", "en": "Channel or playlist URL"},
    "watch_add": {"ja": "追加", "en": "Add"},
    "watch_remove": {"ja": "選択を削除", "en": "Remove selected"},
    "watch_added_log": {"ja": "新着監視: {n}件の新着をキューに追加しました", "en": "Watch: added {n} new video(s) to the queue"},
    "watch_notify_title": {"ja": "新着動画", "en": "New videos"},
    "preset_label": {"ja": "プリセット", "en": "Presets"},
    "preset_save": {"ja": "保存", "en": "Save"},
    "preset_apply": {"ja": "適用", "en": "Apply"},
    "preset_delete": {"ja": "削除", "en": "Delete"},
    "preset_name_title": {"ja": "プリセット名", "en": "Preset name"},
    "preset_name_label": {"ja": "プリセットの名前", "en": "Name for the preset"},
    "prevent_sleep_cb": {"ja": "ダウンロード中はスリープを防止", "en": "Prevent sleep while downloading"},
    "preview_play": {"ja": "プレビュー再生", "en": "Preview"},
    "preview_stop": {"ja": "プレビュー停止", "en": "Stop preview"},
    "preview_unavailable": {"ja": "プレビューを再生できませんでした", "en": "Could not play the preview"},
    "disk_warn_title": {"ja": "空き容量の警告", "en": "Low disk space"},
    "disk_warn_msg": {"ja": "保存先の空き容量が不足している可能性があります（空き {free} MB／推定必要 {need} MB）。続行しますか？", "en": "The destination may be low on space ({free} MB free, about {need} MB needed). Continue?"},
    "convert_btn": {"ja": "ローカル変換（Pro）", "en": "Convert files (Pro)"},
    "convert_title": {"ja": "ローカルファイル一括変換", "en": "Convert local files"},
    "convert_add": {"ja": "ファイルを追加", "en": "Add files"},
    "convert_remove": {"ja": "選択を削除", "en": "Remove selected"},
    "convert_start": {"ja": "変換開始", "en": "Start conversion"},
    "convert_done_log": {"ja": "変換が完了しました: {name}", "en": "Converted: {name}"},
    "convert_failed_log": {"ja": "変換に失敗しました: {name}", "en": "Conversion failed: {name}"},
    "convert_pro_only": {"ja": "この機能は Pro 版で利用できます", "en": "This feature requires Pro"},
    "filter_audio": {"ja": "音声ファイル (*.mp3 *.m4a *.wav *.flac *.opus *.ogg)", "en": "Audio files (*.mp3 *.m4a *.wav *.flac *.opus *.ogg)"},
    "tag_edit_btn": {"ja": "タグ編集", "en": "Edit tags"},
    "tag_title": {"ja": "タグ編集", "en": "Edit tags"},
    "tag_title_label": {"ja": "タイトル", "en": "Title"},
    "tag_artist_label": {"ja": "アーティスト", "en": "Artist"},
    "tag_album_label": {"ja": "アルバム", "en": "Album"},
    "tag_saved": {"ja": "タグを保存しました", "en": "Tags saved"},
    "tag_failed": {"ja": "タグの保存に失敗しました", "en": "Failed to save tags"},
    "mirror_label": {"ja": "ミラー出力先（Pro）", "en": "Mirror folder (Pro)"},
    "split_artist_cb": {"ja": "タイトルを「アーティスト - 曲名」に自動分離してタグ付け（Pro）", "en": "Split 'Artist - Title' into tags automatically (Pro)"},
    "ctx_error_detail": {"ja": "エラー詳細", "en": "Error details"},
    "err_advice_login": {"ja": "ログインが必要な動画の可能性があります。設定の「ブラウザCookie」または cookies.txt を設定してみてください。", "en": "This video may require sign-in. Try setting browser cookies or a cookies.txt file in Settings."},
    "err_advice_private": {"ja": "非公開動画の可能性があります。公開状態を確認してください。", "en": "This video may be private. Check its visibility."},
    "err_advice_unavailable": {"ja": "動画が削除・非公開になっている可能性があります。", "en": "The video may have been removed or made unavailable."},
    "err_advice_age": {"ja": "年齢制限のある動画の可能性があります。ブラウザCookieの設定で回避できる場合があります。", "en": "This video may be age-restricted. Browser cookies may help."},
    "err_advice_format": {"ja": "利用できる形式が見つかりませんでした。時間をおいて再試行するか、別の動画でお試しください。", "en": "No downloadable format was found. Try again later or with another video."},
    "err_advice_403": {"ja": "アクセスが拒否されました（403）。時間をおくか、ブラウザCookieを設定してみてください。", "en": "Access was denied (403). Wait a while or try browser cookies."},
    "err_advice_network": {"ja": "通信に失敗しました。ネットワーク接続を確認して再試行してください。", "en": "A network error occurred. Check your connection and retry."},
    "err_advice_generic": {"ja": "ダウンロードに失敗しました。しばらく待ってから再試行してください。", "en": "The download failed. Please retry after a while."},
    "export_queue_btn": {"ja": "キュー書き出し", "en": "Export queue"},
    "export_queue_done": {"ja": "キューのURLを書き出しました（{n}件）", "en": "Exported {n} queue URL(s)"},
    "downloaded_suffix": {"ja": "DL済み", "en": "Downloaded"},
    "pause_btn": {"ja": "一時停止", "en": "Pause"},
    "resume_btn": {"ja": "再開", "en": "Resume"},
    "status_paused": {"ja": "一時停止中（実行中の分が終わると止まります）", "en": "Paused (stops after current downloads finish)"},
    "playlist_cb": {"ja": "完了時にm3uプレイリストを作成", "en": "Create an .m3u playlist when a batch finishes"},
    "log_playlist_created": {"ja": "プレイリストを作成しました: {name}", "en": "Playlist created: {name}"},
    "ctx_priority": {"ja": "優先してダウンロード", "en": "Download first"},
    "history_bulk_redownload": {"ja": "選択を再DL", "en": "Redownload selected"},
    "history_bulk_delete": {"ja": "選択を削除", "en": "Delete selected"},
    "history_delete_confirm": {"ja": "選択した履歴を削除しますか？", "en": "Delete the selected history entries?"},
    "confirm_title": {"ja": "確認", "en": "Confirm"},
    "template_preview_label": {"ja": "プレビュー: {name}", "en": "Preview: {name}"},
    "rename_rules_label": {"ja": "スマートリネーム（Pro）: ファイル名への正規表現ルール（1行に1つ。「パターン => 置換」、パターンのみで削除）", "en": "Smart rename (Pro): regex rules for file names, one per line ('pattern => replacement', or pattern only to remove)"},
    "rename_rules_ph": {"ja": "例: 【[^】]*】 => ", "en": "Example: \\[[^\\]]*\\] => "},
    "queue_empty_hint": {"ja": "キューは空です。\nURLを貼り付けて「キューに追加」を押すか、ここにドロップしてください", "en": "Queue is empty.\nPaste a URL and press Add to Queue, or drop files here"},
    "status_overall": {"ja": "全体 {pct}%", "en": "Overall {pct}%"},
    "status_overall_eta": {"ja": "全体 {pct}% ・ 残り約 {eta}", "en": "Overall {pct}% · about {eta} left"},
    "ctx_remove_selected": {"ja": "選択を削除", "en": "Remove selected"},
    "clipboard_cb": {"ja": "クリップボードを監視してURLを自動入力", "en": "Monitor clipboard and auto-fill URLs"},
    "cookies_label": {"ja": "ブラウザCookie（年齢制限など用）", "en": "Browser cookies (for age-restricted videos)"},
    "cookies_none": {"ja": "使用しない", "en": "None"},
    "cookies_file_label": {"ja": "cookies.txt（指定時は優先）", "en": "cookies.txt (takes precedence)"},
    "cookies_file_ph": {"ja": "cookies.txt のパス（任意）", "en": "Path to cookies.txt (optional)"},
    "select": {"ja": "選択", "en": "Select"},
    "tab_general": {"ja": "一般", "en": "General"},
    "tab_pro": {"ja": "Pro", "en": "Pro"},
    "pro_intro": {"ja": "Pro版の機能はこのタブにまとめています。ライセンスキーを入力すると解放されます。",
                  "en": "Pro features are collected on this tab. Enter a license key to unlock them."},
    "pro_features_note": {"ja": "並列ダウンロード 3〜10 本（一般タブの「並列ダウンロード数」）と、出力ファイル名テンプレートでのフォルダ分け（出力タブ）、新着監視も Pro 機能です。",
                          "en": "Parallel downloads 3-10 (General tab), subfolders via the output filename template (Output tab), and new-video watching are also Pro features."},
    "language_label": {"ja": "言語", "en": "Language"},
    "max_parallel_label": {"ja": "同時ダウンロード数（1〜10）", "en": "Parallel downloads (1-10)"},
    "retry_failed": {"ja": "失敗を再試行", "en": "Retry Failed"},
    "log_duplicate_skipped": {"ja": "ダウンロード済みのためスキップしました: {name}", "en": "Already downloaded, skipped: {name}"},
    "log_retry_failed": {"ja": "失敗した {n} 件を再試行します", "en": "Retrying {n} failed item(s)"},
    "status_done_with_failed": {"ja": "完了（失敗 {n} 件が残っています）", "en": "Done ({n} failed item(s) remain)"},
    "skip_dup_cb": {"ja": "ダウンロード済みの動画はキューに追加しない", "en": "Do not queue videos that were already downloaded"},
    "after_finish_label": {"ja": "全て完了したら:", "en": "When all downloads finish:"},
    "after_finish_": {"ja": "何もしない", "en": "Do nothing"},
    "after_finish_sleep": {"ja": "スリープ", "en": "Sleep"},
    "after_finish_shutdown": {"ja": "シャットダウン（30秒後）", "en": "Shut down (in 30 seconds)"},
    "log_after_finish": {"ja": "全て完了したため、{action}を実行します", "en": "All downloads finished; performing: {action}"},
    "log_after_finish_failed": {"ja": "完了後アクションに失敗しました: {err}", "en": "After-finish action failed: {err}"},
    "auto_retry_label": {"ja": "失敗時の自動リトライ回数（0〜3）", "en": "Auto-retry on failure (0-3)"},
    "log_auto_retry": {"ja": "自動リトライ {n}/{max}: {name}", "en": "Auto-retry {n}/{max}: {name}"},
    "rate_limit_label": {"ja": "速度制限 MB/s（0=無制限）", "en": "Rate limit MB/s (0 = unlimited)"},
    "history_search_ph": {"ja": "タイトルで検索", "en": "Search by title"},
    "ctx_copy_url": {"ja": "URLをコピー", "en": "Copy URL"},
    "ctx_open_browser": {"ja": "ブラウザで開く", "en": "Open in browser"},
    "ctx_remove": {"ja": "キューから削除", "en": "Remove from queue"},
    "ctx_retry": {"ja": "再試行", "en": "Retry"},
    "log_queue_restored": {"ja": "前回のキューを {n} 件復元しました", "en": "Restored {n} item(s) from the previous queue"},
    "queue_summary": {"ja": "{n} 件 / 合計 {dur}", "en": "{n} item(s) / total {dur}"},
    "parallel_pro_note": {"ja": "※3以上は Pro ライセンスが必要です（未登録の場合は2まで有効）", "en": "3 or more requires a Pro license (capped at 2 without one)."},
    "license_label": {"ja": "Pro ライセンスキー", "en": "Pro license key"},
    "buy_pro": {"ja": "Pro版を購入（¥500・買い切り）", "en": "Buy Pro (¥500, one-time)"},
    "buy_pro_short": {"ja": "Pro版を購入", "en": "Buy Pro"},
    "pro_active": {"ja": "✓ Pro 有効", "en": "✓ Pro active"},
    "license_check": {"ja": "確認", "en": "Check"},
    "license_valid": {"ja": "✓ Pro 有効（{name}）", "en": "✓ Pro active ({name})"},
    "license_invalid": {"ja": "未登録、または無効なキーです", "en": "Not registered, or the key is invalid."},
    "language_note": {"ja": "※言語の変更は再起動後に反映されます", "en": "Language changes apply after restarting the app."},
    "folder_dialog": {"ja": "フォルダを選択", "en": "Select Folder"},
    "cookies_dialog": {"ja": "cookies.txt を選択", "en": "Select cookies.txt"},
}


def set_language(lang):
    global CURRENT_LANG
    CURRENT_LANG = lang if lang in ("ja", "en") else "ja"


def tr(key, **kwargs):
    entry = TEXTS.get(key, {})
    text = entry.get(CURRENT_LANG) or entry.get("ja") or key
    return text.format(**kwargs) if kwargs else text


ACCENT = "#7C5CFF"

PALETTES = {
    True: {  # dark
        "bg": "#202228", "surface": "#2B2E35", "entry": "#1C1E23",
        "fg": "#F2F2F2", "muted": "#A7ABB3", "border": "#3A3E47",
        "btn": "#3A3E47", "btn_hover": "#464B57", "track": "#3A3E47",
        "log_bg": "#181A1E", "sidebar": "#26282F",
    },
    False: {  # light
        "bg": "#E9EBEF", "surface": "#FFFFFF", "entry": "#FFFFFF",
        "fg": "#1C1E22", "muted": "#6E737A", "border": "#D6D9DE",
        "btn": "#FFFFFF", "btn_hover": "#F0F1F5", "track": "#D6D9DE",
        "log_bg": "#FFFFFF", "sidebar": "#DEE1E7",
    },
}


def build_stylesheet(dark):
    p = PALETTES[dark]
    qss = """
    QMainWindow, QDialog { background: @BG@; }
    QWidget { color: @FG@; font-family: "Segoe UI", "Yu Gothic UI", sans-serif; font-size: 10pt; }
    QFrame#card { background: @SURFACE@; border: 1px solid @BORDER@; border-radius: 12px; }
    QLabel#section { color: @ACCENT@; font-size: 12pt; font-weight: bold; }
    QLabel#appTitle { font-size: 20pt; font-weight: bold; }
    QLabel#muted { color: @MUTED@; }
    QLineEdit, QComboBox, QDoubleSpinBox {
        background: @ENTRY@; border: 1px solid @BORDER@; border-radius: 8px;
        padding: 6px 10px; min-height: 20px;
    }
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid @ACCENT@; }
    QComboBox::drop-down { border: none; width: 24px; }
    QPushButton {
        background: @BTN@; border: 1px solid @BORDER@; border-radius: 8px;
        padding: 8px 16px; min-height: 20px;
    }
    QPushButton:hover { background: @BTN_HOVER@; }
    QPushButton:disabled { color: @MUTED@; }
    QPushButton#primary { background: @ACCENT@; color: #FFFFFF; border: none; font-weight: bold; }
    QPushButton#primary:hover { background: #8F73FF; }
    QPushButton#primary:disabled { background: @TRACK@; color: @MUTED@; }
    QListWidget { background: transparent; border: none; outline: none; }
    QListWidget::item { padding: 6px 8px; border-radius: 6px; }
    QListWidget::item:selected { background: rgba(124, 92, 255, 0.25); }
    QProgressBar {
        background: @TRACK@; border: none; border-radius: 8px;
        min-height: 16px; max-height: 16px; text-align: center;
        color: @FG@; font-size: 8pt; font-weight: bold;
    }
    QProgressBar::chunk { background: @ACCENT@; border-radius: 8px; }
    QPlainTextEdit {
        background: @LOG_BG@; border: none; border-radius: 8px;
        font-family: Consolas, "Courier New", monospace; font-size: 9pt; padding: 6px;
    }
    QTabWidget::pane { border: 1px solid @BORDER@; border-radius: 8px; background: @SURFACE@; }
    QTabBar::tab {
        background: transparent; color: @MUTED@; padding: 8px 18px; border: none;
    }
    QTabBar::tab:selected { color: @ACCENT@; font-weight: bold; }
    QCheckBox { spacing: 8px; }
    QStatusBar { background: @BG@; color: @MUTED@; }
    QToolTip { background: @SURFACE@; color: @FG@; border: 1px solid @BORDER@; padding: 4px; }
    QFrame#sidebar { background: @SIDEBAR@; border-right: 1px solid @BORDER@; }
    QPushButton#nav {
        background: transparent; border: none; text-align: left;
        padding: 10px 14px; border-radius: 8px; font-size: 11pt;
    }
    QPushButton#nav:hover { background: @BTN_HOVER@; }
    QPushButton#nav:checked { background: @ACCENT@; color: #FFFFFF; font-weight: bold; }
    QLabel#proBadge { color: @ACCENT@; font-weight: bold; font-size: 11pt; }
    """
    return (qss.replace("@BG@", p["bg"]).replace("@SURFACE@", p["surface"])
            .replace("@ENTRY@", p["entry"]).replace("@FG@", p["fg"])
            .replace("@MUTED@", p["muted"]).replace("@BORDER@", p["border"])
            .replace("@BTN@", p["btn"]).replace("@BTN_HOVER@", p["btn_hover"])
            .replace("@TRACK@", p["track"]).replace("@LOG_BG@", p["log_bg"])
            .replace("@ACCENT@", ACCENT).replace("@SIDEBAR@", p["sidebar"]))


def make_app_icon():
    """アプリアイコンをコードで描く（外部ファイル不要）。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtGui import QColor
    painter.setBrush(QColor(ACCENT))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "V")
    painter.end()
    return QIcon(pixmap)


def parse_time(timestr):
    """時刻文字列を秒に変換する。空欄は None、不正な入力は ValueError。"""
    timestr = timestr.strip()
    if not timestr:
        return None
    if ':' in timestr:
        parts = [int(p) for p in timestr.split(':')]
        if len(parts) == 2:
            seconds = parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            raise ValueError(f"時刻の形式が不正です: {timestr}")
    else:
        seconds = int(timestr)
    if seconds < 0:
        raise ValueError(f"時刻が負の値です: {timestr}")
    return seconds


class QueueItem:
    def __init__(self, url, start_sec, end_sec):
        self.url = url
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.status = "waiting"
        # 情報取得後に埋まる表示用メタデータ
        self.title = None
        self.duration = None
        self.thumb_url = None
        self.thumb_data = None  # サムネイル画像のバイト列
        self.retry_count = 0
        self.error = ""


class DownloadCancelled(Exception):
    """キャンセル要求時にダウンロードを中断するための例外。"""


class DownloadWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str, str)  # percent, speed, eta
    phase = Signal(str)
    item_finished = Signal(object, object)  # item, dest_path or None
    item_cancelled = Signal(object)  # item

    def __init__(self, item, config, ffmpeg_info, parent=None):
        super().__init__(parent)
        self.item = item
        self.config = config
        self.ffmpeg_info = ffmpeg_info
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _check_cancelled(self):
        if self._cancel_requested:
            raise DownloadCancelled()

    def _progress_hook(self, d):
        # ダウンロード中は進捗コールバックのたびにキャンセルを確認する
        self._check_cancelled()
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            percent = int(downloaded / total * 100) if total else 0
            self.progress.emit(percent,
                               strip_ansi(d.get('_speed_str')).strip(),
                               strip_ansi(d.get('_eta_str')).strip())
        elif d.get('status') == 'finished':
            self.progress.emit(100, "", "")

    def run(self):
        try:
            self.item.status = "downloading"
            self.log.emit(tr("log_processing", url=self.item.url))
            pro = _license_is_pro(self.config.get("license_key", ""))
            data = download_audio(
                self.item.url, self.config["output_folder"],
                output_format=self.config["output_format"],
                bitrate=self.config["bitrate"],
                progress_hook=self._progress_hook,
                start_sec=self.item.start_sec,
                end_sec=self.item.end_sec,
                name_template=self.config.get("name_template", "{title}"),
                cookies_browser=self.config.get("cookies_browser") or None,
                cookies_file=self.config.get("cookies_file") or None,
                with_subtitles=bool(
                    pro and self.config.get("embed_lyrics")
                    and self.config.get("embed_metadata")),
                allow_folders=pro,
                ratelimit=(int(float(self.config.get("rate_limit_mbps", 0))
                               * 1024 * 1024)
                           if float(self.config.get("rate_limit_mbps", 0)) > 0
                           else None),
            )
            self.log.emit(tr("log_dl_done"))
            chapters = data.get('chapters') or []
            if pro and self.config.get("split_chapters") \
                    and len(chapters) >= 2 and self.item.start_sec is None \
                    and check_ffmpeg(self.ffmpeg_info['path']):
                if self._run_chapters(data, chapters, pro):
                    return
            temp_out = self._post_process(
                data['temp_raw'], data['title'], data['uploader'],
                data['thumb'], data.get('lyrics'), pro)

            if os.path.exists(data['dest_path']):
                os.remove(data['dest_path'])
            os.rename(temp_out, data['dest_path'])

            # 中間ファイル（生ファイル・_trim・_tmp 等）をすべて掃除する
            raw_base, raw_ext = os.path.splitext(data['temp_raw'])
            for leftover in (data['temp_raw'],
                             f"{raw_base}_trim{raw_ext}",
                             f"{raw_base}_tmp{raw_ext}",
                             f"{raw_base}_trim_tmp{raw_ext}"):
                if leftover != data['dest_path'] \
                        and os.path.exists(leftover):
                    try:
                        os.remove(leftover)
                    except OSError:
                        pass

            if pro and self.config.get("rename_rules"):
                new_dest = renamed_path(data['dest_path'],
                                        self.config["rename_rules"])
                if new_dest != data['dest_path']:
                    os.rename(data['dest_path'], new_dest)
                    data['dest_path'] = new_dest

            self.log.emit(tr("log_complete", path=data['dest_path']))
            self.item_finished.emit(self.item, data['dest_path'])
        except DownloadCancelled:
            self._handle_cancelled(data if 'data' in locals() else None,
                                   temp_out if 'temp_out' in locals() else None)
        except Exception as e:
            # yt-dlpがフック内例外を包んで返す場合も、キャンセル要求が
            # 立っていればエラーではなくキャンセルとして扱う
            if self._cancel_requested:
                self._handle_cancelled(data if 'data' in locals() else None,
                                       temp_out if 'temp_out' in locals() else None)
            else:
                self.item.error = str(e)
                self.log.emit(tr("log_error", url=self.item.url, err=e))
                self.item_finished.emit(self.item, None)

    def _post_process(self, temp_out, title, uploader, thumb, lyrics, pro):
        """トリム→正規化→メタデータの後処理を行い、最終の中間パスを返す。"""
        self._check_cancelled()
        if (self.config.get("trim_silence") or self.config.get("fade_enabled")) \
                and check_ffmpeg(self.ffmpeg_info['path']):
            self.phase.emit(tr("phase_trim"))
            self.log.emit(tr("log_trim"))
            fade_sec = float(self.config.get("fade_seconds", 1.0)) \
                if self.config.get("fade_enabled") else 0.0
            trimmed = trim_and_fade(
                temp_out,
                trim_silence=bool(self.config.get("trim_silence")),
                fade_sec=fade_sec,
                ffmpeg_info=self.ffmpeg_info)
            if trimmed:
                temp_out = trimmed
                self.log.emit(tr("log_trim_done"))
            else:
                self.log.emit(tr("log_trim_failed"))

        if self.config["normalize"] and check_ffmpeg(self.ffmpeg_info['path']):
            self.phase.emit(tr("phase_normalize"))
            self.log.emit(tr("log_normalize"))
            normalized = normalize_audio(
                temp_out, self.config["target_lufs"],
                ffmpeg_info=self.ffmpeg_info,
                bitrate=self.config["bitrate"],
                target_tp=float(self.config.get("loudnorm_tp", -2.0))
                if pro else -2.0)
            if normalized:
                temp_out = normalized
                self.log.emit(tr("log_normalize_done"))
            else:
                self.log.emit(tr("log_normalize_failed"))
        else:
            self.log.emit(tr("log_normalize_skip"))

        self._check_cancelled()
        if self.config["embed_metadata"]:
            self.phase.emit(tr("phase_metadata"))
            self.log.emit(tr("log_metadata"))
            meta_title, meta_artist = title, uploader
            if pro and self.config.get("split_artist_title"):
                parsed_artist, parsed_title = parse_artist_title(title)
                if parsed_artist:
                    meta_title, meta_artist = parsed_title, parsed_artist
            try:
                embed_metadata(temp_out, meta_title, meta_artist, thumb,
                               lyrics=lyrics)
            except Exception as e:
                # メタデータ失敗で完成したファイルまで失わない
                self.log.emit(tr("log_metadata_failed", err=e))
        return temp_out

    def _run_chapters(self, data, chapters, pro):
        """チャプター分割モードの処理。分割できたら True（呼び出し側は終了）。"""
        parts = split_into_chapters(
            data['temp_raw'], chapters, ffmpeg_info=self.ffmpeg_info,
            bitrate=self.config["bitrate"])
        if not parts:
            self.log.emit(tr("log_chapter_failed"))
            return False
        self.log.emit(tr("log_chapter_split", count=len(parts)))
        base, ext = os.path.splitext(data['dest_path'])
        dests = []
        for part in parts:
            out = self._post_process(
                part['path'], part['title'], data['uploader'],
                data['thumb'], None, pro)
            dest = get_unique_path(
                f"{base} [{part['index'] + 1:02d} "
                f"{clean_title(part['title'])}]{ext}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.rename(out, dest)
            part_base, part_ext = os.path.splitext(part['path'])
            for leftover in (part['path'], f"{part_base}_trim{part_ext}",
                             f"{part_base}_tmp{part_ext}",
                             f"{part_base}_trim_tmp{part_ext}"):
                if os.path.exists(leftover):
                    try:
                        os.remove(leftover)
                    except OSError:
                        pass
            dests.append(dest)
            self.log.emit(tr("log_complete", path=dest))
        if os.path.exists(data['temp_raw']):
            os.remove(data['temp_raw'])
        self.item_finished.emit(self.item, dests[0])
        return True

    def _handle_cancelled(self, data, temp_out):
        # ダウンロード後にキャンセルされた場合は中間ファイルを掃除する
        # （ダウンロード中の .part ファイルは対象外）
        candidates = set()
        if data:
            candidates.add(data.get('temp_raw'))
        if temp_out:
            candidates.add(temp_out)
        for path in candidates:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self.log.emit(tr("log_cancelled", url=self.item.url))
        self.item_cancelled.emit(self.item)


class FFmpegDownloadThread(QThread):
    progress = Signal(int, int)
    done = Signal(object)

    def run(self):
        path = download_ffmpeg(
            progress_callback=lambda d, t: self.progress.emit(d, t))
        self.done.emit(path)


def parse_version(text):
    """'Release-1.2.3' や 'v1.2.3' から (1, 2, 3) を取り出す。"""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def fetch_latest_release():
    """GitHub の最新リリース情報を dict で返す（失敗時は例外）。"""
    req = urllib.request.Request(
        UPDATE_API_URL,
        headers={"User-Agent": f"VibeDL/{APP_VERSION}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {"version": parse_version(data.get("tag_name", "")),
            "tag": data.get("tag_name", ""),
            "url": data.get("html_url", "")}


def parse_artist_title(title):
    """「アーティスト - 曲名」形式なら (アーティスト, 曲名) を返す。

    分離できない場合は (None, title) を返す。
    """
    for sep in (" - ", " – ", " — "):
        if sep in (title or ""):
            artist, song = title.split(sep, 1)
            artist, song = artist.strip(), song.strip()
            if artist and song:
                return artist, song
    return None, title


def classify_error(message):
    """エラーメッセージから対処法の TEXTS キーを選ぶ。"""
    text = message or ""
    low = text.lower()
    if "sign in" in low or "login required" in low or "cookies" in low:
        return "err_advice_login"
    if "private" in low:
        return "err_advice_private"
    if "age" in low or "年齢" in text:
        return "err_advice_age"
    if "unavailable" in low or "removed" in low or "deleted" in low:
        return "err_advice_unavailable"
    if "format is not available" in low or "requested format" in low:
        return "err_advice_format"
    if "403" in low:
        return "err_advice_403"
    if "timed out" in low or "timeout" in low or "connection" in low:
        return "err_advice_network"
    return "err_advice_generic"


def apply_rename_rules(name, rules_text):
    """ファイル名（拡張子なし）に正規表現ルールを上から順に適用する。"""
    result = name
    for line in (rules_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            pattern, repl = line.split("=>", 1)
            pattern, repl = pattern.strip(), repl.strip()
        else:
            pattern, repl = line, ""
        if not pattern:
            continue
        try:
            result = re.sub(pattern, repl, result)
        except re.error:
            continue
    result = re.sub(r'[\\/:*?"<>|]', "", result)
    return re.sub(r"\s+", " ", result).strip()


def renamed_path(path, rules_text):
    """ルール適用後の保存パスを返す（変わらなければ元のパス）。"""
    folder = os.path.dirname(path)
    base, ext = os.path.splitext(os.path.basename(path))
    new_base = apply_rename_rules(base, rules_text)
    if not new_base or new_base == base:
        return path
    return get_unique_path(os.path.join(folder, new_base + ext))


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text):
    """ANSIエスケープシーケンス（色付け等）を取り除く。"""
    return ANSI_RE.sub("", text or "")


def parse_speed_bytes(text):
    """yt-dlp の速度文字列（例: 1.23MiB/s）を bytes/sec に変換する。"""
    match = re.match(r"\s*([\d.]+)\s*([KMGT]?i?B)/s", strip_ansi(text))
    if not match:
        return None
    value = float(match.group(1))
    factors = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3,
               "TB": 1000 ** 4, "KiB": 1024, "MiB": 1024 ** 2,
               "GiB": 1024 ** 3, "TiB": 1024 ** 4}
    return value * factors.get(match.group(2), 1)


def render_template_preview(template):
    """ファイル名テンプレートをサンプル値で描画する（プレビュー用）。"""
    rendered = template or "{title}"
    for key, sample in (("{title}", "サンプル曲名"),
                        ("{uploader}", "サンプルアーティスト"),
                        ("{id}", "dQw4w9WgXcQ"),
                        ("{date}", "20261123")):
        rendered = rendered.replace(key, sample)
    return rendered


class SpeedGraph(QWidget):
    """直近のダウンロード速度を折れ線で描く小さなウィジェット。"""

    MAX_SAMPLES = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples = []
        self.setFixedHeight(34)

    def add_sample(self, bytes_per_sec):
        self._samples.append(bytes_per_sec)
        del self._samples[:-self.MAX_SAMPLES]
        self.update()

    def clear(self):
        self._samples = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        if len(self._samples) >= 2:
            peak = max(max(self._samples), 1024 * 1024)
            step = width / (self.MAX_SAMPLES - 1)
            points = []
            offset = self.MAX_SAMPLES - len(self._samples)
            for i, value in enumerate(self._samples):
                x = (offset + i) * step
                y = height - 3 - (value / peak) * (height - 8)
                points.append(QPointF(x, y))
            painter.setPen(QPen(QColor(ACCENT), 1.6))
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
        painter.end()


def find_new_entries(entries, seen_urls):
    """entries（新しい順）から未見のものを古い順に返す。"""
    seen = set(seen_urls)
    new = [e for e in entries if e.get("url") and e["url"] not in seen]
    return list(reversed(new))


class WatchWorker(QThread):
    """登録URLごとに最新エントリ（最大30件）を取得する。"""

    done = Signal(object)

    def __init__(self, urls, cookies_browser, cookies_file, parent=None):
        super().__init__(parent)
        self.urls = urls
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file

    def run(self):
        results = {}
        for url in self.urls:
            try:
                entries = get_playlist_entries(
                    url, self.cookies_browser, self.cookies_file)
            except Exception:
                continue
            results[url] = entries[:30]
        self.done.emit(results)


class StreamUrlWorker(QThread):
    """プレビュー再生用にストリームURLを解決する。"""

    got = Signal(object, str)
    failed = Signal(object)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item

    def run(self):
        try:
            import yt_dlp
            opts = {
                'quiet': True, 'no_warnings': True, 'skip_download': True,
                'format': 'bestaudio/best',
                'js_runtimes': JS_RUNTIMES,
                'remote_components': ['ejs:github'],
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.item.url, download=False)
            url = info.get('url') or ''
            if not url:
                audio_fmts = [f for f in info.get('formats') or []
                              if f.get('acodec') not in (None, 'none')
                              and f.get('url')]
                if audio_fmts:
                    url = audio_fmts[-1]['url']
            if url:
                self.got.emit(self.item, url)
            else:
                self.failed.emit(self.item)
        except Exception:
            self.failed.emit(self.item)


class ConvertWorker(QThread):
    """ローカルファイル一括変換（Pro）用ワーカー。"""

    log = Signal(str)
    done = Signal()

    def __init__(self, files, config, ffmpeg_info, parent=None):
        super().__init__(parent)
        self.files = files
        self.config = config
        self.ffmpeg_info = ffmpeg_info

    def run(self):
        fmt = self.config.get('output_format', 'mp3')
        bitrate = self.config.get('bitrate')
        for path in self.files:
            base, src_ext = os.path.splitext(path)
            dest = get_unique_path(f"{base}.{fmt}")
            ok = True
            if src_ext.lower() == f".{fmt}" and \
                    not self.config.get('normalize'):
                try:
                    shutil.copy2(path, dest)
                except OSError:
                    ok = False
            else:
                out = convert_audio(path, dest, self.ffmpeg_info, bitrate)
                if not out:
                    ok = False
                elif self.config.get('normalize'):
                    normalized = normalize_audio(
                        out, self.config.get('target_lufs', -14.0),
                        self.ffmpeg_info, bitrate,
                        self.config.get('loudnorm_tp', -2.0))
                    if normalized:
                        os.replace(normalized, out)
            if ok and self.config.get('embed_metadata'):
                try:
                    embed_metadata(dest, os.path.basename(base), '', None)
                except Exception:
                    pass
            if ok:
                self.log.emit(tr("convert_done_log",
                                 name=os.path.basename(dest)))
            else:
                self.log.emit(tr("convert_failed_log",
                                 name=os.path.basename(path)))
        self.done.emit()


class UpdateCheckThread(QThread):
    done = Signal(object, bool)
    failed = Signal(str, bool)

    def __init__(self, manual=False, parent=None):
        super().__init__(parent)
        self.manual = manual

    def run(self):
        try:
            self.done.emit(fetch_latest_release(), self.manual)
        except Exception as e:
            self.failed.emit(str(e), self.manual)


def format_duration(seconds):
    if not seconds:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class SearchWorker(QThread):
    results = Signal(list)
    failed = Signal(str)

    def __init__(self, keyword, parent=None):
        super().__init__(parent)
        self.keyword = keyword

    def run(self):
        try:
            self.results.emit(search_youtube(self.keyword))
        except Exception as e:
            self.failed.emit(str(e))


class InfoWorker(QThread):
    """キュー追加時に動画情報（タイトル・長さ・サムネイル）を取得する。"""
    got = Signal(object, dict)
    failed = Signal(object)

    def __init__(self, item, cookies_browser=None, cookies_file=None, parent=None):
        super().__init__(parent)
        self.item = item
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file

    def run(self):
        try:
            info = get_video_info(self.item.url, self.cookies_browser, self.cookies_file)
            self.got.emit(self.item, info)
        except Exception:
            self.failed.emit(self.item)


class ThumbWorker(QThread):
    """サムネイル画像をダウンロードする。"""
    got = Signal(object, bytes)

    def __init__(self, item, url, parent=None):
        super().__init__(parent)
        self.item = item
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(
                self.url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            if data:
                self.got.emit(self.item, data)
        except Exception:
            pass


class PlaylistWorker(QThread):
    """プレイリストを展開して収録動画の一覧を返す。"""
    got = Signal(list)
    failed = Signal(str)

    def __init__(self, url, cookies_browser=None, cookies_file=None, parent=None):
        super().__init__(parent)
        self.url = url
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file

    def run(self):
        try:
            self.got.emit(get_playlist_entries(self.url, self.cookies_browser, self.cookies_file))
        except Exception as e:
            self.failed.emit(str(e))


def make_card():
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    return card, layout


def section_label(text):
    label = QLabel(text)
    label.setObjectName("section")
    return label


class VibeDLFrame(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeDL - Audio Downloader")
        self.setWindowIcon(make_app_icon())
        self.resize(900, 680)
        self.setMinimumSize(780, 580)

        self.ffmpeg_info = get_ffmpeg_info()
        self.config = get_config()
        set_language(self.config.get("language", "ja"))
        self.queue = []
        self.active_workers = []
        self.max_workers = max(1, int(self.config.get("max_parallel", 2)))
        self.pro = _license_is_pro(self.config.get("license_key", ""))
        if self.pro:
            self.setWindowTitle("VibeDL - Audio Downloader Pro")
        self.last_dest_path = None
        self._batch_success = False
        self._batch_files = []
        self._queue_paused = False
        self._batch_total = 0
        self._batch_done = 0
        self._batch_start = None
        self._really_quit = False
        # 前回のウィンドウ位置・サイズを復元
        try:
            _w = int(self.config.get("window_w", 0))
            _h = int(self.config.get("window_h", 0))
            if _w > 0 and _h > 0:
                self.resize(_w, _h)
            _x = int(self.config.get("window_x", -1))
            _y = int(self.config.get("window_y", -1))
            if _x >= 0 and _y >= 0:
                self.move(_x, _y)
        except (TypeError, ValueError):
            pass
        self.download_history = load_download_history()
        self.watch_state = load_watch_state()
        self._bg_threads = set()
        self.setAcceptDrops(True)

        self._init_ui()
        self.apply_theme()
        try:
            QApplication.instance().styleHints().colorSchemeChanged.connect(
                lambda *_: self.apply_theme())
        except Exception:
            pass
        self.update_settings_display()
        self._restore_queue()
        self.update_queue_display()

        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.show()
        tray_menu = QMenu(self)
        tray_show = tray_menu.addAction(tr("tray_show"))
        tray_show.triggered.connect(self._show_from_tray)
        tray_quit = tray_menu.addAction(tr("tray_quit"))
        tray_quit.triggered.connect(self._quit_from_tray)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)

        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self.on_clipboard_timer)
        self.update_clipboard_monitor()

        QTimer.singleShot(100, self.check_ffmpeg_on_startup)
        if self.config.get("check_updates", True):
            QTimer.singleShot(1500, lambda: self.check_for_updates(False))
        self._schedule_fired_date = None
        self._schedule_timer = QTimer(self)
        self._schedule_timer.setInterval(20000)
        self._schedule_timer.timeout.connect(self._check_schedule)
        self._schedule_timer.start()
        self._watch_thread = None
        QTimer.singleShot(4000, self._check_watch)
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(30 * 60 * 1000)
        self._watch_timer.timeout.connect(self._check_watch)
        self._watch_timer.start()
        self._sleep_prevented = False
        self._preview_item = None
        self._preview_player = None
        self._preview_audio = None
        if QMediaPlayer is not None:
            self._preview_audio = QAudioOutput(self)
            self._preview_player = QMediaPlayer(self)
            self._preview_player.setAudioOutput(self._preview_audio)

    # ---------- UI構築 ----------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # サイドバー
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(14, 16, 14, 14)
        sb_layout.setSpacing(8)
        title = QLabel(f'<span style="color:{ACCENT}">Vibe</span>DL')
        title.setObjectName("appTitle")
        sb_layout.addWidget(title)
        subtitle = QLabel("YouTube Audio Downloader")
        subtitle.setObjectName("muted")
        sb_layout.addWidget(subtitle)
        sb_layout.addSpacing(14)
        self._nav_buttons = []
        for i, (icon, key) in enumerate([
                ("⬇", "section_download"), ("🕘", "history"),
                ("⚙", "settings")]):
            btn = QPushButton(f"{icon}  {tr(key)}")
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda _=False, idx=i: self._switch_page(idx))
            sb_layout.addWidget(btn)
            self._nav_buttons.append(btn)
        self._nav_buttons[0].setChecked(True)
        sb_layout.addStretch()
        self.sidebar_pro_btn = QPushButton(tr("buy_pro_short"))
        self.sidebar_pro_btn.setObjectName("primary")
        self.sidebar_pro_btn.clicked.connect(
            lambda: webbrowser.open(PRO_PURCHASE_URL))
        sb_layout.addWidget(self.sidebar_pro_btn)
        self.sidebar_pro_label = QLabel(tr("pro_active"))
        self.sidebar_pro_label.setObjectName("proBadge")
        sb_layout.addWidget(self.sidebar_pro_label)
        main_layout.addWidget(sidebar)

        # ページ側（ダウンロードページのレイアウトを root として構築する）
        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages, 1)
        download_page = QWidget()
        root = QVBoxLayout(download_page)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # カード1: 入力 + 操作
        card, card_layout = make_card()
        card_layout.addWidget(section_label(tr("section_download")))

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("YouTube URL:"))
        self.url_ctrl = QComboBox()
        self.url_ctrl.setEditable(True)
        self.url_ctrl.lineEdit().setPlaceholderText("https://www.youtube.com/...")
        self.url_ctrl.lineEdit().returnPressed.connect(self.on_add_to_queue)
        self._populate_url_history()
        url_row.addWidget(self.url_ctrl, 1)
        self.search_btn = QPushButton(tr("search"))
        self.search_btn.setToolTip(tr("search_tip"))
        self.search_btn.clicked.connect(self.on_search)
        url_row.addWidget(self.search_btn)
        card_layout.addLayout(url_row)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel(tr("start_label")))
        self.start_ctrl = QLineEdit()
        self.start_ctrl.setPlaceholderText("0:00")
        self.start_ctrl.setFixedWidth(110)
        time_row.addWidget(self.start_ctrl)
        time_row.addSpacing(16)
        time_row.addWidget(QLabel(tr("end_label")))
        self.end_ctrl = QLineEdit()
        self.end_ctrl.setPlaceholderText("3:00")
        self.end_ctrl.setFixedWidth(110)
        time_row.addWidget(self.end_ctrl)
        time_row.addStretch()
        card_layout.addLayout(time_row)

        btn_row = QHBoxLayout()
        self.add_queue_btn = QPushButton(tr("add_queue"))
        self.add_queue_btn.clicked.connect(self.on_add_to_queue)
        btn_row.addWidget(self.add_queue_btn)
        self.start_queue_btn = QPushButton(tr("start_queue"))
        self.start_queue_btn.setObjectName("primary")
        self.start_queue_btn.clicked.connect(self.on_start_queue)
        self.start_queue_btn.setEnabled(False)
        btn_row.addWidget(self.start_queue_btn)
        self.clear_queue_btn = QPushButton(tr("clear_queue"))
        self.clear_queue_btn.clicked.connect(self.on_clear_queue)
        btn_row.addWidget(self.clear_queue_btn)
        self.retry_failed_btn = QPushButton(tr("retry_failed"))
        self.retry_failed_btn.clicked.connect(self.on_retry_failed)
        self.retry_failed_btn.setEnabled(False)
        btn_row.addWidget(self.retry_failed_btn)
        self.cancel_btn = QPushButton(tr("cancel"))
        self.cancel_btn.setToolTip(tr("cancel_tip"))
        self.cancel_btn.clicked.connect(self.on_cancel_downloads)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.cancel_btn)
        self.pause_btn = QPushButton(tr("pause_btn"))
        self.pause_btn.clicked.connect(self.on_toggle_pause)
        btn_row.addWidget(self.pause_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        # ボタンが多いので2段目に分ける（狭い画面で見切れないように）
        btn_row2 = QHBoxLayout()
        self.import_btn = QPushButton(tr("import_btn"))
        self.import_btn.setToolTip(tr("import_tip"))
        self.import_btn.clicked.connect(self.on_import_file)
        btn_row2.addWidget(self.import_btn)
        self.export_queue_btn = QPushButton(tr("export_queue_btn"))
        self.export_queue_btn.clicked.connect(self.on_export_queue)
        btn_row2.addWidget(self.export_queue_btn)
        self.open_folder_btn = QPushButton(tr("open_folder"))
        self.open_folder_btn.setToolTip(tr("open_folder_tip"))
        self.open_folder_btn.clicked.connect(self.on_open_folder)
        self.open_folder_btn.setEnabled(False)
        btn_row2.addWidget(self.open_folder_btn)
        self.convert_btn = QPushButton(tr("convert_btn"))
        self.convert_btn.clicked.connect(self.on_convert_local)
        btn_row2.addWidget(self.convert_btn)
        self.play_btn = QPushButton(tr("play"))
        self.play_btn.setToolTip(tr("play_tip"))
        self.play_btn.clicked.connect(self.on_play_last)
        self.play_btn.setEnabled(False)
        btn_row2.addWidget(self.play_btn)
        btn_row2.addStretch()
        card_layout.addLayout(btn_row2)
        root.addWidget(card)

        # カード2: キュー + 進捗
        card2, card2_layout = make_card()
        card2_layout.addWidget(section_label(tr("section_queue")))
        self.queue_summary = QLabel("")
        self.queue_summary.setObjectName("muted")
        card2_layout.addWidget(self.queue_summary)
        self.queue_list = QListWidget()
        self.queue_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(
            self._on_queue_context_menu)
        self.queue_list.setIconSize(QSize(96, 54))
        # ドラッグで並べ替え可能にし、表示順を self.queue に同期する
        self.queue_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)
        self.queue_list.model().rowsMoved.connect(self._on_queue_rows_moved)
        self.queue_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.queue_list.setFixedHeight(110)
        card2_layout.addWidget(self.queue_list)
        self.queue_empty_label = QLabel(tr("queue_empty_hint"), self.queue_list)
        self.queue_empty_label.setAlignment(Qt.AlignCenter)
        self.queue_empty_label.setObjectName("muted")
        self.queue_empty_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        card2_layout.addWidget(self.progress)
        self.speed_graph = SpeedGraph()
        card2_layout.addWidget(self.speed_graph)
        self.status_label = QLabel("")
        self.status_label.setObjectName("muted")
        card2_layout.addWidget(self.status_label)
        root.addWidget(card2)

        # カード3: ログ
        card3, card3_layout = make_card()
        card3_layout.addWidget(section_label(tr("section_log")))
        self.log_ctrl = QPlainTextEdit()
        self.log_ctrl.setReadOnly(True)
        card3_layout.addWidget(self.log_ctrl)
        root.addWidget(card3, 1)

        # ショートカット: Ctrl+Enter でキュー開始、Delete で選択削除
        start_sc = QShortcut(QKeySequence("Ctrl+Return"), self)
        start_sc.activated.connect(self.on_start_queue)
        start_sc2 = QShortcut(QKeySequence("Ctrl+Enter"), self)
        start_sc2.activated.connect(self.on_start_queue)
        del_sc = QShortcut(QKeySequence("Delete"), self.queue_list)
        del_sc.setContext(Qt.WidgetShortcut)
        del_sc.activated.connect(self._remove_selected_items)

        status = self.statusBar()
        self.status_fmt = QLabel()
        self.status_norm = QLabel()
        self.status_meta = QLabel()
        status.addWidget(self.status_fmt, 2)
        status.addWidget(self.status_norm, 2)
        status.addWidget(self.status_meta, 1)
        self.status_overall = QLabel("")
        status.addWidget(self.status_overall, 2)

        # ページを組み立てる（履歴・設定）
        self.pages.addWidget(download_page)
        self.history_panel = HistoryPanel(self)
        self.pages.addWidget(self.history_panel)
        self.settings_panel = SettingsPanel(
            self, self.config,
            watch_urls=self.watch_state.get("urls", []))
        self.settings_panel.changed.connect(self._on_settings_panel_changed)
        self.settings_panel.update_check_requested.connect(
            lambda: self.check_for_updates(True))
        self.pages.addWidget(self.settings_panel)
        self._update_sidebar_pro()

    # ---------- テーマ・表示 ----------
    def apply_theme(self):
        mode = self.config.get("theme_mode") or (
            "dark" if self.config.get("dark_mode", False) else "light")
        if mode == "system":
            dark = False
            try:
                dark = (QApplication.instance().styleHints().colorScheme()
                        == Qt.ColorScheme.Dark)
            except Exception:
                pass
        else:
            dark = mode == "dark"
        QApplication.instance().setStyleSheet(build_stylesheet(dark))

    def update_settings_display(self):
        self.status_fmt.setText(
            tr("status_format", fmt=self.config['output_format'], br=self.config['bitrate']))
        self.status_norm.setText(
            tr("status_normalize", onoff='ON' if self.config['normalize'] else 'OFF', lufs=self.config['target_lufs']))
        self.status_meta.setText(
            tr("status_metadata", onoff='ON' if self.config['embed_metadata'] else 'OFF'))

    def log(self, msg):
        self.log_ctrl.appendPlainText(msg)

    def on_download_progress(self, percent, speed="", eta=""):
        self.progress.setValue(percent)
        speed_value = parse_speed_bytes(speed)
        if speed_value is not None:
            self.speed_graph.add_sample(speed_value)
        parts = []
        if speed:
            parts.append(tr("speed", speed=speed))
        if eta:
            parts.append(tr("eta", eta=eta))
        if parts:
            self.status_label.setText("  ".join(parts))
        self._update_overall_status(percent / 100.0)

    def set_status_label(self, text):
        self.status_label.setText(text)

    def notify_user(self, title, message):
        if self.config.get("notify_sound", True):
            winsound.MessageBeep(winsound.MB_OK)
        if self.config.get("notify_toast", True):
            self.tray.showMessage(title, message, make_app_icon(), 5000)

    # ---------- 履歴・クリップボード ----------
    def _populate_url_history(self):
        current = self.url_ctrl.currentText() if self.url_ctrl.count() else ""
        self.url_ctrl.clear()
        for url in self.config.get("url_history", []):
            self.url_ctrl.addItem(url)
        self.url_ctrl.setCurrentText(current)

    def add_to_history(self, url):
        history = self.config.get("url_history", [])
        if url in history:
            history.remove(url)
        history.insert(0, url)
        self.config["url_history"] = history[:10]
        self._populate_url_history()
        save_config(self.config)

    def update_clipboard_monitor(self):
        if self.config.get("clipboard_monitor", False):
            self.clipboard_timer.start(1000)
        else:
            self.clipboard_timer.stop()

    def on_clipboard_timer(self):
        text = QApplication.clipboard().text().strip()
        if ("youtube.com/watch" in text or "youtu.be/" in text) and text.startswith("http"):
            if text != self.url_ctrl.currentText().strip():
                self.url_ctrl.setCurrentText(text)
                self.log(tr("clipboard_pasted"))

    # ---------- 新着監視（Pro） ----------
    def _check_watch(self):
        if not self.pro:
            return
        urls = [u for u in self.watch_state.get("urls", []) if u]
        if not urls:
            return
        if self._watch_thread is not None and self._watch_thread.isRunning():
            return
        browser, cookie_file = self._cookie_args()
        self._watch_thread = WatchWorker(urls, browser, cookie_file, self)
        self._watch_thread.done.connect(self._on_watch_result)
        self._watch_thread.start()

    def _on_watch_result(self, results):
        seen_map = self.watch_state.setdefault("seen", {})
        added = 0
        for list_url, entries in results.items():
            entry_urls = [e.get("url", "") for e in entries if e.get("url")]
            if list_url not in seen_map:
                # 初回は既存分を既見として記録するだけ（追加しない）
                seen_map[list_url] = entry_urls[:300]
                continue
            for e in find_new_entries(entries, seen_map[list_url]):
                if self._add_item(e["url"], None, None,
                                  title=e.get("title"),
                                  duration=e.get("duration"),
                                  thumb_url=e.get("thumb")):
                    added += 1
            merged = entry_urls + [u for u in seen_map[list_url]
                                   if u not in entry_urls]
            seen_map[list_url] = merged[:300]
        save_watch_state(self.watch_state)
        if added:
            self.log(tr("watch_added_log", n=added))
            self.notify_user(tr("watch_notify_title"),
                             tr("watch_added_log", n=added))

    def _sync_watch_urls(self):
        urls = self.settings_panel.get_watch_urls()
        if urls == self.watch_state.get("urls", []):
            return
        self.watch_state["urls"] = urls
        seen = self.watch_state.setdefault("seen", {})
        for key in list(seen):
            if key not in urls:
                del seen[key]
        save_watch_state(self.watch_state)

    # ---------- 予約ダウンロード・Webhook通知 ----------
    def _check_schedule(self):
        if not self.config.get("schedule_enabled", False):
            return
        if self.active_workers:
            return
        if not any(i.status == "waiting" for i in self.queue):
            return
        now = datetime.now()
        if now.strftime("%H:%M") != \
                str(self.config.get("schedule_time", "")):
            return
        today = now.strftime("%Y-%m-%d")
        if self._schedule_fired_date == today:
            return
        self._schedule_fired_date = today
        self.log(tr("log_scheduled_start"))
        self.start_queue()

    def _send_webhook(self, text):
        url = str(self.config.get("webhook_url", "")).strip()
        if not url:
            return

        def _post():
            try:
                data = json.dumps({"content": text}).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/json",
                             "User-Agent": f"VibeDL/{APP_VERSION}"})
                urllib.request.urlopen(req, timeout=8).read()
            except Exception:
                pass

        threading.Thread(target=_post, daemon=True).start()

    def _write_batch_playlist(self):
        if not self.config.get("make_playlist", False):
            return
        files = [p for p in self._batch_files if os.path.exists(p)]
        if not files:
            return
        folder = self.config.get("output_folder", "")
        name = f"VibeDL_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m3u8"
        path = os.path.join(folder, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for dest in files:
                    title = os.path.splitext(os.path.basename(dest))[0]
                    f.write(f"#EXTINF:-1,{title}\n")
                    f.write(os.path.relpath(dest, folder) + "\n")
        except OSError:
            return
        self.log(tr("log_playlist_created", name=name))

    def _notify_batch_webhook(self):
        if not self._batch_success:
            return
        if self._batch_done > 1:
            self._send_webhook(tr("webhook_msg_multi", n=self._batch_done))
        elif self.last_dest_path:
            self._send_webhook(tr(
                "webhook_msg",
                name=os.path.basename(self.last_dest_path)))

    # ---------- アップデート確認 ----------
    def check_for_updates(self, manual=False):
        if getattr(self, "_update_thread", None) is not None \
                and self._update_thread.isRunning():
            if manual:
                # 実行中の自動チェックを手動扱いに昇格させる
                self._update_thread.manual = True
            return
        self._update_thread = UpdateCheckThread(manual, self)
        self._update_thread.done.connect(self._on_update_checked)
        self._update_thread.failed.connect(self._on_update_check_failed)
        self._update_thread.start()

    def _on_update_checked(self, info, manual=False):
        latest = info.get("version")
        if latest is None:
            # タグからバージョンを読めなかったら「最新」とは言わず失敗扱い
            if manual:
                QMessageBox.warning(self, tr("update_available_title"),
                                    tr("update_failed_msg"))
            return
        current = parse_version(APP_VERSION)
        if current and latest > current:
            answer = QMessageBox.question(
                self, tr("update_available_title"),
                tr("update_available_msg", tag=info.get("tag", ""),
                   current=APP_VERSION))
            if answer == QMessageBox.Yes and info.get("url"):
                webbrowser.open(info["url"])
        elif manual:
            QMessageBox.information(
                self, tr("update_available_title"),
                tr("update_latest_msg", current=APP_VERSION))

    def _on_update_check_failed(self, message, manual=False):
        if manual:
            QMessageBox.warning(self, tr("update_available_title"),
                                  tr("update_failed_msg"))
        else:
            self.log(tr("update_failed_msg"))

    # ---------- FFmpeg ----------
    def check_ffmpeg_on_startup(self):
        if check_ffmpeg(self.ffmpeg_info['path']):
            return
        answer = QMessageBox.question(
            self, tr("ffmpeg_not_found_title"),
            tr("ffmpeg_not_found_msg"))
        if answer != QMessageBox.Yes:
            self.log(tr("ffmpeg_without"))
            return
        self.log(tr("ffmpeg_downloading"))
        dialog = QProgressDialog(tr("ffmpeg_dialog"), None, 0, 100, self)
        dialog.setWindowTitle(tr("ffmpeg_dialog_title"))
        dialog.setCancelButton(None)
        dialog.setModal(True)
        thread = FFmpegDownloadThread(self)

        def on_progress(done, total):
            dialog.setValue(int(done / total * 100) if total else 0)
            dialog.setLabelText(f"{done}/{total} bytes")

        def on_done(path):
            dialog.accept()
            if path:
                self.ffmpeg_info = get_ffmpeg_info()
                self.log(tr("ffmpeg_ready"))
            else:
                self.log(tr("ffmpeg_failed"))

        thread.progress.connect(on_progress)
        thread.done.connect(on_done)
        thread.start()
        dialog.exec()
        thread.wait()

    # ---------- キュー処理 ----------
    def _current_time_range(self):
        """開始・終了欄を検証して (start, end) を返す。不正なら警告して None。"""
        try:
            start_sec = parse_time(self.start_ctrl.text())
            end_sec = parse_time(self.end_ctrl.text())
        except ValueError:
            QMessageBox.warning(
                self, tr("input_error"),
                tr("time_format_msg"))
            return None
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            QMessageBox.warning(self, tr("input_error"), tr("end_after_start_msg"))
            return None
        return (start_sec, end_sec)

    # ---------- キュー追加（共通） ----------
    def _cookie_args(self):
        return (self.config.get("cookies_browser") or None,
                self.config.get("cookies_file") or None)

    @staticmethod
    def _is_playlist_url(url):
        return "list=" in url or "youtube.com/playlist" in url

    def _keep_thread(self, thread):
        self._bg_threads.add(thread)
        thread.finished.connect(lambda: self._bg_threads.discard(thread))

    @staticmethod
    def _video_key(url):
        """URL表記の違いを吸収するため、動画IDが取れればそれを比較キーにする。"""
        m = re.search(r'(?:v=|youtu\.be/|/shorts/|/live/)([\w-]{11})',
                      url or '')
        return m.group(1) if m else (url or '')

    def _add_item(self, url, start_sec, end_sec, title=None, duration=None,
                  thumb_url=None, fetch_info=True):
        if self.config.get("skip_duplicates"):
            key = self._video_key(url)
            known = {self._video_key(e.get('url', ''))
                     for e in self.download_history}
            known |= {self._video_key(i.url) for i in self.queue}
            if key in known:
                self.log(tr("log_duplicate_skipped", name=title or url))
                return None
        item = QueueItem(url, start_sec, end_sec)
        item.title = title
        item.duration = duration
        item.thumb_url = thumb_url
        self.queue.append(item)
        self._save_queue()
        self.add_to_history(url)
        self.update_queue_display()
        self.log(tr("added_to_queue", name=title or url))
        if thumb_url:
            self._fetch_thumb(item)
        elif fetch_info:
            browser, cookie_file = self._cookie_args()
            worker = InfoWorker(item, browser, cookie_file, self)
            worker.got.connect(self._on_info_got)
            self._keep_thread(worker)
            worker.start()
        return item

    def _fetch_thumb(self, item):
        worker = ThumbWorker(item, item.thumb_url, self)
        worker.got.connect(self._on_thumb_got)
        self._keep_thread(worker)
        worker.start()

    def _on_info_got(self, item, info):
        if item not in self.queue:
            return
        item.title = info.get('title')
        item.duration = info.get('duration')
        item.thumb_url = info.get('thumb')
        self.update_queue_display()
        if item.thumb_url:
            self._fetch_thumb(item)

    def _on_thumb_got(self, item, data):
        if item not in self.queue:
            return
        item.thumb_data = data
        self.update_queue_display()

    def _dispatch_add(self, url, start_sec, end_sec):
        """プレイリストURLなら展開し、それ以外はそのままキューへ追加する。"""
        if self._is_playlist_url(url):
            self.log(tr("playlist_expanding"))
            browser, cookie_file = self._cookie_args()
            worker = PlaylistWorker(url, browser, cookie_file, self)

            def _got(entries, s=start_sec, e=end_sec):
                if not entries:
                    self.log(tr("playlist_empty"))
                    return
                for entry in entries:
                    self._add_item(entry['url'], s, e, title=entry['title'],
                                   duration=entry['duration'],
                                   thumb_url=entry.get('thumb'),
                                   fetch_info=False)
                self.log(tr("playlist_added", n=len(entries)))

            worker.got.connect(_got)
            worker.failed.connect(
                lambda msg: self.log(tr("playlist_failed", msg=msg)))
            self._keep_thread(worker)
            worker.start()
        else:
            self._add_item(url, start_sec, end_sec)

    def on_search(self):
        dlg = SearchDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        selected = dlg.selected_items()
        if not selected:
            return
        time_range = self._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        for entry in selected:
            self._add_item(entry['url'], start_sec, end_sec,
                           title=entry['title'], duration=entry['duration'],
                           thumb_url=entry.get('thumb'), fetch_info=False)

    def on_add_to_queue(self):
        url = self.url_ctrl.currentText().strip()
        if not url:
            QMessageBox.warning(self, tr("input_error"), tr("url_required"))
            return
        time_range = self._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        self._dispatch_add(url, start_sec, end_sec)
        self.url_ctrl.setCurrentText("")
        self.start_ctrl.clear()
        self.end_ctrl.clear()

    def update_queue_display(self):
        self.queue_list.clear()
        icons = {"waiting": "⏳", "downloading": "⬇️", "done": "✅",
                 "failed": "❌"}
        for item in self.queue:
            label = item.title or item.url
            if item.duration:
                label += f"  ({format_duration(item.duration)})"
            list_item = QListWidgetItem(f"{icons.get(item.status, '')} {label}")
            list_item.setData(Qt.UserRole, item)
            if item.thumb_data:
                pixmap = QPixmap()
                if pixmap.loadFromData(item.thumb_data):
                    list_item.setIcon(QIcon(pixmap.scaled(
                        96, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.queue_list.addItem(list_item)
        has_waiting = any(item.status == "waiting" for item in self.queue)
        self.start_queue_btn.setEnabled(has_waiting)
        self.retry_failed_btn.setEnabled(
            any(item.status == "failed" for item in self.queue))
        if hasattr(self, "queue_summary"):
            total_dur = sum(i.duration or 0 for i in self.queue)
            self.queue_summary.setText(tr(
                "queue_summary", n=len(self.queue),
                dur=format_duration(total_dur) if total_dur else "--:--"))
        if hasattr(self, "queue_empty_label"):
            empty = not self.queue
            self.queue_empty_label.setVisible(empty)
            if empty:
                self.queue_empty_label.setGeometry(self.queue_list.rect())
                self.queue_empty_label.raise_()

    def _on_queue_rows_moved(self, *args):
        """ドラッグ並べ替え後の表示順を self.queue に反映する。"""
        new_order = []
        for i in range(self.queue_list.count()):
            obj = self.queue_list.item(i).data(Qt.UserRole)
            if obj is not None:
                new_order.append(obj)
        if len(new_order) == len(self.queue):
            self.queue = new_order
            self._save_queue()

    # ---------- キューの保存・復元 / 右クリックメニュー ----------
    def _save_queue(self):
        entries = [{
            'url': i.url, 'title': i.title, 'duration': i.duration,
            'thumb_url': i.thumb_url,
            'start_sec': i.start_sec, 'end_sec': i.end_sec,
            'status': 'failed' if i.status == 'failed' else 'waiting',
            'retry_count': i.retry_count,
            'error': i.error,
        } for i in self.queue]
        try:
            save_queue_items(entries)
        except OSError:
            pass

    def _restore_queue(self):
        try:
            entries = load_queue_items()
        except OSError:
            entries = []
        restored = 0
        for e in entries:
            if not e.get('url'):
                continue
            item = QueueItem(e['url'], e.get('start_sec'), e.get('end_sec'))
            item.title = e.get('title')
            item.duration = e.get('duration')
            item.thumb_url = e.get('thumb_url')
            item.status = ('failed' if e.get('status') == 'failed'
                           else 'waiting')
            item.retry_count = int(e.get('retry_count', 0))
            item.error = e.get('error', '') or ''
            self.queue.append(item)
            restored += 1
            if item.thumb_url:
                self._fetch_thumb(item)
        if restored:
            self.update_queue_display()
            self.log(tr("log_queue_restored", n=restored))

    def _on_queue_context_menu(self, pos):
        list_item = self.queue_list.itemAt(pos)
        if list_item is None:
            return
        item = list_item.data(Qt.UserRole)
        if item is None:
            return
        menu = QMenu(self)
        if self._preview_item is item and self._preview_player is not None \
                and self._preview_player.playbackState() == \
                QMediaPlayer.PlaybackState.PlayingState:
            act_preview = menu.addAction(tr("preview_stop"))
        else:
            act_preview = menu.addAction(tr("preview_play"))
        act_copy = menu.addAction(tr("ctx_copy_url"))
        act_open = menu.addAction(tr("ctx_open_browser"))
        act_retry = None
        act_error = None
        if item.status == "failed":
            act_retry = menu.addAction(tr("ctx_retry"))
            act_error = menu.addAction(tr("ctx_error_detail"))
        act_priority = None
        if item.status == "waiting":
            act_priority = menu.addAction(tr("ctx_priority"))
        act_remove = None
        if item.status in ("waiting", "failed"):
            act_remove = menu.addAction(tr("ctx_remove"))
        act_remove_sel = None
        selected = [lw.data(Qt.UserRole)
                    for lw in self.queue_list.selectedItems()]
        if len(selected) >= 2 and any(
                i is not None and i.status in ("waiting", "failed")
                for i in selected):
            act_remove_sel = menu.addAction(tr("ctx_remove_selected"))
        action = menu.exec(self.queue_list.mapToGlobal(pos))
        if action == act_preview:
            self.toggle_preview(item)
        elif act_error is not None and action == act_error:
            self._show_error_detail(item)
        elif act_priority is not None and action == act_priority:
            self.queue.remove(item)
            first_waiting = next(
                (idx for idx, i in enumerate(self.queue)
                 if i.status == "waiting"), len(self.queue))
            self.queue.insert(first_waiting, item)
            self._save_queue()
            self.update_queue_display()
            self.start_queue()
        elif action == act_copy:
            QApplication.clipboard().setText(item.url)
        elif action == act_open:
            webbrowser.open(item.url)
        elif act_retry is not None and action == act_retry:
            item.status = "waiting"
            item.retry_count = 0
            self._save_queue()
            self.update_queue_display()
            self.start_queue()
        elif act_remove is not None and action == act_remove:
            self.queue.remove(item)
            self._save_queue()
            self.update_queue_display()
        elif act_remove_sel is not None and action == act_remove_sel:
            self._remove_selected_items()

    # ---------- ミラー出力・ローカル変換（Pro） ----------
    def _mirror_file(self, dest_path):
        folder = str(self.config.get("mirror_folder", "")).strip()
        if not self.pro or not folder:
            return

        def _copy():
            try:
                os.makedirs(folder, exist_ok=True)
                target = os.path.join(folder, os.path.basename(dest_path))
                if os.path.abspath(target) != os.path.abspath(dest_path):
                    shutil.copy2(dest_path, target)
            except Exception:
                pass

        threading.Thread(target=_copy, daemon=True).start()

    def on_convert_local(self):
        if not self.pro:
            QMessageBox.information(self, "VibeDL", tr("convert_pro_only"))
            return
        LocalConvertDialog(self).exec()

    def _show_error_detail(self, item):
        box = QMessageBox(self)
        box.setWindowTitle(tr("ctx_error_detail"))
        box.setText(tr(classify_error(item.error)))
        if item.error:
            box.setDetailedText(item.error)
        box.exec()

    # ---------- プレビュー再生 ----------
    def toggle_preview(self, item):
        if self._preview_player is None:
            QMessageBox.information(self, "VibeDL",
                                    tr("preview_unavailable"))
            return
        if self._preview_item is item and \
                self._preview_player.playbackState() == \
                QMediaPlayer.PlaybackState.PlayingState:
            self._preview_player.stop()
            self._preview_item = None
            return
        worker = StreamUrlWorker(item, self)
        worker.got.connect(self._on_preview_url)
        worker.failed.connect(
            lambda _item: QMessageBox.information(
                self, "VibeDL", tr("preview_unavailable")))
        self._keep_thread(worker)
        worker.start()

    def _on_preview_url(self, item, url):
        if self._preview_player is None:
            return
        self._preview_item = item
        self._preview_player.setSource(QUrl(url))
        self._preview_player.play()

    def _stop_preview(self):
        if self._preview_player is not None:
            self._preview_player.stop()
        self._preview_item = None

    def _remove_selected_items(self):
        selected = [lw.data(Qt.UserRole)
                    for lw in self.queue_list.selectedItems()]
        targets = [i for i in selected
                   if i is not None and i.status in ("waiting", "failed")]
        if not targets:
            return
        for i in targets:
            self.queue.remove(i)
        self._save_queue()
        self.update_queue_display()

    def on_start_queue(self):
        if not self.queue:
            QMessageBox.information(self, tr("info_title"), tr("queue_empty"))
            return
        if not self._check_disk_space():
            return
        self.start_queue()

    def _estimate_needed_bytes(self):
        total_dur = sum(i.duration or 0 for i in self.queue
                        if i.status == "waiting")
        try:
            kbps = int(str(self.config.get("bitrate", "256k"))
                       .rstrip("kK"))
        except ValueError:
            kbps = 256
        if total_dur:
            return int(total_dur * kbps * 1000 / 8 * 1.2)
        return 200 * 1024 * 1024

    def _check_disk_space(self):
        folder = self.config.get("output_folder", "")
        if not folder or not os.path.isdir(folder):
            return True
        try:
            free = shutil.disk_usage(folder).free
        except OSError:
            return True
        need = self._estimate_needed_bytes()
        if free >= need:
            return True
        answer = QMessageBox.question(
            self, tr("disk_warn_title"),
            tr("disk_warn_msg", free=free // (1024 * 1024),
               need=need // (1024 * 1024)))
        return answer == QMessageBox.Yes

    def _set_sleep_prevention(self, active):
        if not self.config.get("prevent_sleep", False):
            active = False
        if self._sleep_prevented == active:
            return
        self._sleep_prevented = active
        try:
            if active:
                ctypes.windll.kernel32.SetThreadExecutionState(
                    0x80000000 | 0x00000001)  # ES_CONTINUOUS | SYSTEM_REQUIRED
            else:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass

    def on_toggle_pause(self):
        self._queue_paused = not self._queue_paused
        self.pause_btn.setText(
            tr("resume_btn") if self._queue_paused else tr("pause_btn"))
        if self._queue_paused:
            self.status_label.setText(tr("status_paused"))
        else:
            self.start_queue()

    def start_queue(self):
        if self._queue_paused:
            return
        # 実行中のワーカーがある場合は進捗表示をリセットしない（設定変更で
        # 空き枠を埋める場合など、途中での呼び出しに備える）
        if not self.active_workers and any(item.status == "waiting" for item in self.queue):
            self.progress.setValue(0)
            self.status_label.setText("")
            self._batch_total = sum(
                1 for i in self.queue
                if i.status in ("waiting", "downloading"))
            self._batch_done = 0
            self._batch_success = False
            self._batch_files = []
            self._batch_start = time.monotonic()
            self._update_overall_status()
        # 同時数の実効上限: Pro でなければ 2 まで
        limit = self.max_workers if self.pro else min(self.max_workers, 2)
        while len(self.active_workers) < limit:
            waiting = [i for i in self.queue if i.status == "waiting"]
            if not waiting:
                break
            item = waiting[0]
            item.status = "downloading"
            worker = DownloadWorker(item, self.config, self.ffmpeg_info, self)
            worker.log.connect(self.log)
            worker.progress.connect(self.on_download_progress)
            worker.phase.connect(self.set_status_label)
            worker.item_finished.connect(self.on_item_completed)
            worker.item_cancelled.connect(self.on_item_cancelled)
            self.active_workers.append(worker)
            self.cancel_btn.setEnabled(True)
            self.update_queue_display()
            worker.start()
        self._set_sleep_prevention(bool(self.active_workers))

    def on_cancel_downloads(self):
        if not self.active_workers:
            return
        for worker in list(self.active_workers):
            worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.log(tr("cancel_requested"))

    def on_item_cancelled(self, item):
        if item in self.queue:
            self.queue.remove(item)
        self._save_queue()
        sender = self.sender()
        if sender in self.active_workers:
            self.active_workers.remove(sender)
        self.update_queue_display()
        if any(i.status == "waiting" for i in self.queue):
            self.start_queue()
        elif not self.active_workers:
            self.cancel_btn.setEnabled(False)
            self.status_label.setText(tr("status_cancelled"))
            self.status_overall.setText("")
            self._batch_start = None

    def on_item_completed(self, item, dest_path):
        if item in self.queue:
            if dest_path:
                item.status = "done"
                self.last_dest_path = dest_path
                self.open_folder_btn.setEnabled(True)
                self.play_btn.setEnabled(True)
                self._record_download_history(item, dest_path)
                self._batch_files.append(dest_path)
                self._mirror_file(dest_path)
                self.notify_user(tr("notify_complete"), os.path.basename(dest_path))
                self.queue.remove(item)
                self._batch_success = True
                self._batch_done += 1
            else:
                # 自動リトライの上限内なら待ちに戻し、上限を超えたら
                # 失敗としてキューに残す（手動の再試行ボタンで再開できる）
                max_retry = int(self.config.get("auto_retry", 0))
                if item.retry_count < max_retry:
                    item.retry_count += 1
                    item.status = "waiting"
                    self.log(tr("log_auto_retry",
                                name=item.title or item.url,
                                n=item.retry_count, max=max_retry))
                else:
                    item.status = "failed"
                    self._batch_done += 1
        self._save_queue()
        sender = self.sender()
        if sender in self.active_workers:
            self.active_workers.remove(sender)
        self.update_queue_display()
        self._update_overall_status()
        self._set_sleep_prevention(bool(self.active_workers))
        if any(i.status == "waiting" for i in self.queue):
            self.start_queue()
        elif not self.active_workers:
            self.cancel_btn.setEnabled(False)
            self.progress.setValue(100)
            self.status_overall.setText("")
            self._batch_start = None
            failed_n = sum(1 for i in self.queue if i.status == "failed")
            if failed_n:
                self.status_label.setText(
                    tr("status_done_with_failed", n=failed_n))
            else:
                self.status_label.setText(tr("status_done"))
                self._write_batch_playlist()
                self._notify_batch_webhook()
                self._run_after_finish_action()

    def on_retry_failed(self):
        failed = [i for i in self.queue if i.status == "failed"]
        if not failed:
            return
        for item in failed:
            item.status = "waiting"
            item.retry_count = 0
        self._save_queue()
        self.log(tr("log_retry_failed", n=len(failed)))
        self.update_queue_display()
        self.start_queue()

    def _run_after_finish_action(self):
        action = self.config.get("after_finish", "")
        if action not in ("sleep", "shutdown") or not self._batch_success:
            return
        self._batch_success = False
        self.log(tr("log_after_finish",
                    action=tr("after_finish_" + action)))
        try:
            if action == "sleep":
                subprocess.run(
                    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                    check=False)
            else:
                subprocess.run(["shutdown", "/s", "/t", "30"], check=False)
        except OSError as e:
            self.log(tr("log_after_finish_failed", err=e))

    def on_clear_queue(self):
        self.queue = [i for i in self.queue
                      if i.status not in ("waiting", "failed")]
        self._save_queue()
        self.update_queue_display()
        self.log(tr("queue_cleared"))

    # ---------- ドラッグ＆ドロップ / インポート ----------
    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        handled = False
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".txt"):
                try:
                    with open(url.toLocalFile(), encoding="utf-8", errors="replace") as f:
                        self._import_text(f.read())
                    handled = True
                except OSError as e:
                    self.log(tr("file_read_failed", err=e))
        if not handled and mime.hasText():
            self._import_text(mime.text())
        event.acceptProposedAction()

    def on_export_queue(self):
        targets = [i for i in self.queue
                   if i.status in ("waiting", "failed")]
        if not targets:
            QMessageBox.information(self, tr("info_title"),
                                    tr("queue_empty"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_queue_btn"), "vibedl_queue.txt",
            tr("filter_text"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for i in targets:
                    if i.title:
                        f.write(f"# {i.title}\n")
                    f.write(f"{i.url}\n")
        except OSError as e:
            QMessageBox.warning(self, tr("error_title"),
                                tr("file_unreadable", err=e))
            return
        self.log(tr("export_queue_done", n=len(targets)))

    def on_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("import_dialog_title"), "", tr("filter_text"))
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                self._import_text(f.read())
        except OSError as e:
            QMessageBox.warning(self, tr("error_title"), tr("file_unreadable", err=e))

    def _import_text(self, text):
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.search(r"https?://[^\s]+", line)
            if match:
                urls.append(match.group(0))
        if not urls:
            self.log(tr("no_urls"))
            return
        time_range = self._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        for url in urls:
            self._dispatch_add(url, start_sec, end_sec)
        self.log(tr("urls_loaded", n=len(urls)))

    # ---------- 再生 / 履歴 ----------
    def on_play_last(self):
        if self.last_dest_path and os.path.exists(self.last_dest_path):
            os.startfile(self.last_dest_path)

    def _record_download_history(self, item, dest_path):
        entry = {
            'title': item.title or os.path.basename(dest_path),
            'url': item.url,
            'path': dest_path,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.download_history.insert(0, entry)
        self.download_history = self.download_history[:50]
        save_download_history(self.download_history)

    # ---------- その他 ----------
    def on_open_folder(self):
        if self.last_dest_path:
            os.startfile(os.path.dirname(self.last_dest_path))

    def on_settings(self):
        self._switch_page(2)

    def _switch_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        if index == 1:
            self.history_panel.refresh(self.download_history)

    def _update_sidebar_pro(self):
        if hasattr(self, "sidebar_pro_btn"):
            self.sidebar_pro_btn.setVisible(not self.pro)
            self.sidebar_pro_label.setVisible(self.pro)

    def _on_settings_panel_changed(self):
        self.config = self.settings_panel.get_config()
        save_config(self.config)
        self.max_workers = max(1, int(self.config.get("max_parallel", 2)))
        self.pro = _license_is_pro(self.config.get("license_key", ""))
        self.setWindowTitle("VibeDL - Audio Downloader"
                            + (" Pro" if self.pro else ""))
        # 実行中に上限を上げたら空き枠をすぐ埋める
        if self.active_workers:
            self.start_queue()
        self.apply_theme()
        self.update_settings_display()
        self.update_clipboard_monitor()
        self._update_sidebar_pro()
        self._sync_watch_urls()

    # ---------- トレイ・全体進捗 ----------
    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self):
        self._really_quit = True
        self.close()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self._show_from_tray()

    def _update_overall_status(self, frac=0.0):
        if self._batch_start is None or self._batch_total <= 0:
            return
        overall = (self._batch_done + max(0.0, min(1.0, frac))) \
            / self._batch_total
        pct = int(overall * 100)
        if 0 < overall < 1:
            elapsed = time.monotonic() - self._batch_start
            eta = elapsed / overall - elapsed
            self.status_overall.setText(tr(
                "status_overall_eta", pct=pct, eta=format_duration(eta)))
        else:
            self.status_overall.setText(tr("status_overall", pct=pct))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 空キュー案内ラベルの大きさをリストに合わせ直す（起動直後や
        # リサイズ時に幅がずれて左寄せに見えるのを防ぐ）
        if hasattr(self, "queue_empty_label"):
            self.queue_empty_label.setGeometry(self.queue_list.rect())

    def closeEvent(self, event):
        self._stop_preview()
        # ウィンドウ位置・サイズを保存
        self.config["window_x"] = self.x()
        self.config["window_y"] = self.y()
        self.config["window_w"] = self.width()
        self.config["window_h"] = self.height()
        save_config(self.config)
        if self.config.get("minimize_to_tray", False) \
                and not self._really_quit:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "VibeDL", tr("tray_minimized"), make_app_icon(), 3000)
            return
        # 実行中のアップデート確認スレッドは、ウィンドウ破棄前に
        # 終わるのを待つ（取得タイムアウト6秒＋余裕）
        if getattr(self, "_update_thread", None) is not None \
                and self._update_thread.isRunning():
            self._update_thread.wait(8000)
        super().closeEvent(event)


class SearchDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("search_title"))
        self.resize(660, 480)
        self._thread = None

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.keyword_ctrl = QLineEdit()
        self.keyword_ctrl.setPlaceholderText(tr("keyword_placeholder"))
        self.keyword_ctrl.returnPressed.connect(self.on_search)
        row.addWidget(self.keyword_ctrl, 1)
        self.search_btn = QPushButton(tr("search"))
        self.search_btn.clicked.connect(self.on_search)
        row.addWidget(self.search_btn)
        layout.addLayout(row)

        self.status_label = QLabel(tr("search_status_initial"))
        self.status_label.setObjectName("muted")
        layout.addWidget(self.status_label)

        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.results_list.itemDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.results_list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        add_btn = QPushButton(tr("add_selected"))
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.on_add_selected)
        btn_row.addWidget(add_btn)
        close_btn = QPushButton(tr("close"))
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.keyword_ctrl.setFocus()

    def on_search(self):
        keyword = self.keyword_ctrl.text().strip()
        if not keyword:
            return
        self.search_btn.setEnabled(False)
        self.status_label.setText(tr("searching"))
        self.results_list.clear()
        self._thread = SearchWorker(keyword, self)
        self._thread.results.connect(self.on_results)
        self._thread.failed.connect(self.on_failed)
        self._thread.start()

    def _downloaded_keys(self):
        frame = self.parent()
        keys = set()
        if frame is not None and hasattr(frame, "download_history"):
            for e in frame.download_history:
                key = frame._video_key(e.get("url", ""))
                if key:
                    keys.add(key)
        return keys

    def on_results(self, results):
        self.search_btn.setEnabled(True)
        downloaded = self._downloaded_keys()
        for r in results:
            text = r['title']
            if self.parent() is not None and \
                    self.parent()._video_key(r.get("url", "")) in downloaded:
                text += f"  ✓ {tr('downloaded_suffix')}"
            if r['uploader']:
                text += f"  ―  {r['uploader']}"
            text += f"  ({format_duration(r['duration'])})"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, r)
            self.results_list.addItem(item)
        if results:
            self.status_label.setText(tr("results_found", n=len(results)))
        else:
            self.status_label.setText(tr("no_results"))

    def on_failed(self, message):
        self.search_btn.setEnabled(True)
        self.status_label.setText(tr("search_failed", msg=message))

    def selected_items(self):
        return [item.data(Qt.UserRole) for item in self.results_list.selectedItems()]

    def on_add_selected(self):
        if not self.selected_items():
            QMessageBox.information(self, tr("info_title"), tr("select_result"))
            return
        self.accept()

    def on_double_click(self, item):
        self.results_list.clearSelection()
        item.setSelected(True)
        self.accept()


class HistoryPanel(QWidget):
    """ダウンロード履歴ページ（旧 HistoryDialog のページ版）。"""

    def __init__(self, frame):
        super().__init__(frame)
        self.frame = frame
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.search_ctrl = QLineEdit()
        self.search_ctrl.setPlaceholderText(tr("history_search_ph"))
        self.search_ctrl.textChanged.connect(self._filter_history)
        layout.addWidget(self.search_ctrl)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.list_widget, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        bulk_redl_btn = QPushButton(tr("history_bulk_redownload"))
        bulk_redl_btn.clicked.connect(self.on_bulk_redownload)
        btn_row.addWidget(bulk_redl_btn)
        bulk_del_btn = QPushButton(tr("history_bulk_delete"))
        bulk_del_btn.clicked.connect(self.on_bulk_delete)
        btn_row.addWidget(bulk_del_btn)
        export_btn = QPushButton(tr("export_csv_btn"))
        export_btn.clicked.connect(self.on_export_csv)
        btn_row.addWidget(export_btn)
        tag_btn = QPushButton(tr("tag_edit_btn"))
        tag_btn.clicked.connect(self.on_tag_edit)
        btn_row.addWidget(tag_btn)
        play_btn = QPushButton(tr("play2"))
        play_btn.clicked.connect(self.on_play)
        btn_row.addWidget(play_btn)
        redl_btn = QPushButton(tr("redownload"))
        redl_btn.clicked.connect(self.on_redownload)
        btn_row.addWidget(redl_btn)
        layout.addLayout(btn_row)

    def refresh(self, entries):
        self.list_widget.clear()
        for entry in entries:
            text = f"{entry.get('title', '')}  ―  {entry.get('date', '')}"
            if not os.path.exists(entry.get('path', '')):
                text += tr("missing_file_suffix")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry)
            self.list_widget.addItem(item)
        if not entries:
            self.list_widget.addItem(tr("history_empty"))
        self._filter_history(self.search_ctrl.text())

    def _filter_history(self, text):
        needle = (text or "").lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            entry = item.data(Qt.UserRole)
            if not isinstance(entry, dict):
                continue
            haystack = ((entry.get('title', '') or '') + ' '
                        + (entry.get('url', '') or '')).lower()
            item.setHidden(needle not in haystack)

    def _selected_entry(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def on_tag_edit(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        entry = item.data(Qt.UserRole)
        if not entry:
            return
        path = entry.get("path", "")
        if not path or not os.path.exists(path):
            return
        tags = read_tags(path)
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("tag_title"))
        form = QVBoxLayout(dialog)
        title_edit = QLineEdit(tags.get("title") or entry.get("title", ""))
        artist_edit = QLineEdit(tags.get("artist", ""))
        album_edit = QLineEdit(tags.get("album", ""))
        for label, edit in ((tr("tag_title_label"), title_edit),
                            (tr("tag_artist_label"), artist_edit),
                            (tr("tag_album_label"), album_edit)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(edit, 1)
            form.addLayout(row)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("primary")
        ok_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(cancel_btn)
        form.addLayout(btn_row)
        if dialog.exec() != QDialog.Accepted:
            return
        if update_tags(path, title_edit.text(), artist_edit.text(),
                       album_edit.text()):
            entry["title"] = title_edit.text()
            save_download_history(self.frame.download_history)
            self.refresh(self.frame.download_history)
            QMessageBox.information(self, "VibeDL", tr("tag_saved"))
        else:
            QMessageBox.warning(self, "VibeDL", tr("tag_failed"))

    def on_export_csv(self):
        entries = self.frame.download_history
        if not entries:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_csv_btn"), "vibedl_history.csv",
            tr("csv_filter"))
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["date", "title", "url", "path"])
                for e in entries:
                    writer.writerow([e.get("date", ""), e.get("title", ""),
                                     e.get("url", ""), e.get("path", "")])
        except OSError:
            return
        QMessageBox.information(self, "VibeDL", tr("export_done"))

    def on_play(self):
        entry = self._selected_entry()
        if entry and os.path.exists(entry.get('path', '')):
            os.startfile(entry['path'])
        elif entry:
            QMessageBox.information(self, tr("info_title"),
                                    tr("file_not_found"))

    def on_redownload(self):
        entry = self._selected_entry()
        if not entry:
            return
        time_range = self.frame._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        self.frame._dispatch_add(entry['url'], start_sec, end_sec)
        self.frame._switch_page(0)

    def _selected_entries(self):
        return [item.data(Qt.UserRole)
                for item in self.list_widget.selectedItems()]

    def on_bulk_redownload(self):
        entries = [e for e in self._selected_entries() if e]
        if not entries:
            return
        time_range = self.frame._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        for entry in entries:
            self.frame._dispatch_add(entry['url'], start_sec, end_sec)
        self.frame._switch_page(0)

    def on_bulk_delete(self):
        entries = [e for e in self._selected_entries() if e]
        if not entries:
            return
        answer = QMessageBox.question(
            self, tr("confirm_title"), tr("history_delete_confirm"))
        if answer != QMessageBox.Yes:
            return
        for entry in entries:
            if entry in self.frame.download_history:
                self.frame.download_history.remove(entry)
        try:
            save_download_history(self.frame.download_history)
        except OSError:
            pass
        self.refresh()


class LocalConvertDialog(QDialog):
    """ローカルファイル一括変換ダイアログ（Pro）。現在の設定で変換する。"""

    def __init__(self, frame):
        super().__init__(frame)
        self.frame = frame
        self.setWindowTitle(tr("convert_title"))
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)
        self.log_label = QLabel("")
        self.log_label.setObjectName("muted")
        layout.addWidget(self.log_label)
        btn_row = QHBoxLayout()
        add_btn = QPushButton(tr("convert_add"))
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(add_btn)
        rm_btn = QPushButton(tr("convert_remove"))
        rm_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(rm_btn)
        btn_row.addStretch()
        self.start_btn = QPushButton(tr("convert_start"))
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self.start_btn)
        close_btn = QPushButton(tr("cancel"))
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        self._worker = None

    def _on_add(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("convert_add"), "", tr("filter_audio"))
        for path in paths:
            if not self.list_widget.findItems(path, Qt.MatchExactly):
                self.list_widget.addItem(path)

    def _on_remove(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def _on_start(self):
        files = [self.list_widget.item(i).text()
                 for i in range(self.list_widget.count())]
        if not files:
            return
        self.start_btn.setEnabled(False)
        self._worker = ConvertWorker(
            files, self.frame.config, self.frame.ffmpeg_info, self)
        self._worker.log.connect(
            lambda msg: self.log_label.setText(msg))
        self._worker.done.connect(
            lambda: self.start_btn.setEnabled(True))
        self._worker.start()


class SettingsPanel(QWidget):
    """設定ページ。変更はデバウンスして changed シグナルで通知する。"""

    changed = Signal()
    update_check_requested = Signal()

    def __init__(self, parent, config, watch_urls=None):
        super().__init__(parent)
        self._initial_watch_urls = list(watch_urls or [])
        self.config = dict(config)
        self.config["url_history"] = list(config.get("url_history", []))
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        tabs = QTabWidget()

        # 出力タブ
        output_tab = QWidget()
        out_layout = QVBoxLayout(output_tab)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel(tr("format_label")))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["mp3", "m4a", "wav", "flac", "opus"])
        self.fmt_combo.setCurrentText(self.config["output_format"])
        fmt_row.addWidget(self.fmt_combo, 1)
        out_layout.addLayout(fmt_row)

        br_row = QHBoxLayout()
        br_row.addWidget(QLabel(tr("bitrate_label")))
        self.br_combo = QComboBox()
        self.br_combo.addItems(["128k", "160k", "192k", "256k", "320k"])
        self.br_combo.setCurrentText(self.config["bitrate"])
        br_row.addWidget(self.br_combo, 1)
        out_layout.addLayout(br_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(tr("folder_label")))
        self.folder_ctrl = QLineEdit(self.config["output_folder"])
        folder_row.addWidget(self.folder_ctrl, 1)
        browse_btn = QPushButton(tr("browse"))
        browse_btn.clicked.connect(self.on_browse_folder)
        folder_row.addWidget(browse_btn)
        out_layout.addLayout(folder_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("name_pattern_label")))
        self.name_template_ctrl = QLineEdit(self.config.get("name_template", "{title}"))
        self.name_template_ctrl.setPlaceholderText("{title} - {uploader}")
        name_row.addWidget(self.name_template_ctrl, 1)
        out_layout.addLayout(name_row)
        mirror_row = QHBoxLayout()
        mirror_row.addWidget(QLabel(tr("mirror_label")))
        self.mirror_ctrl = QLineEdit(self.config.get("mirror_folder", ""))
        mirror_row.addWidget(self.mirror_ctrl, 1)
        mirror_browse_btn = QPushButton(tr("browse"))
        mirror_browse_btn.clicked.connect(self.on_browse_mirror)
        mirror_row.addWidget(mirror_browse_btn)
        out_layout.addLayout(mirror_row)
        template_note = QLabel(tr("template_note"))
        template_note.setObjectName("muted")
        out_layout.addWidget(template_note)
        self.template_preview = QLabel("")
        self.template_preview.setObjectName("muted")
        self.template_preview.setWordWrap(True)
        out_layout.addWidget(self.template_preview)
        self.name_template_ctrl.textChanged.connect(
            self._update_template_preview)
        self._update_template_preview()
        out_layout.addStretch()
        tabs.addTab(output_tab, tr("tab_output"))

        # 処理タブ
        proc_tab = QWidget()
        proc_layout = QVBoxLayout(proc_tab)
        self.normalize_cb = QCheckBox(tr("normalize_cb"))
        self.normalize_cb.setChecked(self.config["normalize"])
        self.normalize_cb.toggled.connect(self.on_normalize_toggle)
        proc_layout.addWidget(self.normalize_cb)
        lufs_row = QHBoxLayout()
        lufs_row.addWidget(QLabel(tr("lufs_label")))
        self.lufs_spin = QDoubleSpinBox()
        self.lufs_spin.setRange(-70.0, 0.0)
        self.lufs_spin.setSingleStep(0.5)
        self.lufs_spin.setDecimals(1)
        self.lufs_spin.setValue(self.config["target_lufs"])
        lufs_row.addWidget(self.lufs_spin)
        lufs_row.addStretch()
        proc_layout.addLayout(lufs_row)
        self.meta_cb = QCheckBox(tr("meta_cb"))
        self.meta_cb.setChecked(self.config["embed_metadata"])
        proc_layout.addWidget(self.meta_cb)
        self.trim_cb = QCheckBox(tr("trim_cb"))
        self.trim_cb.setChecked(self.config.get("trim_silence", False))
        proc_layout.addWidget(self.trim_cb)
        self.fade_cb = QCheckBox(tr("fade_cb"))
        self.fade_cb.setChecked(self.config.get("fade_enabled", False))
        proc_layout.addWidget(self.fade_cb)
        fade_row = QHBoxLayout()
        fade_row.addWidget(QLabel(tr("fade_sec_label")))
        self.fade_spin = QDoubleSpinBox()
        self.fade_spin.setRange(0.5, 10.0)
        self.fade_spin.setSingleStep(0.5)
        self.fade_spin.setDecimals(1)
        self.fade_spin.setValue(float(self.config.get("fade_seconds", 1.0)))
        fade_row.addWidget(self.fade_spin)
        fade_row.addStretch()
        proc_layout.addLayout(fade_row)
        proc_layout.addStretch()
        tabs.addTab(proc_tab, tr("tab_processing"))

        # 通知タブ
        notif_tab = QWidget()
        notif_layout = QVBoxLayout(notif_tab)
        self.sound_cb = QCheckBox(tr("sound_cb"))
        self.sound_cb.setChecked(self.config.get("notify_sound", True))
        notif_layout.addWidget(self.sound_cb)
        self.toast_cb = QCheckBox(tr("toast_cb"))
        self.toast_cb.setChecked(self.config.get("notify_toast", True))
        notif_layout.addWidget(self.toast_cb)
        notif_layout.addStretch()
        tabs.addTab(notif_tab, tr("tab_notif"))

        # 一般タブ
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel(tr("theme_label")))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([tr("theme_light"), tr("theme_dark"),
                                   tr("theme_system")])
        self._theme_values = ["light", "dark", "system"]
        current_theme = self.config.get("theme_mode") or (
            "dark" if self.config.get("dark_mode", False) else "light")
        self.theme_combo.setCurrentIndex(
            self._theme_values.index(current_theme)
            if current_theme in self._theme_values else 0)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        general_layout.addLayout(theme_row)
        self.tray_cb = QCheckBox(tr("tray_cb"))
        self.tray_cb.setChecked(self.config.get("minimize_to_tray", False))
        general_layout.addWidget(self.tray_cb)
        self.update_cb = QCheckBox(tr("update_cb"))
        self.update_cb.setChecked(self.config.get("check_updates", True))
        general_layout.addWidget(self.update_cb)
        self.update_btn = QPushButton(tr("update_check_btn"))
        self.update_btn.clicked.connect(self.update_check_requested.emit)
        update_row = QHBoxLayout()
        update_row.addWidget(self.update_btn)
        update_row.addStretch()
        general_layout.addLayout(update_row)
        schedule_row = QHBoxLayout()
        self.schedule_cb = QCheckBox(tr("schedule_cb"))
        self.schedule_cb.setChecked(
            self.config.get("schedule_enabled", False))
        schedule_row.addWidget(self.schedule_cb)
        schedule_row.addWidget(QLabel(tr("schedule_time_label")))
        self.schedule_time = QTimeEdit()
        self.schedule_time.setDisplayFormat("HH:mm")
        _t = QTime.fromString(
            str(self.config.get("schedule_time", "23:00")), "HH:mm")
        self.schedule_time.setTime(_t if _t.isValid() else QTime(23, 0))
        self.schedule_time.timeChanged.connect(self._schedule_apply)
        schedule_row.addWidget(self.schedule_time)
        schedule_row.addStretch()
        general_layout.addLayout(schedule_row)
        webhook_row = QHBoxLayout()
        webhook_row.addWidget(QLabel(tr("webhook_label")))
        self.webhook_ctrl = QLineEdit(self.config.get("webhook_url", ""))
        self.webhook_ctrl.setPlaceholderText(
            "https://discord.com/api/webhooks/...")
        webhook_row.addWidget(self.webhook_ctrl, 1)
        general_layout.addLayout(webhook_row)
        self.prevent_sleep_cb = QCheckBox(tr("prevent_sleep_cb"))
        self.prevent_sleep_cb.setChecked(
            self.config.get("prevent_sleep", False))
        general_layout.addWidget(self.prevent_sleep_cb)
        self.playlist_cb = QCheckBox(tr("playlist_cb"))
        self.playlist_cb.setChecked(self.config.get("make_playlist", False))
        general_layout.addWidget(self.playlist_cb)
        self.clipboard_cb = QCheckBox(tr("clipboard_cb"))
        self.clipboard_cb.setChecked(self.config.get("clipboard_monitor", False))
        general_layout.addWidget(self.clipboard_cb)
        self.skip_dup_cb = QCheckBox(tr("skip_dup_cb"))
        self.skip_dup_cb.setChecked(self.config.get("skip_duplicates", False))
        general_layout.addWidget(self.skip_dup_cb)
        after_row = QHBoxLayout()
        after_row.addWidget(QLabel(tr("after_finish_label")))
        self.after_combo = QComboBox()
        self.after_combo.addItems([tr("after_finish_"),
                                   tr("after_finish_sleep"),
                                   tr("after_finish_shutdown")])
        self._after_values = ["", "sleep", "shutdown"]
        current_after = self.config.get("after_finish", "")
        self.after_combo.setCurrentIndex(
            self._after_values.index(current_after)
            if current_after in self._after_values else 0)
        after_row.addWidget(self.after_combo)
        after_row.addStretch()
        general_layout.addLayout(after_row)
        cookie_row = QHBoxLayout()
        cookie_row.addWidget(QLabel(tr("cookies_label")))
        self.cookies_combo = QComboBox()
        self.cookies_combo.addItems([tr("cookies_none"), "Chrome", "Edge", "Firefox"])
        cookie_values = ["", "chrome", "edge", "firefox"]
        current_cookie = self.config.get("cookies_browser", "")
        self.cookies_combo.setCurrentIndex(
            cookie_values.index(current_cookie) if current_cookie in cookie_values else 0)
        cookie_row.addWidget(self.cookies_combo)
        cookie_row.addStretch()
        general_layout.addLayout(cookie_row)
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel(tr("cookies_file_label")))
        self.cookies_file_ctrl = QLineEdit()
        self.cookies_file_ctrl.setText(self.config.get("cookies_file", ""))
        self.cookies_file_ctrl.setPlaceholderText(tr("cookies_file_ph"))
        file_row.addWidget(self.cookies_file_ctrl, 1)
        browse_cookie_btn = QPushButton(tr("select"))
        browse_cookie_btn.clicked.connect(self.on_browse_cookies_file)
        file_row.addWidget(browse_cookie_btn)
        general_layout.addLayout(file_row)
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(tr("language_label")))
        self.language_combo = QComboBox()
        self.language_combo.addItems(["日本語", "English"])
        self.language_combo.setCurrentIndex(
            1 if self.config.get("language", "ja") == "en" else 0)
        lang_row.addWidget(self.language_combo)
        lang_row.addStretch()
        general_layout.addLayout(lang_row)
        lang_note = QLabel(tr("language_note"))
        lang_note.setObjectName("muted")
        general_layout.addWidget(lang_note)
        parallel_row = QHBoxLayout()
        parallel_row.addWidget(QLabel(tr("max_parallel_label")))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 10)
        self.parallel_spin.setValue(
            max(1, min(5, int(self.config.get("max_parallel", 2)))))
        parallel_row.addWidget(self.parallel_spin)
        parallel_row.addStretch()
        general_layout.addLayout(parallel_row)
        parallel_note = QLabel(tr("parallel_pro_note"))
        parallel_note.setObjectName("muted")
        general_layout.addWidget(parallel_note)
        retry_row = QHBoxLayout()
        retry_row.addWidget(QLabel(tr("auto_retry_label")))
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 3)
        self.retry_spin.setValue(int(self.config.get("auto_retry", 0)))
        retry_row.addWidget(self.retry_spin)
        retry_row.addStretch()
        general_layout.addLayout(retry_row)
        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel(tr("rate_limit_label")))
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.0, 100.0)
        self.rate_spin.setSingleStep(0.5)
        self.rate_spin.setDecimals(1)
        self.rate_spin.setValue(float(self.config.get("rate_limit_mbps", 0)))
        rate_row.addWidget(self.rate_spin)
        rate_row.addStretch()
        general_layout.addLayout(rate_row)
        general_layout.addStretch()
        tabs.addTab(general_tab, tr("tab_general"))

        # Proタブ（Pro機能をここに集約）
        pro_tab = QWidget()
        pro_layout = QVBoxLayout(pro_tab)
        pro_intro = QLabel(tr("pro_intro"))
        pro_intro.setObjectName("muted")
        pro_intro.setWordWrap(True)
        pro_layout.addWidget(pro_intro)
        license_row = QHBoxLayout()
        license_row.addWidget(QLabel(tr("license_label")))
        self.license_ctrl = QLineEdit(self.config.get("license_key", ""))
        license_row.addWidget(self.license_ctrl, 1)
        license_check_btn = QPushButton(tr("license_check"))
        license_check_btn.clicked.connect(self._on_license_check)
        license_row.addWidget(license_check_btn)
        pro_layout.addLayout(license_row)
        self.license_status = QLabel("")
        self.license_status.setObjectName("muted")
        pro_layout.addWidget(self.license_status)
        self._update_license_status()
        buy_btn = QPushButton(tr("buy_pro"))
        buy_btn.clicked.connect(lambda: webbrowser.open(PRO_PURCHASE_URL))
        pro_layout.addWidget(buy_btn)
        self.split_cb = QCheckBox(tr("split_chapters_cb"))
        self.split_cb.setChecked(self.config.get("split_chapters", False))
        pro_layout.addWidget(self.split_cb)
        self.lyrics_cb = QCheckBox(tr("embed_lyrics_cb"))
        self.lyrics_cb.setChecked(self.config.get("embed_lyrics", False))
        pro_layout.addWidget(self.lyrics_cb)
        self.artist_split_cb = QCheckBox(tr("split_artist_cb"))
        self.artist_split_cb.setChecked(
            self.config.get("split_artist_title", False))
        pro_layout.addWidget(self.artist_split_cb)
        watch_label = QLabel(tr("watch_label"))
        watch_label.setObjectName("muted")
        watch_label.setWordWrap(True)
        pro_layout.addWidget(watch_label)
        watch_row = QHBoxLayout()
        self.watch_ctrl = QLineEdit()
        self.watch_ctrl.setPlaceholderText(tr("watch_ph"))
        watch_row.addWidget(self.watch_ctrl, 1)
        watch_add_btn = QPushButton(tr("watch_add"))
        watch_add_btn.clicked.connect(self._on_watch_add)
        watch_row.addWidget(watch_add_btn)
        pro_layout.addLayout(watch_row)
        self.watch_list = QListWidget()
        self.watch_list.setMaximumHeight(90)
        for _u in self._initial_watch_urls:
            self.watch_list.addItem(_u)
        pro_layout.addWidget(self.watch_list)
        watch_rm_row = QHBoxLayout()
        watch_rm_btn = QPushButton(tr("watch_remove"))
        watch_rm_btn.clicked.connect(self._on_watch_remove)
        watch_rm_row.addWidget(watch_rm_btn)
        watch_rm_row.addStretch()
        pro_layout.addLayout(watch_rm_row)
        tp_row = QHBoxLayout()
        tp_row.addWidget(QLabel(tr("tp_label")))
        self.tp_spin = QDoubleSpinBox()
        self.tp_spin.setRange(-5.0, 0.0)
        self.tp_spin.setSingleStep(0.5)
        self.tp_spin.setDecimals(1)
        self.tp_spin.setValue(float(self.config.get("loudnorm_tp", -2.0)))
        tp_row.addWidget(self.tp_spin)
        tp_row.addStretch()
        pro_layout.addLayout(tp_row)
        rename_label = QLabel(tr("rename_rules_label"))
        rename_label.setObjectName("muted")
        rename_label.setWordWrap(True)
        pro_layout.addWidget(rename_label)
        self.rename_rules_ctrl = QPlainTextEdit(
            self.config.get("rename_rules", ""))
        self.rename_rules_ctrl.setPlaceholderText(tr("rename_rules_ph"))
        self.rename_rules_ctrl.setMaximumHeight(70)
        self.rename_rules_ctrl.textChanged.connect(self._schedule_apply)
        pro_layout.addWidget(self.rename_rules_ctrl)
        pro_note = QLabel(tr("pro_features_note"))
        pro_note.setObjectName("muted")
        pro_note.setWordWrap(True)
        pro_layout.addWidget(pro_note)
        pro_layout.addStretch()
        tabs.addTab(pro_tab, tr("tab_pro"))
        self.on_normalize_toggle()

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(tr("preset_label")))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(sorted(load_presets().keys()))
        preset_row.addWidget(self.preset_combo, 1)
        preset_save_btn = QPushButton(tr("preset_save"))
        preset_save_btn.clicked.connect(self._on_preset_save)
        preset_row.addWidget(preset_save_btn)
        preset_apply_btn = QPushButton(tr("preset_apply"))
        preset_apply_btn.clicked.connect(self._on_preset_apply)
        preset_row.addWidget(preset_apply_btn)
        preset_del_btn = QPushButton(tr("preset_delete"))
        preset_del_btn.clicked.connect(self._on_preset_delete)
        preset_row.addWidget(preset_del_btn)
        layout.addLayout(preset_row)
        layout.addWidget(tabs)
        self._wire_live_apply()

    def _wire_live_apply(self):
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(500)
        self._apply_timer.timeout.connect(self.changed.emit)
        for cls, sig in ((QCheckBox, "toggled"),
                         (QComboBox, "currentIndexChanged"),
                         (QLineEdit, "textChanged"),
                         (QSpinBox, "valueChanged"),
                         (QDoubleSpinBox, "valueChanged")):
            for w in self.findChildren(cls):
                getattr(w, sig).connect(self._schedule_apply)

    def _schedule_apply(self, *_):
        self._apply_timer.start()

    def on_normalize_toggle(self):
        self.lufs_spin.setEnabled(self.normalize_cb.isChecked())

    def on_theme_changed(self, index):
        # 設定ダイアログとメイン画面へ即時プレビュー
        mode = self._theme_values[index]
        if mode == "system":
            dark = False
            try:
                dark = (QApplication.instance().styleHints().colorScheme()
                        == Qt.ColorScheme.Dark)
            except Exception:
                pass
        else:
            dark = mode == "dark"
        QApplication.instance().setStyleSheet(build_stylesheet(dark))

    def on_browse_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("folder_dialog"), self.folder_ctrl.text())
        if path:
            self.folder_ctrl.setText(path)

    def on_browse_cookies_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("cookies_dialog"), "", tr("filter_text"))
        if path:
            self.cookies_file_ctrl.setText(path)

    def _update_license_status(self):
        payload = parse_license_key(self.license_ctrl.text().strip())
        if payload:
            self.license_status.setText(
                tr("license_valid", name=payload.get("name", "")))
        else:
            self.license_status.setText(tr("license_invalid"))

    def _on_license_check(self):
        self._update_license_status()

    PRESET_KEYS = (
        "output_format", "bitrate", "output_folder", "target_lufs",
        "loudnorm_tp", "normalize", "embed_metadata", "embed_lyrics",
        "split_chapters", "trim_silence", "fade_enabled", "fade_seconds",
        "name_template", "rate_limit_mbps", "auto_retry", "max_parallel",
    )

    def _on_preset_save(self):
        name, ok = QInputDialog.getText(
            self, tr("preset_name_title"), tr("preset_name_label"))
        name = name.strip()
        if not ok or not name:
            return
        presets = load_presets()
        current = self.get_config()
        presets[name] = {k: current.get(k) for k in self.PRESET_KEYS}
        save_presets(presets)
        if self.preset_combo.findText(name) < 0:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText(name)

    def _on_preset_apply(self):
        name = self.preset_combo.currentText()
        preset = load_presets().get(name)
        if not preset:
            return
        if "output_format" in preset:
            self.fmt_combo.setCurrentText(str(preset["output_format"]))
        if "bitrate" in preset:
            self.br_combo.setCurrentText(str(preset["bitrate"]))
        if "output_folder" in preset:
            self.folder_ctrl.setText(str(preset["output_folder"]))
        if "target_lufs" in preset:
            self.lufs_spin.setValue(float(preset["target_lufs"]))
        if "loudnorm_tp" in preset:
            self.tp_spin.setValue(float(preset["loudnorm_tp"]))
        if "normalize" in preset:
            self.normalize_cb.setChecked(bool(preset["normalize"]))
        if "embed_metadata" in preset:
            self.meta_cb.setChecked(bool(preset["embed_metadata"]))
        if "embed_lyrics" in preset:
            self.lyrics_cb.setChecked(bool(preset["embed_lyrics"]))
        if "split_chapters" in preset:
            self.split_cb.setChecked(bool(preset["split_chapters"]))
        if "trim_silence" in preset:
            self.trim_cb.setChecked(bool(preset["trim_silence"]))
        if "fade_enabled" in preset:
            self.fade_cb.setChecked(bool(preset["fade_enabled"]))
        if "fade_seconds" in preset:
            self.fade_spin.setValue(float(preset["fade_seconds"]))
        if "name_template" in preset:
            self.name_template_ctrl.setText(str(preset["name_template"]))
        if "rate_limit_mbps" in preset:
            self.rate_spin.setValue(float(preset["rate_limit_mbps"]))
        if "auto_retry" in preset:
            self.retry_spin.setValue(int(preset["auto_retry"]))
        if "max_parallel" in preset:
            self.parallel_spin.setValue(int(preset["max_parallel"]))
        self._schedule_apply()

    def _on_preset_delete(self):
        name = self.preset_combo.currentText()
        presets = load_presets()
        if name in presets:
            del presets[name]
            save_presets(presets)
        index = self.preset_combo.findText(name)
        if index >= 0:
            self.preset_combo.removeItem(index)

    def on_browse_mirror(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("folder_dialog"), self.mirror_ctrl.text())
        if path:
            self.mirror_ctrl.setText(path)

    def _on_watch_add(self):
        url = self.watch_ctrl.text().strip()
        if not url.startswith("http"):
            return
        if url in self.get_watch_urls():
            return
        self.watch_list.addItem(url)
        self.watch_ctrl.clear()
        self._schedule_apply()

    def _on_watch_remove(self):
        for item in self.watch_list.selectedItems():
            self.watch_list.takeItem(self.watch_list.row(item))
        self._schedule_apply()

    def get_watch_urls(self):
        return [self.watch_list.item(i).text()
                for i in range(self.watch_list.count())]

    def _update_template_preview(self):
        self.template_preview.setText(tr(
            "template_preview_label",
            name=render_template_preview(self.name_template_ctrl.text())))

    def get_config(self):
        self.config["output_format"] = self.fmt_combo.currentText()
        self.config["bitrate"] = self.br_combo.currentText()
        self.config["output_folder"] = self.folder_ctrl.text()
        self.config["target_lufs"] = self.lufs_spin.value()
        self.config["loudnorm_tp"] = self.tp_spin.value()
        self.config["normalize"] = self.normalize_cb.isChecked()
        self.config["embed_metadata"] = self.meta_cb.isChecked()
        self.config["embed_lyrics"] = self.lyrics_cb.isChecked()
        self.config["split_artist_title"] = self.artist_split_cb.isChecked()
        self.config["split_chapters"] = self.split_cb.isChecked()
        self.config["trim_silence"] = self.trim_cb.isChecked()
        self.config["fade_enabled"] = self.fade_cb.isChecked()
        self.config["fade_seconds"] = self.fade_spin.value()
        self.config["theme_mode"] = \
            self._theme_values[self.theme_combo.currentIndex()]
        self.config["dark_mode"] = self.config["theme_mode"] == "dark"
        self.config["minimize_to_tray"] = self.tray_cb.isChecked()
        self.config["check_updates"] = self.update_cb.isChecked()
        self.config["schedule_enabled"] = self.schedule_cb.isChecked()
        self.config["schedule_time"] = \
            self.schedule_time.time().toString("HH:mm")
        self.config["webhook_url"] = self.webhook_ctrl.text().strip()
        self.config["prevent_sleep"] = self.prevent_sleep_cb.isChecked()
        self.config["make_playlist"] = self.playlist_cb.isChecked()
        self.config["rename_rules"] = self.rename_rules_ctrl.toPlainText()
        self.config["mirror_folder"] = self.mirror_ctrl.text().strip()
        self.config["notify_sound"] = self.sound_cb.isChecked()
        self.config["notify_toast"] = self.toast_cb.isChecked()
        self.config["clipboard_monitor"] = self.clipboard_cb.isChecked()
        self.config["skip_duplicates"] = self.skip_dup_cb.isChecked()
        self.config["after_finish"] = \
            self._after_values[self.after_combo.currentIndex()]
        self.config["cookies_browser"] = ["", "chrome", "edge", "firefox"][self.cookies_combo.currentIndex()]
        self.config["cookies_file"] = self.cookies_file_ctrl.text().strip()
        self.config["language"] = ["ja", "en"][self.language_combo.currentIndex()]
        self.config["max_parallel"] = self.parallel_spin.value()
        self.config["auto_retry"] = self.retry_spin.value()
        self.config["rate_limit_mbps"] = self.rate_spin.value()
        self.config["license_key"] = self.license_ctrl.text().strip()
        self.config["name_template"] = self.name_template_ctrl.text().strip() or "{title}"
        return self.config


class SettingsDialog(QDialog):
    """互換用ラッパー: 設定パネルをダイアログとして開く。"""

    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.resize(520, 560)
        layout = QVBoxLayout(self)
        self.panel = SettingsPanel(self, config)
        layout.addWidget(self.panel)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("primary")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_config(self):
        return self.panel.get_config()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = VibeDLFrame()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
