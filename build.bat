@echo off
chcp 65001 >nul
cd /d %~dp0
echo === VibeDL exe ビルド ===
echo 依存パッケージをインストールします...
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error
echo アイコンを生成します...
python tools\make_icon.py
if errorlevel 1 goto :error
echo PyInstaller で exe を生成します...
python -m PyInstaller --clean --noconfirm VibeDL.spec
if errorlevel 1 goto :error
echo.
echo 完了: dist\VibeDL.exe
pause
exit /b 0
:error
echo.
echo ビルドに失敗しました。
pause
exit /b 1
