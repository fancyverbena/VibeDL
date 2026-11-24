import json
import os
import winreg

REG_PATH = r"Software\VibeDL"

DEFAULT_CONFIG = {
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
    "name_template": "{title}",
    "cookies_browser": "",
    "cookies_file": "",
    "trim_silence": False,
    "fade_enabled": False,
    "fade_seconds": 1.0,
    "language": "ja",
    "max_parallel": 2,
    "license_key": "",
    "split_chapters": False,
    "embed_lyrics": False,
    "loudnorm_tp": -2.0,
    "skip_duplicates": False,
    "after_finish": "",
    "auto_retry": 0,
    "rate_limit_mbps": 0.0,
    "theme_mode": "",
    "minimize_to_tray": False,
    "check_updates": True,
    "schedule_enabled": False,
    "schedule_time": "23:00",
    "webhook_url": "",
    "prevent_sleep": False,
    "mirror_folder": "",
    "window_x": -1,
    "window_y": -1,
    "window_w": 0,
    "window_h": 0,
}

# config key -> (registry value name, kind)
_KEY_MAP = {
    "target_lufs": ("TargetLUFS", "float"),
    "output_folder": ("OutputFolder", "str"),
    "output_format": ("OutputFormat", "str"),
    "bitrate": ("Bitrate", "str"),
    "normalize": ("Normalize", "bool"),
    "embed_metadata": ("EmbedMetadata", "bool"),
    "dark_mode": ("DarkMode", "bool"),
    "notify_sound": ("NotifySound", "bool"),
    "notify_toast": ("NotifyToast", "bool"),
    "clipboard_monitor": ("ClipboardMonitor", "bool"),
    "name_template": ("NameTemplate", "str"),
    "cookies_browser": ("CookiesBrowser", "str"),
    "cookies_file": ("CookiesFile", "str"),
    "trim_silence": ("TrimSilence", "bool"),
    "fade_enabled": ("FadeEnabled", "bool"),
    "fade_seconds": ("FadeSeconds", "float"),
    "language": ("Language", "str"),
    "max_parallel": ("MaxParallel", "int"),
    "license_key": ("LicenseKey", "str"),
    "split_chapters": ("SplitChapters", "bool"),
    "embed_lyrics": ("EmbedLyrics", "bool"),
    "loudnorm_tp": ("LoudnormTP", "float"),
    "skip_duplicates": ("SkipDuplicates", "bool"),
    "after_finish": ("AfterFinish", "str"),
    "auto_retry": ("AutoRetry", "int"),
    "rate_limit_mbps": ("RateLimitMbps", "float"),
    "theme_mode": ("ThemeMode", "str"),
    "minimize_to_tray": ("MinimizeToTray", "bool"),
    "check_updates": ("CheckUpdates", "bool"),
    "schedule_enabled": ("ScheduleEnabled", "bool"),
    "schedule_time": ("ScheduleTime", "str"),
    "webhook_url": ("WebhookUrl", "str"),
    "prevent_sleep": ("PreventSleep", "bool"),
    "mirror_folder": ("MirrorFolder", "str"),
    "window_x": ("WindowX", "int"),
    "window_y": ("WindowY", "int"),
    "window_w": ("WindowW", "int"),
    "window_h": ("WindowH", "int"),
}


def get_config():
    """Load config from the registry.

    Each value is read independently so that a missing or invalid
    single value does not discard the rest of the saved config.
    """
    config = dict(DEFAULT_CONFIG)
    config["url_history"] = list(DEFAULT_CONFIG["url_history"])
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except FileNotFoundError:
        return config
    with key:
        for cfg_key, (reg_name, kind) in _KEY_MAP.items():
            try:
                raw = winreg.QueryValueEx(key, reg_name)[0]
            except FileNotFoundError:
                continue
            try:
                if kind == "float":
                    config[cfg_key] = float(raw)
                elif kind == "int":
                    config[cfg_key] = int(raw)
                elif kind == "bool":
                    config[cfg_key] = raw == "True"
                else:
                    config[cfg_key] = str(raw)
            except (TypeError, ValueError):
                print(f"設定値 {reg_name} が不正です。デフォルト値を使います。")
        try:
            raw_history = winreg.QueryValueEx(key, "UrlHistory")[0]
            history = json.loads(raw_history)
            if isinstance(history, list):
                config["url_history"] = [str(u) for u in history][:10]
        except FileNotFoundError:
            pass
        except (TypeError, ValueError):
            print("URL履歴が不正です。履歴なしで起動します。")
    return config


def save_config(config):
    """Save config to the registry (all values stored as REG_SZ)."""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        for cfg_key, (reg_name, kind) in _KEY_MAP.items():
            if cfg_key not in config:
                continue
            value = config[cfg_key]
            if cfg_key == "output_folder":
                value = os.path.abspath(value)
                config["output_folder"] = value
            winreg.SetValueEx(key, reg_name, 0, winreg.REG_SZ, str(value))
        history = config.get("url_history", [])
        winreg.SetValueEx(key, "UrlHistory", 0, winreg.REG_SZ,
                          json.dumps(list(history)[:10], ensure_ascii=False))


def load_download_history():
    """ダウンロード履歴（完了したファイルの一覧）を読み込む。最大50件。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except FileNotFoundError:
        return []
    with key:
        try:
            raw = winreg.QueryValueEx(key, "DownloadHistory")[0]
            data = json.loads(raw)
        except (FileNotFoundError, TypeError, ValueError):
            return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)][:50]


def save_download_history(entries):
    """ダウンロード履歴を保存する。最大50件。"""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "DownloadHistory", 0, winreg.REG_SZ,
                          json.dumps(list(entries)[:50], ensure_ascii=False))


def load_watch_state():
    """新着監視の状態 {"urls": [...], "seen": {url: [動画URL, ...]}} を読み込む。"""
    default = {"urls": [], "seen": {}}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except FileNotFoundError:
        return default
    with key:
        try:
            raw = winreg.QueryValueEx(key, "WatchState")[0]
            data = json.loads(raw)
        except (FileNotFoundError, TypeError, ValueError):
            return default
    if not isinstance(data, dict):
        return default
    urls = data.get("urls")
    seen = data.get("seen")
    return {
        "urls": [u for u in urls if isinstance(u, str)][:20]
        if isinstance(urls, list) else [],
        "seen": seen if isinstance(seen, dict) else {},
    }


def save_watch_state(state):
    """新着監視の状態を保存する。"""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0,
                            winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "WatchState", 0, winreg.REG_SZ,
                          json.dumps(state, ensure_ascii=False))


def load_presets():
    """設定プリセット {名前: {config部分集合}} を読み込む。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except FileNotFoundError:
        return {}
    with key:
        try:
            raw = winreg.QueryValueEx(key, "Presets")[0]
            data = json.loads(raw)
        except (FileNotFoundError, TypeError, ValueError):
            return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def save_presets(presets):
    """設定プリセットを保存する。"""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0,
                            winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "Presets", 0, winreg.REG_SZ,
                          json.dumps(presets, ensure_ascii=False))


def load_queue_items():
    """保存されたキュー（未完了アイテム）を読み込む。最大200件。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except FileNotFoundError:
        return []
    with key:
        try:
            raw = winreg.QueryValueEx(key, "QueueItems")[0]
            data = json.loads(raw)
        except (FileNotFoundError, TypeError, ValueError):
            return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)][:200]


def save_queue_items(entries):
    """キュー（未完了アイテム）を保存する。最大200件。"""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "QueueItems", 0, winreg.REG_SZ,
                          json.dumps(list(entries)[:200], ensure_ascii=False))
