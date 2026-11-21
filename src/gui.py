import wx
import wx.adv
import os
import threading
import winsound
from downloader import download_audio
from audio_processor import (
    normalize_audio, embed_metadata,
    get_ffmpeg_info, check_ffmpeg, download_ffmpeg
)
from config_store import get_config, save_config

ACCENT = wx.Colour(124, 92, 255)  # バイオレット（ブランドカラー）


def get_palette(dark):
    """テーマ色一式。bg（土台）より surface（カード）を一段明るくして奥行きを出す。"""
    if dark:
        return {
            "bg": wx.Colour(32, 34, 40),
            "surface": wx.Colour(43, 46, 53),
            "fg": wx.Colour(242, 242, 242),
            "muted": wx.Colour(167, 171, 179),
            "entry_bg": wx.Colour(28, 30, 35),
            "log_bg": wx.Colour(24, 26, 30),
            "btn_bg": wx.Colour(58, 62, 71),
            "accent": ACCENT,
            "accent_fg": wx.Colour(255, 255, 255),
            "track": wx.Colour(58, 62, 71),
        }
    return {
        "bg": wx.Colour(233, 235, 239),
        "surface": wx.Colour(255, 255, 255),
        "fg": wx.Colour(28, 30, 34),
        "muted": wx.Colour(110, 115, 122),
        "entry_bg": wx.Colour(255, 255, 255),
        "log_bg": wx.Colour(255, 255, 255),
        "btn_bg": wx.Colour(255, 255, 255),
        "accent": ACCENT,
        "accent_fg": wx.Colour(255, 255, 255),
        "track": wx.Colour(214, 217, 222),
    }


class ProgressBar(wx.Panel):
    """自前描画のプログレスバー。

    標準の wx.Gauge はダークモードでも白い帯になって浮くため、
    パレット色で角丸バーと％文字を描く。
    """

    def __init__(self, parent):
        super().__init__(parent, size=(-1, 22))
        self._percent = 0
        self._palette = get_palette(False)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def set_palette(self, palette):
        self._palette = palette
        self.Refresh()

    def SetValue(self, percent):
        self._percent = max(0, min(100, int(percent)))
        self.Refresh()

    def GetValue(self):
        return self._percent

    def _on_paint(self, event):
        dc = wx.PaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        w, h = self.GetSize()
        if w <= 0 or h <= 0:
            return
        track = self._palette["track"]
        dc.SetBrush(wx.Brush(track))
        dc.SetPen(wx.Pen(track))
        dc.DrawRoundedRectangle(0, 0, w, h, 6)
        if self._percent > 0:
            fill_w = max(h, int(w * self._percent / 100))
            accent = self._palette["accent"]
            dc.SetBrush(wx.Brush(accent))
            dc.SetPen(wx.Pen(accent))
            dc.DrawRoundedRectangle(0, 0, fill_w, h, 6)
        font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        text = f"{self._percent}%"
        tw, th = dc.GetTextExtent(text)
        # 中央が塗りの上なら白文字、トラックの上なら通常色
        if self._percent >= 50:
            dc.SetTextForeground(self._palette["accent_fg"])
        else:
            dc.SetTextForeground(self._palette["fg"])
        dc.DrawText(text, (w - tw) // 2, (h - th) // 2)


def apply_theme_recursive(window, dark, accent_controls=()):
    """ウィンドウ配下の全コントロールへテーマを再帰適用する。

    以前はパネル直下の子だけが対象で、入れ子のコントロールや
    設定ダイアログの一部にテーマが効いていなかった。
    accent_controls に渡したボタンは強調表示のまま維持する。
    """
    palette = get_palette(dark)
    window.SetBackgroundColour(palette["bg"])
    for child in window.GetChildren():
        if isinstance(child, wx.StaticText):
            child.SetForegroundColour(palette["fg"])
        elif isinstance(child, (wx.TextCtrl, wx.ComboBox, wx.ListBox, wx.SpinCtrlDouble)):
            child.SetBackgroundColour(palette["entry_bg"])
            child.SetForegroundColour(palette["fg"])
        elif isinstance(child, (wx.Button, wx.BitmapButton)):
            if child not in accent_controls:
                child.SetBackgroundColour(palette["btn_bg"])
                child.SetForegroundColour(palette["fg"])
        elif isinstance(child, wx.CheckBox):
            child.SetForegroundColour(palette["fg"])
        apply_theme_recursive(child, dark, accent_controls)
    window.Refresh()


def make_section_label(parent, text):
    label = wx.StaticText(parent, label=text)
    label.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
    label.SetForegroundColour(ACCENT)
    return label


def make_card(parent):
    """カード型の土台パネルと、その内側サイザーを返す。"""
    card = wx.Panel(parent)
    sizer = wx.BoxSizer(wx.VERTICAL)
    card.SetSizer(sizer)
    return card, sizer


class QueueItem:
    def __init__(self, url, start_sec, end_sec):
        self.url = url
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.status = "waiting"

class DownloadWorker(threading.Thread):
    def __init__(self, parent, item, config):
        super().__init__()
        self.parent = parent
        self.item = item
        self.config = config
        self.daemon = True

    def _progress_hook(self, d):
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            percent = int(downloaded / total * 100) if total else 0
            speed = (d.get('_speed_str') or '').strip()
            eta = (d.get('_eta_str') or '').strip()
            wx.CallAfter(self.parent.on_download_progress, percent, speed, eta)
        elif d.get('status') == 'finished':
            wx.CallAfter(self.parent.on_download_progress, 100, "", "")

    def run(self):
        try:
            self.item.status = "downloading"
            wx.CallAfter(self.parent.update_queue_display)
            wx.CallAfter(self.parent.log, f"処理中: {self.item.url}")
            output_dir = self.config["output_folder"]
            fmt = self.config["output_format"]
            br = self.config["bitrate"]
            name_template = self.config.get("name_template", "{title}")

            data = download_audio(
                self.item.url, output_dir,
                output_format=fmt, bitrate=br,
                progress_hook=self._progress_hook,
                start_sec=self.item.start_sec,
                end_sec=self.item.end_sec,
                name_template=name_template
            )
            wx.CallAfter(self.parent.log, "[1/3] ダウンロード完了")
            temp_out = data['temp_raw']

            if self.config["normalize"] and check_ffmpeg(self.parent.ffmpeg_info['path']):
                wx.CallAfter(self.parent.set_status_label, "音量最適化中...")
                wx.CallAfter(self.parent.log, "[2/3] 音量最適化中...")
                normalized = normalize_audio(temp_out, self.config["target_lufs"],
                                             ffmpeg_info=self.parent.ffmpeg_info)
                if normalized:
                    temp_out = normalized
                    wx.CallAfter(self.parent.log, "音量調整完了")
                else:
                    wx.CallAfter(self.parent.log, "音量調整に失敗しました。")
            else:
                wx.CallAfter(self.parent.log, "音量正規化をスキップ")

            if self.config["embed_metadata"]:
                wx.CallAfter(self.parent.set_status_label, "メタデータ埋め込み中...")
                wx.CallAfter(self.parent.log, "[3/3] メタデータ埋め込み中...")
                embed_metadata(temp_out, data['title'], data['uploader'], data['thumb'])

            if os.path.exists(data['dest_path']):
                os.remove(data['dest_path'])
            os.rename(temp_out, data['dest_path'])

            if os.path.exists(data['temp_raw']) and data['temp_raw'] != temp_out:
                os.remove(data['temp_raw'])

            wx.CallAfter(self.parent.log, f"✨ 完了: {data['dest_path']}")
            wx.CallAfter(self.parent.on_item_completed, self.item, data['dest_path'])
        except Exception as e:
            wx.CallAfter(self.parent.log, f"❌ エラー ({self.item.url}): {e}")
            wx.CallAfter(self.parent.on_item_completed, self.item, None)


class VibeDLFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="VibeDL - Audio Downloader", size=(880, 660))
        self.SetMinSize((760, 560))
        self.ffmpeg_info = get_ffmpeg_info()
        # 設定はレジストリから読み込む（CLI版と共通）。
        # 以前は起動ごとの初期値で、設定も履歴も保存されなかった。
        self.config = get_config()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.queue = []
        self.active_workers = []
        self.max_workers = 2
        self.last_dest_path = None
        self.clipboard_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_clipboard_timer, self.clipboard_timer)
        self.init_ui()
        self.apply_theme()
        self.update_settings_display()
        self.check_ffmpeg_on_startup()
        self.update_clipboard_monitor()
        self.Centre()

    def init_ui(self):
        self.panel = wx.Panel(self)
        self.panel.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._cards = []

        # --- カード1: 入力 + 操作ボタン ---
        card, card_sizer = make_card(self.panel)
        self._cards.append(card)
        card_sizer.Add(make_section_label(card, "ダウンロード"), 0, wx.ALL, 12)

        input_sizer = wx.FlexGridSizer(rows=3, cols=2, vgap=10, hgap=10)
        input_sizer.AddGrowableCol(1, 1)

        url_label = wx.StaticText(card, label="YouTube URL:")
        self.url_ctrl = wx.ComboBox(card, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER, size=(-1, 30))
        self.url_ctrl.SetHint("https://www.youtube.com/...")
        self.url_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_add_to_queue)
        self._populate_url_history()
        input_sizer.Add(url_label, 0, wx.ALIGN_CENTER_VERTICAL)
        input_sizer.Add(self.url_ctrl, 1, wx.EXPAND)

        start_label = wx.StaticText(card, label="開始 (秒 / mm:ss):")
        self.start_ctrl = wx.TextCtrl(card, size=(110, 28))
        self.start_ctrl.SetHint("0:00")
        input_sizer.Add(start_label, 0, wx.ALIGN_CENTER_VERTICAL)
        input_sizer.Add(self.start_ctrl, 0)

        end_label = wx.StaticText(card, label="終了 (秒 / mm:ss):")
        self.end_ctrl = wx.TextCtrl(card, size=(110, 28))
        self.end_ctrl.SetHint("3:00")
        input_sizer.Add(end_label, 0, wx.ALIGN_CENTER_VERTICAL)
        input_sizer.Add(self.end_ctrl, 0)

        card_sizer.Add(input_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_queue_btn = wx.Button(card, label="キューに追加", size=(140, 36))
        self.add_queue_btn.Bind(wx.EVT_BUTTON, self.on_add_to_queue)
        btn_sizer.Add(self.add_queue_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        self.start_queue_btn = wx.Button(card, label="キューを開始", size=(140, 36))
        self.start_queue_btn.SetBackgroundColour(ACCENT)
        self.start_queue_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        start_font = self.start_queue_btn.GetFont()
        start_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.start_queue_btn.SetFont(start_font)
        self.start_queue_btn.Bind(wx.EVT_BUTTON, self.on_start_queue)
        self.start_queue_btn.Enable(False)
        btn_sizer.Add(self.start_queue_btn, 0, wx.LEFT, 10)

        self.clear_queue_btn = wx.Button(card, label="キューをクリア", size=(120, 36))
        self.clear_queue_btn.Bind(wx.EVT_BUTTON, self.on_clear_queue)
        btn_sizer.Add(self.clear_queue_btn, 0, wx.LEFT, 10)

        btn_sizer.AddStretchSpacer()

        self.open_folder_btn = wx.Button(card, label="フォルダを開く", size=(120, 36))
        self.open_folder_btn.SetToolTip("最後に保存したフォルダを開く")
        self.open_folder_btn.Bind(wx.EVT_BUTTON, self.on_open_folder)
        self.open_folder_btn.Enable(False)
        btn_sizer.Add(self.open_folder_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        self.settings_btn = wx.Button(card, label="設定", size=(80, 36))
        self.settings_btn.Bind(wx.EVT_BUTTON, self.on_settings)
        btn_sizer.Add(self.settings_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        card_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 12)
        main_sizer.Add(card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # --- カード2: キュー + 進捗 ---
        card2, card2_sizer = make_card(self.panel)
        self._cards.append(card2)
        card2_sizer.Add(make_section_label(card2, "キュー"), 0, wx.ALL, 12)
        self.queue_list = wx.ListBox(card2, size=(-1, 100), style=wx.BORDER_NONE)
        card2_sizer.Add(self.queue_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        self.progress = ProgressBar(card2)
        card2_sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.status_label = wx.StaticText(card2, label="")
        card2_sizer.Add(self.status_label, 0, wx.EXPAND | wx.ALL, 12)
        main_sizer.Add(card2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # --- カード3: ログ ---
        card3, card3_sizer = make_card(self.panel)
        self._cards.append(card3)
        card3_sizer.Add(make_section_label(card3, "ログ"), 0, wx.ALL, 12)
        self.log_ctrl = wx.TextCtrl(card3, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.BORDER_NONE)
        self.log_ctrl.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        card3_sizer.Add(self.log_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        main_sizer.Add(card3, 1, wx.EXPAND | wx.ALL, 10)

        self.panel.SetSizer(main_sizer)

        # 設定サマリはステータスバーへ（画面下端に常駐して見やすく）
        self.CreateStatusBar(3)
        self.SetStatusWidths([-3, -2, -2])

    def _populate_url_history(self):
        self.url_ctrl.Clear()
        history = self.config.get("url_history", [])
        for url in history:
            self.url_ctrl.Append(url)

    def add_to_history(self, url):
        history = self.config.get("url_history", [])
        if url in history:
            history.remove(url)
        history.insert(0, url)
        if len(history) > 10:
            history = history[:10]
        self.config["url_history"] = history
        self._populate_url_history()
        save_config(self.config)

    def on_close(self, event):
        save_config(self.config)
        event.Skip()

    def update_clipboard_monitor(self):
        if self.config.get("clipboard_monitor", False):
            self.clipboard_timer.Start(1000)
        else:
            self.clipboard_timer.Stop()

    def on_clipboard_timer(self, event):
        if wx.TheClipboard.IsOpened():
            return
        if not wx.TheClipboard.Open():
            return
        try:
            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
                data = wx.TextDataObject()
                wx.TheClipboard.GetData(data)
                text = data.GetText().strip()
                if ("youtube.com/watch" in text or "youtu.be/" in text) and text.startswith("http"):
                    current = self.url_ctrl.GetValue().strip()
                    if text != current:
                        self.url_ctrl.SetValue(text)
                        self.log("🔗 クリップボードからURLを貼り付けました")
        except Exception:
            pass
        finally:
            # 例外時も必ず閉じる（開いたままだと他のアプリが使えない）
            wx.TheClipboard.Close()

    def apply_theme(self):
        dark = self.config.get("dark_mode", False)
        palette = get_palette(dark)
        apply_theme_recursive(self, dark,
                              accent_controls=(self.start_queue_btn,))
        # カードは土台より一段明るい surface 色にして奥行きを出す
        for card in self._cards:
            card.SetBackgroundColour(palette["surface"])
        # ログ欄だけ背景を一段暗くする
        self.log_ctrl.SetBackgroundColour(palette["log_bg"])
        self.log_ctrl.SetForegroundColour(palette["fg"])
        self.progress.set_palette(palette)
        status_bar = self.GetStatusBar()
        if status_bar:
            status_bar.SetBackgroundColour(palette["bg"])
            status_bar.SetForegroundColour(palette["muted"])
        self.Refresh()

    def update_settings_display(self):
        self.SetStatusText(f"フォーマット: {self.config['output_format']} / {self.config['bitrate']}", 0)
        self.SetStatusText(f"正規化: {'ON' if self.config['normalize'] else 'OFF'} ({self.config['target_lufs']} LUFS)", 1)
        self.SetStatusText(f"メタデータ: {'ON' if self.config['embed_metadata'] else 'OFF'}", 2)

    def log(self, msg):
        self.log_ctrl.AppendText(msg + "\n")

    def on_download_progress(self, percent, speed="", eta=""):
        self.progress.SetValue(percent)
        parts = []
        if speed:
            parts.append(f"速度: {speed}")
        if eta:
            parts.append(f"残り: {eta}")
        self.status_label.SetLabel("  ".join(parts))

    def set_status_label(self, text):
        self.status_label.SetLabel(text)

    def notify_user(self, title, message):
        if self.config.get("notify_sound", True):
            winsound.MessageBeep(winsound.MB_OK)
        if self.config.get("notify_toast", True):
            notify = wx.adv.NotificationMessage(title=title, message=message, parent=self)
            notify.Show(timeout=5)

    def check_ffmpeg_on_startup(self):
        if not check_ffmpeg(self.ffmpeg_info['path']):
            dlg = wx.MessageDialog(self,
                                   "FFmpegが見つかりません。自動ダウンロードしますか？",
                                   "FFmpeg 未検出",
                                   wx.YES_NO | wx.ICON_QUESTION)
            if dlg.ShowModal() == wx.ID_YES:
                self.log("FFmpegをダウンロード中...")
                progress_dlg = wx.ProgressDialog("FFmpeg ダウンロード",
                                                 "ダウンロードしています...",
                                                 maximum=100, parent=self,
                                                 style=wx.PD_AUTO_HIDE)
                def progress_callback(done, total):
                    percent = int(done / total * 100) if total else 0
                    wx.CallAfter(progress_dlg.Update, percent, f"{done}/{total} bytes")
                new_path = download_ffmpeg(progress_callback=progress_callback)
                progress_dlg.Destroy()
                if new_path:
                    self.ffmpeg_info = get_ffmpeg_info()
                    self.log("FFmpeg の準備が完了しました。")
                else:
                    self.log("FFmpeg のダウンロードに失敗しました。")
            else:
                self.log("FFmpeg なしで続行します。音量正規化は利用不可。")
            dlg.Destroy()

    def on_add_to_queue(self, event):
        url = self.url_ctrl.GetValue().strip()
        if not url:
            wx.MessageBox("URLを入力してください。", "入力エラー", wx.OK | wx.ICON_WARNING)
            return
        try:
            start_sec = self.parse_time(self.start_ctrl.GetValue())
            end_sec = self.parse_time(self.end_ctrl.GetValue())
        except ValueError:
            wx.MessageBox("開始・終了は「秒」または「mm:ss」で入力してください。",
                          "入力エラー", wx.OK | wx.ICON_WARNING)
            return
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            wx.MessageBox("終了は開始より後を指定してください。",
                          "入力エラー", wx.OK | wx.ICON_WARNING)
            return
        item = QueueItem(url, start_sec, end_sec)
        self.queue.append(item)
        self.update_queue_display()
        self.url_ctrl.SetValue("")
        self.start_ctrl.SetValue("")
        self.end_ctrl.SetValue("")
        self.add_to_history(url)
        self.log(f"キューに追加: {url}")

    def update_queue_display(self):
        self.queue_list.Clear()
        for item in self.queue:
            status = "⏳" if item.status == "waiting" else "⬇️" if item.status == "downloading" else "✅"
            self.queue_list.Append(f"{status} {item.url}")
        has_waiting = any(item.status == "waiting" for item in self.queue)
        self.start_queue_btn.Enable(has_waiting)

    def on_start_queue(self, event):
        if not self.queue:
            wx.MessageBox("キューが空です。", "情報", wx.OK | wx.ICON_INFORMATION)
            return
        self.start_queue()

    def start_queue(self):
        if any(item.status == "waiting" for item in self.queue):
            self.progress.SetValue(0)
            self.status_label.SetLabel("")
        while len(self.active_workers) < self.max_workers:
            waiting = [item for item in self.queue if item.status == "waiting"]
            if not waiting:
                break
            item = waiting[0]
            worker = DownloadWorker(self, item, self.config)
            self.active_workers.append(worker)
            worker.start()

    def on_item_completed(self, item, dest_path):
        if item in self.queue:
            item.status = "done"
            if dest_path:
                self.last_dest_path = dest_path
                self.open_folder_btn.Enable(True)
                self.notify_user("ダウンロード完了", os.path.basename(dest_path))
            self.queue.remove(item)
        self.active_workers = [w for w in self.active_workers if w.is_alive()]
        self.update_queue_display()
        if self.queue:
            self.start_queue()
        elif not self.active_workers:
            self.progress.SetValue(100)
            self.status_label.SetLabel("完了")

    def on_clear_queue(self, event):
        # イテレーション中の remove は要素を飛ばすため、作り直す
        self.queue = [item for item in self.queue if item.status != "waiting"]
        self.update_queue_display()
        self.log("キューをクリアしました。")

    def parse_time(self, timestr):
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

    def on_open_folder(self, event):
        if self.last_dest_path:
            folder = os.path.dirname(self.last_dest_path)
            os.startfile(folder)

    def on_settings(self, event):
        dlg = SettingsDialog(self, self.config)
        if dlg.ShowModal() == wx.ID_OK:
            self.config = dlg.GetConfig()
            save_config(self.config)
            self.apply_theme()
            self.update_settings_display()
            self.update_clipboard_monitor()
        dlg.Destroy()


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, config):
        super().__init__(parent, title="設定", size=(480, 520))
        self.config = config.copy()
        self.parent = parent
        self.init_ui()
        self.apply_theme_to_dialog()
        self.Centre()

    def init_ui(self):
        self.panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        notebook = wx.Notebook(self.panel)
        self.notebook = notebook

        output_panel = wx.Panel(notebook)
        output_sizer = wx.BoxSizer(wx.VERTICAL)
        grid_out = wx.FlexGridSizer(rows=4, cols=2, vgap=10, hgap=10)
        grid_out.AddGrowableCol(1, 1)

        fmt_label = wx.StaticText(output_panel, label="フォーマット:")
        self.fmt_combo = wx.ComboBox(output_panel, choices=["mp3", "m4a", "wav", "flac"],
                                     value=self.config["output_format"],
                                     style=wx.CB_READONLY)
        grid_out.Add(fmt_label, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        grid_out.Add(self.fmt_combo, 1, wx.EXPAND)

        br_label = wx.StaticText(output_panel, label="ビットレート:")
        self.br_combo = wx.ComboBox(output_panel, choices=["128k", "160k", "192k", "256k", "320k"],
                                    value=self.config["bitrate"],
                                    style=wx.CB_READONLY)
        grid_out.Add(br_label, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        grid_out.Add(self.br_combo, 1, wx.EXPAND)

        folder_label = wx.StaticText(output_panel, label="保存先:")
        folder_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.folder_ctrl = wx.TextCtrl(output_panel, value=self.config["output_folder"])
        folder_sizer.Add(self.folder_ctrl, 1, wx.EXPAND)
        browse_btn = wx.Button(output_panel, label="参照")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_folder)
        folder_sizer.Add(browse_btn, 0, wx.LEFT, 5)
        grid_out.Add(folder_label, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        grid_out.Add(folder_sizer, 1, wx.EXPAND)

        name_label = wx.StaticText(output_panel, label="ファイル名パターン:")
        self.name_template_ctrl = wx.TextCtrl(output_panel, value=self.config.get("name_template", "{title}"))
        self.name_template_ctrl.SetHint("{title} - {uploader}")
        grid_out.Add(name_label, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        grid_out.Add(self.name_template_ctrl, 1, wx.EXPAND)

        output_sizer.Add(grid_out, 0, wx.EXPAND | wx.ALL, 15)
        output_panel.SetSizer(output_sizer)
        notebook.AddPage(output_panel, "出力")

        proc_panel = wx.Panel(notebook)
        proc_sizer = wx.BoxSizer(wx.VERTICAL)

        self.normalize_cb = wx.CheckBox(proc_panel, label="音量正規化")
        self.normalize_cb.SetValue(self.config["normalize"])
        self.normalize_cb.Bind(wx.EVT_CHECKBOX, self.on_normalize_toggle)
        proc_sizer.Add(self.normalize_cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 15)

        lufs_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lufs_sizer.Add(wx.StaticText(proc_panel, label="目標 LUFS:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.lufs_spin = wx.SpinCtrlDouble(proc_panel, min=-70.0, max=0.0, initial=self.config["target_lufs"], inc=0.1)
        self.lufs_spin.SetDigits(1)
        lufs_sizer.Add(self.lufs_spin, 0)
        proc_sizer.Add(lufs_sizer, 0, wx.LEFT | wx.RIGHT, 15)

        self.meta_cb = wx.CheckBox(proc_panel, label="メタデータ埋め込み")
        self.meta_cb.SetValue(self.config["embed_metadata"])
        proc_sizer.Add(self.meta_cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.on_normalize_toggle(None)
        proc_panel.SetSizer(proc_sizer)
        notebook.AddPage(proc_panel, "処理")

        notif_panel = wx.Panel(notebook)
        notif_sizer = wx.BoxSizer(wx.VERTICAL)
        self.sound_cb = wx.CheckBox(notif_panel, label="完了時に通知音を鳴らす")
        self.sound_cb.SetValue(self.config.get("notify_sound", True))
        notif_sizer.Add(self.sound_cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 15)
        self.toast_cb = wx.CheckBox(notif_panel, label="完了時にトースト通知を表示")
        self.toast_cb.SetValue(self.config.get("notify_toast", True))
        notif_sizer.Add(self.toast_cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        notif_panel.SetSizer(notif_sizer)
        notebook.AddPage(notif_panel, "通知")

        general_panel = wx.Panel(notebook)
        general_sizer = wx.BoxSizer(wx.VERTICAL)
        self.dark_cb = wx.CheckBox(general_panel, label="ダークモード")
        self.dark_cb.SetValue(self.config.get("dark_mode", False))
        self.dark_cb.Bind(wx.EVT_CHECKBOX, self.on_dark_toggle)
        general_sizer.Add(self.dark_cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 15)
        self.clipboard_cb = wx.CheckBox(general_panel, label="クリップボードを監視してURLを自動入力")
        self.clipboard_cb.SetValue(self.config.get("clipboard_monitor", False))
        general_sizer.Add(self.clipboard_cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        general_panel.SetSizer(general_sizer)
        notebook.AddPage(general_panel, "一般")

        sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(self.panel, wx.ID_OK, "OK")
        cancel_btn = wx.Button(self.panel, wx.ID_CANCEL, "キャンセル")
        btn_sizer.Add(ok_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(cancel_btn, 0)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 15)

        self.panel.SetSizer(sizer)

    def apply_theme_to_dialog(self):
        # メイン画面と共通の再帰テーマ適用を使う
        apply_theme_recursive(self, self.dark_cb.GetValue())

    def on_normalize_toggle(self, event):
        self.lufs_spin.Enable(self.normalize_cb.GetValue())

    def on_dark_toggle(self, event):
        self.apply_theme_to_dialog()

    def on_browse_folder(self, event):
        dlg = wx.DirDialog(self, "フォルダを選択", defaultPath=self.config["output_folder"])
        if dlg.ShowModal() == wx.ID_OK:
            self.folder_ctrl.SetValue(dlg.GetPath())
        dlg.Destroy()

    def GetConfig(self):
        self.config["output_format"] = self.fmt_combo.GetValue()
        self.config["bitrate"] = self.br_combo.GetValue()
        self.config["output_folder"] = self.folder_ctrl.GetValue()
        self.config["target_lufs"] = self.lufs_spin.GetValue()
        self.config["normalize"] = self.normalize_cb.GetValue()
        self.config["embed_metadata"] = self.meta_cb.GetValue()
        self.config["dark_mode"] = self.dark_cb.GetValue()
        self.config["notify_sound"] = self.sound_cb.GetValue()
        self.config["notify_toast"] = self.toast_cb.GetValue()
        self.config["clipboard_monitor"] = self.clipboard_cb.GetValue()
        self.config["name_template"] = self.name_template_ctrl.GetValue().strip() or "{title}"
        return self.config


if __name__ == "__main__":
    app = wx.App()
    frame = VibeDLFrame()
    frame.Show()
    app.MainLoop()