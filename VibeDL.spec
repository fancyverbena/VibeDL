# -*- mode: python ; coding: utf-8 -*-
# PyInstaller ビルド設定（単一 exe / ウィンドウアプリ）
# 使い方: build.bat を実行するか、python -m PyInstaller VibeDL.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
# yt-dlp / yt-dlp-ejs のデータファイル（EJS チャレンジ解決用 JS 等）を取り込む
datas += collect_data_files('yt_dlp')
datas += collect_data_files('yt_dlp_ejs')

hiddenimports = []
hiddenimports += collect_submodules('yt_dlp_ejs')

a = Analysis(
    ['src/gui.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VibeDL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
