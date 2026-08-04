import wx
import wx.adv
import os
import threading
import math
import winsound
import time
from downloader import download_audio
from audio_processor import (
    normalize_audio, embed_metadata,
    get_ffmpeg_info, check_ffmpeg, download_ffmpeg
)

def create_gear_bitmap(size=24, color=wx.Colour(80, 80, 80)):
    bitmap = wx.Bitmap(size, size)
    mdc = wx.MemoryDC(bitmap)
    mdc.SetBackground(wx.Brush(wx.Colour(240, 240, 240)))
    mdc.Clear()
    gc = wx.GraphicsContext.Create(mdc)
    gc.SetPen(wx.Pen(color, 2))
    gc.SetBrush(wx.Brush(color))
    cx, cy = size/2, size/2
    r_outer = size/2 - 3
    r_inner = r_outer - 5
    gc.DrawEllipse(cx - r_outer, cy - r_outer, r_outer*2, r_outer*2)
    gc.SetBrush(wx.Brush(wx.Colour(240, 240, 240)))
    gc.DrawEllipse(cx - r_inner, cy - r_inner, r_inner*2, r_inner*2)
    gc.SetBrush(wx.Brush(color))
    tooth_w = 4
    tooth_h = 6
    for angle in range(0, 360, 45):
        rad = angle * math.pi / 180
        tx = cx + (r_outer - 1) * math.cos(rad) - tooth_w/2
        ty = cy + (r_outer - 1) * math.sin(rad) - tooth_h/2
        gc.DrawRectangle(tx, ty, tooth_w, tooth_h)
    del gc
    mdc.SelectObject(wx.NullBitmap)
    return bitmap

def create_folder_bitmap(size=24, color=wx.Colour(80, 80, 80)):
    bitmap = wx.Bitmap(size, size)
    mdc = wx.MemoryDC(bitmap)
    mdc.SetBackground(wx.Brush(wx.Colour(240, 240, 240)))
    mdc.Clear()
    gc = wx.GraphicsContext.Create(mdc)
    gc.SetPen(wx.Pen(color, 2))
    gc.SetBrush(wx.Brush(color))
    gc.DrawRectangle(2, size/3, size-4, size*2/3-2)
    gc.DrawRectangle(2, size/3, size/2, size/6)
    del gc
    mdc.SelectObject(wx.NullBitmap)
    return bitmap


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
                progress_hook=None,
                start_sec=self.item.start_sec,
                end_sec=self.item.end_sec,
                name_template=name_template
            )
            wx.CallAfter(self.parent.log, "[1/3] ダウンロード完了")
            temp_out = data['temp_raw']

            if self.config["normalize"] and check_ffmpeg(self.parent.ffmpeg_info['path']):
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
        super().__init__(None, title="VibeDL - Audio Downloader", size=(850, 650))
        self.ffmpeg_info = get_ffmpeg_info()
        self.config = {
            "target_lufs": -14.0,
            "output_folder": os.path.join(os.path.expanduser("~"), "downloads"),
            "output_format": "mp3",
            "bitrate": "256k",
            "normalize": True,
            "embed_metadata": True,
            "dark_mode": False,
            "notify_sound": True,
            "notify_toast": True,
            "clipboard_monitor": False,
            "url_history": [],
            "name_template": "{title}"
        }
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
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        input_sizer = wx.FlexGridSizer(rows=3, cols=2, vgap=10, hgap=10)
        input_sizer.AddGrowableCol(1, 1)

        url_label = wx.StaticText(self.panel, label="YouTube URL:")
        self.url_ctrl = wx.ComboBox(self.panel, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER)
        self.url_ctrl.SetHint("https://www.youtube.com/...")
        self.url_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_add_to_queue)
        self._populate_url_history()
        input_sizer.Add(url_label, 0, wx.ALIGN_CENTER_VERTICAL)
        input_sizer.Add(self.url_ctrl, 1, wx.EXPAND)

        start_label = wx.StaticText(self.panel, label="開始 (秒 / mm:ss):")
        start_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_ctrl = wx.TextCtrl(self.panel, size=(100, -1))
        self.start_ctrl.SetHint("0:00")
        start_sizer.Add(self.start_ctrl, 0)
        start_sizer.AddStretchSpacer()
        input_sizer.Add(start_label, 0, wx.ALIGN_CENTER_VERTICAL)
        input_sizer.Add(start_sizer, 1, wx.EXPAND)

        end_label = wx.StaticText(self.panel, label="終了 (秒 / mm:ss):")
        end_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.end_ctrl = wx.TextCtrl(self.panel, size=(100, -1))
        self.end_ctrl.SetHint("3:00")
        end_sizer.Add(self.end_ctrl, 0)
        end_sizer.AddStretchSpacer()
        input_sizer.Add(end_label, 0, wx.ALIGN_CENTER_VERTICAL)
        input_sizer.Add(end_sizer, 1, wx.EXPAND)

        main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.ALL, 15)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.add_queue_btn = wx.Button(self.panel, label="キューに追加", size=(140, 32))
        self.add_queue_btn.Bind(wx.EVT_BUTTON, self.on_add_to_queue)
        btn_sizer.Add(self.add_queue_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        self.start_queue_btn = wx.Button(self.panel, label="キューを開始", size=(140, 32))
        self.start_queue_btn.SetBackgroundColour(wx.Colour(0, 150, 0))
        self.start_queue_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        self.start_queue_btn.Bind(wx.EVT_BUTTON, self.on_start_queue)
        btn_sizer.Add(self.start_queue_btn, 0, wx.LEFT, 10)

        self.clear_queue_btn = wx.Button(self.panel, label="キューをクリア", size=(120, 32))
        self.clear_queue_btn.Bind(wx.EVT_BUTTON, self.on_clear_queue)
        btn_sizer.Add(self.clear_queue_btn, 0, wx.LEFT, 10)

        btn_sizer.AddStretchSpacer()

        gear_bmp = create_gear_bitmap()
        folder_bmp = create_folder_bitmap()

        self.open_folder_btn = wx.BitmapButton(self.panel, bitmap=folder_bmp, size=(32, 32))
        self.open_folder_btn.SetToolTip("最後に保存したフォルダを開く")
        self.open_folder_btn.Bind(wx.EVT_BUTTON, self.on_open_folder)
        self.open_folder_btn.Enable(False)
        btn_sizer.Add(self.open_folder_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)

        self.settings_btn = wx.BitmapButton(self.panel, bitmap=gear_bmp, size=(32, 32))
        self.settings_btn.SetToolTip("設定")
        self.settings_btn.Bind(wx.EVT_BUTTON, self.on_settings)
        btn_sizer.Add(self.settings_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        queue_sizer = wx.BoxSizer(wx.HORIZONTAL)
        queue_sizer.Add(wx.StaticText(self.panel, label="キュー:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.queue_list = wx.ListBox(self.panel, size=(-1, 80))
        queue_sizer.Add(self.queue_list, 1, wx.EXPAND)
        main_sizer.Add(queue_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)

        self.progress = wx.Gauge(self.panel, range=100, style=wx.GA_HORIZONTAL)
        self.progress.SetValue(0)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.log_ctrl = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        main_sizer.Add(self.log_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        settings_display = wx.BoxSizer(wx.HORIZONTAL)
        font = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_LIGHT)
        self.fmt_text = wx.StaticText(self.panel, label=f"フォーマット: {self.config['output_format']} / {self.config['bitrate']}")
        self.fmt_text.SetFont(font)
        settings_display.Add(self.fmt_text, 0, wx.RIGHT, 20)
        self.norm_text = wx.StaticText(self.panel, label=f"正規化: {'ON' if self.config['normalize'] else 'OFF'} ({self.config['target_lufs']} LUFS)")
        self.norm_text.SetFont(font)
        settings_display.Add(self.norm_text, 0, wx.RIGHT, 20)
        self.meta_text = wx.StaticText(self.panel, label=f"メタデータ: {'ON' if self.config['embed_metadata'] else 'OFF'}")
        self.meta_text.SetFont(font)
        settings_display.Add(self.meta_text, 0)
        main_sizer.Add(settings_display, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)

        self.panel.SetSizer(main_sizer)

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

    def update_clipboard_monitor(self):
        if self.config.get("clipboard_monitor", False):
            self.clipboard_timer.Start(1000)
        else:
            self.clipboard_timer.Stop()

    def on_clipboard_timer(self, event):
        if not wx.TheClipboard.IsOpened():
            try:
                if wx.TheClipboard.Open():
                    if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
                        data = wx.TextDataObject()
                        wx.TheClipboard.GetData(data)
                        text = data.GetText().strip()
                        if ("youtube.com/watch" in text or "youtu.be/" in text) and text.startswith("http"):
                            current = self.url_ctrl.GetValue().strip()
                            if text != current:
                                self.url_ctrl.SetValue(text)
                                self.log("🔗 クリップボードからURLを貼り付けました")
                    wx.TheClipboard.Close()
            except:
                pass

    def apply_theme(self):
        dark = self.config.get("dark_mode", False)
        if dark:
            bg = wx.Colour(45, 45, 48)
            fg = wx.Colour(255, 255, 255)
            entry_bg = wx.Colour(60, 60, 60)
            log_bg = wx.Colour(30, 30, 30)
            btn_bg = wx.Colour(85, 85, 85)
        else:
            bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
            entry_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            log_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            btn_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)

        self.SetBackgroundColour(bg)
        self.panel.SetBackgroundColour(bg)

        for child in self.panel.GetChildren():
            if isinstance(child, wx.StaticText):
                child.SetForegroundColour(fg)
            elif isinstance(child, wx.TextCtrl) and child != self.log_ctrl:
                child.SetBackgroundColour(entry_bg)
                child.SetForegroundColour(fg)
            elif isinstance(child, wx.Button):
                if child in (self.start_queue_btn, self.add_queue_btn):
                    continue
                child.SetBackgroundColour(btn_bg)
                child.SetForegroundColour(fg)
            elif isinstance(child, wx.BitmapButton):
                child.SetBackgroundColour(btn_bg)
            elif isinstance(child, wx.ComboBox):
                child.SetBackgroundColour(entry_bg)
                child.SetForegroundColour(fg)
            elif isinstance(child, wx.ListBox):
                child.SetBackgroundColour(entry_bg)
                child.SetForegroundColour(fg)

        self.log_ctrl.SetBackgroundColour(log_bg)
        self.log_ctrl.SetForegroundColour(fg)
        self.progress.SetBackgroundColour(bg)

        self.Refresh()

    def update_settings_display(self):
        self.fmt_text.SetLabel(f"フォーマット: {self.config['output_format']} / {self.config['bitrate']}")
        self.norm_text.SetLabel(f"正規化: {'ON' if self.config['normalize'] else 'OFF'} ({self.config['target_lufs']} LUFS)")
        self.meta_text.SetLabel(f"メタデータ: {'ON' if self.config['embed_metadata'] else 'OFF'}")

    def log(self, msg):
        self.log_ctrl.AppendText(msg + "\n")

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
        start_sec = self.parse_time(self.start_ctrl.GetValue().strip())
        end_sec = self.parse_time(self.end_ctrl.GetValue().strip())
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

    def on_start_queue(self, event):
        if not self.queue:
            wx.MessageBox("キューが空です。", "情報", wx.OK | wx.ICON_INFORMATION)
            return
        self.start_queue()

    def start_queue(self):
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

    def on_clear_queue(self, event):
        for item in self.queue:
            if item.status == "waiting":
                self.queue.remove(item)
        self.update_queue_display()
        self.log("キューをクリアしました。")

    def parse_time(self, timestr):
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

    def on_open_folder(self, event):
        if self.last_dest_path:
            folder = os.path.dirname(self.last_dest_path)
            os.startfile(folder)

    def on_settings(self, event):
        dlg = SettingsDialog(self, self.config)
        if dlg.ShowModal() == wx.ID_OK:
            self.config = dlg.GetConfig()
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
        dark = self.dark_cb.GetValue()
        if dark:
            bg = wx.Colour(45, 45, 48)
            fg = wx.Colour(255, 255, 255)
            entry_bg = wx.Colour(60, 60, 60)
            btn_bg = wx.Colour(85, 85, 85)
        else:
            bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
            entry_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            btn_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)

        self.SetBackgroundColour(bg)
        self.panel.SetBackgroundColour(bg)

        for page_index in range(self.notebook.GetPageCount()):
            page = self.notebook.GetPage(page_index)
            page.SetBackgroundColour(bg)
            for child in page.GetChildren():
                if isinstance(child, wx.StaticText):
                    child.SetForegroundColour(fg)
                elif isinstance(child, wx.TextCtrl):
                    child.SetBackgroundColour(entry_bg)
                    child.SetForegroundColour(fg)
                elif isinstance(child, wx.Button):
                    child.SetBackgroundColour(btn_bg)
                    child.SetForegroundColour(fg)
                elif isinstance(child, wx.ComboBox):
                    child.SetBackgroundColour(entry_bg)
                    child.SetForegroundColour(fg)
                elif isinstance(child, wx.CheckBox):
                    child.SetForegroundColour(fg)
                elif isinstance(child, wx.SpinCtrlDouble):
                    child.SetBackgroundColour(entry_bg)
                    child.SetForegroundColour(fg)

        self.Refresh()

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