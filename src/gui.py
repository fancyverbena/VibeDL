"""VibeDL GUI (PySide6 / Qt)

wxPython 版から移行した GUI。見た目は QSS（Qt Style Sheets）で
一元管理し、カード型レイアウト + アクセントカラーで統一している。
ダウンロード・音声処理・設定保存は従来モジュールをそのまま使う。
"""
import os
import sys
import winsound

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QProgressDialog, QPushButton, QTabWidget, QVBoxLayout, QWidget,
    QSystemTrayIcon,
)

from downloader import download_audio, search_youtube
from audio_processor import (
    normalize_audio, embed_metadata,
    get_ffmpeg_info, check_ffmpeg, download_ffmpeg,
)
from config_store import get_config, save_config

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
            self.log.emit(f"処理中: {self.item.url}")
            data = download_audio(
                self.item.url, self.config["output_folder"],
                output_format=self.config["output_format"],
                bitrate=self.config["bitrate"],
                progress_hook=self._progress_hook,
                start_sec=self.item.start_sec,
                end_sec=self.item.end_sec,
                name_template=self.config.get("name_template", "{title}"),
            )
            self.log.emit("[1/3] ダウンロード完了")
            temp_out = data['temp_raw']

            self._check_cancelled()
            if self.config["normalize"] and check_ffmpeg(self.ffmpeg_info['path']):
                self.phase.emit("音量最適化中...")
                self.log.emit("[2/3] 音量最適化中...")
                normalized = normalize_audio(
                    temp_out, self.config["target_lufs"],
                    ffmpeg_info=self.ffmpeg_info)
                if normalized:
                    temp_out = normalized
                    self.log.emit("音量調整完了")
                else:
                    self.log.emit("音量調整に失敗しました。")
            else:
                self.log.emit("音量正規化をスキップ")

            self._check_cancelled()
            if self.config["embed_metadata"]:
                self.phase.emit("メタデータ埋め込み中...")
                self.log.emit("[3/3] メタデータ埋め込み中...")
                embed_metadata(temp_out, data['title'], data['uploader'], data['thumb'])

            if os.path.exists(data['dest_path']):
                os.remove(data['dest_path'])
            os.rename(temp_out, data['dest_path'])

            if os.path.exists(data['temp_raw']) and data['temp_raw'] != temp_out:
                os.remove(data['temp_raw'])

            self.log.emit(f"✨ 完了: {data['dest_path']}")
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
                self.log.emit(f"❌ エラー ({self.item.url}): {e}")
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
        self.log.emit(f"⏹ キャンセルしました: {self.item.url}")
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
        self.queue = []
        self.active_workers = []
        self.max_workers = 2
        self.last_dest_path = None

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
        card_layout.addWidget(section_label("ダウンロード"))

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("YouTube URL:"))
        self.url_ctrl = QComboBox()
        self.url_ctrl.setEditable(True)
        self.url_ctrl.lineEdit().setPlaceholderText("https://www.youtube.com/...")
        self.url_ctrl.lineEdit().returnPressed.connect(self.on_add_to_queue)
        self._populate_url_history()
        url_row.addWidget(self.url_ctrl, 1)
        self.search_btn = QPushButton("検索")
        self.search_btn.setToolTip("キーワードでYouTubeを検索")
        self.search_btn.clicked.connect(self.on_search)
        url_row.addWidget(self.search_btn)
        card_layout.addLayout(url_row)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("開始 (秒 / mm:ss):"))
        self.start_ctrl = QLineEdit()
        self.start_ctrl.setPlaceholderText("0:00")
        self.start_ctrl.setFixedWidth(110)
        time_row.addWidget(self.start_ctrl)
        time_row.addSpacing(16)
        time_row.addWidget(QLabel("終了 (秒 / mm:ss):"))
        self.end_ctrl = QLineEdit()
        self.end_ctrl.setPlaceholderText("3:00")
        self.end_ctrl.setFixedWidth(110)
        time_row.addWidget(self.end_ctrl)
        time_row.addStretch()
        card_layout.addLayout(time_row)

        btn_row = QHBoxLayout()
        self.add_queue_btn = QPushButton("キューに追加")
        self.add_queue_btn.clicked.connect(self.on_add_to_queue)
        btn_row.addWidget(self.add_queue_btn)
        self.start_queue_btn = QPushButton("キューを開始")
        self.start_queue_btn.setObjectName("primary")
        self.start_queue_btn.clicked.connect(self.on_start_queue)
        self.start_queue_btn.setEnabled(False)
        btn_row.addWidget(self.start_queue_btn)
        self.clear_queue_btn = QPushButton("キューをクリア")
        self.clear_queue_btn.clicked.connect(self.on_clear_queue)
        btn_row.addWidget(self.clear_queue_btn)
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.setToolTip("実行中のダウンロードをすべてキャンセル")
        self.cancel_btn.clicked.connect(self.on_cancel_downloads)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        self.open_folder_btn = QPushButton("フォルダを開く")
        self.open_folder_btn.setToolTip("最後に保存したフォルダを開く")
        self.open_folder_btn.clicked.connect(self.on_open_folder)
        self.open_folder_btn.setEnabled(False)
        btn_row.addWidget(self.open_folder_btn)
        self.settings_btn = QPushButton("設定")
        self.settings_btn.clicked.connect(self.on_settings)
        btn_row.addWidget(self.settings_btn)
        card_layout.addLayout(btn_row)
        root.addWidget(card)

        # カード2: キュー + 進捗
        card2, card2_layout = make_card()
        card2_layout.addWidget(section_label("キュー"))
        self.queue_list = QListWidget()
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
        card3_layout.addWidget(section_label("ログ"))
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
            f"フォーマット: {self.config['output_format']} / {self.config['bitrate']}")
        self.status_norm.setText(
            f"正規化: {'ON' if self.config['normalize'] else 'OFF'} ({self.config['target_lufs']} LUFS)")
        self.status_meta.setText(
            f"メタデータ: {'ON' if self.config['embed_metadata'] else 'OFF'}")

    def log(self, msg):
        self.log_ctrl.appendPlainText(msg)

    def on_download_progress(self, percent, speed="", eta=""):
        self.progress.setValue(percent)
        parts = []
        if speed:
            parts.append(f"速度: {speed}")
        if eta:
            parts.append(f"残り: {eta}")
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
                self.log("🔗 クリップボードからURLを貼り付けました")

    # ---------- FFmpeg ----------
    def check_ffmpeg_on_startup(self):
        if check_ffmpeg(self.ffmpeg_info['path']):
            return
        answer = QMessageBox.question(
            self, "FFmpeg 未検出",
            "FFmpegが見つかりません。自動ダウンロードしますか？")
        if answer != QMessageBox.Yes:
            self.log("FFmpeg なしで続行します。音量正規化は利用不可。")
            return
        self.log("FFmpegをダウンロード中...")
        dialog = QProgressDialog("ダウンロードしています...", None, 0, 100, self)
        dialog.setWindowTitle("FFmpeg ダウンロード")
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
                self.log("FFmpeg の準備が完了しました。")
            else:
                self.log("FFmpeg のダウンロードに失敗しました。")

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
                self, "入力エラー",
                "開始・終了は「秒」または「mm:ss」で入力してください。")
            return None
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            QMessageBox.warning(self, "入力エラー", "終了は開始より後を指定してください。")
            return None
        return (start_sec, end_sec)

    def on_search(self):
        dlg = SearchDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        urls = dlg.selected_urls()
        if not urls:
            return
        time_range = self._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        for url in urls:
            self.queue.append(QueueItem(url, start_sec, end_sec))
            self.add_to_history(url)
            self.log(f"キューに追加: {url}")
        self.update_queue_display()

    def on_add_to_queue(self):
        url = self.url_ctrl.currentText().strip()
        if not url:
            QMessageBox.warning(self, "入力エラー", "URLを入力してください。")
            return
        time_range = self._current_time_range()
        if time_range is None:
            return
        start_sec, end_sec = time_range
        item = QueueItem(url, start_sec, end_sec)
        self.queue.append(item)
        self.update_queue_display()
        self.url_ctrl.setCurrentText("")
        self.start_ctrl.clear()
        self.end_ctrl.clear()
        self.add_to_history(url)
        self.log(f"キューに追加: {url}")

    def update_queue_display(self):
        self.queue_list.clear()
        icons = {"waiting": "⏳", "downloading": "⬇️", "done": "✅"}
        for item in self.queue:
            self.queue_list.addItem(f"{icons.get(item.status, '')} {item.url}")
        has_waiting = any(item.status == "waiting" for item in self.queue)
        self.start_queue_btn.setEnabled(has_waiting)

    def on_start_queue(self):
        if not self.queue:
            QMessageBox.information(self, "情報", "キューが空です。")
            return
        self.start_queue()

    def start_queue(self):
        if any(item.status == "waiting" for item in self.queue):
            self.progress.setValue(0)
            self.status_label.setText("")
        while len(self.active_workers) < self.max_workers:
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
        self.log("キャンセルを要求しました（ダウンロード中はすぐ、変換・音量調整中は工程の合間で止まります）")

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
            self.status_label.setText("キャンセルしました")

    def on_item_completed(self, item, dest_path):
        if item in self.queue:
            item.status = "done"
            if dest_path:
                self.last_dest_path = dest_path
                self.open_folder_btn.setEnabled(True)
                self.notify_user("ダウンロード完了", os.path.basename(dest_path))
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
            self.status_label.setText("完了")

    def on_clear_queue(self):
        self.queue = [i for i in self.queue if i.status != "waiting"]
        self.update_queue_display()
        self.log("キューをクリアしました。")

    # ---------- その他 ----------
    def on_open_folder(self):
        if self.last_dest_path:
            os.startfile(os.path.dirname(self.last_dest_path))

    def on_settings(self):
        dlg = SettingsDialog(self, self.config)
        if dlg.exec() == QDialog.Accepted:
            self.config = dlg.get_config()
            save_config(self.config)
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
        self.setWindowTitle("YouTube検索")
        self.resize(660, 480)
        self._thread = None

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.keyword_ctrl = QLineEdit()
        self.keyword_ctrl.setPlaceholderText("キーワードを入力")
        self.keyword_ctrl.returnPressed.connect(self.on_search)
        row.addWidget(self.keyword_ctrl, 1)
        self.search_btn = QPushButton("検索")
        self.search_btn.clicked.connect(self.on_search)
        row.addWidget(self.search_btn)
        layout.addLayout(row)

        self.status_label = QLabel("キーワードを入力して検索してください（最大10件）")
        self.status_label.setObjectName("muted")
        layout.addWidget(self.status_label)

        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.results_list.itemDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.results_list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        add_btn = QPushButton("選択をキューに追加")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.on_add_selected)
        btn_row.addWidget(add_btn)
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.keyword_ctrl.setFocus()

    def on_search(self):
        keyword = self.keyword_ctrl.text().strip()
        if not keyword:
            return
        self.search_btn.setEnabled(False)
        self.status_label.setText("検索中...")
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
            item.setData(Qt.UserRole, r['url'])
            self.results_list.addItem(item)
        if results:
            self.status_label.setText(f"{len(results)}件見つかりました。複数選択もできます")
        else:
            self.status_label.setText("見つかりませんでした")

    def on_failed(self, message):
        self.search_btn.setEnabled(True)
        self.status_label.setText(f"検索に失敗しました: {message}")

    def selected_urls(self):
        return [item.data(Qt.UserRole) for item in self.results_list.selectedItems()]

    def on_add_selected(self):
        if not self.selected_urls():
            QMessageBox.information(self, "情報", "結果を選択してください。")
            return
        self.accept()

    def on_double_click(self, item):
        self.results_list.clearSelection()
        item.setSelected(True)
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("設定")
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
        fmt_row.addWidget(QLabel("フォーマット:"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["mp3", "m4a", "wav", "flac"])
        self.fmt_combo.setCurrentText(self.config["output_format"])
        fmt_row.addWidget(self.fmt_combo, 1)
        out_layout.addLayout(fmt_row)

        br_row = QHBoxLayout()
        br_row.addWidget(QLabel("ビットレート:"))
        self.br_combo = QComboBox()
        self.br_combo.addItems(["128k", "160k", "192k", "256k", "320k"])
        self.br_combo.setCurrentText(self.config["bitrate"])
        br_row.addWidget(self.br_combo, 1)
        out_layout.addLayout(br_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("保存先:"))
        self.folder_ctrl = QLineEdit(self.config["output_folder"])
        folder_row.addWidget(self.folder_ctrl, 1)
        browse_btn = QPushButton("参照")
        browse_btn.clicked.connect(self.on_browse_folder)
        folder_row.addWidget(browse_btn)
        out_layout.addLayout(folder_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("ファイル名パターン:"))
        self.name_template_ctrl = QLineEdit(self.config.get("name_template", "{title}"))
        self.name_template_ctrl.setPlaceholderText("{title} - {uploader}")
        name_row.addWidget(self.name_template_ctrl, 1)
        out_layout.addLayout(name_row)
        out_layout.addStretch()
        tabs.addTab(output_tab, "出力")

        # 処理タブ
        proc_tab = QWidget()
        proc_layout = QVBoxLayout(proc_tab)
        self.normalize_cb = QCheckBox("音量正規化")
        self.normalize_cb.setChecked(self.config["normalize"])
        self.normalize_cb.toggled.connect(self.on_normalize_toggle)
        proc_layout.addWidget(self.normalize_cb)
        lufs_row = QHBoxLayout()
        lufs_row.addWidget(QLabel("目標 LUFS:"))
        self.lufs_spin = QDoubleSpinBox()
        self.lufs_spin.setRange(-70.0, 0.0)
        self.lufs_spin.setSingleStep(0.5)
        self.lufs_spin.setDecimals(1)
        self.lufs_spin.setValue(self.config["target_lufs"])
        lufs_row.addWidget(self.lufs_spin)
        lufs_row.addStretch()
        proc_layout.addLayout(lufs_row)
        self.meta_cb = QCheckBox("メタデータ埋め込み")
        self.meta_cb.setChecked(self.config["embed_metadata"])
        proc_layout.addWidget(self.meta_cb)
        proc_layout.addStretch()
        self.on_normalize_toggle()
        tabs.addTab(proc_tab, "処理")

        # 通知タブ
        notif_tab = QWidget()
        notif_layout = QVBoxLayout(notif_tab)
        self.sound_cb = QCheckBox("完了時に通知音を鳴らす")
        self.sound_cb.setChecked(self.config.get("notify_sound", True))
        notif_layout.addWidget(self.sound_cb)
        self.toast_cb = QCheckBox("完了時にトースト通知を表示")
        self.toast_cb.setChecked(self.config.get("notify_toast", True))
        notif_layout.addWidget(self.toast_cb)
        notif_layout.addStretch()
        tabs.addTab(notif_tab, "通知")

        # 一般タブ
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        self.dark_cb = QCheckBox("ダークモード")
        self.dark_cb.setChecked(self.config.get("dark_mode", False))
        self.dark_cb.toggled.connect(self.on_dark_toggle)
        general_layout.addWidget(self.dark_cb)
        self.clipboard_cb = QCheckBox("クリップボードを監視してURLを自動入力")
        self.clipboard_cb.setChecked(self.config.get("clipboard_monitor", False))
        general_layout.addWidget(self.clipboard_cb)
        general_layout.addStretch()
        tabs.addTab(general_tab, "一般")

        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("primary")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("キャンセル")
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
            self, "フォルダを選択", self.folder_ctrl.text())
        if path:
            self.folder_ctrl.setText(path)

    def get_config(self):
        self.config["output_format"] = self.fmt_combo.currentText()
        self.config["bitrate"] = self.br_combo.currentText()
        self.config["output_folder"] = self.folder_ctrl.text()
        self.config["target_lufs"] = self.lufs_spin.value()
        self.config["normalize"] = self.normalize_cb.isChecked()
        self.config["embed_metadata"] = self.meta_cb.isChecked()
        self.config["dark_mode"] = self.dark_cb.isChecked()
        self.config["notify_sound"] = self.sound_cb.isChecked()
        self.config["notify_toast"] = self.toast_cb.isChecked()
        self.config["clipboard_monitor"] = self.clipboard_cb.isChecked()
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
