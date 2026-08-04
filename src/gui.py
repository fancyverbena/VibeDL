import wx
import wx.adv
import os
import threading
import math
import winsound

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


class DownloadThread(threading.Thread):
    def __init__(self, parent, url, config, start_sec=None, end_sec=None):
        super().__init__()
        self.parent = parent
        self.url = url
        self.config = config
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.daemon = True

    def run(self):
        try:
            wx.CallAfter(self.parent.update_progress, 0)
            wx.CallAfter(self.parent.log, f"処理中: {self.url}")
            output_dir = self.config["output_folder"]
            fmt = self.config["output_format"]
            br = self.config["bitrate"]

            data = download_audio(
                self.url, output_dir,
                output_format=fmt, bitrate=br,
                progress_hook=None,
                start_sec=self.start_sec,
                end_sec=self.end_sec
            )
            wx.CallAfter(self.parent.log, "[1/3] ダウンロード完了")
            wx.CallAfter(self.parent.update_progress, 33)
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
            wx.CallAfter(self.parent.update_progress, 66)

            if self.config["embed_metadata"]:
                wx.CallAfter(self.parent.log, "[3/3] メタデータ埋め込み中...")
                embed_metadata(temp_out, data['title'], data['uploader'], data['thumb'])
            wx.CallAfter(self.parent.update_progress, 100)

            if os.path.exists(data['dest_path']):
                os.remove(data['dest_path'])
            os.rename(temp_out, data['dest_path'])

            if os.path.exists(data['temp_raw']) and data['temp_raw'] != temp_out:
                os.remove(data['temp_raw'])

            wx.CallAfter(self.parent.log, f"✨ 完了: {data['dest_path']}")
            wx.CallAfter(self.parent.on_download_success, data['dest_path'])
        except Exception as e:
            wx.CallAfter(self.parent.log, f"❌ エラー: {e}")
            wx.CallAfter(self.parent.update_progress, 0)
            wx.CallAfter(self.parent.on_download_finished)


class VibeDLFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="VibeDL - Audio Downloader", size=(750, 550))
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
            "notify_toast": True
        }
        self.last_dest_path = None
        self.init_ui()
        self.apply_theme()
        self.update_settings_display()
        self.check_ffmpeg_on_startup()
        self.Centre()

    def init_ui(self):
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        input_sizer = wx.FlexGridSizer(rows=3, cols=2, vgap=10, hgap=10)
        input_sizer.AddGrowableCol(1, 1)

        url_label = wx.StaticText(self.panel, label="YouTube URL:")
        self.url_ctrl = wx.TextCtrl(self.panel, style=wx.TE_PROCESS_ENTER)
        self.url_ctrl.SetHint("https://www.youtube.com/...")
        self.url_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_download)
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

        self.dl_btn = wx.Button(self.panel, label="ダウンロード開始", size=(200, 40))
        dl_font = self.dl_btn.GetFont()
        dl_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.dl_btn.SetFont(dl_font)
        self.dl_btn.SetBackgroundColour(wx.Colour(0, 120, 215))
        self.dl_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        self.dl_btn.Bind(wx.EVT_BUTTON, self.on_download)
        btn_sizer.Add(self.dl_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        gear_bmp = create_gear_bitmap()
        folder_bmp = create_folder_bitmap()

        self.open_folder_btn = wx.BitmapButton(self.panel, bitmap=folder_bmp, size=(32, 32))
        self.open_folder_btn.SetToolTip("保存先フォルダを開く")
        self.open_folder_btn.Bind(wx.EVT_BUTTON, self.on_open_folder)
        self.open_folder_btn.Enable(False)
        btn_sizer.Add(self.open_folder_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)

        btn_sizer.AddStretchSpacer()

        self.settings_btn = wx.BitmapButton(self.panel, bitmap=gear_bmp, size=(32, 32))
        self.settings_btn.SetToolTip("設定")
        self.settings_btn.Bind(wx.EVT_BUTTON, self.on_settings)
        btn_sizer.Add(self.settings_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

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
                if child == self.dl_btn:
                    continue
                child.SetBackgroundColour(btn_bg)
                child.SetForegroundColour(fg)
            elif isinstance(child, wx.BitmapButton):
                child.SetBackgroundColour(btn_bg)
            elif isinstance(child, wx.ComboBox):
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

    def on_download(self, event):
        url = self.url_ctrl.GetValue().strip()
        if not url:
            wx.MessageBox("URLを入力してください。", "入力エラー", wx.OK | wx.ICON_WARNING)
            return

        start_sec = self.parse_time(self.start_ctrl.GetValue().strip())
        end_sec = self.parse_time(self.end_ctrl.GetValue().strip())

        self.log_ctrl.Clear()
        self.dl_btn.Disable()
        self.open_folder_btn.Enable(False)
        self.progress.SetValue(0)
        thread = DownloadThread(self, url, self.config, start_sec, end_sec)
        thread.start()

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

    def update_progress(self, percent):
        self.progress.SetValue(percent)

    def on_download_success(self, dest_path):
        self.last_dest_path = dest_path
        self.open_folder_btn.Enable(True)
        self.dl_btn.Enable()
        self.progress.SetValue(100)
        self.notify_user("ダウンロード完了", os.path.basename(dest_path))

    def on_download_finished(self):
        self.dl_btn.Enable()
        self.progress.SetValue(0)

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
        dlg.Destroy()


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, config):
        super().__init__(parent, title="設定", size=(450, 480))
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
        grid_out = wx.FlexGridSizer(rows=3, cols=2, vgap=10, hgap=10)
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

        self.dark_cb = wx.CheckBox(proc_panel, label="ダークモード")
        self.dark_cb.SetValue(self.config.get("dark_mode", False))
        self.dark_cb.Bind(wx.EVT_CHECKBOX, self.on_dark_toggle)
        proc_sizer.Add(self.dark_cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

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
        return self.config


if __name__ == "__main__":
    app = wx.App()
    frame = VibeDLFrame()
    frame.Show()
    app.MainLoop()