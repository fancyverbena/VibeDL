"""VibeDL GUI (PySide6 / Qt)

wxPython 版から移行した GUI。見た目は QSS（Qt Style Sheets）で
一元管理し、カード型レイアウト + アクセントカラーで統一している。
ダウンロード・音声処理・設定保存は従来モジュールをそのまま使う。
"""
import os
import re
import sys
import urllib.request
import winsound
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QProgressDialog, QPushButton, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget, QSystemTrayIcon,
)

from downloader import (
    download_audio, search_youtube, get_playlist_entries, get_video_info,
)
from license_check import is_pro as _license_is_pro, parse_license_key
from audio_processor import (
    normalize_audio, embed_metadata, trim_and_fade,
    get_ffmpeg_info, check_ffmpeg, download_ffmpeg,
)
from config_store import (
    get_config, save_config, load_download_history, save_download_history,
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
    "meta_cb": {"ja": "メタデータ埋め込み", "en": "Embed metadata"},
    "tab_processing": {"ja": "処理", "en": "Processing"},
    "trim_cb": {"ja": "無音トリミング（先頭・末尾）", "en": "Trim silence (start/end)"},
    "fade_cb": {"ja": "フェードイン／アウト", "en": "Fade in / out"},
    "fade_sec_label": {"ja": "フェード時間（秒）:", "en": "Fade duration (sec):"},
    "sound_cb": {"ja": "完了時に通知音を鳴らす", "en": "Play a sound when finished"},
    "toast_cb": {"ja": "完了時にトースト通知を表示", "en": "Show a toast notification when finished"},
    "tab_notif": {"ja": "通知", "en": "Notifications"},
    "dark_cb": {"ja": "ダークモード", "en": "Dark mode"},
    "clipboard_cb": {"ja": "クリップボードを監視してURLを自動入力", "en": "Monitor clipboard and auto-fill URLs"},
    "cookies_label": {"ja": "ブラウザCookie（年齢制限など用）", "en": "Browser cookies (for age-restricted videos)"},
    "cookies_none": {"ja": "使用しない", "en": "None"},
    "cookies_file_label": {"ja": "cookies.txt（指定時は優先）", "en": "cookies.txt (takes precedence)"},
    "cookies_file_ph": {"ja": "cookies.txt のパス（任意）", "en": "Path to cookies.txt (optional)"},
    "select": {"ja": "選択", "en": "Select"},
    "tab_general": {"ja": "一般", "en": "General"},
    "language_label": {"ja": "言語", "en": "Language"},
    "max_parallel_label": {"ja": "同時ダウンロード数（1〜5）", "en": "Parallel downloads (1-5)"},
    "parallel_pro_note": {"ja": "※3以上は Pro ライセンスが必要です（未登録の場合は2まで有効）", "en": "3 or more requires a Pro license (capped at 2 without one)."},
    "license_label": {"ja": "Pro ライセンスキー", "en": "Pro license key"},
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
        "log_bg": "#181A1E",
    },
    False: {  # light
        "bg": "#E9EBEF", "surface": "#FFFFFF", "entry": "#FFFFFF",
        "fg": "#1C1E22", "muted": "#6E737A", "border": "#D6D9DE",
        "btn": "#FFFFFF", "btn_hover": "#F0F1F5", "track": "#D6D9DE",
        "log_bg": "#FFFFFF",
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
    """
    return (qss.replace("@BG@", p["bg"]).replace("@SURFACE@", p["surface"])
            .replace("@ENTRY@", p["entry"]).replace("@FG@", p["fg"])
            .replace("@MUTED@", p["muted"]).replace("@BORDER@", p["border"])
            .replace("@BTN@", p["btn"]).replace("@BTN_HOVER@", p["btn_hover"])
            .replace("@TRACK@", p["track"]).replace("@LOG_BG@", p["log_bg"])
            .replace("@ACCENT@", ACCENT))


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
                               (d.get('_speed_str') or '').strip(),
                               (d.get('_eta_str') or '').strip())
        elif d.get('status') == 'finished':
            self.progress.emit(100, "", "")

    def run(self):
        try:
            self.item.status = "downloading"
            self.log.emit(tr("log_processing", url=self.item.url))
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
            )
            self.log.emit(tr("log_dl_done"))
            temp_out = data['temp_raw']

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
                    bitrate=self.config["bitrate"])
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
                embed_metadata(temp_out, data['title'], data['uploader'], data['thumb'])

            if os.path.exists(data['dest_path']):
                os.remove(data['dest_path'])
            os.rename(temp_out, data['dest_path'])

            if os.path.exists(data['temp_raw']) and data['temp_raw'] != temp_out:
                os.remove(data['temp_raw'])

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
                self.log.emit(tr("log_error", url=self.item.url, err=e))
                self.item_finished.emit(self.item, None)

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
        self.download_history = load_download_history()
        self._bg_threads = set()
        self.setAcceptDrops(True)

        self._init_ui()
        self.apply_theme()
        self.update_settings_display()

        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.show()

        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self.on_clipboard_timer)
        self.update_clipboard_monitor()

        QTimer.singleShot(100, self.check_ffmpeg_on_startup)

    # ---------- UI構築 ----------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(f'<span style="color:{ACCENT}">Vibe</span>DL')
        title.setObjectName("appTitle")
        header.addWidget(title)
        subtitle = QLabel("YouTube Audio Downloader")
        subtitle.setObjectName("muted")
        header.addWidget(subtitle)
        header.addStretch()
        root.addLayout(header)

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
        self.cancel_btn = QPushButton(tr("cancel"))
        self.cancel_btn.setToolTip(tr("cancel_tip"))
        self.cancel_btn.clicked.connect(self.on_cancel_downloads)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.cancel_btn)
        self.import_btn = QPushButton(tr("import_btn"))
        self.import_btn.setToolTip(tr("import_tip"))
        self.import_btn.clicked.connect(self.on_import_file)
        btn_row.addWidget(self.import_btn)
        btn_row.addStretch()
        self.open_folder_btn = QPushButton(tr("open_folder"))
        self.open_folder_btn.setToolTip(tr("open_folder_tip"))
        self.open_folder_btn.clicked.connect(self.on_open_folder)
        self.open_folder_btn.setEnabled(False)
        btn_row.addWidget(self.open_folder_btn)
        self.play_btn = QPushButton(tr("play"))
        self.play_btn.setToolTip(tr("play_tip"))
        self.play_btn.clicked.connect(self.on_play_last)
        self.play_btn.setEnabled(False)
        btn_row.addWidget(self.play_btn)
        self.history_btn = QPushButton(tr("history"))
        self.history_btn.setToolTip(tr("history_tip"))
        self.history_btn.clicked.connect(self.on_show_history)
        btn_row.addWidget(self.history_btn)
        self.settings_btn = QPushButton(tr("settings"))
        self.settings_btn.clicked.connect(self.on_settings)
        btn_row.addWidget(self.settings_btn)
        card_layout.addLayout(btn_row)
        root.addWidget(card)

        # カード2: キュー + 進捗
        card2, card2_layout = make_card()
        card2_layout.addWidget(section_label(tr("section_queue")))
        self.queue_list = QListWidget()
        self.queue_list.setIconSize(QSize(96, 54))
        # ドラッグで並べ替え可能にし、表示順を self.queue に同期する
        self.queue_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)
        self.queue_list.model().rowsMoved.connect(self._on_queue_rows_moved)
        self.queue_list.setFixedHeight(110)
        card2_layout.addWidget(self.queue_list)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        card2_layout.addWidget(self.progress)
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

        status = self.statusBar()
        self.status_fmt = QLabel()
        self.status_norm = QLabel()
        self.status_meta = QLabel()
        status.addWidget(self.status_fmt, 2)
        status.addWidget(self.status_norm, 2)
        status.addWidget(self.status_meta, 1)

    # ---------- テーマ・表示 ----------
    def apply_theme(self):
        dark = self.config.get("dark_mode", False)
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
        parts = []
        if speed:
            parts.append(tr("speed", speed=speed))
        if eta:
            parts.append(tr("eta", eta=eta))
        if parts:
            self.status_label.setText("  ".join(parts))

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

    def _add_item(self, url, start_sec, end_sec, title=None, duration=None,
                  thumb_url=None, fetch_info=True):
        item = QueueItem(url, start_sec, end_sec)
        item.title = title
        item.duration = duration
        item.thumb_url = thumb_url
        self.queue.append(item)
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
        icons = {"waiting": "⏳", "downloading": "⬇️", "done": "✅"}
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

    def _on_queue_rows_moved(self, *args):
        """ドラッグ並べ替え後の表示順を self.queue に反映する。"""
        new_order = []
        for i in range(self.queue_list.count()):
            obj = self.queue_list.item(i).data(Qt.UserRole)
            if obj is not None:
                new_order.append(obj)
        if len(new_order) == len(self.queue):
            self.queue = new_order

    def on_start_queue(self):
        if not self.queue:
            QMessageBox.information(self, tr("info_title"), tr("queue_empty"))
            return
        self.start_queue()

    def start_queue(self):
        # 実行中のワーカーがある場合は進捗表示をリセットしない（設定変更で
        # 空き枠を埋める場合など、途中での呼び出しに備える）
        if not self.active_workers and any(item.status == "waiting" for item in self.queue):
            self.progress.setValue(0)
            self.status_label.setText("")
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
        sender = self.sender()
        if sender in self.active_workers:
            self.active_workers.remove(sender)
        self.update_queue_display()
        if any(i.status == "waiting" for i in self.queue):
            self.start_queue()
        elif not self.active_workers:
            self.cancel_btn.setEnabled(False)
            self.status_label.setText(tr("status_cancelled"))

    def on_item_completed(self, item, dest_path):
        if item in self.queue:
            item.status = "done"
            if dest_path:
                self.last_dest_path = dest_path
                self.open_folder_btn.setEnabled(True)
                self.play_btn.setEnabled(True)
                self._record_download_history(item, dest_path)
                self.notify_user(tr("notify_complete"), os.path.basename(dest_path))
            self.queue.remove(item)
        sender = self.sender()
        if sender in self.active_workers:
            self.active_workers.remove(sender)
        self.update_queue_display()
        if any(i.status == "waiting" for i in self.queue):
            self.start_queue()
        elif not self.active_workers:
            self.cancel_btn.setEnabled(False)
            self.progress.setValue(100)
            self.status_label.setText(tr("status_done"))

    def on_clear_queue(self):
        self.queue = [i for i in self.queue if i.status != "waiting"]
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

    def on_show_history(self):
        dlg = HistoryDialog(self, self.download_history)
        dlg.exec()

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
        dlg = SettingsDialog(self, self.config)
        if dlg.exec() == QDialog.Accepted:
            self.config = dlg.get_config()
            save_config(self.config)
            self.max_workers = max(1, int(self.config.get("max_parallel", 2)))
            self.pro = _license_is_pro(self.config.get("license_key", ""))
            self.setWindowTitle("VibeDL - Audio Downloader"
                                + (" Pro" if self.pro else ""))
            # 実行中に上限を上げたら空き枠をすぐ埋める（停止中のキューは動かさない）
            if self.active_workers:
                self.start_queue()
            self.apply_theme()
            self.update_settings_display()
            self.update_clipboard_monitor()
        else:
            # ダークモードのプレビューで変わった見た目を元に戻す
            self.apply_theme()

    def closeEvent(self, event):
        save_config(self.config)
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

    def on_results(self, results):
        self.search_btn.setEnabled(True)
        for r in results:
            text = r['title']
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


class HistoryDialog(QDialog):
    def __init__(self, parent, entries):
        super().__init__(parent)
        self.frame = parent
        self.setWindowTitle(tr("history_title"))
        self.resize(660, 440)

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for entry in entries:
            text = f"{entry.get('title', '')}  ―  {entry.get('date', '')}"
            if not os.path.exists(entry.get('path', '')):
                text += tr("missing_file_suffix")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget, 1)
        if not entries:
            self.list_widget.addItem(tr("history_empty"))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        play_btn = QPushButton(tr("play2"))
        play_btn.clicked.connect(self.on_play)
        btn_row.addWidget(play_btn)
        redl_btn = QPushButton(tr("redownload"))
        redl_btn.clicked.connect(self.on_redownload)
        btn_row.addWidget(redl_btn)
        close_btn = QPushButton(tr("close"))
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _selected_entry(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def on_play(self):
        entry = self._selected_entry()
        if entry and os.path.exists(entry.get('path', '')):
            os.startfile(entry['path'])
        elif entry:
            QMessageBox.information(self, tr("info_title"), tr("file_not_found"))

    def on_redownload(self):
        entry = self._selected_entry()
        if not entry:
            return
        time_range = self.frame._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        self.frame._dispatch_add(entry['url'], start_sec, end_sec)
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.resize(480, 520)
        self.config = dict(config)
        self.config["url_history"] = list(config.get("url_history", []))
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # 出力タブ
        output_tab = QWidget()
        out_layout = QVBoxLayout(output_tab)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel(tr("format_label")))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["mp3", "m4a", "wav", "flac"])
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
        self.on_normalize_toggle()
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
        self.dark_cb = QCheckBox(tr("dark_cb"))
        self.dark_cb.setChecked(self.config.get("dark_mode", False))
        self.dark_cb.toggled.connect(self.on_dark_toggle)
        general_layout.addWidget(self.dark_cb)
        self.clipboard_cb = QCheckBox(tr("clipboard_cb"))
        self.clipboard_cb.setChecked(self.config.get("clipboard_monitor", False))
        general_layout.addWidget(self.clipboard_cb)
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
        self.parallel_spin.setRange(1, 5)
        self.parallel_spin.setValue(
            max(1, min(5, int(self.config.get("max_parallel", 2)))))
        parallel_row.addWidget(self.parallel_spin)
        parallel_row.addStretch()
        general_layout.addLayout(parallel_row)
        parallel_note = QLabel(tr("parallel_pro_note"))
        parallel_note.setObjectName("muted")
        general_layout.addWidget(parallel_note)
        license_row = QHBoxLayout()
        license_row.addWidget(QLabel(tr("license_label")))
        self.license_ctrl = QLineEdit(self.config.get("license_key", ""))
        license_row.addWidget(self.license_ctrl, 1)
        license_check_btn = QPushButton(tr("license_check"))
        license_check_btn.clicked.connect(self._on_license_check)
        license_row.addWidget(license_check_btn)
        general_layout.addLayout(license_row)
        self.license_status = QLabel("")
        self.license_status.setObjectName("muted")
        general_layout.addWidget(self.license_status)
        self._update_license_status()
        general_layout.addStretch()
        tabs.addTab(general_tab, tr("tab_general"))

        layout.addWidget(tabs)

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

    def on_normalize_toggle(self):
        self.lufs_spin.setEnabled(self.normalize_cb.isChecked())

    def on_dark_toggle(self, checked):
        # 設定ダイアログとメイン画面へ即時プレビュー
        QApplication.instance().setStyleSheet(build_stylesheet(checked))

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

    def get_config(self):
        self.config["output_format"] = self.fmt_combo.currentText()
        self.config["bitrate"] = self.br_combo.currentText()
        self.config["output_folder"] = self.folder_ctrl.text()
        self.config["target_lufs"] = self.lufs_spin.value()
        self.config["normalize"] = self.normalize_cb.isChecked()
        self.config["embed_metadata"] = self.meta_cb.isChecked()
        self.config["trim_silence"] = self.trim_cb.isChecked()
        self.config["fade_enabled"] = self.fade_cb.isChecked()
        self.config["fade_seconds"] = self.fade_spin.value()
        self.config["dark_mode"] = self.dark_cb.isChecked()
        self.config["notify_sound"] = self.sound_cb.isChecked()
        self.config["notify_toast"] = self.toast_cb.isChecked()
        self.config["clipboard_monitor"] = self.clipboard_cb.isChecked()
        self.config["cookies_browser"] = ["", "chrome", "edge", "firefox"][self.cookies_combo.currentIndex()]
        self.config["cookies_file"] = self.cookies_file_ctrl.text().strip()
        self.config["language"] = ["ja", "en"][self.language_combo.currentIndex()]
        self.config["max_parallel"] = self.parallel_spin.value()
        self.config["license_key"] = self.license_ctrl.text().strip()
        self.config["name_template"] = self.name_template_ctrl.text().strip() or "{title}"
        return self.config


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = VibeDLFrame()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
